import aiohttp
from utils import log

# Blacklist file
BLACKLIST_FILE = "token_blacklist.txt"

# Configurable thresholds
MIN_24H_VOLUME_USD = 5000


def is_token_blacklisted(token_mint):
    try:
        with open(BLACKLIST_FILE, "r") as f:
            blacklist = set(line.strip() for line in f.readlines())
        return token_mint in blacklist
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


async def is_risky_token(token_mint):
    if is_token_blacklisted(token_mint):
        log(f"[RISK] Token {token_mint} is blacklisted.")
        return True

    volume = await get_token_volume_usd(token_mint)
    if volume < MIN_24H_VOLUME_USD:
        log(f"[RISK] Token {token_mint} has low 24h volume: ${volume:.2f}")
        return True

    return False
