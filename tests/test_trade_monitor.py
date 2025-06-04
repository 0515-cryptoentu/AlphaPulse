import json
import importlib
import os
import base64
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
