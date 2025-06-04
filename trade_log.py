import csv
from datetime import datetime
from decimal import Decimal
import aiohttp
import sqlite3

CSV_FILE = "trade_log.csv"
DB_FILE = "trades.db"


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


def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS trades (
            timestamp TEXT,
            token_mint TEXT,
            token_symbol TEXT,
            amount_token TEXT,
            amount_sol TEXT,
            sol_usd TEXT,
            usd_value TEXT,
            tx_signature TEXT
        )
        """
    )
    conn.commit()
    conn.close()


async def get_sol_usd_price():
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd"
            ) as resp:
                data = await resp.json()
                price = data["solana"]["usd"]
                return Decimal(str(price))
    except Exception as e:
        print(f"[WARNING] Failed to fetch SOL/USD price: {e}")
        return Decimal("165.00")  # Fallback to a fixed average SOL price for practice


async def log_trade(token_mint, token_symbol, amount_token, amount_sol, tx_signature):
    init_log()
    init_db()
    sol_usd = await get_sol_usd_price()
    usd_value = Decimal(amount_sol) * sol_usd
    timestamp = datetime.utcnow().isoformat()
    with open(CSV_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                timestamp,
                token_mint,
                token_symbol,
                str(amount_token),
                str(amount_sol),
                str(sol_usd),
                str(usd_value),
                tx_signature,
            ]
        )

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO trades (timestamp, token_mint, token_symbol, amount_token, amount_sol, sol_usd, usd_value, tx_signature) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            timestamp,
            token_mint,
            token_symbol,
            str(amount_token),
            str(amount_sol),
            str(sol_usd),
            str(usd_value),
            tx_signature,
        ),
    )
    conn.commit()
    conn.close()
