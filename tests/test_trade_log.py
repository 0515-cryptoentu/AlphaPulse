import asyncio
import sqlite3
from decimal import Decimal
from unittest.mock import AsyncMock

import trade_log


def test_log_trade_creates_db_and_logs(tmp_path, monkeypatch):
    csv_path = tmp_path / "trade_log.csv"
    db_path = tmp_path / "trades.db"

    monkeypatch.setattr(trade_log, "CSV_FILE", str(csv_path))
    monkeypatch.setattr(trade_log, "DB_FILE", str(db_path))
    monkeypatch.setattr(trade_log, "get_sol_usd_price", AsyncMock(return_value=Decimal("1")))

    asyncio.run(trade_log.log_trade("TOKEN", "SYM", Decimal("1"), Decimal("2"), "SIG"))

    assert csv_path.exists()
    lines = csv_path.read_text().strip().splitlines()
    assert len(lines) == 2

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT token_mint, token_symbol, amount_token, amount_sol, tx_signature FROM trades"
    ).fetchone()
    conn.close()
    assert row == ("TOKEN", "SYM", "1", "2", "SIG")
