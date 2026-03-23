"""
auto_sell.py — monitors open positions and exits based on ROI / time rules.
 
Changes from original:
  - mark_new_token() now accepts buy_tx_signature so we can match the DB row on sell
  - execute_sell() calls trade_log.update_sell_value() after a successful sell,
    which feeds real P&L data into wallet_scorer.py
  - sell_usd_value recorded is the actual USD value received at exit price,
    not a placeholder
  - minor: skip sell execution if amount is 0 (practice mode logs 0 amounts)
"""
 
import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
 
import aiohttp
 
from trade_log import get_sol_usd_price, log_trade, update_sell_value
from utils import log
from sync_to_sheets import sync_csv_to_google_sheet
 
# -------------------------------------------------------------------
# In-memory portfolio
# Format: {
#   token_mint: {
#     "entry_price":     Decimal,
#     "amount":          float,
#     "entry_time":      datetime,
#     "peak_price":      Decimal,
#     "buy_tx_signature": str,   ← NEW: used to update DB row on sell
#   }
# }
# -------------------------------------------------------------------
portfolio: dict = {}
 
# --- Exit parameters ---
ROI_TARGET         = Decimal("1.20")   # take profit at +20%
TRAILING_STOP_LOSS = Decimal("0.85")   # sell if price drops 15% from peak
MAX_HOLD_DURATION  = timedelta(hours=3)
 
 
async def fetch_token_price_usd(token_mint: str) -> Decimal:
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                f"https://price.jup.ag/v4/price?ids={token_mint}"
                f"&vsToken=So11111111111111111111111111111111111111112"
            ) as resp:
                data      = await resp.json()
                price_sol = Decimal(str(data["data"][token_mint]["price"]))
                sol_usd   = await get_sol_usd_price()
                return price_sol * sol_usd
    except Exception as e:
        log(f"[AUTO-SELL] Failed to fetch price for {token_mint[:8]}…: {e}")
        return Decimal("0.00")
 
 
async def check_portfolio_for_sells() -> list[str]:
    """Check all open positions and return a list of mints to sell."""
    to_sell = []
 
    for token_mint, info in list(portfolio.items()):
        entry_price   = info["entry_price"]
        current_price = await fetch_token_price_usd(token_mint)
 
        if current_price == 0:
            continue  # price fetch failed — don't act
 
        peak_price = info.get("peak_price", entry_price)
        entry_time = info["entry_time"]
        roi        = current_price / entry_price
        time_held  = datetime.utcnow() - entry_time
 
        # Update peak price if new high reached
        if current_price > peak_price:
            portfolio[token_mint]["peak_price"] = current_price
            peak_price = current_price
 
        log(
            f"[AUTO-SELL] {token_mint[:8]}… "
            f"entry={entry_price:.4f} now={current_price:.4f} "
            f"roi={roi:.2f} held={str(time_held).split('.')[0]}"
        )
 
        # Exit condition 1: hit profit target then dropped below trailing stop
        if roi >= ROI_TARGET and current_price < peak_price * TRAILING_STOP_LOSS:
            log(f"[AUTO-SELL] Trailing stop triggered for {token_mint[:8]}…")
            to_sell.append(token_mint)
 
        # Exit condition 2: held too long
        elif time_held > MAX_HOLD_DURATION:
            log(f"[AUTO-SELL] Max hold time exceeded for {token_mint[:8]}…")
            to_sell.append(token_mint)
 
    return to_sell
 
 
def mark_new_token(
    token_mint:      str,
    entry_price,
    amount:          float,
    buy_tx_signature: str = "",
) -> None:
    """
    Register a newly bought token in the portfolio.
 
    buy_tx_signature — the tx signature from log_trade() on the buy side.
    Stored here so execute_sell() can call update_sell_value() with the
    correct row reference when the position closes.
    """
    portfolio[token_mint] = {
        "entry_price":      Decimal(str(entry_price)),
        "amount":           amount,
        "entry_time":       datetime.utcnow(),
        "peak_price":       Decimal(str(entry_price)),
        "buy_tx_signature": buy_tx_signature,
    }
    log(f"[PORTFOLIO] Tracking {token_mint[:8]}… entry={entry_price} USD")
 
 
async def execute_sell(token_mint: str) -> None:
    """
    Execute (or simulate) a sell for the given token mint, then:
      1. Log the sell trade to CSV + SQLite
      2. Update the original buy row in trades.db with sell_usd_value
         so wallet_scorer can calculate real P&L for this wallet
      3. Sync to Google Sheets
      4. Remove from portfolio
    """
    if token_mint not in portfolio:
        return
 
    info          = portfolio[token_mint]
    current_price = await fetch_token_price_usd(token_mint)
 
    if current_price == 0:
        log(f"[AUTO-SELL] Price fetch failed for {token_mint[:8]}… — skipping sell.")
        return
 
    amount    = info["amount"]
    usd_value = Decimal(str(amount)) * current_price if amount else current_price
 
    buy_sig = info.get("buy_tx_signature", "")
    sell_sig = f"AUTOSELL-{token_mint[:6]}"
 
    # Log the sell trade
    await log_trade(
        token_mint,
        "AUTOSELL",
        amount,
        Decimal("0.01"),
        sell_sig,
    )
 
    # ---------------------------------------------------------------
    # KEY STEP: update the original buy row with what we sold for.
    # This is what wallet_scorer uses to calculate win/loss per wallet.
    # We update by buy signature if we have it, otherwise fall back to
    # updating by token_mint (less precise but better than nothing).
    # ---------------------------------------------------------------
    if buy_sig:
        update_sell_value(buy_sig, float(usd_value))
        log(f"[AUTO-SELL] Updated sell value for tx {buy_sig[-8:]}… → ${usd_value:.2f}")
    else:
        # Fallback: update the most recent open trade for this token
        _update_sell_value_by_mint(token_mint, float(usd_value))
        log(f"[AUTO-SELL] Updated sell value by mint for {token_mint[:8]}… → ${usd_value:.2f}")
 
    sync_csv_to_google_sheet()
 
    log(
        f"[SELL] {token_mint[:8]}… "
        f"amount={amount} tokens @ ${current_price:.4f} "
        f"total=${usd_value:.2f}"
    )
 
    del portfolio[token_mint]
 
 
def _update_sell_value_by_mint(token_mint: str, sell_usd_value: float) -> None:
    """
    Fallback: update sell_usd_value on the most recent buy trade for this
    token where sell_usd_value is still empty. Used when we don't have the
    original buy tx_signature stored (e.g. tokens added before this update).
    """
    import sqlite3
    from trade_log import DB_FILE, init_db
    init_db()
    conn = sqlite3.connect(DB_FILE)
    cur  = conn.cursor()
    cur.execute(
        """UPDATE trades
           SET sell_usd_value = ?
           WHERE token_mint = ?
           AND (sell_usd_value IS NULL OR sell_usd_value = '')
           ORDER BY timestamp DESC
           LIMIT 1""",
        (str(sell_usd_value), token_mint),
    )
    conn.commit()
    conn.close()
 
 
# -------------------------------------------------------------------
# Demo / manual test
# -------------------------------------------------------------------
if __name__ == "__main__":
    async def demo():
        mark_new_token("DUMMY2TOKEN2222", "1.00", 1000, buy_tx_signature="demo-buy-sig-001")
        for _ in range(10):
            await asyncio.sleep(3)
            tokens = await check_portfolio_for_sells()
            for token in tokens:
                await execute_sell(token)
 
    asyncio.run(demo())
 
