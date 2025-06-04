import asyncio
import base64
import importlib
import json
import os
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("solana.keypair")
pytest.importorskip("solana.rpc.api")
pytest.importorskip("solana.transaction")


class MockResponse:
    def __init__(self, data, status=200):
        self.status = status
        self._data = data

    async def json(self):
        return self._data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass


class MockSession:
    def __init__(self, data, status=200):
        self._response = MockResponse(data, status)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    def get(self, *args, **kwargs):
        return self._response

    def post(self, *args, **kwargs):
        return self._response


def _import_copy_engine():
    key = base64.b64encode(b"0" * 64).decode()
    env = {"RPC_URL": "http://localhost:8899", "USER_WALLET_PRIVATE_KEY": key}
    with patch.dict(os.environ, env):
        mod = importlib.import_module("copy_engine")
        importlib.reload(mod)
        importlib.reload(importlib.import_module("jupiter_trader"))
        mod.config.PRACTICE_MODE = False
    return mod


def test_execute_trade_integration(monkeypatch):
    copy_engine = _import_copy_engine()
    from jupiter_trader import aiohttp, client, Transaction

    monkeypatch.setattr(copy_engine, "is_risky_token", AsyncMock(return_value=False))
    monkeypatch.setattr(copy_engine, "get_balance", lambda: 1.0)
    monkeypatch.setattr(copy_engine, "log_trade", AsyncMock())
    monkeypatch.setattr(copy_engine, "mark_new_token", MagicMock())
    monkeypatch.setattr(copy_engine, "get_sol_usd_price", AsyncMock(return_value=Decimal("10")))

    route = {"route": 1}
    monkeypatch.setattr(
        importlib.import_module("jupiter_trader"),
        "fetch_jupiter_swap_route",
        AsyncMock(return_value=route),
    )

    tx_bytes = b"tx"
    swap_resp = {"swapTransaction": base64.b64encode(tx_bytes).decode()}
    monkeypatch.setattr(aiohttp, "ClientSession", lambda: MockSession(swap_resp))
    tx_mock = MagicMock()
    monkeypatch.setattr(Transaction, "deserialize", lambda b: tx_mock)
    client.send_transaction = MagicMock(return_value={"result": "sig"})

    trade = {
        "wallet": "W",
        "token_in": copy_engine.MINT_SOL,
        "token_out": "T",
        "signature": "s",
    }
    asyncio.run(copy_engine.execute_trade(trade))

    client.send_transaction.assert_called_once()
    copy_engine.log_trade.assert_called_once()


def _import_trade_monitor(path):
    key = base64.b64encode(b"0" * 64).decode()
    env = {"RPC_URL": "http://localhost:8899", "USER_WALLET_PRIVATE_KEY": key}
    with patch.dict(os.environ, env):
        mod = importlib.import_module("trade_monitor")
        importlib.reload(mod)
        mod.MONITORED_FILE = str(path)
    return mod


def test_monitor_loop_polling(monkeypatch, tmp_path):
    path = tmp_path / "monitored_wallets.json"
    path.write_text(json.dumps([{"wallet": "W"}]))
    trade_monitor = _import_trade_monitor(path)

    monkeypatch.setattr(trade_monitor, "_websocket_wallets", AsyncMock(return_value=False))

    trade_monitor.client.get_signatures_for_address = MagicMock(
        return_value={"result": [{"signature": "sig", "slot": 1}]}
    )
    tx = {
        "slot": 1,
        "transaction": {"signatures": ["sig"], "message": {"instructions": []}},
        "meta": {
            "preTokenBalances": [{"owner": "W", "mint": "A"}],
            "postTokenBalances": [{"owner": "W", "mint": "B"}],
        },
    }
    trade_monitor.client.get_transaction = MagicMock(return_value={"result": tx})

    called = []

    async def fake_execute(trade):
        called.append(trade)

    monkeypatch.setattr(trade_monitor, "execute_trade", fake_execute)

    async def stop_sleep(_):
        raise asyncio.CancelledError()

    monkeypatch.setattr(trade_monitor.asyncio, "sleep", stop_sleep)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(trade_monitor.monitor_loop())

    assert called and called[0]["token_in"] == "A" and called[0]["token_out"] == "B"
