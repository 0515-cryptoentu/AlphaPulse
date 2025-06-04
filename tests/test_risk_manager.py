import json
from unittest.mock import patch
import pytest

pytest.importorskip("requests")
pytest.importorskip("solana")

import risk_manager


def test_is_token_blacklisted(tmp_path):
    blacklist = tmp_path / "token_blacklist.txt"
    blacklist.write_text("TOKEN1\nTOKEN2\n")
    with patch.object(risk_manager, "BLACKLIST_FILE", str(blacklist)):
        assert risk_manager.is_token_blacklisted("TOKEN1")
        assert not risk_manager.is_token_blacklisted("OTHER")


@patch("risk_manager.requests.get")
def test_is_risky_token(mock_get, tmp_path):
    blacklist = tmp_path / "token_blacklist.txt"
    blacklist.write_text("")
    with patch.object(risk_manager, "BLACKLIST_FILE", str(blacklist)):
        mock_get.return_value.json.return_value = {"data": {"volume_usd_24h": 10000}}
        assert not risk_manager.is_risky_token("TOKA")
        mock_get.return_value.json.return_value = {"data": {"volume_usd_24h": 1}}
        assert risk_manager.is_risky_token("TOKB")
