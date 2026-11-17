"""Simulated market participants that keep the exchange alive.

Each symbol has a hidden fair value that drifts randomly and jumps on news.
The bots below react to it in different ways, which creates the same kinds
of opportunities a trading competition case is built around:

* Liquidity Co.   posts passive orders around a *slow* estimate of fair
                  value, so its quotes go stale right after news.
* Retail Flow     sends random market orders (uninformed flow).
* Info Capital    knows fair value and trades when the book is mispriced.
* House MM        an inventory aware market maker (Avellaneda and Stoikov).

Human traders and API bots compete against all of them.
"""

import math
import random
import time
from dataclasses import dataclass, field
from typing import Dict, List

from .exchange import BUY, SELL, Exchange, RejectError

HEADLINES_UP = [
    "{s} beats earnings expectations",
    "{s} wins a major government contract",
    "Analysts upgrade {s} to buy",
    "{s} announces a share buyback",
]
HEADLINES_DOWN = [
    "{s} misses earnings expectations",
    "{s} CEO resigns unexpectedly",
    "Regulators open an investigation into {s}",
    "{s} cuts full year guidance",
]


@dataclass
class SymbolState:
    fair: float                  # hidden fair value in ticks
    lp_view: float               # liquidity provider's lagging estimate
    lp_orders: Dict[int, float] = field(default_factory=dict)   # id -> expiry time


class MarketSimulation:
    def __init__(self, exchange: Exchange, seed: int = 7):
        self.exchange = exchange
        self.settings = exchange.settings
        self.rng = random.Random(seed)
        self.lp = exchange.register("Liquidity Co.", is_bot=True)
        self.retail = exchange.register("Retail Flow", is_bot=True)
        self.informed = exchange.register("Info Capital", is_bot=True)
        self.house = exchange.register("House MM", is_bot=True)
        self.state: Dict[str, SymbolState] = {}
        self.steps = 0
        for symbol in exchange.books:
            fair = float(exchange.last_price[symbol])
            self.state[symbol] = SymbolState(fair=fair, lp_view=fair)
            self._seed_book(symbol)

    # ------------------------------------------------------------------
    def step(self) -> None:
        self.steps += 1
        now = time.time()
        for symbol, state in self.state.items():
            self._move_fair_value(symbol, state)
            self._liquidity_provider(symbol, state, now)
            self._house_market_maker(symbol, state)
            self._takers(symbol, state)

    # ------------------------------------------------------------------
    def _move_fair_value(self, symbol: str, state: SymbolState) -> None:
        state.fair += self.rng.gauss(0.0, self.settings.fundamental_vol)
        if self.rng.random() < self.settings.news_prob:
            move = self.rng.gauss(0.0, self.settings.news_impact_ticks)
            if move >= 0:
                template = self.rng.choice(HEADLINES_UP)
            else:
                template = self.rng.choice(HEADLINES_DOWN)
            state.fair += move
            self.exchange.news.appendleft({
                "time": time.time(),
                "symbol": symbol,
                "headline": template.format(s=symbol),
            })
        # Liquidity Co. only catches up to fair value gradually.
        state.lp_view += 0.04 * (state.fair - state.lp_view)

    def _seed_book(self, symbol: str) -> None:
        state = self.state[symbol]
        center = int(round(state.fair))
        for offset in range(1, 12):
            self._lp_order(symbol, state, BUY, center - offset, self.rng.randint(5, 40), time.time() + 60)
            self._lp_order(symbol, state, SELL, center + offset, self.rng.randint(5, 40), time.time() + 60)

    def _lp_order(self, symbol, state, side, price_ticks, qty, expiry) -> None:
        try:
            result = self.exchange.place_order(
                self.lp, symbol, side, "limit", qty, self.exchange.to_price(price_ticks)
            )
        except RejectError:
            return
        if result["order_id"]:
            state.lp_orders[result["order_id"]] = expiry

    def _liquidity_provider(self, symbol: str, state: SymbolState, now: float) -> None:
        expired = []
        for order_id, expiry in state.lp_orders.items():
            if expiry <= now:
                expired.append(order_id)
        for order_id in expired:
            self.exchange.cancel(self.lp, order_id)
            del state.lp_orders[order_id]
        # Forget orders that already traded.
        book = self.exchange.books[symbol]
        gone = [oid for oid in state.lp_orders if book.get_order(oid) is None]
        for order_id in gone:
            del state.lp_orders[order_id]

        for _ in range(self.rng.randint(1, 4)):
            side = BUY if self.rng.random() < 0.5 else SELL
            offset = 1 + int(self.rng.expovariate(0.35))
            view = state.lp_view + self.rng.gauss(0.0, 1.0)
            if side == BUY:
                price = math.floor(view) - offset
            else:
                price = math.ceil(view) + offset
            life = now + self.rng.uniform(4.0, 20.0)
            self._lp_order(symbol, state, side, price, self.rng.randint(1, 30), life)

    def _house_market_maker(self, symbol: str, state: SymbolState) -> None:
        # Pull our quotes first so fair value comes from everyone else's orders.
        self.exchange.cancel_all(self.house, symbol)
        mid = self.exchange.mid_ticks(symbol)
        inventory = self.house.positions.get(symbol, 0)
        skew_per_share = 0.02
        reservation = mid - inventory * skew_per_share
        half_spread = 2.0
        bid = math.floor(reservation - half_spread)
        ask = math.ceil(reservation + half_spread)

        book = self.exchange.books[symbol]
        best_ask = book.best_ask()
        best_bid = book.best_bid()
        if best_ask is not None and bid >= best_ask:
            bid = best_ask - 1
        if best_bid is not None and ask <= best_bid:
            ask = best_bid + 1
        for side, price in ((BUY, bid), (SELL, ask)):
            try:
                self.exchange.place_order(self.house, symbol, side, "limit", 10,
                                          self.exchange.to_price(price))
            except RejectError:
                pass

    def _takers(self, symbol: str, state: SymbolState) -> None:
        book = self.exchange.books[symbol]
        if self.rng.random() < 0.35:
            side = BUY if self.rng.random() < 0.5 else SELL
            self._market(self.retail, symbol, side, self.rng.randint(1, 25))

        best_bid = book.best_bid()
        best_ask = book.best_ask()
        if self.rng.random() < 0.5 and best_bid is not None and best_ask is not None:
            if state.fair - best_ask > 2:
                self._market(self.informed, symbol, BUY, self.rng.randint(5, 40))
            elif best_bid - state.fair > 2:
                self._market(self.informed, symbol, SELL, self.rng.randint(5, 40))

    def _market(self, account, symbol, side, qty) -> None:
        try:
            self.exchange.place_order(account, symbol, side, "market", qty)
        except RejectError:
            pass

    # Used by the API to show how far the market is from fair value after
    # a round ends. Not exposed during trading.
    def fair_values(self) -> Dict[str, float]:
        out = {}
        for symbol, state in self.state.items():
            out[symbol] = self.exchange.to_price(state.fair)
        return out

    def ensure_liquidity(self) -> List[str]:
        """Re-seed any side of a book that has emptied out."""
        reseeded = []
        for symbol, state in self.state.items():
            book = self.exchange.books[symbol]
            if book.best_bid() is None or book.best_ask() is None:
                self._seed_book(symbol)
                reseeded.append(symbol)
        return reseeded
