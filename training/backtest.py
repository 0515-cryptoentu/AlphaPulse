"""
training/backtest.py — real trade replay backtester.

Replaces the original naive simulation (which assumed a fixed win rate)
with a real replay of actual trades from trades.db.

What it does:
  - Loads all closed trades (buy + sell_usd_value both present) from trades.db
  - Replays them chronologically, applying position sizing rules
  - Calculates actual P&L, win rate, drawdown, Sharpe ratio per wallet
  - Outputs a full performance report per wallet + overall

Run via CLI:
  alphapulse train --db trades.db
  alphapulse train --db trades.db --min-closed 5 --starting-balance 500

Or directly:
  python -m training.backtest
"""

from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Optional
import math

import pandas as pd
import logging
from utils import log

from . import load_trade_history, DB_FILE


# ── Result dataclasses ────────────────────────────────────────────────────────

@dataclass
class WalletResult:
    wallet:          str
    total_trades:    int     = 0
    closed_trades:   int     = 0
    wins:            int     = 0
    losses:          int     = 0
    total_invested:  float   = 0.0
    total_returned:  float   = 0.0
    pnl_usd:         float   = 0.0
    win_rate:        float   = 0.0
    avg_roi_pct:     float   = 0.0
    best_trade_pct:  float   = 0.0
    worst_trade_pct: float   = 0.0
    max_drawdown_pct: float  = 0.0
    sharpe_ratio:    float   = 0.0
    go_live_ready:   bool    = False
    roi_per_trade:   list    = field(default_factory=list)


@dataclass
class BacktestResult:
    starting_balance:  float
    final_balance:     float
    total_pnl:         float
    roi_pct:           float
    total_trades:      int
    closed_trades:     int
    wins:              int
    win_rate:          float
    max_drawdown_pct:  float
    sharpe_ratio:      float
    best_wallet:       Optional[str]
    worst_wallet:      Optional[str]
    go_live_ready:     bool
    wallet_results:    dict[str, WalletResult]
    warnings:          list[str]


# ── Core replay engine ────────────────────────────────────────────────────────

def _calc_sharpe(returns: list[float], risk_free: float = 0.0) -> float:
    """Annualised Sharpe ratio from a list of per-trade returns."""
    if len(returns) < 2:
        return 0.0
    mean   = sum(returns) / len(returns)
    var    = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    stddev = math.sqrt(var)
    if stddev == 0:
        return 0.0
    # Annualise assuming ~10 trades/day
    return round((mean - risk_free) / stddev * math.sqrt(10 * 365), 4)


def _calc_max_drawdown(balance_curve: list[float]) -> float:
    """Maximum peak-to-trough drawdown as a percentage."""
    if not balance_curve:
        return 0.0
    peak     = balance_curve[0]
    max_dd   = 0.0
    for val in balance_curve:
        if val > peak:
            peak = val
        dd = (peak - val) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
    return round(max_dd * 100, 2)


