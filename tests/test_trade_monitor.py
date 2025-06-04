import json
import importlib
import os
import base64
import asyncio
from unittest.mock import patch, MagicMock
import pytest

# Skip these tests entirely if the Solana client libraries are unavailable.
pytest.importorskip("solana.rpc.api")
pytest.importorskip("solana.publickey")


def test_load_wallets(tmp_path):
    data = [{"wallet": "W1"}, {"wallet": "W2"}]
    path = tmp_path / "monitored_wallets.json"
    path.write_text(json.dumps(data))
    with patch.dict(os.environ, {"HELIUS_RPC_URL": "http://localhost:8899"}):
        trade_monitor = importlib.import_module("trade_monitor")
        importlib.reload(trade_monitor)
        with patch.object(trade_monitor, "MONITORED_FILE", str(path)):
            wallets = trade_monitor.load_wallets()
            assert wallets == ["W1", "W2"]


def _import_module(env):
    key = base64.b64encode(b"0" * 64).decode()
    env_vars = {"RPC_URL": "http://localhost:8899", "USER_WALLET_PRIVATE_KEY": key}
    env_vars.update(env)
    with patch.dict(os.environ, env_vars):
        mod = importlib.import_module("trade_monitor")
        importlib.reload(mod)
    return mod


def test_detect_platform_and_swap():
    mod = _import_module({})
    instructions = [{"programId": "JUP4Fb2cqiRUcaTHdrPC8h2gNsA2ETXiPDD33WcGuJB"}]
    assert mod.detect_platform(instructions) == "Jupiter"

    tx = {
        "transaction": {"message": {"instructions": instructions}, "signatures": ["sig"]},
        "slot": 1,
        "meta": {
            "preTokenBalances": [{"owner": "W", "mint": "A"}],
            "postTokenBalances": [{"owner": "W", "mint": "B"}],
        },
    }
    trade = mod.detect_swap(tx, "W")
    assert trade["token_in"] == "A" and trade["token_out"] == "B"


def test_get_recent_signatures_and_transaction(monkeypatch):
    mod = _import_module({})
    client = MagicMock()
    client.get_signatures_for_address.return_value = {"result": [{"signature": "s", "slot": 1}]}
    client.get_transaction.return_value = {"result": "tx"}
    monkeypatch.setattr(mod, "client", client)
    sigs = mod.get_recent_signatures("W")
    assert sigs == [{"signature": "s", "slot": 1}]
    tx = mod.get_transaction("s")
    assert tx == "tx"


def test_websocket_wallets_retry(monkeypatch):
    mod = _import_module({})

    class FailConn:
        def __init__(self):
            self.calls = 0

        def __call__(self, *a, **k):
            self.calls += 1
            return self

        async def __aenter__(self):
            raise ConnectionError("fail")

        async def __aexit__(self, exc_type, exc, tb):
            pass

    conn = FailConn()
    monkeypatch.setattr(mod.websockets, "connect", conn)
    result = asyncio.run(mod._websocket_wallets(["W"], retries=2, delay=0))
    assert result is False
    assert conn.calls == 2


def test_record_heartbeat_and_supervisor(monkeypatch, tmp_path):
    mod = _import_module({})
    hb = tmp_path / 'hb.txt'
    monkeypatch.setattr(mod, 'HEARTBEAT_FILE', str(hb))
    mod.record_heartbeat()
    assert hb.read_text()

    calls = 0

    async def fail_loop():
        nonlocal calls
        calls += 1
        raise RuntimeError('boom')

    monkeypatch.setattr(mod, 'monitor_loop', fail_loop)
    async def fast_sleep(*_):
        pass

    monkeypatch.setattr(mod.asyncio, 'sleep', fast_sleep)
    asyncio.run(mod.supervisor_loop(delay=0, max_restarts=2))
    assert calls == 2
