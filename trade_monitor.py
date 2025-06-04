import asyncio
import json
import logging
from solana.rpc.api import Client
try:
    from solana.publickey import PublicKey
except Exception:  # pragma: no cover - compatibility with newer solana-py
    from solders.pubkey import Pubkey as PublicKey
import websockets
from copy_engine import execute_trade
from datetime import datetime
import config

# RPC endpoint configured via unified ``config``
MONITORED_FILE = "monitored_wallets.json"
SLOT_HISTORY = {}  # Prevent re-processing

client = Client(config.HELIUS_RPC_URL or config.RPC_URL)

logging.basicConfig(level=logging.INFO)

# Heartbeat file updated on every successful monitoring iteration
HEARTBEAT_FILE = "monitor_heartbeat.txt"


def record_heartbeat() -> None:
    """Write the current UTC timestamp to ``HEARTBEAT_FILE``."""
    try:
        with open(HEARTBEAT_FILE, "w") as f:
            f.write(datetime.utcnow().isoformat())
    except Exception as exc:
        logging.error(f"Failed to write heartbeat: {exc}")


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

    tokens_in = [
        bal.get("mint") for bal in pre_token_balances if bal.get("owner") == wallet
    ]
    tokens_out = [
        bal.get("mint") for bal in post_token_balances if bal.get("owner") == wallet
    ]

    if tokens_in and tokens_out and tokens_in != tokens_out:
        return {
            "wallet": wallet,
            "signature": tx["transaction"].get("signatures", [None])[0],
            "slot": tx["slot"],
            "token_in": tokens_in[0],
            "token_out": tokens_out[0],
            "platform": detect_platform(instructions),
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


async def _poll_wallets(wallets):
    """Fallback polling implementation."""
    while True:
        record_heartbeat()
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


async def _websocket_wallets(wallets, retries: int = 3, delay: float = 1.0) -> bool:
    """Attempt monitoring via WebSocket. Returns True on success."""
    ws_url = (config.HELIUS_RPC_URL or config.RPC_URL).replace("https://", "wss://").replace("http://", "ws://")
    for attempt in range(1, retries + 1):
        request_map = {}
        sub_map = {}
        req_id = 1
        try:
            async with websockets.connect(ws_url) as ws:
                for wallet in wallets:
                    params = [{"mentions": [wallet]}, {"commitment": "confirmed"}]
                    await ws.send(
                        json.dumps({"jsonrpc": "2.0", "id": req_id, "method": "logsSubscribe", "params": params})
                    )
                    request_map[req_id] = wallet
                    req_id += 1

                while len(sub_map) < len(request_map):
                    data = json.loads(await ws.recv())
                    if "id" in data and data.get("result") is not None:
                        wallet = request_map.pop(data["id"], None)
                        if wallet:
                            sub_map[data["result"]] = wallet

                logging.info("🔗 WebSocket subscriptions established")

                while True:
                    record_heartbeat()
                    message = json.loads(await ws.recv())
                    if message.get("method") != "logsNotification":
                        continue
                    params = message.get("params", {})
                    result = params.get("result", {})
                    sub_id = params.get("subscription")
                    wallet = sub_map.get(sub_id)
                    if not wallet:
                        continue
                    signature = result.get("signature")
                    slot = result.get("context", {}).get("slot")
                    if not signature or (wallet, slot) in SLOT_HISTORY:
                        continue

                    tx = get_transaction(signature)
                    trade = detect_swap(tx, wallet)
                    if trade:
                        logging.info(f"🟢 Trade Detected: {trade}")
                        await execute_trade(trade)

                    record_heartbeat()

                    SLOT_HISTORY[(wallet, slot)] = True
                    await asyncio.sleep(0.25)
        except Exception as exc:  # pragma: no cover - network dependent
            logging.warning(f"WebSocket attempt {attempt} failed: {exc}")
            if attempt < retries:
                await asyncio.sleep(delay)
                continue
            logging.error("WebSocket retries exhausted")
            return False
    return True


async def monitor_loop():
    wallets = load_wallets()
    if not wallets:
        logging.error("❌ No wallets loaded.")
        return

    logging.info(f"🔍 Monitoring {len(wallets)} wallets...")

    if not await _websocket_wallets(wallets):
        logging.info("ℹ️ Falling back to polling mode")
        await _poll_wallets(wallets)


async def supervisor_loop(delay: float = 5.0, max_restarts: int | None = None) -> None:
    """Restart ``monitor_loop`` if it exits with an error."""
    restarts = 0
    while max_restarts is None or restarts < max_restarts:
        try:
            await monitor_loop()
        except Exception as exc:  # pragma: no cover - runtime safety
            logging.error(f"Monitor crashed: {exc}")
        restarts += 1
        logging.info(f"Restarting monitor in {delay} seconds")
        await asyncio.sleep(delay)


if __name__ == "__main__":
    try:
        asyncio.run(supervisor_loop())
    except KeyboardInterrupt:
        logging.info("🛑 Monitor stopped by user.")
