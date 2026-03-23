"""
risk_manager.py — AlphaPulse trade risk and token safety filter.

New in this version — token safety checks added to is_risky_token():
  1. Honeypot detection    — calls RugCheck API to flag known scam contracts
  2. Minimum token age     — rejects tokens younger than MIN_TOKEN_AGE_HOURS
  3. Minimum liquidity     — rejects tokens with < MIN_LIQUIDITY_USD pool depth
  4. Top holder concentration — rejects tokens where top 10 wallets hold > MAX_TOP_HOLDER_PCT

All checks are async, run in parallel where possible, and are individually
wrapped in try/except so a failed API call never blocks a real trade.

Results are cached per token for SAFETY_CACHE_TTL_SECONDS to avoid
hammering external APIs on every signal.
"""

import aiohttp
import asyncio
import csv
import time
from datetime import datetime
from decimal import Decimal
from typing import Optional

from utils import log
import config
import auto_sell
import trade_log

# ── File-based allow/block lists ─────────────────────────────────────────────
BLACKLIST_FILE = "token_blacklist.txt"
WHITELIST_FILE = "token_whitelist.txt"

# ── Basic thresholds ─────────────────────────────────────────────────────────
MIN_24H_VOLUME_USD    = 5_000     # minimum 24h trading volume in USD
MAX_OPEN_POSITIONS    = 5         # max concurrent open positions
SLIPPAGE_THRESHOLD    = 0.02      # 2% — above this config.TRADE_SLIPPAGE is too high
DAILY_TRADE_LIMIT     = 20        # max trades per UTC day
EXPOSURE_CAP_PER_TOKEN = Decimal("100.0")  # USD exposure cap per token

# ── Token safety thresholds ──────────────────────────────────────────────────
MIN_TOKEN_AGE_HOURS    = 72       # reject tokens younger than 3 days
MIN_LIQUIDITY_USD      = 50_000   # reject tokens with < $50k pool liquidity
MAX_TOP_HOLDER_PCT     = 0.30     # reject if top 10 wallets hold > 30% of supply
SAFETY_CACHE_TTL_SECONDS = 300    # cache safety results for 5 minutes

# ── In-memory safety cache ───────────────────────────────────────────────────
# { token_mint: (is_safe: bool, reason: str, timestamp: float) }
_safety_cache: dict[str, tuple[bool, str, float]] = {}


# ── File-based lists ─────────────────────────────────────────────────────────

def is_token_blacklisted(token_mint: str) -> bool:
    try:
        with open(BLACKLIST_FILE) as f:
            return token_mint in {l.strip() for l in f}
    except FileNotFoundError:
        return False


def is_token_whitelisted(token_mint: str) -> bool:
    try:
        with open(WHITELIST_FILE) as f:
            return token_mint in {l.strip() for l in f}
    except FileNotFoundError:
        return False


def add_to_blacklist(token_mint: str) -> None:
    """Permanently blacklist a token mint (appends to file)."""
    with open(BLACKLIST_FILE, "a") as f:
        f.write(token_mint + "\n")
    log(f"[RISK] {token_mint[:8]}… added to blacklist.")


# ── Volume check (Birdeye) ───────────────────────────────────────────────────

async def get_token_volume_usd(token_mint: str) -> float:
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                f"https://public-api.birdeye.so/public/token/{token_mint}",
                headers={"X-API-KEY": config.CONFIG.cielo_api_key or "public"},
            ) as resp:
                data = await resp.json()
                return float(data.get("data", {}).get("volume_usd_24h", 0))
    except Exception as e:
        log(f"[RISK] Volume fetch failed for {token_mint[:8]}…: {e}")
        return 0.0


# ── Token safety checks ──────────────────────────────────────────────────────

async def _check_honeypot(token_mint: str) -> tuple[bool, str]:
    """
    Query RugCheck.xyz for known scam/honeypot flags.
    Returns (is_safe, reason).
    """
    try:
        timeout = aiohttp.ClientTimeout(total=6)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                f"https://api.rugcheck.xyz/v1/tokens/{token_mint}/report/summary"
            ) as resp:
                if resp.status != 200:
                    return True, "rugcheck unavailable"
                data = await resp.json()

                score  = data.get("score", 0)   # 0 = safe, higher = riskier
                risks  = data.get("risks", [])
                labels = [r.get("name", "") for r in risks]

                # Hard fail on known dangerous flags
                danger_flags = {
                    "Honeypot", "Freeze Authority Enabled",
                    "Mint Authority Enabled", "Rugged", "High Risk",
                }
                flagged = danger_flags & set(labels)
                if flagged:
                    return False, f"RugCheck flags: {', '.join(flagged)}"

                # Score > 500 = high risk
                if score > 500:
                    return False, f"RugCheck risk score too high: {score}"

                return True, "rugcheck passed"

    except Exception as e:
        log(f"[RISK] RugCheck failed for {token_mint[:8]}…: {e}")
        return True, "rugcheck skipped (API error)"  # fail open — don't block on API errors


