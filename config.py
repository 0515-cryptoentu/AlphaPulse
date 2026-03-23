"""Central configuration management.

This module exposes a :class:`Config` dataclass which loads settings from
environment variables, optional ``.env`` files and command-line overrides.
It validates that required variables are present so importing modules can rely
on them being available.

Change from original: CONFIG is loaded safely so that importing this module
during tests (or without a .env) does not crash the process.
"""

from __future__ import annotations

import argparse
import logging
import os
from dataclasses import dataclass, field
from typing import Iterable, Optional, Dict


def _load_dotenv(path: str = ".env") -> None:
    """Populate ``os.environ`` with variables from a ``.env`` file.

    The implementation is intentionally lightweight to avoid introducing an
    additional dependency. Existing environment variables are left untouched.
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
    """Load secret values from HashiCorp Vault if configuration is present.

    When Vault configuration is supplied all mandatory secrets must be
    available either in the current ``env`` or inside the Vault payload. An
    :class:`EnvironmentError` is raised if any are missing.
    """
    addr = env.get("VAULT_ADDR")
    token = env.get("VAULT_TOKEN")
    secret_path = env.get("VAULT_SECRET_PATH")

    if not (addr and token and secret_path):
        return env

    try:
        import hvac
    except Exception:  # pragma: no cover - optional dependency
        raise EnvironmentError("hvac library required for Vault integration")

    client = hvac.Client(url=addr, token=token)
    if not client.is_authenticated():
        raise EnvironmentError("Vault authentication failed")

    try:
        secret = client.secrets.kv.v2.read_secret_version(path=secret_path)
    except Exception as exc:  # pragma: no cover - network errors
        raise EnvironmentError(f"Error loading Vault secret: {exc}")

    data = secret.get("data", {}).get("data", {})

    # Merge secrets, preferring already provided environment values
    env = {**data, **env}

    missing = []
    if not env.get("USER_WALLET_PRIVATE_KEY"):
        missing.append("USER_WALLET_PRIVATE_KEY")
    if not env.get("RPC_URL") and not env.get("HELIUS_RPC_URL"):
        missing.append("RPC_URL or HELIUS_RPC_URL")

    if missing:
        raise EnvironmentError(
            "Missing required Vault secrets: " + ", ".join(missing)
        )

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
    min_tx_count_lower: int = 1

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
            practice_mode=env.get("PRACTICE_MODE", "true").lower() != "false",
            cielo_api_key=env.get("CIELO_API_KEY"),
            twitter_api_key=env.get("TWITTER_API_KEY"),
            twitter_api_secret=env.get("TWITTER_API_SECRET"),
            twitter_access_token=env.get("TWITTER_ACCESS_TOKEN"),
            twitter_access_secret=env.get("TWITTER_ACCESS_SECRET"),
            google_credentials=env.get(
                "GOOGLE_CREDENTIALS", "google_credentials.json"
            ),
            min_tx_count_lower=int(env.get("MIN_TX_COUNT_LOWER", 1)),
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


# ---------------------------------------------------------------------------
# Safe module-level load — won't crash tests or partial environments
# ---------------------------------------------------------------------------

logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(message)s")

try:
    CONFIG = Config.load(argv=os.sys.argv[1:])
    logging.basicConfig(
        level=CONFIG.log_level,
        format="%(asctime)s %(levelname)s %(message)s",
        force=True,
    )
except EnvironmentError as _cfg_err:
    logging.warning(
        f"[CONFIG] Could not fully load config: {_cfg_err} — "
        "running in limited/test mode. Set required env vars to enable live trading."
    )
    CONFIG = Config()  # safe empty config for imports during tests / CI


# ---------------------------------------------------------------------------
# Backwards-compatible module-level constants (other modules import these)
# ---------------------------------------------------------------------------

PRACTICE_MODE            = CONFIG.practice_mode
TELEGRAM_BOT_TOKEN       = CONFIG.telegram_bot_token
USER_WALLET_PRIVATE_KEY  = CONFIG.user_wallet_private_key
RPC_URL                  = CONFIG.rpc_url or CONFIG.helius_rpc_url
HELIUS_RPC_URL           = CONFIG.helius_rpc_url
LOG_LEVEL                = CONFIG.log_level

# Static configuration used across modules
MONITORED_WALLETS = [
    "5fWkLJfoDsRAaXhPJcJY19qNtDDQ5h6q1SPzsAPRrUNG",
    "EdCNh8EzETJLFphW8yvdY7rDd8zBiyweiz8DU5gUUUka",
    "5CP6zv8a17mz91v6rMruVH6ziC5qAL8GFaJzwrX9Fvup",
]

MIN_BALANCE_SOL   = 0.1
TRADE_SLIPPAGE    = 0.005    # 0.5% — passed as bps to Jupiter (50 bps)
MIN_TX_COUNT_LOWER = CONFIG.min_tx_count_lower
