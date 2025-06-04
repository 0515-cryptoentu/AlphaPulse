import asyncio
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import auto_sell


def setup_function(_):
    auto_sell.portfolio.clear()


def test_check_portfolio_trailing_stop(monkeypatch):
    auto_sell.portfolio['TOK'] = {
        'entry_price': Decimal('1.0'),
        'amount': 1,
        'entry_time': datetime.utcnow() - timedelta(minutes=10),
        'peak_price': Decimal('2.0'),
    }
    monkeypatch.setattr(auto_sell, 'fetch_token_price_usd', AsyncMock(return_value=Decimal('1.6')))
    monkeypatch.setattr(auto_sell, 'log', lambda *a, **k: None)
    result = asyncio.run(auto_sell.check_portfolio_for_sells())
    assert result == ['TOK']


def test_check_portfolio_updates_peak(monkeypatch):
    auto_sell.portfolio['TOK'] = {
        'entry_price': Decimal('1.0'),
        'amount': 1,
        'entry_time': datetime.utcnow(),
        'peak_price': Decimal('1.0'),
    }
    monkeypatch.setattr(auto_sell, 'fetch_token_price_usd', AsyncMock(return_value=Decimal('1.5')))
    monkeypatch.setattr(auto_sell, 'log', lambda *a, **k: None)
    result = asyncio.run(auto_sell.check_portfolio_for_sells())
    assert result == []
    assert auto_sell.portfolio['TOK']['peak_price'] == Decimal('1.5')


def test_check_portfolio_max_hold(monkeypatch):
    auto_sell.portfolio['TOK'] = {
        'entry_price': Decimal('1.0'),
        'amount': 1,
        'entry_time': datetime.utcnow() - auto_sell.MAX_HOLD_DURATION - timedelta(minutes=1),
        'peak_price': Decimal('1.0'),
    }
    monkeypatch.setattr(auto_sell, 'fetch_token_price_usd', AsyncMock(return_value=Decimal('1.1')))
    monkeypatch.setattr(auto_sell, 'log', lambda *a, **k: None)
    result = asyncio.run(auto_sell.check_portfolio_for_sells())
    assert result == ['TOK']

