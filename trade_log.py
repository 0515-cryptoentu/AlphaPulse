"""
trade_log.py — trade recording to CSV + SQLite.
 
Changes from original:
  - trades table now includes `wallet` (address we copied) and `sell_usd_value`
    (filled in when auto_sell closes the position — used by wallet_scorer)
  - init_db() runs a safe migration so existing trades.db files are upgraded
    without losing data
  - log_trade() accepts an optional `wallet` argument
"""
 
import csv
from datetime import datetime
from decimal import Decimal
import aiohttp
import sqlite3
 
CSV_FILE  = "trade_log.csv"
DB_FILE   = "trades.db"
 
 
def init_log():
    try:
        with open(CSV_FILE, "x", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp",
                "wallet",
                "token_mint",
                "token_symbol",
                "amount_token",
                "amount_sol",
                "sol_usd",
                "usd_value",
                "sell_usd_value",
                "tx_signature",
            ])
    except FileExistsError:
        pass
 
 
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur  = conn.cursor()
 
    # Create table with full schema for new installs
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            timestamp       TEXT,
            wallet          TEXT,
            token_mint      TEXT,
            token_symbol    TEXT,
            amount_token    TEXT,
            amount_sol      TEXT,
            sol_usd         TEXT,
            usd_value       TEXT,
            sell_usd_value  TEXT,
            tx_signature    TEXT
        )
    """)
 
    # Safe migration: add new columns to existing DBs without wiping data
    existing_cols = {row[1] for row in cur.execute("PRAGMA table_info(trades)")}
    for col, typedef in [("wallet", "TEXT"), ("sell_usd_value", "TEXT")]:
        if col not in existing_cols:
            cur.execute(f"ALTER TABLE trades ADD COLUMN {col} {typedef}")
 
    conn.commit()
    conn.close()
 
 
async def get_sol_usd_price() -> Decimal:
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                "https://api.coingecko.com/api/v3/simple/price"
                "?ids=solana&vs_currencies=usd"
            ) as resp:
                data  = await resp.json()
                price = data["solana"]["usd"]
                return Decimal(str(price))
    except Exception as e:
        print(f"[WARNING] Failed to fetch SOL/USD price: {e}")
        return Decimal("165.00")  # fallback
 
 
async def log_trade(
    token_mint:    str,
    token_symbol:  str,
    amount_token,
    amount_sol,
    tx_signature:  str,
    wallet:        str = "",
    sell_usd_value = None,
) -> None:
    """
    Record a trade to both CSV and SQLite.
 
    wallet         — the Solana address we copied (empty string if unknown)
    sell_usd_value — USD value when position was closed; None until then
    """
    init_log()
    init_db()
 
    sol_usd    = await get_sol_usd_price()
    usd_value  = Decimal(str(amount_sol)) * sol_usd
    timestamp  = datetime.utcnow().isoformat()
    sell_str   = str(sell_usd_value) if sell_usd_value is not None else ""
 
    # --- CSV ---
    with open(CSV_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            timestamp,
            wallet,
            token_mint,
            token_symbol,
            str(amount_token),
            str(amount_sol),
            str(sol_usd),
            str(usd_value),
            sell_str,
            tx_signature,
        ])
 
    # --- SQLite ---
    conn = sqlite3.connect(DB_FILE)
    cur  = conn.cursor()
    cur.execute(
        """INSERT INTO trades
           (timestamp, wallet, token_mint, token_symbol,
            amount_token, amount_sol, sol_usd, usd_value,
            sell_usd_value, tx_signature)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            timestamp,
            wallet,
            token_mint,
            token_symbol,
            str(amount_token),
            str(amount_sol),
            str(sol_usd),
            str(usd_value),
            sell_str,
            tx_signature,
        ),
    )
    conn.commit()
    conn.close()
 
 
def update_sell_value(tx_signature: str, sell_usd_value: float) -> None:
    """
    Called by auto_sell when a position is closed.
    Updates the sell_usd_value for the matching buy trade so wallet_scorer
    can calculate real P&L per wallet.
    """
    init_db()
    conn = sqlite3.connect(DB_FILE)
    cur  = conn.cursor()
    cur.execute(
        "UPDATE trades SET sell_usd_value = ? WHERE tx_signature = ?",
        (str(sell_usd_value), tx_signature),
    )
    conn.commit()
    conn.close()
