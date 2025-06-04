import aiohttp
import csv
from datetime import datetime
from decimal import Decimal
from utils import log
import config
import auto_sell
import trade_log

# Blacklist file
BLACKLIST_FILE = "token_blacklist.txt"
WHITELIST_FILE = "token_whitelist.txt"

# Configurable thresholds
MIN_24H_VOLUME_USD = 5000
MAX_OPEN_POSITIONS = 5
SLIPPAGE_THRESHOLD = 0.02

# Daily trading constraints
DAILY_TRADE_LIMIT = 20
EXPOSURE_CAP_PER_TOKEN = Decimal("100.0")  # USD value


def is_token_blacklisted(token_mint):
    try:
        with open(BLACKLIST_FILE, "r") as f:
            blacklist = set(line.strip() for line in f.readlines())
        return token_mint in blacklist
    except FileNotFoundError:
        return False


def is_token_whitelisted(token_mint):
    try:
        with open(WHITELIST_FILE, "r") as f:
            whitelist = set(line.strip() for line in f.readlines())
        return token_mint in whitelist
    except FileNotFoundError:
        return False


async def get_token_volume_usd(token_mint):
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                f"https://public-api.birdeye.so/public/token/{token_mint}",
                headers={"X-API-KEY": "public"},
            ) as resp:
                data = await resp.json()
                volume = data.get("data", {}).get("volume_usd_24h", 0)
                return float(volume)
    except Exception as e:
        log(f"[RISK] Failed to fetch token volume: {e}")
        return 0


def _today() -> datetime.date:
    return datetime.utcnow().date()


def get_today_trade_count() -> int:
    """Return number of trades logged for the current UTC day."""
    try:
        with open(trade_log.CSV_FILE, newline="") as f:
            reader = csv.DictReader(f)
            return sum(
                1
                for row in reader
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
    exposure = Decimal(str(info.get("entry_price", 0))) * Decimal(str(info.get("amount", 0)))
    return exposure > EXPOSURE_CAP_PER_TOKEN


def _trade_results():
    """Return list of booleans representing win (True) or loss (False)."""
    results = []
    try:
        with open(trade_log.CSV_FILE, newline="") as f:
            reader = csv.DictReader(f)
            buys = {}
            for row in reader:
                mint = row["token_mint"]
                usd = Decimal(row["usd_value"])
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
    """Return position size adjusted for win/loss streak."""
    results = _trade_results()
    streak = 0
    for res in reversed(results):
        if res:
            if streak < 0:
                break
            streak += 1
        else:
            if streak > 0:
                break
            streak -= 1
    if streak >= 3:
        return base * Decimal("1.5")
    if streak <= -3:
        return base * Decimal("0.5")
    return base


async def is_risky_token(token_mint):
    if daily_limit_reached():
        log("[RISK] Daily trade limit reached.")
        return True

    if is_exposure_exceeded(token_mint):
        log(f"[RISK] Exposure cap exceeded for {token_mint}.")
        return True

    if is_token_whitelisted(token_mint):
        return False

    if is_token_blacklisted(token_mint):
        log(f"[RISK] Token {token_mint} is blacklisted.")
        return True

    if len(getattr(auto_sell, "portfolio", {})) >= MAX_OPEN_POSITIONS:
        log("[RISK] Position limit reached.")
        return True

    if config.TRADE_SLIPPAGE > SLIPPAGE_THRESHOLD:
        log(f"[RISK] Slippage {config.TRADE_SLIPPAGE} exceeds threshold.")
        return True

    volume = await get_token_volume_usd(token_mint)
    if volume < MIN_24H_VOLUME_USD:
        log(f"[RISK] Token {token_mint} has low 24h volume: ${volume:.2f}")
        return True

    return False
