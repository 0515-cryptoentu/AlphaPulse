"""
jupiter_trader.py — Jupiter swap routing + Jito MEV-protected execution.

Changes from original:
  - fetch_jupiter_swap_route() now accepts slippage_bps as a parameter
    (was hardcoded to config.TRADE_SLIPPAGE before)
  - execute_jupiter_swap() routes through Jito bundles in LIVE mode
    for sandwich/MEV protection
  - Falls back to direct RPC submission if Jito submission fails,
    so a Jito outage never stops the bot entirely
  - PRACTICE_MODE always uses direct RPC (no point paying Jito tips
    on simulated trades)
  - Fixed Jupiter v6 API response format (was accessing data[0] which
    is the v4 format — v6 returns the quote object directly)
"""

import asyncio
import base64
import logging
import os
from typing import Optional

import aiohttp
from solana.rpc.api import Client
from solana.rpc.types import TxOpts

try:
    from solders.keypair import Keypair
except ImportError:
    from solana.keypair import Keypair

try:
    from solana.transaction import Transaction
except ImportError:
    from solders.transaction import Transaction  # solana-py >= 0.30

import config
from jito_client import submit_bundle, wait_for_bundle, _pick_tip_account, JITO_TIP_LAMPORTS
from utils import log

# ── Clients ───────────────────────────────────────────────────────────────────
client = Client(config.RPC_URL)
wallet = Keypair.from_bytes(base64.b64decode(config.USER_WALLET_PRIVATE_KEY))

JUPITER_QUOTE_URL = "https://quote-api.jup.ag/v6/quote"
JUPITER_SWAP_URL  = "https://quote-api.jup.ag/v6/swap"


# ── Quote ─────────────────────────────────────────────────────────────────────

async def fetch_jupiter_swap_route(
    input_mint:   str,
    output_mint:  str,
    amount:       int,           # in lamports
    slippage_bps: int = 50,      # 50 bps = 0.5%
) -> Optional[dict]:
    """
    Fetch the best swap route from Jupiter v6.
    Returns the quote dict or None if no route found.
    """
    params = {
        "inputMint":   input_mint,
        "outputMint":  output_mint,
        "amount":      str(amount),
        "slippageBps": slippage_bps,
        "onlyDirectRoutes": "false",
        "asLegacyTransaction": "true",
    }

    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(JUPITER_QUOTE_URL, params=params) as resp:
                if resp.status != 200:
                    log(f"[JUPITER] Quote failed: HTTP {resp.status}", logging.WARNING)
                    return None

                data = await resp.json()

                # Jupiter v6 returns quote directly (not wrapped in data[])
                if "routePlan" in data:
                    return data

                # Fallback for older response format
                routes = data.get("data", [])
                if routes:
                    return routes[0]

                log("[JUPITER] No routes found.", logging.WARNING)
                return None

    except Exception as e:
        log(f"[JUPITER] Quote error: {e}", logging.ERROR)
        return None


# ── Swap transaction builder ──────────────────────────────────────────────────

async def _build_swap_transaction(route: dict) -> Optional[bytes]:
    """
    Call Jupiter swap endpoint to get the serialized transaction.
    Returns raw transaction bytes ready for signing, or None on failure.
    """
    payload = {
        "quoteResponse":       route,
        "userPublicKey":       str(wallet.public_key),
        "wrapAndUnwrapSol":    True,
        "asLegacyTransaction": True,
        "dynamicComputeUnitLimit": True,
        "prioritizationFeeLamports": "auto",
    }

    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(JUPITER_SWAP_URL, json=payload) as resp:
                if resp.status != 200:
                    log(f"[JUPITER] Swap build failed: HTTP {resp.status}", logging.ERROR)
                    return None
                data = await resp.json()
                tx_b64 = data.get("swapTransaction")
                if not tx_b64:
                    log("[JUPITER] No swapTransaction in response.", logging.ERROR)
                    return None
                return base64.b64decode(tx_b64)

    except Exception as e:
        log(f"[JUPITER] Swap build error: {e}", logging.ERROR)
        return None


# ── Direct RPC submission (fallback / practice mode) ─────────────────────────

def _send_direct(tx_bytes: bytes) -> Optional[dict]:
    """
    Sign and submit transaction directly to RPC.
    Used in practice mode and as Jito fallback.
    """
    try:
        tx = Transaction.deserialize(tx_bytes)
        tx.sign(wallet)
        return client.send_transaction(
            tx,
            wallet,
            opts=TxOpts(skip_preflight=True, preflight_commitment="confirmed"),
        )
    except Exception as e:
        log(f"[JUPITER] Direct send failed: {e}", logging.ERROR)
        return None


# ── Main execution ────────────────────────────────────────────────────────────

async def execute_jupiter_swap(
    route:   dict,
    retries: int   = 3,
    delay:   float = 1.0,
) -> Optional[dict]:
    """
    Execute a Jupiter swap.

    PRACTICE_MODE  → direct RPC (no Jito tip wasted on sim trades)
    LIVE MODE      → Jito bundle first, falls back to direct RPC if Jito fails

    Returns the RPC/bundle result dict on success, None on failure.
    """
    # Build the transaction
    tx_bytes = None
    for attempt in range(1, retries + 1):
        tx_bytes = await _build_swap_transaction(route)
        if tx_bytes:
            break
        log(f"[JUPITER] Build attempt {attempt} failed.", logging.WARNING)
        if attempt < retries:
            await asyncio.sleep(delay)

    if not tx_bytes:
        log("[JUPITER] Could not build swap transaction.", logging.ERROR)
        return None

    # Practice mode — direct RPC, no Jito
    if config.PRACTICE_MODE:
        log("[JUPITER] Practice mode — sending direct (no Jito).")
        result = _send_direct(tx_bytes)
        return result

    # Live mode — try Jito first
    log(f"[JITO] Submitting bundle (tip: {JITO_TIP_LAMPORTS} lamports)…")
    bundle_id = await submit_bundle(tx_bytes)

    if bundle_id:
        landed = await wait_for_bundle(bundle_id, timeout_seconds=30)
        if landed:
            return {"result": bundle_id, "via": "jito"}
        else:
            log("[JITO] Bundle did not land — falling back to direct RPC.", logging.WARNING)

    # Jito fallback — direct RPC
    log("[JUPITER] Sending via direct RPC (Jito fallback).")
    result = _send_direct(tx_bytes)
    if result:
        result["via"] = "direct_rpc"
    return result
