import asyncio
import aiohttp
import re
import json
from solana.rpc.api import Client
from solana.publickey import PublicKey
import tweepy
import os

# Set up Solana RPC client
RPC_URL = os.getenv("HELIUS_RPC_URL")
client = Client(RPC_URL)

# Cielo API URL and key
CIELO_API = "https://feed-api.cielo.finance/api/v1/feed"
API_KEY = os.getenv("CIELO_API_KEY")
WHALETRACKER_API = "https://whaletracker.xyz/api/topwallets"
MIN_TX_COUNT = 3
MAX_AVG_INTERVAL = 3600 * 6  # 6 hours

# Twitter API credentials (Replace these with your actual credentials)
API_KEY_TWITTER = os.getenv("TWITTER_API_KEY")
API_SECRET_KEY_TWITTER = os.getenv("TWITTER_API_SECRET")
ACCESS_TOKEN_TWITTER = os.getenv("TWITTER_ACCESS_TOKEN")
ACCESS_TOKEN_SECRET_TWITTER = os.getenv("TWITTER_ACCESS_SECRET")

# Twitter API Authentication using Tweepy
auth = tweepy.OAuth1UserHandler(
    consumer_key=API_KEY_TWITTER,
    consumer_secret=API_SECRET_KEY_TWITTER,
    access_token=ACCESS_TOKEN_TWITTER,
    access_token_secret=ACCESS_TOKEN_SECRET_TWITTER,
)
api = tweepy.API(auth)

# Targeted crypto Twitter accounts
CRYPTO_ACCOUNTS = [
    "JacobCryptoBury",
    "MarkKellyCrypto",
    "Bluntz",
    "Pentoshi",
    "CrediBullCrypto",
    "DonAlt",
    "CryptoCred",
    "CryptoChase",
    "ColdBloodedShiller",
    "NinjaScalp",
    "CryptoLouca",
]


# Function to get transaction metrics for a wallet
def get_tx_metrics(wallet):
    try:
        res = client.get_signatures_for_address(wallet, limit=20)
        signatures = res.get("result", [])
        timestamps = [
            sig.get("blockTime") for sig in signatures if sig.get("blockTime")
        ]
        if len(timestamps) < 2:
            return 0, -1
        timestamps.sort(reverse=True)
        intervals = [
            timestamps[i] - timestamps[i + 1] for i in range(len(timestamps) - 1)
        ]
        avg_interval = sum(intervals) / len(intervals) if intervals else -1
        return len(signatures), avg_interval
    except Exception as e:
        print(f"Error in get_tx_metrics: {e}")
        return 0, -1


# Function to add valid wallets to the list
def add_wallet(wallets, wallet, source):
    if re.match(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$", wallet):
        tx_count, avg = get_tx_metrics(wallet)
        if tx_count >= MIN_TX_COUNT and (avg < MAX_AVG_INTERVAL and avg > 0):
            wallets.append(
                {
                    "wallet": wallet,
                    "source": source,
                    "tx_count": tx_count,
                    "avg_interval": avg,
                }
            )


# Fetch wallets from the Cielo Feed API
async def fetch_wallets_from_cielo(session, wallet, limit=10):
    wallets = []
    params = {
        "wallet": wallet,
        "limit": limit,
        "chains": "solana",  # Filter by Solana chain
        "txTypes": "swap,transfer",  # Add more tx types as needed
        "newTrades": "true",
    }

    # Headers to authenticate the API request
    headers = {
        "User-Agent": "SolanaCopyTraderBot/1.0 (https://yourwebsite.com)",  # Modify with your actual bot info
        "Accept": "application/json",
        "Authorization": f"Bearer {API_KEY}",  # API key for Cielo API authentication
    }

    try:
        async with session.get(CIELO_API, params=params, headers=headers) as response:
            if response.status != 200:
                print(f"⚠️ Cielo API error: {response.status}, URL: {CIELO_API}")
                return wallets
            data = await response.json()
            if "data" in data:
                for item in data["data"]:
                    wallet = item.get("wallet")
                    if wallet:
                        add_wallet(wallets, wallet, "cielo")
    except Exception as e:
        print(f"⚠️ Failed Cielo scrape: {e}")
    return wallets


# Function to scrape wallets from WhaleTracker API
async def fetch_wallets_from_whaletracker(session):
    wallets = []
    try:
        async with session.get(WHALETRACKER_API) as response:
            if response.status != 200:
                print(f"⚠️ WhaleTracker API error: {response.status}")
                return wallets
            data = await response.json()
            for entry in data.get("wallets", [])[:20]:
                add_wallet(wallets, entry.get("address"), "whaletracker")
    except Exception as e:
        print(f"⚠️ Failed WhaleTracker scrape: {e}")
    return wallets


# Function to scrape wallets from Twitter API
async def fetch_wallets_from_twitter(session):
    wallets = []
    for account in CRYPTO_ACCOUNTS:
        print(f"🔍 Scraping {account}'s tweets...")
        try:
            # Fetch tweets from the user
            tweets = api.user_timeline(
                screen_name=account, count=100, tweet_mode="extended"
            )
            for tweet in tweets:
                found = re.findall(r"[1-9A-HJ-NP-Za-km-z]{32,44}", tweet.full_text)
                for addr in found:
                    add_wallet(wallets, addr, f"twitter:{account}")
        except Exception as e:
            print(f"⚠️ Failed Twitter scrape: {account}, Error: {e}")
    return wallets


# Main function to scrape all wallets from the three sources (Cielo, WhaleTracker, Twitter)
async def scrape_all_wallets(wallet_list):
    async with aiohttp.ClientSession() as session:
        tasks = []
        for wallet in wallet_list:
            tasks.append(fetch_wallets_from_cielo(session, wallet))
            tasks.append(fetch_wallets_from_whaletracker(session))
            tasks.append(fetch_wallets_from_twitter(session))
        wallets = await asyncio.gather(*tasks)
        return [wallet for sublist in wallets for wallet in sublist]


# Function to export the wallets to JSON file
def export_json(wallets):
    unique_wallets = {w["wallet"]: w for w in wallets}.values()
    with open("monitored_wallets.json", "w") as f:
        json.dump(list(unique_wallets), f, indent=2)
    print(f"✅ Exported {len(unique_wallets)} wallets to monitored_wallets.json")


if __name__ == "__main__":
    wallet_list = [
        "9djU9o4CD14ak5G4TNLp1KvqbWZ4BptU6WyquvDjWYJz",
        "FjYFNY2KXwRbDMEiEdxAF3uCWJTL5sCHwMGR6ZaSkbtu",
    ]  # Sample wallets
    all_wallets = asyncio.run(scrape_all_wallets(wallet_list))
    if not all_wallets:
        print("🔁 Adding known good backup wallets...")
        fallback_wallets = [
            ("9djU9o4CD14ak5G4TNLp1KvqbWZ4BptU6WyquvDjWYJz", "known_trader"),
            ("FjYFNY2KXwRbDMEiEdxAF3uCWJTL5sCHwMGR6ZaSkbtu", "jito_whale"),
            ("5hFZ9vbK9gXx1NSeYZi1o9nPjLkgzBnJjqVXbVWuTbW", "dex_god"),
        ]
        for wallet, src in fallback_wallets:
            add_wallet(all_wallets, wallet, src)
    export_json(all_wallets)
    print("✅ Scraping complete. Run wallet_curator.py to update stats.")