def replay_trades(
    df:               pd.DataFrame,
    starting_balance: float = 1000.0,
    position_pct:     float = 0.03,     # 3% per trade (mid-range of our 1–5% scale)
    min_closed:       int   = 5,        # minimum closed trades to include wallet
) -> BacktestResult:
    """
    Replay closed trades from the DataFrame in chronological order.

    Only trades with both usd_value (buy) and sell_usd_value (sell) are
    included. Open positions are skipped.

    Args:
        df:               DataFrame from load_trade_history()
        starting_balance: Starting USD balance to simulate
        position_pct:     Fraction of current balance per trade
        min_closed:       Minimum closed trades to include a wallet in results
    """
    warnings = []

    # Filter to buy trades with a closed sell value
    closed = df[
        (df["token_symbol"] != "AUTOSELL")
        & df["sell_usd_value"].notna()
        & (df["sell_usd_value"] != "")
        & (df["usd_value"].notna())
    ].copy()

    if closed.empty:
        warnings.append(
            "No closed trades found in trades.db. "
            "Run in practice mode until auto_sell closes some positions."
        )
        return BacktestResult(
            starting_balance=starting_balance,
            final_balance=starting_balance,
            total_pnl=0.0,
            roi_pct=0.0,
            total_trades=len(df),
            closed_trades=0,
            wins=0,
            win_rate=0.0,
            max_drawdown_pct=0.0,
            sharpe_ratio=0.0,
            best_wallet=None,
            worst_wallet=None,
            go_live_ready=False,
            wallet_results={},
            warnings=warnings,
        )

    # Convert numeric columns
    closed["usd_value"]      = pd.to_numeric(closed["usd_value"],      errors="coerce").fillna(0)
    closed["sell_usd_value"] = pd.to_numeric(closed["sell_usd_value"], errors="coerce").fillna(0)

    # Sort chronologically
    closed = closed.sort_values("timestamp").reset_index(drop=True)

    # ── Per-wallet stats ──────────────────────────────────────────────────────
    wallet_results: dict[str, WalletResult] = {}

    for _, row in closed.iterrows():
        wallet   = str(row.get("wallet") or "unknown")
        buy_usd  = float(row["usd_value"])
        sell_usd = float(row["sell_usd_value"])

        if wallet not in wallet_results:
            wallet_results[wallet] = WalletResult(wallet=wallet)

        wr = wallet_results[wallet]
        wr.closed_trades   += 1
        wr.total_invested  += buy_usd
        wr.total_returned  += sell_usd

        trade_roi = (sell_usd - buy_usd) / buy_usd if buy_usd > 0 else 0.0
        wr.roi_per_trade.append(trade_roi)

        if sell_usd > buy_usd:
            wr.wins += 1
        else:
            wr.losses += 1

        wr.best_trade_pct  = max(wr.best_trade_pct,  trade_roi * 100)
        wr.worst_trade_pct = min(wr.worst_trade_pct, trade_roi * 100)

    # Finalise wallet stats
    for wr in wallet_results.values():
        if wr.closed_trades > 0:
            wr.pnl_usd     = wr.total_returned - wr.total_invested
            wr.win_rate    = wr.wins / wr.closed_trades
            wr.avg_roi_pct = sum(wr.roi_per_trade) / len(wr.roi_per_trade) * 100
            wr.sharpe_ratio = _calc_sharpe(wr.roi_per_trade)

            # Calculate drawdown from cumulative returns
            cum_balance = [1.0]
            for r in wr.roi_per_trade:
                cum_balance.append(cum_balance[-1] * (1 + r))
            wr.max_drawdown_pct = _calc_max_drawdown(cum_balance)

            wr.go_live_ready = (
                wr.win_rate >= 0.55
                and wr.closed_trades >= min_closed
                and wr.avg_roi_pct > 0
                and wr.max_drawdown_pct < 30
            )

    # Filter wallets with too few trades
    qualified = {
        k: v for k, v in wallet_results.items()
        if v.closed_trades >= min_closed
    }
    if len(wallet_results) > len(qualified):
        warnings.append(
            f"{len(wallet_results) - len(qualified)} wallet(s) skipped "
            f"(fewer than {min_closed} closed trades)."
        )

    # ── Portfolio-level replay ────────────────────────────────────────────────
    balance       = starting_balance
    balance_curve = [balance]
    wins          = 0

    for _, row in closed.iterrows():
        buy_usd  = float(row["usd_value"])
        sell_usd = float(row["sell_usd_value"])
        if buy_usd <= 0:
            continue

        # Simulate position as fixed % of current balance
        stake  = balance * position_pct
        roi    = (sell_usd - buy_usd) / buy_usd
        pnl    = stake * roi
        balance += pnl

        if pnl > 0:
            wins += 1

        balance_curve.append(balance)

    total_closed   = len(closed)
    overall_win_rate = wins / total_closed if total_closed > 0 else 0.0
    total_pnl      = balance - starting_balance
    roi_pct        = (total_pnl / starting_balance) * 100
    max_drawdown   = _calc_max_drawdown(balance_curve)

    # Overall Sharpe from all trades
    all_returns = []
    for _, row in closed.iterrows():
        buy  = float(row["usd_value"])
        sell = float(row["sell_usd_value"])
        if buy > 0:
            all_returns.append((sell - buy) / buy)
    sharpe = _calc_sharpe(all_returns)

    # Best and worst wallets by avg ROI
    best_wallet  = max(qualified, key=lambda k: qualified[k].avg_roi_pct, default=None)
    worst_wallet = min(qualified, key=lambda k: qualified[k].avg_roi_pct, default=None)

    go_live_ready = (
        overall_win_rate >= 0.55
        and total_closed >= 50
        and max_drawdown < 25
        and total_pnl > 0
    )

    if not go_live_ready:
        reasons = []
        if overall_win_rate < 0.55:
            reasons.append(f"win rate {overall_win_rate*100:.1f}% < 55%")
        if total_closed < 50:
            reasons.append(f"only {total_closed} closed trades (need 50+)")
        if max_drawdown >= 25:
            reasons.append(f"drawdown {max_drawdown:.1f}% >= 25%")
        if total_pnl <= 0:
            reasons.append("overall P&L is negative")
        warnings.append("NOT ready to go live: " + ", ".join(reasons))

    return BacktestResult(
        starting_balance=starting_balance,
        final_balance=round(balance, 2),
        total_pnl=round(total_pnl, 2),
        roi_pct=round(roi_pct, 2),
        total_trades=len(df),
        closed_trades=total_closed,
        wins=wins,
        win_rate=round(overall_win_rate, 4),
        max_drawdown_pct=max_drawdown,
        sharpe_ratio=sharpe,
        best_wallet=best_wallet,
        worst_wallet=worst_wallet,
        go_live_ready=go_live_ready,
        wallet_results=qualified,
        warnings=warnings,
    )


