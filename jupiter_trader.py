import requests
import json
import base64
import aiohttp
import asyncio
from solana.rpc.api import Client
from solana.transaction import Transaction
from solana.keypair import Keypair
from solana.rpc.types import TxOpts
import config
import os
import logging
from utils import log

client = Client(config.RPC_URL)
wallet = Keypair.from_secret_key(base64.b64decode(config.USER_WALLET_PRIVATE_KEY))


async def fetch_jupiter_swap_route(input_mint, output_mint, amount):
    url = "https://quote-api.jup.ag/v6/quote"
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount),
        "slippageBps": int(config.TRADE_SLIPPAGE * 10000),
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                return data["data"][0]
    return None


async def execute_jupiter_swap(route, retries: int = 3, delay: float = 1.0):
    url = "https://quote-api.jup.ag/v6/swap"
    payload = {
        "route": route,
        "userPublicKey": str(wallet.public_key),
        "wrapUnwrapSOL": True,
        "feeAccount": None,
        "asLegacyTransaction": True,
    }

    swap_data = None
    for attempt in range(1, retries + 1):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        swap_data = await response.json()
                        break
                    log(
                        f"[Jupiter] Swap prep failed with status {response.status} (attempt {attempt})",
                        logging.ERROR,
                    )
        except Exception as exc:
            log(
                f"[Jupiter] Swap request error on attempt {attempt}: {exc}",
                logging.ERROR,
            )

        if attempt < retries:
            await asyncio.sleep(delay)

    if not swap_data:
        log("[Jupiter] Exhausted swap retries", logging.ERROR)
        return None

    try:
        tx_encoded = swap_data["swapTransaction"]
        tx = Transaction.deserialize(base64.b64decode(tx_encoded))
        tx.sign(wallet)
        return client.send_transaction(
            tx,
            wallet,
            opts=TxOpts(skip_preflight=True, preflight_commitment="confirmed"),
        )
    except Exception as exc:
        log(f"[Jupiter] Transaction send failed: {exc}", logging.ERROR)
        return None
