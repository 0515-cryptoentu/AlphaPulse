from fastapi import FastAPI
from pydantic import BaseModel
import sqlite3
import csv
import trade_log
import wallet_manager

app = FastAPI(title="AlphaPulse Dashboard")

class Trade(BaseModel):
    timestamp: str
    token_mint: str
    token_symbol: str
    amount_token: float
    amount_sol: float
    sol_usd: float
    usd_value: float
    tx_signature: str

def _read_trades(limit: int | None = None):
    trades = []
    try:
        conn = sqlite3.connect(trade_log.DB_FILE)
        cur = conn.execute(
            "SELECT timestamp, token_mint, token_symbol, amount_token, amount_sol, sol_usd, usd_value, tx_signature "
            "FROM trades ORDER BY timestamp DESC" + (" LIMIT ?" if limit else ""),
            ([limit] if limit else []),
        )
        rows = cur.fetchall()
        conn.close()
        for row in rows:
            trades.append(
                {
                    "timestamp": row[0],
                    "token_mint": row[1],
                    "token_symbol": row[2],
                    "amount_token": float(row[3]),
                    "amount_sol": float(row[4]),
                    "sol_usd": float(row[5]),
                    "usd_value": float(row[6]),
                    "tx_signature": row[7],
                }
            )
    except Exception:
        try:
            with open(trade_log.CSV_FILE, newline="") as f:
                reader = list(csv.DictReader(f))
                rows = reader[-limit:] if limit else reader
                for row in reversed(rows):
                    trades.append(
                        {
                            "timestamp": row["timestamp"],
                            "token_mint": row["token_mint"],
                            "token_symbol": row["token_symbol"],
                            "amount_token": float(row["amount_token"]),
                            "amount_sol": float(row["amount_sol"]),
                            "sol_usd": float(row["sol_usd"]),
                            "usd_value": float(row["usd_value"]),
                            "tx_signature": row["tx_signature"],
                        }
                    )
        except FileNotFoundError:
            pass
    return trades

@app.get("/balance")
def balance():
    try:
        bal = wallet_manager.get_balance()
    except Exception:
        bal = 0.0
    return {"balance_sol": bal}

@app.get("/trades")
def trades(limit: int = 10):
    data = _read_trades(limit)
    return {"trades": data}

@app.get("/metrics")
def metrics():
    data = _read_trades()
    total_usd = sum(t["usd_value"] for t in data)
    total_sol = sum(t["amount_sol"] for t in data)
    return {
        "total_usd": total_usd,
        "total_sol": total_sol,
        "num_trades": len(data),
    }
