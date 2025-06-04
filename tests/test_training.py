import sqlite3
from pathlib import Path

import pandas as pd

import training
from training import backtest


def _create_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE trades (
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
    cur.execute(
        "INSERT INTO trades VALUES (?,?,?,?,?,?,?,?)",
        (
            "2024-01-01T00:00:00Z",
            "M1",
            "TKN",
            "1",
            "1",
            "100",
            "100",
            "sig1",
        ),
    )
    cur.execute(
        "INSERT INTO trades VALUES (?,?,?,?,?,?,?,?)",
        (
            "2024-01-02T00:00:00Z",
            "M2",
            "TKN",
            "2",
            "2",
            "100",
            "200",
            "sig2",
        ),
    )
    conn.commit()
    conn.close()


def test_load_and_simulate(tmp_path: Path) -> None:
    db = tmp_path / "trades.db"
    _create_db(db)

    df = training.load_trade_history(db)
    assert len(df) == 2

    strat = backtest.Strategy(
        position_size=0.5,
        win_rate=0.5,
        profit_pct=0.1,
        loss_pct=0.05,
        starting_balance=100,
    )
    result = backtest.simulate(df, strat)
    assert round(result["final_balance"], 2) == 102.38
    assert round(result["roi"], 4) == 0.0238
