import json
import importlib
import os
from unittest.mock import patch
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
