import csv
from datetime import datetime
from decimal import Decimal
import requests

CSV_FILE = "trade_log.csv"


def init_log():
    try:
        with open(CSV_FILE, "x", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "timestamp",
                    "token_mint",
                    "token_symbol",
                    "amount_token",
                    "amount_sol",
                    "sol_usd",
                    "usd_value",
                    "tx_signature",
                ]
            )
    except FileExistsError:
        pass


def get_sol_usd_price():
    try:
        resp = requests.get(
            "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd",
            timeout=5,
        )
        price = resp.json()["solana"]["usd"]
        return Decimal(str(price))
    except Exception as e:
        print(f"[WARNING] Failed to fetch SOL/USD price: {e}")
        return Decimal("165.00")  # Fallback to a fixed average SOL price for practice


def log_trade(token_mint, token_symbol, amount_token, amount_sol, tx_signature):
    init_log()
    sol_usd = get_sol_usd_price()
    usd_value = Decimal(amount_sol) * sol_usd
    with open(CSV_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                datetime.utcnow().isoformat(),
                token_mint,
                token_symbol,
                str(amount_token),
                str(amount_sol),
                str(sol_usd),
                str(usd_value),
                tx_signature,
            ]
        )
