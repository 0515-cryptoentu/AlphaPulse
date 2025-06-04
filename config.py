"""Central configuration management.

This module exposes a :class:`Config` dataclass which loads settings from
environment variables, optional ``.env`` files and command–line overrides.
It validates that required variables are present so importing modules can rely
on them being available.
"""

from __future__ import annotations

import argparse
import logging
import os
from dataclasses import dataclass
from typing import Iterable, Optional, Dict


def _load_dotenv(path: str = ".env") -> None:
    """Populate ``os.environ`` with variables from a ``.env`` file.

    The implementation is intentionally lightweight to avoid introducing an
    additional dependency.  Existing environment variables are left untouched.
    """

    if not os.path.exists(path):
        return

    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key, value)


def _load_from_vault(env: Dict[str, str]) -> Dict[str, str]:
    """Load secret values from HashiCorp Vault if configuration is present."""
    addr = env.get("VAULT_ADDR")
    token = env.get("VAULT_TOKEN")
    secret_path = env.get("VAULT_SECRET_PATH")
    if not (addr and token and secret_path):
        return env

    try:
        import hvac
    except Exception:  # pragma: no cover - optional dependency
        logging.warning("hvac library missing, skipping Vault secrets")
        return env

    client = hvac.Client(url=addr, token=token)
    if not client.is_authenticated():
        logging.error("Vault authentication failed")
        return env

    try:
        secret = client.secrets.kv.v2.read_secret_version(path=secret_path)
    except Exception as exc:  # pragma: no cover - network errors
        logging.error("Error loading Vault secret: %s", exc)
        return env

    data = secret.get("data", {}).get("data", {})
    for key, value in data.items():
        env.setdefault(key, value)

    return env


@dataclass
class Config:
    """Application configuration loaded from the environment."""

    telegram_bot_token: Optional[str] = None
    user_wallet_private_key: Optional[str] = None
    rpc_url: Optional[str] = None
    helius_rpc_url: Optional[str] = None
    log_level: str = "INFO"
    practice_mode: bool = True
    cielo_api_key: Optional[str] = None
    twitter_api_key: Optional[str] = None
    twitter_api_secret: Optional[str] = None
    twitter_access_token: Optional[str] = None
    twitter_access_secret: Optional[str] = None
    google_credentials: str = "google_credentials.json"

    @classmethod
    def load(
        cls, argv: Optional[Iterable[str]] = None, *, dotenv_path: str = ".env"
    ) -> "Config":
        """Load configuration from environment and optional CLI overrides."""

        _load_dotenv(dotenv_path)

        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--telegram-bot-token")
        parser.add_argument("--user-wallet-private-key")
        parser.add_argument("--rpc-url")
        parser.add_argument("--helius-rpc-url")
        parser.add_argument("--log-level")
        args, _ = parser.parse_known_args(argv)

        env = os.environ.copy()
        env = _load_from_vault(env)
        if args.telegram_bot_token:
            env["TELEGRAM_BOT_TOKEN"] = args.telegram_bot_token
        if args.user_wallet_private_key:
            env["USER_WALLET_PRIVATE_KEY"] = args.user_wallet_private_key
        if args.rpc_url:
            env["RPC_URL"] = args.rpc_url
        if args.helius_rpc_url:
            env["HELIUS_RPC_URL"] = args.helius_rpc_url
        if args.log_level:
            env["LOG_LEVEL"] = args.log_level

        cfg = cls(
            telegram_bot_token=env.get("TELEGRAM_BOT_TOKEN"),
            user_wallet_private_key=env.get("USER_WALLET_PRIVATE_KEY"),
            rpc_url=env.get("RPC_URL"),
            helius_rpc_url=env.get("HELIUS_RPC_URL"),
            log_level=env.get("LOG_LEVEL", "INFO"),
            cielo_api_key=env.get("CIELO_API_KEY"),
            twitter_api_key=env.get("TWITTER_API_KEY"),
            twitter_api_secret=env.get("TWITTER_API_SECRET"),
            twitter_access_token=env.get("TWITTER_ACCESS_TOKEN"),
            twitter_access_secret=env.get("TWITTER_ACCESS_SECRET"),
            google_credentials=env.get(
                "GOOGLE_CREDENTIALS", "google_credentials.json"
            ),
        )

        cfg._validate()
        return cfg

    def _validate(self) -> None:
        """Ensure mandatory configuration values are present."""

        missing = []
        if not self.user_wallet_private_key:
            missing.append("USER_WALLET_PRIVATE_KEY")
        if not (self.rpc_url or self.helius_rpc_url):
            missing.append("RPC_URL or HELIUS_RPC_URL")

        if missing:
            raise EnvironmentError(
                "Missing required environment variables: " + ", ".join(missing)
            )


# Load configuration at import time so other modules can simply ``import
# config``.  ``sys.argv[1:]`` is passed so overrides can be supplied when running
# any module directly.
CONFIG = Config.load(argv=os.sys.argv[1:])

logging.basicConfig(level=CONFIG.log_level, format="%(asctime)s %(levelname)s %(message)s")

# Backwards compatible module-level constants ---------------------------------

PRACTICE_MODE = CONFIG.practice_mode
TELEGRAM_BOT_TOKEN = CONFIG.telegram_bot_token
USER_WALLET_PRIVATE_KEY = CONFIG.user_wallet_private_key
RPC_URL = CONFIG.rpc_url or CONFIG.helius_rpc_url
HELIUS_RPC_URL = CONFIG.helius_rpc_url
LOG_LEVEL = CONFIG.log_level

# Static configuration used across modules
MONITORED_WALLETS = [
    "5fWkLJfoDsRAaXhPJcJY19qNtDDQ5h6q1SPzsAPRrUNG",
    "EdCNh8EzETJLFphW8yvdY7rDd8zBiyweiz8DU5gUUUka",
    "5CP6zv8a17mz91v6rMruVH6ziC5qAL8GFaJzwrX9Fvup",
]
MIN_BALANCE_SOL = 0.1
TRADE_SLIPPAGE = 0.005