# ── CLI output ────────────────────────────────────────────────────────────────

def _print_report(result: BacktestResult) -> None:
    sep = "─" * 52

    print(f"\n{sep}")
    print("  AlphaPulse Backtest Report")
    print(sep)
    print(f"  Starting balance : ${result.starting_balance:>10,.2f}")
    print(f"  Final balance    : ${result.final_balance:>10,.2f}")
    print(f"  Total P&L        : ${result.total_pnl:>+10,.2f}")
    print(f"  ROI              : {result.roi_pct:>+10.2f}%")
    print(sep)
    print(f"  Total trades     : {result.total_trades:>10}")
    print(f"  Closed trades    : {result.closed_trades:>10}")
    print(f"  Wins             : {result.wins:>10}")
    print(f"  Win rate         : {result.win_rate*100:>9.1f}%")
    print(f"  Max drawdown     : {result.max_drawdown_pct:>9.1f}%")
    print(f"  Sharpe ratio     : {result.sharpe_ratio:>10.2f}")
    print(sep)

    ready_str = "✅ YES — safe to go live" if result.go_live_ready else "❌ NO — keep practising"
    print(f"  Go-live ready    : {ready_str}")
    print(sep)

    if result.wallet_results:
        print("\n  Per-wallet breakdown:")
        print(f"  {'Wallet':<14} {'Closed':>6} {'Win%':>6} {'AvgROI':>8} {'P&L':>10} {'Sharpe':>7} {'Ready':>6}")
        print(f"  {'-'*14} {'-'*6} {'-'*6} {'-'*8} {'-'*10} {'-'*7} {'-'*6}")
        for wr in sorted(result.wallet_results.values(), key=lambda x: x.avg_roi_pct, reverse=True):
            ready = "✅" if wr.go_live_ready else "❌"
            print(
                f"  {wr.wallet[:12]:<14} {wr.closed_trades:>6} "
                f"{wr.win_rate*100:>5.1f}% {wr.avg_roi_pct:>+7.1f}% "
                f"${wr.pnl_usd:>+9.2f} {wr.sharpe_ratio:>7.2f} {ready:>6}"
            )

    if result.warnings:
        print(f"\n  Warnings:")
        for w in result.warnings:
            print(f"  ⚠️  {w}")

    print(f"\n{sep}\n")


# ── Entry point ───────────────────────────────────────────────────────────────

def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="AlphaPulse real trade backtest")
    parser.add_argument("--db",               default=DB_FILE,  help="Path to trades.db")
    parser.add_argument("--position",         type=float, default=0.03, help="Position size fraction (default 0.03 = 3%%)")
    parser.add_argument("--starting-balance", type=float, default=1000.0, help="Starting USD balance")
    parser.add_argument("--min-closed",       type=int,   default=5, help="Min closed trades per wallet")
    args = parser.parse_args(argv)

    log(f"Loading trade history from {args.db}…", logging.INFO)
    df = load_trade_history(args.db)

    if df.empty:
        log("No trades found in database. Run the bot in practice mode first.", logging.WARNING)
        return

    log(f"Replaying {len(df)} trades…", logging.INFO)
    result = replay_trades(
        df,
        starting_balance=args.starting_balance,
        position_pct=args.position,
        min_closed=args.min_closed,
    )

    _print_report(result)


if __name__ == "__main__":
    main()
