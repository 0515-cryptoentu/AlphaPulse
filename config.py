import os
import logging

# Basic logging configuration.  Modules obtain loggers via ``logging.getLogger``.
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)

PRACTICE_MODE = True
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
USER_WALLET_PRIVATE_KEY = os.getenv("USER_WALLET_PRIVATE_KEY")
RPC_URL = os.getenv("RPC_URL")

# Validate required environment variables early so modules importing this
# configuration fail fast with a helpful message.  Only the RPC endpoint and
# private key are strictly required for the bot to function.
_required = {
    "RPC_URL": RPC_URL,
    "USER_WALLET_PRIVATE_KEY": USER_WALLET_PRIVATE_KEY,
}
_missing = [name for name, value in _required.items() if not value]
if _missing:
    missing = ", ".join(_missing)
    raise EnvironmentError(
        f"Missing required environment variables: {missing}. Check your .env configuration."
    )
MONITORED_WALLETS = [
    "5fWkLJfoDsRAaXhPJcJY19qNtDDQ5h6q1SPzsAPRrUNG",
    "EdCNh8EzETJLFphW8yvdY7rDd8zBiyweiz8DU5gUUUka",
    "5CP6zv8a17mz91v6rMruVH6ziC5qAL8GFaJzwrX9Fvup",
]
MIN_BALANCE_SOL = 0.1
TRADE_SLIPPAGE = 0.005