async def _check_token_age_and_liquidity(token_mint: str) -> tuple[bool, str]:
    """
    Use Jupiter token list + Birdeye to check:
      - Token age (creation date)
      - Pool liquidity depth
    Returns (is_safe, reason).
    """
    try:
        timeout = aiohttp.ClientTimeout(total=6)
        async with aiohttp.ClientSession(timeout=timeout) as session:

            # Birdeye token overview — has creation_time and liquidity
            async with session.get(
                f"https://public-api.birdeye.so/defi/token_overview?address={token_mint}",
                headers={"X-API-KEY": config.CONFIG.cielo_api_key or "public"},
            ) as resp:
                if resp.status != 200:
                    return True, "birdeye unavailable"

                data = await resp.json()
                info = data.get("data", {})

                # Age check
                created_ts = info.get("createdTime")
                if created_ts:
                    age_hours = (time.time() - created_ts) / 3600
                    if age_hours < MIN_TOKEN_AGE_HOURS:
                        return False, (
                            f"Token too new: {age_hours:.1f}h old "
                            f"(min {MIN_TOKEN_AGE_HOURS}h)"
                        )

                # Liquidity check
                liquidity = float(info.get("liquidity", 0))
                if liquidity < MIN_LIQUIDITY_USD:
                    return False, (
                        f"Liquidity too low: ${liquidity:,.0f} "
                        f"(min ${MIN_LIQUIDITY_USD:,})"
                    )

                return True, f"age/liquidity ok (liq=${liquidity:,.0f})"

    except Exception as e:
        log(f"[RISK] Age/liquidity check failed for {token_mint[:8]}…: {e}")
        return True, "age/liquidity check skipped"


async def _check_holder_concentration(token_mint: str) -> tuple[bool, str]:
    """
    Check if top 10 holders control too much of the supply.
    Uses Birdeye top holders endpoint.
    High concentration = likely team/insider dump risk.
    """
    try:
        timeout = aiohttp.ClientTimeout(total=6)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                f"https://public-api.birdeye.so/defi/token_holder?"
                f"address={token_mint}&offset=0&limit=10",
                headers={"X-API-KEY": config.CONFIG.cielo_api_key or "public"},
            ) as resp:
                if resp.status != 200:
                    return True, "holder check unavailable"

                data    = await resp.json()
                holders = data.get("data", {}).get("items", [])

                if not holders:
                    return True, "no holder data"

                top_pct = sum(h.get("percentage", 0) for h in holders) / 100.0

                if top_pct > MAX_TOP_HOLDER_PCT:
                    return False, (
                        f"Top 10 holders own {top_pct*100:.1f}% "
                        f"(max {MAX_TOP_HOLDER_PCT*100:.0f}%)"
                    )

                return True, f"holder concentration ok ({top_pct*100:.1f}%)"

    except Exception as e:
        log(f"[RISK] Holder check failed for {token_mint[:8]}…: {e}")
        return True, "holder check skipped"


async def is_token_safe(token_mint: str) -> tuple[bool, str]:
    """
    Run all three safety checks in parallel and return (is_safe, reason).
    Results cached for SAFETY_CACHE_TTL_SECONDS.

    Returns (True, reason) if safe to trade.
    Returns (False, reason) if the token should be rejected.
    """
    # Check cache
    cached = _safety_cache.get(token_mint)
    if cached and (time.time() - cached[2]) < SAFETY_CACHE_TTL_SECONDS:
        return cached[0], cached[1]

    # Run all checks concurrently
    honeypot_result, age_liq_result, holder_result = await asyncio.gather(
        _check_honeypot(token_mint),
        _check_token_age_and_liquidity(token_mint),
        _check_holder_concentration(token_mint),
        return_exceptions=True,
    )

    # Unpack results (handle any unexpected exceptions from gather)
    checks = []
    for result in [honeypot_result, age_liq_result, holder_result]:
        if isinstance(result, Exception):
            checks.append((True, f"check error: {result}"))
        else:
            checks.append(result)

    # Any single failure = token is rejected
    for is_safe, reason in checks:
        if not is_safe:
            log(f"[SAFETY] {token_mint[:8]}… REJECTED — {reason}")
            add_to_blacklist(token_mint)   # auto-blacklist so we never check again
            _safety_cache[token_mint] = (False, reason, time.time())
            return False, reason

    combined_reason = " | ".join(r for _, r in checks)
    log(f"[SAFETY] {token_mint[:8]}… passed — {combined_reason}")
    _safety_cache[token_mint] = (True, combined_reason, time.time())
    return True, combined_reason


