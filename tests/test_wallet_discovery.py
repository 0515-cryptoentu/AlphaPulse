import asyncio
import json
from unittest.mock import AsyncMock

import pytest

import wallet_discovery

pytest.importorskip("aiohttp")


async def _run(coro):
    return await coro


def test_analyze_wallet(monkeypatch):
    now = 1_000_000_000
    txs = [
        {"blockTime": now - 1000, "tokenTransfers": [{"tokenAddress": "T1"}]},
        {
            "blockTime": now - 5000,
            "tokenTransfers": [
                {"tokenAddress": "T2"},
                {"tokenAddress": "T1"},
            ],
        },
        {"blockTime": now - 700000, "tokenTransfers": [{"tokenAddress": "T3"}]},
    ]

    monkeypatch.setattr(
        wallet_discovery, "fetch_transactions", AsyncMock(return_value=txs)
    )
    monkeypatch.setattr(wallet_discovery.time, "time", lambda: now)

    data = asyncio.run(wallet_discovery.analyze_wallet("WALLET"))
    assert data == {
        "wallet": "WALLET",
        "tx_count": 2,
        "token_count": 2,
        "last_active": now - 1000,
        "avg_trade_size": pytest.approx(1.5),
        "score": pytest.approx(16.5),
    }


def test_export_to_json(tmp_path, monkeypatch):
    wallets = [
        {
            "wallet": "W",
            "score": 1.0,
            "tx_count": 1,
            "token_count": 1,
            "last_active": 0,
        }
    ]
    out = tmp_path / "wallets.json"
    monkeypatch.setattr(wallet_discovery, "JSON_OUTPUT", str(out))
    monkeypatch.setattr(wallet_discovery, "log", lambda *a, **k: None)

    wallet_discovery.export_to_json(wallets)

    assert json.loads(out.read_text()) == wallets
