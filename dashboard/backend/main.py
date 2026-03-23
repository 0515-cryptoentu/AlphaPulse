"""
dashboard/backend/main.py — AlphaPulse FastAPI backend.

Changes from original:
  - _read_trades() now selects wallet + sell_usd_value columns
  - Trade model updated to include wallet + sell_usd_value
  - /pnl uses sell_usd_value for accurate P&L (not AUTOSELL symbol matching)
  - /metrics now includes win_rate, closed_trades, open_trades
  - /wallet_scores — new endpoint, returns live scorer results per wallet
  - /trades now returns wallet + pnl_usd per trade for the dashboard feed
  - All DB reads wrapped in proper error handling with CSV fallback
"""

import sqlite3
import csv
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import trade_log
import wallet_manager
import config

WALLET_DB      = "wallet_repository.db"
HEARTBEAT_FILE = "monitor_heartbeat.txt"

app = FastAPI(title="AlphaPulse Dashboard API")

# Allow the frontend (served separately) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ── Models ────────────────────────────────────────────────────────────────────

class Trade(BaseModel):
    timestamp:      str
    wallet:         str
    token_mint:     str
    token_symbol:   str
    amount_token:   float
    amount_sol:     float
    sol_usd:        float
    usd_value:      float
    sell_usd_value: Optional[float]
    pnl_usd:        Optional[float]   # sell_usd_value - usd_value, None if open
    tx_signature:   str


# ── DB helpers ────────────────────────────────────────────────────────────────

def _read_trades(limit: Optional[int] = None) -> list[dict]:
    """
    Read trades from SQLite (falls back to CSV if DB unavailable).
    Returns full schema including wallet + sell_usd_value.
    """
    trades = []

    try:
        conn = sqlite3.connect(trade_log.DB_FILE)
        query = (
            "SELECT timestamp, wallet, token_mint, token_symbol, "
            "amount_token, amount_sol, sol_usd, usd_value, "
            "sell_usd_value, tx_signature "
            "FROM trades ORDER BY timestamp DESC"
        )
        args = []
        if limit:
            query += " LIMIT ?"
            args.append(limit)

        rows = conn.execute(query, args).fetchall()
        conn.close()

        for row in rows:
            buy_usd  = float(row[7]) if row[7] else 0.0
            sell_usd = float(row[8]) if row[8] else None
            pnl      = round(sell_usd - buy_usd, 4) if sell_usd is not None else None

            trades.append({
                "timestamp":      row[0],
                "wallet":         row[1] or "",
                "token_mint":     row[2],
                "token_symbol":   row[3],
                "amount_token":   float(row[4]) if row[4] else 0.0,
                "amount_sol":     float(row[5]) if row[5] else 0.0,
                "sol_usd":        float(row[6]) if row[6] else 0.0,
                "usd_value":      buy_usd,
                "sell_usd_value": sell_usd,
                "pnl_usd":        pnl,
                "tx_signature":   row[9],
            })
        return trades

    except Exception:
        pass

    # CSV fallback
    try:
        with open(trade_log.CSV_FILE, newline="") as f:
            reader = list(csv.DictReader(f))
            rows   = reader[-limit:] if limit else reader
            for row in reversed(rows):
                buy_usd  = float(row.get("usd_value", 0) or 0)
                sell_raw = row.get("sell_usd_value", "")
                sell_usd = float(sell_raw) if sell_raw else None
                pnl      = round(sell_usd - buy_usd, 4) if sell_usd is not None else None

                trades.append({
                    "timestamp":      row.get("timestamp", ""),
                    "wallet":         row.get("wallet", ""),
                    "token_mint":     row.get("token_mint", ""),
                    "token_symbol":   row.get("token_symbol", ""),
                    "amount_token":   float(row.get("amount_token", 0) or 0),
                    "amount_sol":     float(row.get("amount_sol", 0) or 0),
                    "sol_usd":        float(row.get("sol_usd", 0) or 0),
                    "usd_value":      buy_usd,
                    "sell_usd_value": sell_usd,
                    "pnl_usd":        pnl,
                    "tx_signature":   row.get("tx_signature", ""),
                })
    except FileNotFoundError:
        pass

    return trades


def _read_wallet_stats() -> list[dict]:
    try:
        conn  = sqlite3.connect(WALLET_DB)
        rows  = conn.execute(
            "SELECT wallet, tx_count, avg_tx_interval, last_seen FROM wallets"
        ).fetchall()
        conn.close()
        return [
            {"wallet": r[0], "tx_count": r[1], "avg_interval": r[2], "last_seen": r[3]}
            for r in rows
        ]
    except Exception:
        return []


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/balance")
def balance():
    try:
        bal = wallet_manager.get_balance()
    except Exception:
        bal = 0.0
    return {"balance_sol": round(bal, 6)}


@app.get("/trades")
def get_trades(limit: int = Query(default=20, le=500)):
    return {"trades": _read_trades(limit)}


