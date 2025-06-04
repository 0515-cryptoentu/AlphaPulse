import sqlite3
import importlib
import types
import sys
from unittest.mock import patch
import httpx
import asyncio


def create_app(tmp_path):
    db_path = tmp_path / "trades.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE trades (timestamp TEXT, token_mint TEXT, token_symbol TEXT, amount_token TEXT, amount_sol TEXT, sol_usd TEXT, usd_value TEXT, tx_signature TEXT)"
    )
    conn.execute("INSERT INTO trades VALUES ('t1','M','TOK','1','2','1','2','sig1')")
    conn.execute("INSERT INTO trades VALUES ('t2','M','TOK','3','4','1','4','sig2')")
    conn.commit()
    conn.close()

    dummy = types.SimpleNamespace(get_balance=lambda: 0.0)
    with patch.dict(sys.modules, {'wallet_manager': dummy}):
        import dashboard.backend.main as api
        importlib.reload(api)
    api.trade_log.DB_FILE = str(db_path)
    api.trade_log.CSV_FILE = str(tmp_path / "trade_log.csv")
    return api.app, api


def test_balance_endpoint(tmp_path, monkeypatch):
    app, api = create_app(tmp_path)
    monkeypatch.setattr(api.wallet_manager, 'get_balance', lambda: 1.23)
    async def fetch():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get('/balance')

    resp = asyncio.run(fetch())
    assert resp.status_code == 200
    assert resp.json()['balance_sol'] == 1.23


def test_trades_and_metrics(tmp_path, monkeypatch):
    app, api = create_app(tmp_path)
    monkeypatch.setattr(api.wallet_manager, 'get_balance', lambda: 1.0)
    async def fetch(path):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get(path)

    resp = asyncio.run(fetch('/trades?limit=1'))
    assert resp.status_code == 200
    data = resp.json()['trades']
    assert len(data) == 1
    assert data[0]['tx_signature'] == 'sig2'

    resp = asyncio.run(fetch('/metrics'))
    m = resp.json()
    assert m['num_trades'] == 2
    assert m['total_sol'] == 6.0

