import sqlite3
import json

DB_PATH = "wallet_repository.db"
OUTPUT_FILE = "monitored_wallets.json"
MAX_WALLETS = 10
MIN_TX_COUNT = 1
MAX_AVG_INTERVAL = 3600 * 24  # 12 hours


def init_db():
    conn = sqlite3.connect(DB_PATH)
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


def export_top_wallets():
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        SELECT wallet, tx_count, avg_tx_interval, last_seen FROM wallets
        WHERE is_active = 1 AND tx_count >= ? AND avg_tx_interval > 0 AND avg_tx_interval < ?
        ORDER BY tx_count DESC, avg_tx_interval ASC
        LIMIT ?
    """,
        (MIN_TX_COUNT, MAX_AVG_INTERVAL, MAX_WALLETS),
    )
    rows = c.fetchall()
    conn.close()

    output = [
        {
            "wallet": row[0],
            "tx_count": row[1],
            "avg_interval": row[2],
            "last_active": row[3],
            "score": row[1] * 0.7 + (1 / row[2]) * 0.3 if row[2] > 0 else 0,
        }
        for row in rows
    ]

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"✅ Exported {len(output)} wallets to {OUTPUT_FILE}")


if __name__ == "__main__":
    export_top_wallets()
