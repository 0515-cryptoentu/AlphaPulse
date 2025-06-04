"""Utilities for training and backtesting trading strategies."""

from __future__ import annotations

import sqlite3
import pandas as pd

DB_FILE = "trades.db"


def load_trade_history(db_path: str = DB_FILE) -> pd.DataFrame:
    """Load historical trades from ``db_path`` into a :class:`~pandas.DataFrame`."""
    conn = sqlite3.connect(db_path)
    try:
        df = pd.read_sql_query("SELECT * FROM trades ORDER BY timestamp", conn)
    finally:
        conn.close()

    for col in ["amount_token", "amount_sol", "sol_usd", "usd_value"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    return df

__all__ = ["load_trade_history", "DB_FILE"]
