import asyncio
import importlib
import os
from unittest.mock import patch
import pytest
pytest.importorskip("aiohttp")
pytest.importorskip("tweepy")
pytest.importorskip("solana.rpc.api")
pytest.importorskip("solana.publickey")


class MockResponse:
    def __init__(self, data):
        self.status = 200
        self._data = data

    async def json(self):
        return self._data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass


class MockSession:
    def __init__(self, data):
        self._resp = MockResponse(data)

    def get(self, *args, **kwargs):
        return self._resp


def test_fetch_wallets_from_cielo(monkeypatch):
    env = {
        "HELIUS_RPC_URL": "http://localhost:8899",
        "CIELO_API_KEY": "k",
        "TWITTER_API_KEY": "a",
        "TWITTER_API_SECRET": "b",
        "TWITTER_ACCESS_TOKEN": "c",
        "TWITTER_ACCESS_SECRET": "d",
    }
    with patch.dict(os.environ, env):
        wallet_scraper = importlib.import_module("wallet_scraper")
        importlib.reload(wallet_scraper)

    wallet = "9djU9o4CD14ak5G4TNLp1KvqbWZ4BptU6WyquvDjWYJz"
    session = MockSession({"data": [{"wallet": wallet}]})
    monkeypatch.setattr(wallet_scraper, "get_tx_metrics", lambda w: (5, 100))
    result = asyncio.run(wallet_scraper.fetch_wallets_from_cielo(session, wallet))
    assert result == [
        {"wallet": wallet, "source": "cielo", "tx_count": 5, "avg_interval": 100}
    ]
