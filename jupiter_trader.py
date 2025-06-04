import requests
import json
import base64
import aiohttp
from solana.rpc.api import Client
from solana.transaction import Transaction
from solana.keypair import Keypair
from solana.rpc.types import TxOpts
import config
import os

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


async def execute_jupiter_swap(route):
    url = "https://quote-api.jup.ag/v6/swap"
    payload = {
        "route": route,
        "userPublicKey": str(wallet.public_key),
        "wrapUnwrapSOL": True,
        "feeAccount": None,
        "asLegacyTransaction": True,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as response:
            if response.status != 200:
                print("Swap preparation failed.")
                return None
            swap_data = await response.json()

    tx_encoded = swap_data["swapTransaction"]
    tx = Transaction.deserialize(base64.b64decode(tx_encoded))
    tx.sign(wallet)
    return client.send_transaction(
        tx, wallet, opts=TxOpts(skip_preflight=True, preflight_commitment="confirmed")
    )
