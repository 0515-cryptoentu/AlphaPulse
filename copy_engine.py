"""
copy_engine.py — AlphaPulse trade execution engine.

Improvements over original:
  - Dynamic position sizing based on wallet win rate and trade confidence
  - Slippage passed through to Jupiter swap route
  - Per-wallet trade cooldown to avoid overtrading
  - Hard cap on max position size to protect the bankroll
  - Better logging throughout
"""

from decimal import Decimal
from datetime import datetime, timedelta
from wallet_manager import get_balance
from trade_log import log_trade, get_sol_usd_price
from jupiter_trader import fetch_jupiter_swap_route, execute_jupiter_swap
from auto_sell import mark_new_token
from risk_manager import is_risky_token
from utils import log
import config

MINT_SOL = "So11111111111111111111111111111111111111112"

# --- Position sizing constants ---
BASE_POSITION_PCT   = Decimal("0.01")   # 1% of balance — baseline bet
MAX_POSITION_PCT    = Decimal("0.05")   # 5% of balance — hard cap, never exceed this
MIN_POSITION_SOL    = Decimal("0.02")   # minimum trade size in SOL (to cover fees)
COOLDOWN_SECONDS    = 30               # seconds before copying same wallet again

# In-memory cooldown tracker: { wallet_address: last_trade_datetime }
_last_trade_time: dict[str, datetime] = {}


def _position_size(balance: float, wallet_score: float) -> Decimal:
    """
    Calculate how much SOL to use for this trade.

    wallet_score is a 0.0–1.0 float representing our confidence in this wallet
    (e.g. derived from their historical win rate). Higher score = larger bet,
    scaling linearly between BASE and MAX position size.

    Examples:
      score=0.0  →  1% of balance (baseline, low confidence)
      score=0.5  →  3% of balance
      score=1.0  →  5% of balance (max, highest confidence)
    """
    score = Decimal(str(max(0.0, min(1.0, wallet_score))))
    pct = BASE_POSITION_PCT + (MAX_POSITION_PCT - BASE_POSITION_PCT) * score
    amount = Decimal(str(balance)) * pct

    # Never go below minimum (would just be eaten by fees)
    if amount < MIN_POSITION_SOL:
        log(f"[SIZE] Calculated {amount:.4f} SOL is below minimum {MIN_POSITION_SOL} SOL — skipping.")
        return Decimal("0")

    return amount


def _is_on_cooldown(wallet: str) -> bool:
    """Return True if we've traded this wallet too recently."""
    last = _last_trade_time.get(wallet)
    if last and (datetime.utcnow() - last).total_seconds() < COOLDOWN_SECONDS:
        return True
    return False


def _get_wallet_score(wallet: str) -> float:
    """
    Return a 0.0–1.0 confidence score for this wallet.

    Currently returns 0.5 (neutral) for all wallets. In a future iteration
    this should query trade_log / trades.db to calculate:
      - win rate (wins / total trades)
      - average return per trade
      - recency weighting (recent trades matter more)
    
    TODO: plug in real wallet performance data from trades.db
    """
    # Placeholder — replace with real DB lookup
    _ = wallet
    return 0.5


async def execute_trade(trade: dict) -> None:
    """
    Main entry point. Called by trade_monitor when a watched wallet makes a move.

    trade dict expected keys:
      wallet     — address of the wallet we're copying
      token_in   — mint address of the input token (usually SOL)
      token_out  — mint address of the token being bought
      signature  — transaction signature (for dedup / logging)
    """
    wallet    = trade["wallet"]
    token_in  = trade["token_in"]
    token_out = trade["token_out"]
    signature = trade["signature"]

    # --- Guard: cooldown ---
    if _is_on_cooldown(wallet):
        log(f"[COOLDOWN] Skipping {wallet} — traded too recently.")
        return

    # --- Guard: risk filter ---
    if await is_risky_token(token_out):
        log(f"[RISK] Skipping risky token {token_out}")
        return

    # --- Guard: minimum balance ---
    balance = get_balance()
    if balance < config.MIN_BALANCE_SOL:
        log(f"[BALANCE] {balance:.4f} SOL is below minimum {config.MIN_BALANCE_SOL} SOL. Not trading.")
        return

    # --- Dynamic position sizing ---
    wallet_score = _get_wallet_score(wallet)
    sol_amount   = _position_size(balance, wallet_score)

    if sol_amount == Decimal("0"):
        return  # too small to bother, already logged inside _position_size

    lamports = int(sol_amount * Decimal("1e9"))

    log(
        f"[SIZE] wallet_score={wallet_score:.2f} → "
        f"using {sol_amount:.4f} SOL ({float(sol_amount)/balance*100:.1f}% of balance)"
    )

    # --- Record cooldown before executing (prevents duplicate fires) ---
    _last_trade_time[wallet] = datetime.utcnow()

    # --- Execute ---
    if config.PRACTICE_MODE:
        log(f"[PRACTICE] Copying {wallet}: buying {token_out} with {sol_amount:.4f} SOL")
        await log_trade(token_out, "FAKECOIN", 0, sol_amount, f"sim-{signature[-6:]}")
        mark_new_token(token_out, await get_sol_usd_price(), 0)

    else:
        # Pass slippage from config so Jupiter respects our tolerance
        route = await fetch_jupiter_swap_route(
            token_in,
            token_out,
            lamports,
            slippage_bps=int(config.TRADE_SLIPPAGE * 10_000),  # e.g. 0.005 → 50 bps
        )

        if not route:
            log(f"[JUPITER] No route found for {token_in} → {token_out}. Skipping.")
            return

        result = await execute_jupiter_swap(route)

        if result:
            log(f"[LIVE] Executed buy of {token_out}: tx={result['result']}, size={sol_amount:.4f} SOL")
            await log_trade(token_out, "LIVECOIN", 0, sol_amount, result["result"])
            mark_new_token(token_out, await get_sol_usd_price(), 0)
        else:
            log(f"[LIVE] Swap execution failed for {token_out}. No position taken.")
