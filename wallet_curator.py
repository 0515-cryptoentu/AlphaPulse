import sqlite3
import time
from solana.rpc.api import Client
from solana.publickey import PublicKey

RPC_URL = "https://mainnet.helius-rpc.com/?api-key=22d4c858-530c-4749-adfb-5ffaba4c7a70"
WALLET_DB = "wallet_repository.db"

client = Client(RPC_URL)

def init_db():
    conn = sqlite3.connect(WALLET_DB)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS wallets (
            wallet TEXT PRIMARY KEY,
            source TEXT,
            last_seen INTEGER,
            tx_count INTEGER,
            avg_tx_interval REAL,
            is_active INTEGER DEFAULT 1,
            notes TEXT
        )
    ''')
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
            print(f"❌ Helius RPC failed for {wallet}: {res}")
            return 0, -1

        signatures = res.get("result", [])
        if not signatures:
            print(f"⚠️ No transactions found for {wallet}")
            return 0, -1

        timestamps = [sig["blockTime"] for sig in signatures if sig.get("blockTime")]
        if len(timestamps) < 2:
            print(f"⚠️ Not enough timestamps for {wallet}")
            return len(timestamps), -1

        timestamps.sort(reverse=True)
        intervals = [timestamps[i] - timestamps[i+1] for i in range(len(timestamps)-1)]
        avg_interval = sum(intervals) / len(intervals) if intervals else -1

        roi = calculate_roi(wallet)

        print(f"🟢 {wallet} | tx_count: {len(signatures)}, avg_interval: {avg_interval:.1f} sec, ROI: {roi:.2f}")
        return len(signatures), avg_interval

    except Exception as e:
        import traceback
        print(f"❌ Error checking {wallet}: {e}")
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
            c.execute("""UPDATE wallets SET tx_count = ?, avg_tx_interval = ?, last_seen = ? WHERE wallet = ?""",
                      (tx_count, avg_interval, int(time.time()), wallet))
    conn.commit()
    conn.close()
