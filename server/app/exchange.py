"""Exchange core: accounts, risk checks, order routing into the C++ engine,
trade reporting and P&L.

Everything here runs on the asyncio event loop thread, so the engine is only
touched by one thread at a time and needs no locks.
"""

import secrets
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional

import matching_engine as me

from .config import Settings

BUY = "buy"
SELL = "sell"
SIDES = {BUY: me.Side.BUY, SELL: me.Side.SELL}


class RejectError(Exception):
    """Raised when an order fails a risk or validation check."""


@dataclass
class Account:
    trader_id: int
    name: str
    api_key: str
    is_bot: bool = False
    cash_ticks: int = 0                       # ticks * shares
    positions: Dict[str, int] = field(default_factory=dict)
    volume: int = 0
    trades: int = 0
    tokens: float = 0.0
    last_refill: float = field(default_factory=time.monotonic)


@dataclass
class Trade:
    trade_id: int
    symbol: str
    price_ticks: int
    qty: int
    buyer: int
    seller: int
    aggressor: str
    timestamp: float


@dataclass
class Candle:
    start: int
    open: int
    high: int
    low: int
    close: int
    volume: int


class Exchange:
    def __init__(self, settings: Settings, store=None):
        self.settings = settings
        self.store = store
        self.books: Dict[str, me.OrderBook] = {}
        self.order_symbol: Dict[int, str] = {}
        self.last_price: Dict[str, int] = {}
        self.candles: Dict[str, Deque[Candle]] = {}
        self.trades: Dict[str, Deque[Trade]] = {}
        self.accounts: Dict[int, Account] = {}
        self.by_key: Dict[str, Account] = {}
        self.next_trader_id = 1
        self.next_trade_id = 1
        self.news: Deque[dict] = deque(maxlen=50)
        self.pending_trades: List[Trade] = []

        for symbol, price in zip(settings.symbols, settings.start_prices):
            self.books[symbol] = me.OrderBook()
            self.last_price[symbol] = self.to_ticks(price)
            self.candles[symbol] = deque(maxlen=settings.history_candles)
            self.trades[symbol] = deque(maxlen=200)

    # ------------------------------------------------------------------
    # Units
    # ------------------------------------------------------------------
    def to_ticks(self, price: float) -> int:
        return int(round(price / self.settings.tick_size))

    def to_price(self, ticks: float) -> float:
        return round(ticks * self.settings.tick_size, 4)

    # ------------------------------------------------------------------
    # Accounts
    # ------------------------------------------------------------------
    def register(self, name: str, is_bot: bool = False, api_key: Optional[str] = None,
                 persist: bool = True) -> Account:
        name = name.strip()
        if not name or len(name) > 32:
            raise RejectError("name must be 1 to 32 characters")
        for existing in self.accounts.values():
            if existing.name.lower() == name.lower():
                raise RejectError("that name is taken")
        account = Account(
            trader_id=self.next_trader_id,
            name=name,
            api_key=api_key or secrets.token_urlsafe(24),
            is_bot=is_bot,
            tokens=float(self.settings.order_burst),
        )
        self.next_trader_id += 1
        self.accounts[account.trader_id] = account
        self.by_key[account.api_key] = account
        if self.store is not None and not is_bot and persist:
            self.store.save_account(account)
        return account

    def authenticate(self, api_key: Optional[str]) -> Account:
        account = self.by_key.get(api_key or "")
        if account is None:
            raise PermissionError("unknown API key")
        return account

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------
    def mid_ticks(self, symbol: str) -> float:
        book = self.books[symbol]
        bid = book.best_bid()
        ask = book.best_ask()
        if bid is not None and ask is not None:
            return (bid + ask) / 2.0
        return float(self.last_price[symbol])

    def book_snapshot(self, symbol: str, levels: int = 10) -> dict:
        book = self.books[symbol]
        bids = []
        for level in book.depth(me.Side.BUY, levels):
            bids.append({"price": self.to_price(level.price), "qty": level.qty, "orders": level.orders})
        asks = []
        for level in book.depth(me.Side.SELL, levels):
            asks.append({"price": self.to_price(level.price), "qty": level.qty, "orders": level.orders})
        return {
            "symbol": symbol,
            "bids": bids,
            "asks": asks,
            "mid": self.to_price(self.mid_ticks(symbol)),
            "last": self.to_price(self.last_price[symbol]),
            "volume": book.volume,
        }

    def trade_view(self, trade: Trade) -> dict:
        buyer = self.accounts.get(trade.buyer)
        seller = self.accounts.get(trade.seller)
        return {
            "id": trade.trade_id,
            "symbol": trade.symbol,
            "price": self.to_price(trade.price_ticks),
            "qty": trade.qty,
            "aggressor": trade.aggressor,
            "buyer": buyer.name if buyer else "?",
            "seller": seller.name if seller else "?",
            "time": trade.timestamp,
        }

    def candle_view(self, symbol: str) -> List[dict]:
        out = []
        for candle in self.candles[symbol]:
            out.append({
                "time": candle.start,
                "open": self.to_price(candle.open),
                "high": self.to_price(candle.high),
                "low": self.to_price(candle.low),
                "close": self.to_price(candle.close),
                "volume": candle.volume,
            })
        return out

    # ------------------------------------------------------------------
    # Order entry
    # ------------------------------------------------------------------
    def place_order(self, account: Account, symbol: str, side: str, order_type: str,
                    qty: int, price: Optional[float] = None) -> dict:
        if symbol not in self.books:
            raise RejectError(f"unknown symbol {symbol}")
        if side not in SIDES:
            raise RejectError("side must be buy or sell")
        if qty <= 0 or qty > self.settings.max_order_qty:
            raise RejectError(f"qty must be between 1 and {self.settings.max_order_qty}")
        self._check_rate(account)
        self._check_position_limit(account, symbol, side, qty)

        book = self.books[symbol]
        engine_side = SIDES[side]
        if order_type == "limit":
            if price is None:
                raise RejectError("limit orders need a price")
            price_ticks = self.to_ticks(price)
            self._check_price_band(symbol, price_ticks)
            result = book.add_limit(account.trader_id, engine_side, price_ticks, qty)
        elif order_type == "market":
            result = book.add_market(account.trader_id, engine_side, qty)
        else:
            raise RejectError("type must be limit or market")

        for cancelled in result.self_trade_cancels:
            self.order_symbol.pop(cancelled, None)
        if result.id:
            self.order_symbol[result.id] = symbol
        self._settle(symbol, result.fills)

        return {
            "order_id": result.id or None,
            "filled": result.filled,
            "resting": result.resting,
            "fills": [
                {"price": self.to_price(f.price), "qty": f.qty} for f in result.fills
            ],
            "self_trade_cancels": list(result.self_trade_cancels),
        }

    def cancel(self, account: Account, order_id: int) -> bool:
        symbol = self.order_symbol.get(order_id)
        if symbol is None:
            return False
        order = self.books[symbol].get_order(order_id)
        if order is None or order.trader != account.trader_id:
            return False
        self.books[symbol].cancel(order_id)
        del self.order_symbol[order_id]
        return True

    def cancel_all(self, account: Account, symbol: Optional[str] = None) -> int:
        total = 0
        symbols = [symbol] if symbol else list(self.books)
        for sym in symbols:
            for order in self.books[sym].orders_for(account.trader_id):
                self.order_symbol.pop(order.id, None)
            total += self.books[sym].cancel_all(account.trader_id)
        return total

    def open_orders(self, account: Account) -> List[dict]:
        out = []
        for symbol, book in self.books.items():
            for order in book.orders_for(account.trader_id):
                out.append({
                    "order_id": order.id,
                    "symbol": symbol,
                    "side": BUY if order.side == me.Side.BUY else SELL,
                    "price": self.to_price(order.price),
                    "qty": order.qty,
                })
        return out

    # ------------------------------------------------------------------
    # Risk checks
    # ------------------------------------------------------------------
    def _check_rate(self, account: Account) -> None:
        if account.is_bot:
            return
        now = time.monotonic()
        elapsed = now - account.last_refill
        account.last_refill = now
        account.tokens = min(
            float(self.settings.order_burst),
            account.tokens + elapsed * self.settings.orders_per_second,
        )
        if account.tokens < 1.0:
            raise RejectError("rate limit exceeded, slow down")
        account.tokens -= 1.0

    def _check_position_limit(self, account: Account, symbol: str, side: str, qty: int) -> None:
        """Worst case position if every open order on this side filled."""
        position = account.positions.get(symbol, 0)
        open_buy = 0
        open_sell = 0
        for order in self.books[symbol].orders_for(account.trader_id):
            if order.side == me.Side.BUY:
                open_buy += order.qty
            else:
                open_sell += order.qty
        if account.is_bot:
            limit = self.settings.bot_position_limit
        else:
            limit = self.settings.position_limit
        if side == BUY and position + open_buy + qty > limit:
            raise RejectError(f"would breach position limit of {limit}")
        if side == SELL and position - open_sell - qty < -limit:
            raise RejectError(f"would breach position limit of {limit}")

    def _check_price_band(self, symbol: str, price_ticks: int) -> None:
        reference = self.mid_ticks(symbol)
        band = reference * self.settings.price_band_pct
        if abs(price_ticks - reference) > band:
            raise RejectError("price is too far from the market")
        if price_ticks <= 0:
            raise RejectError("price must be positive")

    # ------------------------------------------------------------------
    # Settlement and P&L
    # ------------------------------------------------------------------
    def _settle(self, symbol: str, fills) -> None:
        now = time.time()
        for fill in fills:
            if fill.taker_side == me.Side.BUY:
                buyer_id = fill.taker
                seller_id = fill.maker
                aggressor = BUY
            else:
                buyer_id = fill.maker
                seller_id = fill.taker
                aggressor = SELL

            if self.books[symbol].get_order(fill.maker_order) is None:
                self.order_symbol.pop(fill.maker_order, None)

            buyer = self.accounts[buyer_id]
            seller = self.accounts[seller_id]
            notional = fill.price * fill.qty
            buyer.cash_ticks -= notional
            seller.cash_ticks += notional
            buyer.positions[symbol] = buyer.positions.get(symbol, 0) + fill.qty
            seller.positions[symbol] = seller.positions.get(symbol, 0) - fill.qty
            for account in (buyer, seller):
                account.volume += fill.qty
                account.trades += 1

            trade = Trade(self.next_trade_id, symbol, fill.price, fill.qty,
                          buyer_id, seller_id, aggressor, now)
            self.next_trade_id += 1
            self.trades[symbol].append(trade)
            self.pending_trades.append(trade)
            self.last_price[symbol] = fill.price
            self._update_candle(symbol, fill.price, fill.qty, now)

    def _update_candle(self, symbol: str, price: int, qty: int, now: float) -> None:
        width = self.settings.candle_seconds
        start = int(now // width * width)
        candles = self.candles[symbol]
        if candles and candles[-1].start == start:
            candle = candles[-1]
            candle.high = max(candle.high, price)
            candle.low = min(candle.low, price)
            candle.close = price
            candle.volume += qty
        else:
            candles.append(Candle(start, price, price, price, price, qty))

    def account_view(self, account: Account) -> dict:
        positions = []
        mark_value = 0.0
        for symbol in self.books:
            qty = account.positions.get(symbol, 0)
            mid = self.mid_ticks(symbol)
            value = qty * mid
            mark_value += value
            positions.append({
                "symbol": symbol,
                "qty": qty,
                "mark": self.to_price(mid),
                "value": round(self.to_price(value), 2),
            })
        pnl = self.to_price(account.cash_ticks + mark_value)
        return {
            "trader_id": account.trader_id,
            "name": account.name,
            "is_bot": account.is_bot,
            "cash": round(self.to_price(account.cash_ticks), 2),
            "pnl": round(pnl, 2),
            "volume": account.volume,
            "trades": account.trades,
            "positions": positions,
            "limits": {
                "position": self.settings.position_limit,
                "max_order_qty": self.settings.max_order_qty,
            },
        }

    def leaderboard(self) -> List[dict]:
        rows = []
        for account in self.accounts.values():
            if account.volume == 0 and account.is_bot is False and account.trades == 0:
                continue
            view = self.account_view(account)
            rows.append({
                "name": view["name"],
                "is_bot": view["is_bot"],
                "pnl": view["pnl"],
                "volume": view["volume"],
            })
        rows.sort(key=lambda row: row["pnl"], reverse=True)
        for rank, row in enumerate(rows, start=1):
            row["rank"] = rank
        return rows

    def drain_trades(self) -> List[Trade]:
        trades = self.pending_trades
        self.pending_trades = []
        return trades
