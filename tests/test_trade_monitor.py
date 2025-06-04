import json
from unittest.mock import patch
import pytest

pytest.importorskip("solana")

import trade_monitor


def test_load_wallets(tmp_path):
    data = [{"wallet": "W1"}, {"wallet": "W2"}]
    path = tmp_path / "monitored_wallets.json"
    path.write_text(json.dumps(data))
    with patch.object(trade_monitor, "MONITORED_FILE", str(path)):
        wallets = trade_monitor.load_wallets()
        assert wallets == ["W1", "W2"]
