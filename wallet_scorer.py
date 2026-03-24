"""
wallet_scorer.py — score wallets based on their historical performance in trades.db.
 
Returns a 0.0–1.0 float for each wallet address. This score is used by
copy_engine.py to size positions: better wallets get bigger bets.
 
Scoring formula (all factors equally weighted at 1/3 each):
  1. Win rate       — % of closed trades that were profitable
  2. Avg ROI        — mean return per closed trade, capped at ±100%
  3. Recency        — wallets with trades in the last 7 days score higher
                      (stale wallets get penalised — their edge may be gone)
 
Only CLOSED trades (where sell_usd_value is recorded) are used for win rate
and ROI. Wallets with no closed trades yet default to 0.5 (neutral).
 
Results are cached in memory for CACHE_TTL_SECONDS to avoid hammering the DB
on every single trade signal.
"""
 
import sqlite3
import time
import math
from typing import Dict, Optional
from utils import log
 
DB_FILE          = "trades.db"
CACHE_TTL_SECONDS = 300   # re-query DB every 5 minutes
MIN_TRADES_FOR_SCORE = 3  # need at least this many closed trades to trust the score
 
# In-memory cache: { wallet: (score, timestamp) }
_cache: Dict[str, tuple[float, float]] = {}
 
 
def _fetch_wallet_stats(wallet: str) -> Optional[dict]:
    """
    Query trades.db for all closed trades belonging to this wallet.
    Returns a dict of stats, or None if the wallet has no trades at all.
    """
    try:
        conn = sqlite3.connect(DB_FILE)
        cur  = conn.cursor()
 
        # All trades for this wallet
        cur.execute(
            "SELECT COUNT(*) FROM trades WHERE wallet = ?",
            (wallet,)
        )
        total_trades = cur.fetchone()[0]
 
        if total_trades == 0:
            conn.close()
            return None
 
        # Closed trades only (sell_usd_value is recorded and non-empty)
        cur.execute(
            """SELECT usd_value, sell_usd_value, timestamp
               FROM trades
               WHERE wallet = ?
               AND sell_usd_value IS NOT NULL
               AND sell_usd_value != ''""",
            (wallet,)
        )
        closed = cur.fetchall()
 
        # Most recent trade timestamp (any trade, open or closed)
        cur.execute(
            "SELECT MAX(timestamp) FROM trades WHERE wallet = ?",
            (wallet,)
        )
        latest_ts = cur.fetchone()[0]
 
        conn.close()
 
        return {
            "total_trades": total_trades,
            "closed":       closed,       # list of (buy_usd, sell_usd, timestamp)
            "latest_ts":    latest_ts,
        }
 
    except Exception as e:
        log(f"[SCORER] DB error for wallet {wallet[:8]}…: {e}")
        return None
 
 
def _win_rate_score(closed: list) -> float:
    """
    Returns 0.0–1.0 based on % of closed trades that were profitable.
    Straight percentage — 70% win rate → 0.7 score.
    """
    if not closed:
        return 0.5  # neutral: no data
 
    wins = sum(
        1 for buy_usd, sell_usd, _ in closed
        if float(sell_usd) > float(buy_usd)
    )
    return wins / len(closed)
 
 
def _avg_roi_score(closed: list) -> float:
    """
    Returns 0.0–1.0 based on average ROI per closed trade.
 
    ROI per trade = (sell - buy) / buy
    We cap individual trade ROI at ±100% to avoid one moon shot
    or one rug pull dominating the entire score.
 
    Mapping:
      avg ROI ≤ -100%  →  0.0
      avg ROI =    0%  →  0.5
      avg ROI ≥ +100%  →  1.0
    """
    if not closed:
        return 0.5
 
    rois = []
    for buy_usd, sell_usd, _ in closed:
        buy  = float(buy_usd)
        sell = float(sell_usd)
        if buy <= 0:
            continue
        roi = (sell - buy) / buy
        roi = max(-1.0, min(1.0, roi))  # cap at ±100%
        rois.append(roi)
 
    if not rois:
        return 0.5
 
    avg_roi = sum(rois) / len(rois)
 
    # Normalise from [-1, 1] → [0, 1]
    return (avg_roi + 1.0) / 2.0
 
 
def _recency_score(latest_ts: Optional[str]) -> float:
    """
    Returns 0.0–1.0 based on how recently this wallet traded.
 
    Decay curve:
      traded today        →  1.0
      traded 7 days ago   →  0.5
      traded 30+ days ago →  0.0
 
    Uses an exponential decay so very recent activity is rewarded heavily
    and old activity drops off quickly.
    """
    if not latest_ts:
        return 0.0
 
    try:
        from datetime import datetime, timezone
        ts  = datetime.fromisoformat(latest_ts.rstrip("Z"))
        now = datetime.utcnow()
        age_days = (now - ts).total_seconds() / 86400
 
        # Exponential decay: score = e^(-age / 7)
        # At 0 days → 1.0, at 7 days → ~0.37, at 30 days → ~0.01
        score = math.exp(-age_days / 7.0)
        return round(min(1.0, max(0.0, score)), 4)
    except Exception:
        return 0.5
 
 
def score_wallet(wallet: str) -> float:
    """
    Return a 0.0–1.0 performance score for the given wallet address.
 
    0.0  →  avoid (consistent losses, stale, or flagged)
    0.5  →  neutral (new wallet, not enough data yet)
    1.0  →  top performer (high win rate, strong ROI, actively trading)
 
    Results are cached for CACHE_TTL_SECONDS.
    """
    # Check cache first
    cached = _cache.get(wallet)
    if cached and (time.time() - cached[1]) < CACHE_TTL_SECONDS:
        return cached[0]
 
    stats = _fetch_wallet_stats(wallet)
 
    # No data at all — neutral score
    if stats is None:
        log(f"[SCORER] {wallet[:8]}… has no trades — defaulting to 0.5")
        _cache[wallet] = (0.5, time.time())
        return 0.5
 
    closed = stats["closed"]
 
    # Not enough closed trades to trust the score yet — slight penalty
    # vs neutral to avoid betting big on unproven wallets
    if len(closed) < MIN_TRADES_FOR_SCORE:
        log(
            f"[SCORER] {wallet[:8]}… only {len(closed)} closed trades "
            f"(need {MIN_TRADES_FOR_SCORE}) — defaulting to 0.4"
        )
        _cache[wallet] = (0.4, time.time())
        return 0.4
 
    # Calculate each component
    wr  = _win_rate_score(closed)
    roi = _avg_roi_score(closed)
    rec = _recency_score(stats["latest_ts"])
 
    # Equal weighting across all three factors
    score = round((wr + roi + rec) / 3.0, 4)
 
    log(
        f"[SCORER] {wallet[:8]}… "
        f"win_rate={wr:.2f} avg_roi={roi:.2f} recency={rec:.2f} "
        f"→ score={score:.2f} "
        f"({len(closed)} closed / {stats['total_trades']} total trades)"
    )
 
    _cache[wallet] = (score, time.time())
    return score
 
 
def invalidate_cache(wallet: Optional[str] = None) -> None:
    """
    Clear cached scores. Pass a wallet address to invalidate just one,
    or call with no args to flush the entire cache (e.g. after a DB migration).
    """
    if wallet:
        _cache.pop(wallet, None)
    else:
        _cache.clear()
 
