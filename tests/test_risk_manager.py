import json
import asyncio
from unittest.mock import patch
import pytest
import os

os.environ.setdefault("USER_WALLET_PRIVATE_KEY", "0" * 64)
os.environ.setdefault("RPC_URL", "http://localhost")

pytest.importorskip("aiohttp")
pytest.importorskip("solana")

import risk_manager


def test_is_token_blacklisted(tmp_path):
    blacklist = tmp_path / "token_blacklist.txt"
    blacklist.write_text("TOKEN1\nTOKEN2\n")
    with patch.object(risk_manager, "BLACKLIST_FILE", str(blacklist)):
        assert risk_manager.is_token_blacklisted("TOKEN1")
        assert not risk_manager.is_token_blacklisted("OTHER")



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
        self._data = data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    def get(self, *args, **kwargs):
        return MockResponse(self._data)


def test_is_risky_token(monkeypatch, tmp_path):
    blacklist = tmp_path / "token_blacklist.txt"
    blacklist.write_text("")
    with patch.object(risk_manager, "BLACKLIST_FILE", str(blacklist)):
        monkeypatch.setattr(
            risk_manager.aiohttp,
            "ClientSession",
            lambda timeout=None: MockSession({"data": {"volume_usd_24h": 10000}}),
        )
        assert not asyncio.run(risk_manager.is_risky_token("TOKA"))

        monkeypatch.setattr(
            risk_manager.aiohttp,
            "ClientSession",
            lambda timeout=None: MockSession({"data": {"volume_usd_24h": 1}}),
        )
        assert asyncio.run(risk_manager.is_risky_token("TOKB"))


def test_is_risky_token_whitelist(monkeypatch, tmp_path):
    whitelist = tmp_path / "token_whitelist.txt"
    whitelist.write_text("TOKW\n")
    blacklist = tmp_path / "token_blacklist.txt"
    blacklist.write_text("TOKW\n")
    with patch.object(risk_manager, "WHITELIST_FILE", str(whitelist)), \
         patch.object(risk_manager, "BLACKLIST_FILE", str(blacklist)):
        monkeypatch.setattr(
            risk_manager.aiohttp,
            "ClientSession",
            lambda timeout=None: MockSession({"data": {"volume_usd_24h": 0}}),
        )
        assert not asyncio.run(risk_manager.is_risky_token("TOKW"))


def test_is_risky_token_position_limit(monkeypatch, tmp_path):
    whitelist = tmp_path / "token_whitelist.txt"
    whitelist.write_text("")
    with patch.object(risk_manager, "WHITELIST_FILE", str(whitelist)), \
         patch.object(risk_manager, "BLACKLIST_FILE", str(whitelist)):
        monkeypatch.setattr(
            risk_manager.aiohttp,
            "ClientSession",
            lambda timeout=None: MockSession({"data": {"volume_usd_24h": 10000}}),
        )
        monkeypatch.setattr(
            risk_manager.auto_sell,
            "portfolio",
            {f"T{i}": {} for i in range(risk_manager.MAX_OPEN_POSITIONS)},
        )
        assert asyncio.run(risk_manager.is_risky_token("TOKL"))


def test_is_risky_token_slippage(monkeypatch, tmp_path):
    whitelist = tmp_path / "token_whitelist.txt"
    whitelist.write_text("")
    with patch.object(risk_manager, "WHITELIST_FILE", str(whitelist)), \
         patch.object(risk_manager, "BLACKLIST_FILE", str(whitelist)):
        monkeypatch.setattr(
            risk_manager.aiohttp,
            "ClientSession",
            lambda timeout=None: MockSession({"data": {"volume_usd_24h": 10000}}),
        )
        monkeypatch.setattr(
            risk_manager.config,
            "TRADE_SLIPPAGE",
            risk_manager.SLIPPAGE_THRESHOLD + 0.01,
        )
        assert asyncio.run(risk_manager.is_risky_token("TOKS"))

