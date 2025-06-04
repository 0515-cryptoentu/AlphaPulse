import json
import asyncio
from unittest.mock import patch
import pytest

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
