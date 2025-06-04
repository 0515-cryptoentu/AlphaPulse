import json
import asyncio
import csv
from datetime import datetime
from decimal import Decimal
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


def _write_trades(path, rows):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "timestamp",
                "token_mint",
                "token_symbol",
                "amount_token",
                "amount_sol",
                "sol_usd",
                "usd_value",
                "tx_signature",
            ]
        )
        for r in rows:
            writer.writerow(r)


def test_daily_trade_limit(monkeypatch, tmp_path):
    csv_path = tmp_path / "trade_log.csv"
    now = datetime.utcnow().isoformat()
    rows = [[now, "T", "BUY", 0, 0, 0, 0, "s1"] for _ in range(3)]
    _write_trades(csv_path, rows)
    monkeypatch.setattr(risk_manager.trade_log, "CSV_FILE", str(csv_path))
    monkeypatch.setattr(risk_manager, "DAILY_TRADE_LIMIT", 2)
    whitelist = tmp_path / "token_whitelist.txt"
    whitelist.write_text("")
    with patch.object(risk_manager, "WHITELIST_FILE", str(whitelist)), \
         patch.object(risk_manager, "BLACKLIST_FILE", str(whitelist)):
        monkeypatch.setattr(
            risk_manager.aiohttp,
            "ClientSession",
            lambda timeout=None: MockSession({"data": {"volume_usd_24h": 10000}}),
        )
        assert asyncio.run(risk_manager.is_risky_token("TOKD"))


def test_exposure_cap(monkeypatch, tmp_path):
    whitelist = tmp_path / "token_whitelist.txt"
    whitelist.write_text("")
    monkeypatch.setattr(risk_manager, "EXPOSURE_CAP_PER_TOKEN", Decimal("10"))
    monkeypatch.setattr(risk_manager.auto_sell, "portfolio", {
        "TOKX": {"entry_price": Decimal("1"), "amount": 20}
    })
    with patch.object(risk_manager, "WHITELIST_FILE", str(whitelist)), \
         patch.object(risk_manager, "BLACKLIST_FILE", str(whitelist)):
        monkeypatch.setattr(
            risk_manager.aiohttp,
            "ClientSession",
            lambda timeout=None: MockSession({"data": {"volume_usd_24h": 10000}}),
        )
        assert asyncio.run(risk_manager.is_risky_token("TOKX"))


def test_adjust_position_size(monkeypatch, tmp_path):
    csv_path = tmp_path / "trade_log.csv"
    now = datetime.utcnow().isoformat()
    rows = [
        [now, "A", "BUY", 0, 0, 0, "1", "b1"],
        [now, "A", "AUTOSELL", 0, 0, 0, "2", "s1"],
        [now, "B", "BUY", 0, 0, 0, "1", "b2"],
        [now, "B", "AUTOSELL", 0, 0, 0, "2", "s2"],
        [now, "C", "BUY", 0, 0, 0, "1", "b3"],
        [now, "C", "AUTOSELL", 0, 0, 0, "2", "s3"],
    ]
    _write_trades(csv_path, rows)
    monkeypatch.setattr(risk_manager.trade_log, "CSV_FILE", str(csv_path))
    result = risk_manager.adjust_position_size(Decimal("1"))
    assert result == Decimal("1.5")

