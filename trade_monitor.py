import asyncio
import json
import logging
from solana.rpc.api import Client
from solana.publickey import PublicKey
from copy_engine import execute_trade
import os

# ✅ Live RPC endpoint using your Helius API key
RPC_URL = os.getenv("HELIUS_RPC_URL")
MONITORED_FILE = "monitored_wallets.json"
SLOT_HISTORY = {}  # Prevent re-processing

client = Client(RPC_URL)

logging.basicConfig(level=logging.INFO)

def load_wallets():
    try:
        with open(MONITORED_FILE, "r") as f:
            data = json.load(f)
            wallets = [entry["wallet"] for entry in data]
            logging.info(f"✅ Loaded {len(wallets)} wallets")
            return wallets
    except Exception as e:
        logging.error(f"Error loading wallets: {e}")
        return []

def get_recent_signatures(wallet, limit=2):
    try:
        res = client.get_signatures_for_address(PublicKey(wallet), limit=limit)
        if "result" in res and res["result"]:
            return res["result"]
        elif "result" in res and not res["result"]:
            logging.info(f"🕓 No new trades for {wallet} (empty result)")
            return []
        else:
            logging.warning(f"⚠️ Unexpected response for {wallet}: {res}")
            return []
    except Exception as e:
        logging.error(f"❌ Signature fetch error for {wallet}: {e}")
        return []

def get_transaction(signature):
    try:
        res = client.get_transaction(signature, encoding="jsonParsed")
        return res.get("result", None)
    except Exception as e:
        logging.error(f"Error getting tx {signature}: {e}")
        return None

def detect_swap(tx, wallet):
    if not tx or not tx.get("meta"):
        return None

    instructions = tx.get("transaction", {}).get("message", {}).get("instructions", [])
    pre_token_balances = tx["meta"].get("preTokenBalances", [])
    post_token_balances = tx["meta"].get("postTokenBalances", [])

    tokens_in = [bal.get("mint") for bal in pre_token_balances if bal.get("owner") == wallet]
    tokens_out = [bal.get("mint") for bal in post_token_balances if bal.get("owner") == wallet]

    if tokens_in and tokens_out and tokens_in != tokens_out:
        return {
            "wallet": wallet,
            "signature": tx["transaction"].get("signatures", [None])[0],
            "slot": tx["slot"],
            "token_in": tokens_in[0],
            "token_out": tokens_out[0],
            "platform": detect_platform(instructions)
        }
    return None

def detect_platform(instructions):
    for ix in instructions:
        pid = ix.get("programId")
        if pid == "JUP4Fb2cqiRUcaTHdrPC8h2gNsA2ETXiPDD33WcGuJB":
            return "Jupiter"
        if pid == "9WnQKiXBNW3TqkASwVC61VDiS7FfY9iQdmjYUsRPG7nP":
            return "Orca"
        if pid == "RVKd61ztZW9jqhDDP1LrL6KSMpGQfq9s8qkQSfH9nY6":
            return "Raydium"
    return "Unknown"

async def monitor_loop():
    wallets = load_wallets()
    if not wallets:
        logging.error("❌ No wallets loaded.")
        return

    logging.info(f"🔍 Monitoring {len(wallets)} wallets...")

    while True:
        for wallet in wallets:
            signatures = get_recent_signatures(wallet, limit=2)
            for sig in signatures:
                signature = sig.get("signature")
                slot = sig.get("slot")

                if not signature or (wallet, slot) in SLOT_HISTORY:
                    continue

                tx = get_transaction(signature)
                trade = detect_swap(tx, wallet)

                if trade:
                    logging.info(f"🟢 Trade Detected: {trade}")
                    await execute_trade(trade)

                SLOT_HISTORY[(wallet, slot)] = True
                await asyncio.sleep(0.25)

        await asyncio.sleep(10)

if __name__ == "__main__":
    try:
        asyncio.run(monitor_loop())
    except KeyboardInterrupt:
        logging.info("🛑 Monitor stopped by user.")
