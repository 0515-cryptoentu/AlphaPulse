"""
jito_client.py — Jito bundle submission for MEV/sandwich protection.

How Jito works:
  Normal Solana tx: broadcast to mempool → visible to bots → sandwiched.
  Jito bundle:      sent directly to a block builder → never hits mempool
                    → bots cannot see or front-run it.

This module wraps the Jito block engine API. A "bundle" is 1–5 transactions
submitted atomically. We use single-tx bundles — one swap per bundle.

Jito charges a small tip (we use 0.001 SOL = 100_000 lamports by default).
This tip goes to the validator. It's cheap insurance against sandwich attacks
which can cost 1–5% of your trade value.

Jito block engine endpoints (use the one closest to your RPC region):
  mainnet:  https://mainnet.block-engine.jito.wtf
  amsterdam: https://amsterdam.mainnet.block-engine.jito.wtf
  frankfurt: https://frankfurt.mainnet.block-engine.jito.wtf
  ny:        https://ny.mainnet.block-engine.jito.wtf
  tokyo:     https://tokyo.mainnet.block-engine.jito.wtf

Set JITO_BLOCK_ENGINE_URL in your .env to pick the closest one.
Default is mainnet (auto-routes).
"""

import asyncio
import base64
import logging
import os
import time
from typing import Optional

import aiohttp

from utils import log

# ── Config ────────────────────────────────────────────────────────────────────
JITO_BLOCK_ENGINE_URL = os.getenv(
    "JITO_BLOCK_ENGINE_URL",
    "https://mainnet.block-engine.jito.wtf",
)

# Tip amount in lamports (0.001 SOL = 100_000 lamports)
# Higher tip = higher priority in the block. Don't go below 10_000.
JITO_TIP_LAMPORTS = int(os.getenv("JITO_TIP_LAMPORTS", "100000"))

# Jito tip accounts — these are the official tip collection addresses.
# Jito randomly selects one per bundle. We pick one at submission time.
JITO_TIP_ACCOUNTS = [
    "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5",
    "HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe",
    "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY",
    "ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49",
    "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh",
    "ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt",
    "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL",
    "3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT",
]

import random
def _pick_tip_account() -> str:
    return random.choice(JITO_TIP_ACCOUNTS)


# ── Core submission ───────────────────────────────────────────────────────────

async def submit_bundle(
    serialized_tx: bytes,
    retries: int = 3,
    delay: float = 0.5,
) -> Optional[str]:
    """
    Submit a single transaction as a Jito bundle.

    serialized_tx — raw signed transaction bytes (before base64 encoding)

    Returns the bundle UUID on success, None on failure.

    The bundle UUID can be used to check confirmation status via
    /api/v1/bundles (not implemented here — we rely on normal tx confirmation).
    """
    encoded = base64.b64encode(serialized_tx).decode("utf-8")

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "sendBundle",
        "params": [[encoded]],
    }

    url = f"{JITO_BLOCK_ENGINE_URL}/api/v1/bundles"

    for attempt in range(1, retries + 1):
        try:
            timeout = aiohttp.ClientTimeout(total=8)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                ) as resp:
                    data = await resp.json()

                    if "result" in data:
                        bundle_id = data["result"]
                        log(f"[JITO] Bundle submitted: {bundle_id[:16]}…")
                        return bundle_id

                    error = data.get("error", {})
                    log(
                        f"[JITO] Bundle rejected (attempt {attempt}): "
                        f"{error.get('message', 'unknown error')}",
                        logging.WARNING,
                    )

        except Exception as e:
            log(f"[JITO] Submission error (attempt {attempt}): {e}", logging.WARNING)

        if attempt < retries:
            await asyncio.sleep(delay)

    log("[JITO] All bundle submission attempts failed.", logging.ERROR)
    return None


async def get_bundle_status(bundle_id: str) -> Optional[str]:
    """
    Poll Jito for bundle confirmation status.
    Returns one of: 'Invalid', 'Pending', 'Failed', 'Landed' — or None on error.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getBundleStatuses",
        "params": [[bundle_id]],
    }
    url = f"{JITO_BLOCK_ENGINE_URL}/api/v1/bundles"

    try:
        timeout = aiohttp.ClientTimeout(total=6)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as resp:
                data  = await resp.json()
                value = data.get("result", {}).get("value", [])
                if value:
                    return value[0].get("confirmation_status")
    except Exception as e:
        log(f"[JITO] Status check error: {e}", logging.WARNING)

    return None


async def wait_for_bundle(
    bundle_id: str,
    timeout_seconds: int = 30,
    poll_interval: float = 2.0,
) -> bool:
    """
    Poll until bundle lands or times out.
    Returns True if landed, False otherwise.
    """
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        status = await get_bundle_status(bundle_id)
        if status == "Landed":
            log(f"[JITO] Bundle {bundle_id[:16]}… landed.")
            return True
        if status in ("Failed", "Invalid"):
            log(f"[JITO] Bundle {bundle_id[:16]}… {status}.")
            return False
        await asyncio.sleep(poll_interval)

    log(f"[JITO] Bundle {bundle_id[:16]}… timed out after {timeout_seconds}s.")
    return False
