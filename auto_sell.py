import time
from datetime import datetime, timedelta
from decimal import Decimal
import requests
from trade_log import get_sol_usd_price, log_trade
from utils import log
from sync_to_sheets import sync_csv_to_google_sheet

# Simulated portfolio for tracking positions
# Format: {token_mint: {"entry_price": Decimal, "amount": float, "entry_time": datetime}}
portfolio = {}

# Parameters
ROI_TARGET = Decimal("1.20")  # 20% gain
TRAILING_STOP_LOSS = Decimal("0.85")  # Sell if price drops 15% from peak
MAX_HOLD_DURATION = timedelta(hours=3)  # Max time to hold token


# Placeholder function for real-time SPL token price
def fetch_token_price_usd(token_mint):
    try:
        resp = requests.get(
            f"https://price.jup.ag/v4/price?ids={token_mint}&vsToken=So11111111111111111111111111111111111111112",
            timeout=5,
        )
        data = resp.json()
        price_sol = Decimal(str(data["data"][token_mint]["price"]))
        sol_usd = get_sol_usd_price()
        return price_sol * sol_usd
    except Exception as e:
        log(f"[WARNING] Failed to fetch price for {token_mint}: {e}")
        return Decimal("0.00")


def check_portfolio_for_sells():
    to_sell = []

    for token_mint, info in list(portfolio.items()):
        entry_price = info["entry_price"]
        current_price = fetch_token_price_usd(token_mint)
        if current_price == 0:
            continue  # Skip if price fetch failed

        peak_price = info.get("peak_price", entry_price)
        entry_time = info["entry_time"]
        roi = current_price / entry_price
        time_held = datetime.utcnow() - entry_time

        # Update peak price
        if current_price > peak_price:
            portfolio[token_mint]["peak_price"] = current_price
            peak_price = current_price

        log(
            f"[AUTO-SELL] {token_mint}: Entry={entry_price}, Now={current_price:.2f}, ROI={roi:.2f}, Held={time_held}"
        )

        if roi >= ROI_TARGET and current_price < peak_price * TRAILING_STOP_LOSS:
            log(f"[AUTO-SELL] Trailing stop-loss triggered for {token_mint}")
            to_sell.append(token_mint)
        elif time_held > MAX_HOLD_DURATION:
            log(f"[AUTO-SELL] Max hold time exceeded for {token_mint}")
            to_sell.append(token_mint)

    return to_sell


def mark_new_token(token_mint, entry_price, amount):
    portfolio[token_mint] = {
        "entry_price": Decimal(entry_price),
        "amount": amount,
        "entry_time": datetime.utcnow(),
        "peak_price": Decimal(entry_price),
    }
    log(f"[PORTFOLIO] Added {token_mint} at {entry_price} USD")


def execute_sell(token_mint):
    if token_mint not in portfolio:
        return
    info = portfolio[token_mint]
    current_price = fetch_token_price_usd(token_mint)
    if current_price == 0:
        return

    usd_value = Decimal(info["amount"]) * current_price
    log_trade(
        token_mint,
        "AUTOSELL",
        info["amount"],
        Decimal("0.01"),
        f"AUTOSELL-{token_mint[:6]}",
    )
    sync_csv_to_google_sheet()
    log(
        f"[SELL] {token_mint}: Sold {info['amount']} tokens at {current_price:.2f} USD, Total: {usd_value:.2f} USD"
    )
    del portfolio[token_mint]


if __name__ == "__main__":
    mark_new_token("DUMMY2TOKEN2222", "1.00", 1000)
    for _ in range(10):
        time.sleep(3)
        tokens = check_portfolio_for_sells()
        for token in tokens:
            execute_sell(token)