@app.get("/metrics")
def metrics():
    """
    Returns trade counts, win rate, total volume.
    win_rate uses sell_usd_value for accuracy — not AUTOSELL symbol matching.
    """
    data = _read_trades()

    buy_trades    = [t for t in data if t["token_symbol"] != "AUTOSELL"]
    closed_trades = [t for t in buy_trades if t["sell_usd_value"] is not None]
    open_trades   = [t for t in buy_trades if t["sell_usd_value"] is None]

    wins     = sum(1 for t in closed_trades if (t["pnl_usd"] or 0) > 0)
    win_rate = wins / len(closed_trades) if closed_trades else 0.0

    total_buy_usd  = sum(t["usd_value"] for t in closed_trades)
    total_sell_usd = sum(t["sell_usd_value"] for t in closed_trades)
    total_pnl      = total_sell_usd - total_buy_usd

    return {
        "total_trades":    len(buy_trades),
        "closed_trades":   len(closed_trades),
        "open_trades":     len(open_trades),
        "wins":            wins,
        "win_rate":        round(win_rate, 4),
        "total_pnl_usd":   round(total_pnl, 2),
        "total_buy_usd":   round(total_buy_usd, 2),
        "total_sell_usd":  round(total_sell_usd, 2),
        "total_sol_spent": round(sum(t["amount_sol"] for t in buy_trades), 4),
    }


@app.get("/pnl")
def pnl():
    """
    Accurate P&L using sell_usd_value column.
    Previous version matched on token_symbol == 'AUTOSELL' which was unreliable.
    """
    data          = _read_trades()
    buy_trades    = [t for t in data if t["token_symbol"] != "AUTOSELL"]
    closed_trades = [t for t in buy_trades if t["sell_usd_value"] is not None]

    total_buy  = sum(t["usd_value"]      for t in closed_trades)
    total_sell = sum(t["sell_usd_value"] for t in closed_trades)
    pnl_usd    = total_sell - total_buy
    wins       = sum(1 for t in closed_trades if (t["pnl_usd"] or 0) > 0)
    win_rate   = wins / len(closed_trades) if closed_trades else 0.0

    return {
        "total_buy_usd":   round(total_buy, 2),
        "total_sell_usd":  round(total_sell, 2),
        "pnl_usd":         round(pnl_usd, 2),
        "closed_trades":   len(closed_trades),
        "wins":            wins,
        "win_rate":        round(win_rate, 4),
        "go_live_ready":   win_rate >= 0.55 and len(closed_trades) >= 50,
    }


@app.get("/portfolio")
def portfolio():
    try:
        import auto_sell
        holdings = [
            {
                "token_mint":  k,
                "entry_price": float(v["entry_price"]),
                "amount":      v["amount"],
                "entry_time":  v["entry_time"].isoformat(),
                "peak_price":  float(v.get("peak_price", v["entry_price"])),
            }
            for k, v in auto_sell.portfolio.items()
        ]
    except Exception:
        holdings = []
    return {"portfolio": holdings, "count": len(holdings)}


@app.get("/wallet_scores")
def wallet_scores():
    """
    Returns live wallet scores from wallet_scorer for all monitored wallets.
    New endpoint — used by dashboard wallet score panel.
    """
    results = []
    try:
        from wallet_scorer import score_wallet
        for addr in config.MONITORED_WALLETS:
            score = score_wallet(addr)
            results.append({
                "wallet":    addr,
                "short":     f"{addr[:6]}…{addr[-4:]}",
                "score":     round(score, 4),
                "grade":     (
                    "A" if score >= 0.75 else
                    "B" if score >= 0.55 else
                    "C" if score >= 0.40 else "D"
                ),
            })
    except Exception as e:
        return {"wallets": [], "error": str(e)}
    return {"wallets": results}


@app.get("/wallet_stats")
def wallet_stats():
    return {"wallets": _read_wallet_stats()}


@app.get("/heartbeat")
def heartbeat():
    try:
        with open(HEARTBEAT_FILE) as f:
            ts = f.read().strip()
        age = (datetime.utcnow() - datetime.fromisoformat(ts)).total_seconds()
        status = "live" if age < 30 else "stale" if age < 120 else "dead"
    except Exception:
        ts, age, status = "", 0, "unknown"
    return {"timestamp": ts, "age_seconds": round(age), "status": status}


@app.get("/status")
def status():
    """Single endpoint the dashboard can ping to get everything at once."""
    try:
        bal = wallet_manager.get_balance()
    except Exception:
        bal = 0.0

    try:
        with open(HEARTBEAT_FILE) as f:
            ts  = f.read().strip()
        age    = (datetime.utcnow() - datetime.fromisoformat(ts)).total_seconds()
        hb_status = "live" if age < 30 else "stale" if age < 120 else "dead"
    except Exception:
        hb_status = "unknown"
        age = 0

    try:
        import telegram_bot
        paused = telegram_bot.PAUSED
    except Exception:
        paused = False

    return {
        "mode":           "practice" if config.PRACTICE_MODE else "live",
        "paused":         paused,
        "balance_sol":    round(bal, 6),
        "monitor_status": hb_status,
        "monitor_age_s":  round(age),
    }
