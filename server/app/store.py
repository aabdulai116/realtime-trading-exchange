"""SQLite persistence for registered traders and the trade tape."""

import sqlite3
from typing import Iterable


class Store:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS traders (
                trader_id INTEGER,
                name TEXT NOT NULL,
                api_key TEXT PRIMARY KEY,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS trades (
                trade_id INTEGER,
                symbol TEXT NOT NULL,
                price REAL NOT NULL,
                qty INTEGER NOT NULL,
                buyer TEXT NOT NULL,
                seller TEXT NOT NULL,
                aggressor TEXT NOT NULL,
                ts REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS trades_symbol_ts ON trades(symbol, ts);
            """
        )
        self.conn.commit()

    def save_account(self, account) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO traders (trader_id, name, api_key) VALUES (?, ?, ?)",
            (account.trader_id, account.name, account.api_key),
        )
        self.conn.commit()

    def load_accounts(self):
        rows = self.conn.execute("SELECT name, api_key FROM traders ORDER BY created_at")
        return rows.fetchall()

    def save_trades(self, trades: Iterable, exchange) -> None:
        rows = []
        for trade in trades:
            rows.append((
                trade.trade_id,
                trade.symbol,
                exchange.to_price(trade.price_ticks),
                trade.qty,
                exchange.accounts[trade.buyer].name,
                exchange.accounts[trade.seller].name,
                trade.aggressor,
                trade.timestamp,
            ))
        self.conn.executemany("INSERT INTO trades VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
        self.conn.commit()

    def trade_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
