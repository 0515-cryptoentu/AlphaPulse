import sqlite3
import importlib
import types
import sys
from unittest.mock import patch
import httpx
import asyncio
from datetime import datetime


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
    api.WALLET_DB = str(tmp_path / "wallet_repository.db")
    api.HEARTBEAT_FILE = str(tmp_path / "hb.txt")
    import auto_sell
    api.auto_sell = auto_sell
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


def test_additional_endpoints(tmp_path, monkeypatch):
    app, api = create_app(tmp_path)

    # add sell trade for pnl calculation
    conn = sqlite3.connect(api.trade_log.DB_FILE)
    conn.execute("INSERT INTO trades VALUES ('t3','M','AUTOSELL','1','1','1','1','sig3')")
    conn.commit()
    conn.close()

    # setup portfolio
    api.auto_sell.portfolio.clear()
    api.auto_sell.portfolio['TOK'] = {
        'entry_price': 1.0,
        'amount': 10,
        'entry_time': datetime.utcnow(),
        'peak_price': 1.0,
    }

    # create wallet stats
    conn = sqlite3.connect(api.WALLET_DB)
    conn.execute(
        "CREATE TABLE wallets (wallet TEXT, tx_count INTEGER, avg_tx_interval REAL, last_seen INTEGER, is_active INTEGER, notes TEXT, source TEXT)"
    )
    conn.execute(
        "INSERT INTO wallets VALUES ('W1',5,10.0,0,1,'','src')"
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(api.wallet_manager, 'get_balance', lambda: 1.0)

    async def fetch(path):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get(path)

    resp = asyncio.run(fetch('/pnl'))
    assert resp.status_code == 200
    pnl = resp.json()
    assert pnl['pnl_usd'] == -5.0

    resp = asyncio.run(fetch('/portfolio'))
    data = resp.json()['portfolio']
    assert len(data) == 1
    assert data[0]['token_mint'] == 'TOK'

    resp = asyncio.run(fetch('/wallet_stats'))
    stats = resp.json()['wallets']
    assert len(stats) == 1
    assert stats[0]['wallet'] == 'W1'


def test_heartbeat_endpoint(tmp_path):
    app, api = create_app(tmp_path)
    hb_path = tmp_path / 'hb.txt'
    hb_path.write_text('2024-01-01T00:00:00')
    api.HEARTBEAT_FILE = str(hb_path)

    async def fetch():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get('/heartbeat')

    resp = asyncio.run(fetch())
    assert resp.status_code == 200
    assert resp.json()['timestamp'] == '2024-01-01T00:00:00'