# ── Daily limit + streak helpers ─────────────────────────────────────────────

def _today():
    return datetime.utcnow().date()


def get_today_trade_count() -> int:
    try:
        with open(trade_log.CSV_FILE, newline="") as f:
            reader = csv.DictReader(f)
            return sum(
                1 for row in reader
                if datetime.fromisoformat(row["timestamp"]).date() == _today()
            )
    except FileNotFoundError:
        return 0


def daily_limit_reached() -> bool:
    return get_today_trade_count() >= DAILY_TRADE_LIMIT


def is_exposure_exceeded(token_mint: str) -> bool:
    info = auto_sell.portfolio.get(token_mint)
    if not info:
        return False
    exposure = (
        Decimal(str(info.get("entry_price", 0)))
        * Decimal(str(info.get("amount", 0)))
    )
    return exposure > EXPOSURE_CAP_PER_TOKEN


def _trade_results() -> list[bool]:
    results = []
    try:
        with open(trade_log.CSV_FILE, newline="") as f:
            reader = csv.DictReader(f)
            buys: dict = {}
            for row in reader:
                mint = row["token_mint"]
                usd  = Decimal(row["usd_value"])
                if row["token_symbol"] == "AUTOSELL":
                    buy = buys.pop(mint, None)
                    if buy is not None:
                        results.append(usd > buy)
                else:
                    buys[mint] = usd
    except FileNotFoundError:
        pass
    return results


def adjust_position_size(base: Decimal) -> Decimal:
    """Scale position size up/down based on current win/loss streak."""
    results = _trade_results()
    streak  = 0
    for res in reversed(results):
        if res:
            if streak < 0: break
            streak += 1
        else:
            if streak > 0: break
            streak -= 1
    if streak >= 3:
        return base * Decimal("1.5")
    if streak <= -3:
        return base * Decimal("0.5")
    return base


# ── Main gate ────────────────────────────────────────────────────────────────

async def is_risky_token(token_mint: str) -> bool:
    """
    Full risk gate — returns True if the token should be SKIPPED.

    Order of checks (fast/cheap first, API calls last):
      1. Daily trade limit
      2. Exposure cap
      3. Whitelist (skip all further checks)
      4. Blacklist
      5. Position limit
      6. Slippage config sanity
      7. 24h volume (Birdeye)
      8. Safety suite: honeypot + age/liquidity + holder concentration
    """

    # 1. Daily limit
    if daily_limit_reached():
        log("[RISK] Daily trade limit reached.")
        return True

    # 2. Exposure cap
    if is_exposure_exceeded(token_mint):
        log(f"[RISK] Exposure cap exceeded for {token_mint[:8]}…")
        return True

    # 3. Whitelist — trusted tokens skip safety checks
    if is_token_whitelisted(token_mint):
        return False

    # 4. Blacklist
    if is_token_blacklisted(token_mint):
        log(f"[RISK] {token_mint[:8]}… is blacklisted.")
        return True

    # 5. Position limit
    if len(getattr(auto_sell, "portfolio", {})) >= MAX_OPEN_POSITIONS:
        log("[RISK] Max open positions reached.")
        return True

    # 6. Slippage sanity
    if config.TRADE_SLIPPAGE > SLIPPAGE_THRESHOLD:
        log(f"[RISK] TRADE_SLIPPAGE {config.TRADE_SLIPPAGE} exceeds threshold.")
        return True

    # 7. Volume check
    volume = await get_token_volume_usd(token_mint)
    if volume < MIN_24H_VOLUME_USD:
        log(f"[RISK] {token_mint[:8]}… low volume: ${volume:,.0f}")
        return True

    # 8. Full safety suite (honeypot + age + liquidity + holders)
    safe, reason = await is_token_safe(token_mint)
    if not safe:
        log(f"[RISK] {token_mint[:8]}… failed safety check: {reason}")
        return True

    return False
