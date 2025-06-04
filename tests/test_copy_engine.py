import asyncio
import base64
import importlib
import os
from decimal import Decimal
from unittest.mock import patch, AsyncMock
import pytest

# Skip if Solana client library missing
pytest.importorskip("solana.keypair")
pytest.importorskip("solana.rpc.api")
pytest.importorskip("solana")


def test_execute_trade_practice_mode():
    key = base64.b64encode(b"0" * 64).decode()
    env = {"RPC_URL": "http://localhost:8899", "USER_WALLET_PRIVATE_KEY": key}
    with patch.dict(os.environ, env):
        copy_engine = importlib.import_module("copy_engine")
        importlib.reload(copy_engine)

    trade = {
        "wallet": "WALLET",
        "token_in": copy_engine.MINT_SOL,
        "token_out": "TOK",
        "signature": "abcdef123456",
    }

    with patch.object(copy_engine, "is_risky_token", new_callable=AsyncMock, return_value=False), \
         patch.object(copy_engine, "get_balance", return_value=1.0), \
         patch.object(copy_engine, "log_trade", new_callable=AsyncMock) as log_trade_mock, \
         patch.object(copy_engine, "mark_new_token") as mark_token_mock, \
         patch.object(copy_engine, "get_sol_usd_price", new_callable=AsyncMock, return_value=Decimal("10")), \
         patch.object(copy_engine, "fetch_jupiter_swap_route", new_callable=AsyncMock) as fetch_mock, \
         patch.object(copy_engine, "execute_jupiter_swap", new_callable=AsyncMock) as exec_mock:
        asyncio.run(copy_engine.execute_trade(trade))
        log_trade_mock.assert_called_once()
        mark_token_mock.assert_called_once()
        fetch_mock.assert_not_called()
        exec_mock.assert_not_called()
