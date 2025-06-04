import requests
import sqlite3
import json
import time
from datetime import datetime, timedelta

DB_FILE = "wallets.db"
JSON_OUTPUT = "monitored_wallets.json"
MAX_WALLETS = 10
TRADE_LOOKBACK_HOURS = 168
MIN_TRADES = 1
MAX_TRADES = 5

SEED_WALLETS = [
    "58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwM2DDvtMb",  # Orca Pool
    "6bZkR29YrWmM2y2pU3uUGj2ozpygV3xKyNdLzX51qz9V",  # Step leaderboard
    "4hDd8FvZ9gKY1XExB4FDoR4Z6ikVb19NvhR6yyHCUdKH",  # Raydium trader
    "7Fn94ozxS5fRPcYXvdcBqUwUjVDz7oLZwhTnAUhmUedT",  # BONK swing trader
    "9EVpHswYDFLStKzJmkKa3XeL7BDroS3X7vBMwV3G7wvx",  # Active Jupiter user
    "5NyLkz3zXbHNkR7EY9VrgTeBdMi4TT4GRkHkwZKicBCa",  # DeFi multisig user
    "HHN2h9JcuF1KDN6BC64tFqcyZYv2Vv7fyjFXZm8PhsXc",  # NFT + memecoin hybrid
    "AYAsU3rSKZVxVZ1Y1PqQoBNcpQrPMnKi7R7uUoCjqKxz",  # LP provider
    "47baTfkaTx82Db5emUiB9b57HcLu8RhXqdfvZYKPLcdm",  # Meme coin holder/trader
    "26zKDJcsHZ6RQvJP6Thq6KMo88cavFLiVvbK8khLKH9F",  # Staking pool user
]


def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS wallets (
            wallet TEXT PRIMARY KEY,
            tx_count INTEGER,
            token_count INTEGER,
            last_active INTEGER,
            score REAL
        )
    """
    )
    conn.commit()
    conn.close()


def fetch_transactions(wallet):
    url = (
        f"https://public-api.solscan.io/account/transactions?account={wallet}&limit=25"
    )
    try:
        res = requests.get(url)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        print(f"Error fetching tx for {wallet}: {e}")
    return []


def analyze_wallet(wallet):
    txs = fetch_transactions(wallet)
    if not txs:
        return None

    recent_txs = [
        tx
        for tx in txs
        if "blockTime" in tx
        and tx["blockTime"] > (time.time() - TRADE_LOOKBACK_HOURS * 3600)
    ]

    if len(recent_txs) == 0:
        return None

    tokens = set()
    last_active = 0

    for tx in recent_txs:
        block_time = tx.get("blockTime", 0)
        if block_time > last_active:
            last_active = block_time
        for transfer in tx.get("tokenTransfers", []):
            token = transfer.get("tokenAddress")
            if token:
                tokens.add(token)

    score = (
        len(recent_txs) * 0.5
        + len(tokens) * 0.4
        + (1 if last_active > time.time() - 86400 else 0) * 0.1
    ) * 10

    return {
        "wallet": wallet,
        "tx_count": len(recent_txs),
        "token_count": len(tokens),
        "last_active": last_active,
        "score": score,
    }


def store_wallets(data_list):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    for w in data_list:
        c.execute(
            """
            INSERT OR REPLACE INTO wallets (wallet, tx_count, token_count, last_active, score)
            VALUES (?, ?, ?, ?, ?)
        """,
            (
                w["wallet"],
                w["tx_count"],
                w["token_count"],
                w["last_active"],
                w["score"],
            ),
        )
    conn.commit()
    conn.close()


def get_top_wallets():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        """
        SELECT wallet, score, tx_count, token_count, last_active FROM wallets
        ORDER BY score DESC
        LIMIT ?
    """,
        (MAX_WALLETS,),
    )
    rows = c.fetchall()
    conn.close()
    return [
        {
            "wallet": row[0],
            "score": row[1],
            "tx_count": row[2],
            "token_count": row[3],
            "last_active": row[4],
        }
        for row in rows
    ]


def export_to_json(wallets):
    with open(JSON_OUTPUT, "w") as f:
        json.dump(wallets, f, indent=2)
    print(f"✅ Exported top {len(wallets)} wallets to {JSON_OUTPUT}")


def run_discovery():
    init_db()
    results = []

    print("🔍 Scanning seed wallets...")
    for wallet in SEED_WALLETS:
        data = analyze_wallet(wallet)
        if data:
            print(f"✅ {wallet} - Score: {data['score']:.2f}")
            results.append(data)
        time.sleep(1)

    store_wallets(results)
    top = get_top_wallets()
    export_to_json(top)


if __name__ == "__main__":
    run_discovery()
