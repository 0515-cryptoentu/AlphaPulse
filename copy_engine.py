"""
copy_engine.py — AlphaPulse trade execution engine.

Changes from previous version:
  - Checks telegram_bot.PAUSED at the top of execute_trade() so /pause
    command immediately stops all new trade execution
"""

from decimal import Decimal
from datetime import datetime

from wallet_manager import get_balance
from trade_log import log_trade, get_sol_usd_price
from jupiter_trader import fetch_jupiter_swap_route, execute_jupiter_swap
from auto_sell import mark_new_token
from risk_manager import is_risky_token
from wallet_scorer import score_wallet
from utils import log
import config

MINT_SOL = "So11111111111111111111111111111111111111112"

# --- Position sizing constants ---
BASE_POSITION_PCT = Decimal("0.01")   # 1% of balance — baseline
MAX_POSITION_PCT  = Decimal("0.05")   # 5% of balance — hard cap
MIN_POSITION_SOL  = Decimal("0.02")   # minimum trade size (covers fees)
COOLDOWN_SECONDS  = 30                # seconds before copying same wallet again

# In-memory cooldown tracker: { wallet_address: last_trade_datetime }
_last_trade_time: dict[str, datetime] = {}


def _position_size(balance: float, wallet_score: float) -> Decimal:
    """
    Scale position between BASE and MAX based on wallet_score (0.0–1.0).

    score=0.0  →  1% of balance
    score=0.5  →  3% of balance
    score=1.0  →  5% of balance
    """
    score  = Decimal(str(max(0.0, min(1.0, wallet_score))))
    pct    = BASE_POSITION_PCT + (MAX_POSITION_PCT - BASE_POSITION_PCT) * score
    amount = Decimal(str(balance)) * pct

    if amount < MIN_POSITION_SOL:
        log(f"[SIZE] {amount:.4f} SOL is below minimum {MIN_POSITION_SOL} SOL — skipping.")
        return Decimal("0")

    return amount


def _is_on_cooldown(wallet: str) -> bool:
    last = _last_trade_time.get(wallet)
    if last and (datetime.utcnow() - last).total_seconds() < COOLDOWN_SECONDS:
        return True
    return False


async def execute_trade(trade: dict) -> None:
    """
    Main entry point — called by trade_monitor when a watched wallet moves.

    trade dict keys:
      wallet     — address of the wallet being copied
      token_in   — mint of input token (usually SOL)
      token_out  — mint of token being bought
      signature  — transaction signature for dedup/logging
    """
    # --- Guard: pause flag (set by /pause Telegram command) ---
    try:
        import telegram_bot
        if telegram_bot.PAUSED:
            log("[PAUSED] Trade signal received but bot is paused — skipping.")
            return
    except ImportError:
        pass  # telegram_bot not loaded (e.g. during tests) — continue normally

    wallet    = trade["wallet"]
    token_in  = trade["token_in"]
    token_out = trade["token_out"]
    signature = trade["signature"]

    # --- Guard: cooldown ---
    if _is_on_cooldown(wallet):
        log(f"[COOLDOWN] Skipping {wallet[:8]}… — traded too recently.")
        return

    # --- Guard: risk filter ---
    if await is_risky_token(token_out):
        log(f"[RISK] Skipping risky token {token_out[:8]}…")
        return

    # --- Guard: minimum balance ---
    balance = get_balance()
    if balance < config.MIN_BALANCE_SOL:
        log(f"[BALANCE] {balance:.4f} SOL is below minimum {config.MIN_BALANCE_SOL} — not trading.")
        return

    # --- Real wallet score from trades.db ---
    wallet_score = score_wallet(wallet)

    # --- Dynamic position sizing ---
    sol_amount = _position_size(balance, wallet_score)
    if sol_amount == Decimal("0"):
        return

    lamports = int(sol_amount * Decimal("1e9"))

    log(
        f"[SIZE] {wallet[:8]}… score={wallet_score:.2f} → "
        f"{sol_amount:.4f} SOL ({float(sol_amount)/balance*100:.1f}% of balance)"
    )

    # Record cooldown before executing to prevent duplicate fires
    _last_trade_time[wallet] = datetime.utcnow()

    # --- Execute ---
    if config.PRACTICE_MODE:
        log(f"[PRACTICE] Copying {wallet[:8]}…: buying {token_out[:8]}… with {sol_amount:.4f} SOL")
        await log_trade(
            token_out, "FAKECOIN", 0, sol_amount,
            f"sim-{signature[-6:]}",
            wallet=wallet,
        )
        mark_new_token(token_out, await get_sol_usd_price(), 0)

    else:
        route = await fetch_jupiter_swap_route(
            token_in,
            token_out,
            lamports,
            slippage_bps=int(config.TRADE_SLIPPAGE * 10_000),  # e.g. 0.005 → 50 bps
        )

        if not route:
            log(f"[JUPITER] No route found for {token_in[:8]}… → {token_out[:8]}…. Skipping.")
            return

        result = await execute_jupiter_swap(route)

        if result:
            tx = result["result"]
            log(f"[LIVE] Bought {token_out[:8]}… | tx={tx} | size={sol_amount:.4f} SOL")
            await log_trade(
                token_out, "LIVECOIN", 0, sol_amount, tx,
                wallet=wallet,
            )
            mark_new_token(token_out, await get_sol_usd_price(), 0)
        else:
            log(f"[LIVE] Swap failed for {token_out[:8]}…. No position taken.")
