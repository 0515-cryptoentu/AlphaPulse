"""Backtesting utilities for AlphaPulse strategies."""

from __future__ import annotations

from dataclasses import dataclass
import argparse
from typing import Iterable, Dict, Any

import pandas as pd

from . import load_trade_history, DB_FILE


@dataclass
class Strategy:
    """Parameters defining a simple trading strategy."""

    position_size: float = 0.1  # Fraction of balance used per trade
    win_rate: float = 0.5       # Proportion of trades that are profitable
    profit_pct: float = 0.05    # Return on a winning trade
    loss_pct: float = 0.03      # Loss on a losing trade
    starting_balance: float = 1000.0


def simulate(trades: pd.DataFrame, strategy: Strategy) -> Dict[str, Any]:
    """Run a naive simulation over ``trades`` using ``strategy`` parameters."""

    winners = int(len(trades) * strategy.win_rate)
    balance = strategy.starting_balance
    for idx, _ in trades.iterrows():
        stake = balance * strategy.position_size
        if idx < winners:
            balance += stake * strategy.profit_pct
        else:
            balance -= stake * strategy.loss_pct

    roi = (balance - strategy.starting_balance) / strategy.starting_balance
    return {
        "trades": len(trades),
        "final_balance": balance,
        "roi": roi,
    }


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run strategy backtests")
    parser.add_argument("--db", default=DB_FILE, help="Path to trade database")
    parser.add_argument("--position", type=float, default=0.1, help="Fraction of balance per trade")
    parser.add_argument("--win-rate", type=float, default=0.5, help="Fraction of profitable trades")
    parser.add_argument("--profit", type=float, default=0.05, help="Profit percentage on wins")
    parser.add_argument("--loss", type=float, default=0.03, help="Loss percentage on losses")
    parser.add_argument("--starting-balance", type=float, default=1000.0)
    args = parser.parse_args(argv)

    trades = load_trade_history(args.db)
    strat = Strategy(
        position_size=args.position,
        win_rate=args.win_rate,
        profit_pct=args.profit,
        loss_pct=args.loss,
        starting_balance=args.starting_balance,
    )
    results = simulate(trades, strat)

    print(f"Trades: {results['trades']}")
    print(f"Final balance: {results['final_balance']:.2f} USD")
    print(f"ROI: {results['roi'] * 100:.2f}%")


if __name__ == "__main__":
    main()
