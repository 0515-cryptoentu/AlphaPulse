import sqlite3
import time
from solana.rpc.api import Client
from solana.publickey import PublicKey
import config
import logging
from utils import log

WALLET_DB = "wallet_repository.db"

client = Client(config.HELIUS_RPC_URL or config.RPC_URL)


def init_db():
    conn = sqlite3.connect(WALLET_DB)
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS wallets (
            wallet TEXT PRIMARY KEY,
            source TEXT,
            last_seen INTEGER,
            tx_count INTEGER,
            avg_tx_interval REAL,
            is_active INTEGER DEFAULT 1,
            notes TEXT
        )
    """
    )
    conn.commit()
    conn.close()


def calculate_roi(wallet):
    # Placeholder for ROI calculation based on wallet's trading history
    # In a real scenario, you would fetch past buy/sell data and calculate ROI
    return 0.05  # Dummy ROI for now


def get_recent_activity(wallet):
    try:
        res = client.get_signatures_for_address(PublicKey(wallet), limit=20)
        if res is None or "result" not in res:
            log(f"❌ Helius RPC failed for {wallet}: {res}", logging.ERROR)
            return 0, -1

        signatures = res.get("result", [])
        if not signatures:
            log(f"⚠️ No transactions found for {wallet}", logging.WARNING)
            return 0, -1

        timestamps = [sig["blockTime"] for sig in signatures if sig.get("blockTime")]
        if len(timestamps) < 2:
            log(f"⚠️ Not enough timestamps for {wallet}", logging.WARNING)
            return len(timestamps), -1

        timestamps.sort(reverse=True)
        intervals = [
            timestamps[i] - timestamps[i + 1] for i in range(len(timestamps) - 1)
        ]
        avg_interval = sum(intervals) / len(intervals) if intervals else -1

        roi = calculate_roi(wallet)

        log(
            f"🟢 {wallet} | tx_count: {len(signatures)}, avg_interval: {avg_interval:.1f} sec, ROI: {roi:.2f}",
            logging.INFO,
        )
        return len(signatures), avg_interval

    except Exception as e:
        import traceback

        log(f"❌ Error checking {wallet}: {e}", logging.ERROR)
        traceback.print_exc()
        return 0, -1


def update_wallet_stats():
    init_db()
    conn = sqlite3.connect(WALLET_DB)
    c = conn.cursor()
    c.execute("SELECT wallet FROM wallets WHERE is_active = 1")
    rows = c.fetchall()
    for row in rows:
        wallet = row[0]
        tx_count, avg_interval = get_recent_activity(wallet)

        if tx_count > 0 and avg_interval > 0:
            c.execute(
                """UPDATE wallets SET tx_count = ?, avg_tx_interval = ?, last_seen = ? WHERE wallet = ?""",
                (tx_count, avg_interval, int(time.time()), wallet),
            )
    conn.commit()
    conn.close()
