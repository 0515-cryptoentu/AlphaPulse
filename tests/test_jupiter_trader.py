import asyncio
import base64
import importlib
import os
from unittest.mock import MagicMock, patch
import pytest

pytest.importorskip("solana.keypair")
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


def setup_module(module):
    key = base64.b64encode(b"0" * 64).decode()
    env = {"RPC_URL": "http://localhost:8899", "USER_WALLET_PRIVATE_KEY": key}
    module._patch = patch.dict(os.environ, env)
    module._patch.start()
    module.jupiter_trader = importlib.import_module("jupiter_trader")
    importlib.reload(module.jupiter_trader)


def teardown_module(module):
    module._patch.stop()


def test_fetch_jupiter_swap_route(monkeypatch):
    resp_data = {"data": [{"foo": "bar"}]}
    monkeypatch.setattr(jupiter_trader.aiohttp, "ClientSession", lambda: MockSession(resp_data))
    route = asyncio.run(jupiter_trader.fetch_jupiter_swap_route("A", "B", 1))
    assert route == {"foo": "bar"}


def test_execute_jupiter_swap(monkeypatch):
    tx_bytes = b"tx"
    swap_resp = {"swapTransaction": base64.b64encode(tx_bytes).decode()}
    monkeypatch.setattr(jupiter_trader.aiohttp, "ClientSession", lambda: MockSession(swap_resp))
    tx_mock = MagicMock()
    monkeypatch.setattr(jupiter_trader.Transaction, "deserialize", lambda b: tx_mock)
    jupiter_trader.client.send_transaction = MagicMock(return_value={"result": "sig"})
    result = asyncio.run(jupiter_trader.execute_jupiter_swap({}))
    assert result == {"result": "sig"}
    tx_mock.sign.assert_called_once()
    jupiter_trader.client.send_transaction.assert_called_once()


class SeqFactory:
    """Factory returning sessions with sequential responses."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def __call__(self):
        data, status = self._responses[self.calls]
        self.calls += 1
        return MockSession(data, status)


def test_execute_jupiter_swap_retries(monkeypatch):
    tx_bytes = b"tx"
    responses = [
        (None, 500),
        ({"swapTransaction": base64.b64encode(tx_bytes).decode()}, 200),
    ]
    factory = SeqFactory(responses)
    monkeypatch.setattr(jupiter_trader.aiohttp, "ClientSession", factory)
    tx_mock = MagicMock()
    monkeypatch.setattr(jupiter_trader.Transaction, "deserialize", lambda b: tx_mock)
    jupiter_trader.client.send_transaction = MagicMock(return_value={"result": "sig"})
    result = asyncio.run(jupiter_trader.execute_jupiter_swap({}, retries=2, delay=0))
    assert result == {"result": "sig"}
    assert factory.calls == 2


def test_execute_jupiter_swap_retry_failure(monkeypatch):
    responses = [(None, 500), (None, 500)]
    factory = SeqFactory(responses)
    monkeypatch.setattr(jupiter_trader.aiohttp, "ClientSession", factory)
    result = asyncio.run(jupiter_trader.execute_jupiter_swap({}, retries=2, delay=0))
    assert result is None
    assert factory.calls == 2
