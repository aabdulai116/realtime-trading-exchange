"""FastAPI app: REST endpoints for trading, a WebSocket market data feed,
and the background loop that runs the simulated market.

Every endpoint is `async def` on purpose. FastAPI runs plain `def` endpoints
in a thread pool, which would let requests touch the order books, accounts
and SQLite connection at the same time as the market loop. Keeping all of it
on the event loop thread means only one piece of code changes state at a time.
"""

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Dict, Optional, Set

from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .bots import MarketSimulation
from .config import Settings, settings as default_settings
from .exchange import Account, Exchange, RejectError
from .store import Store

log = logging.getLogger("exchange")

WEB_DIST = os.path.join(os.path.dirname(__file__), "..", "..", "web", "dist")


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=32)


class OrderRequest(BaseModel):
    symbol: str
    side: str = Field(pattern="^(buy|sell)$")
    type: str = Field(default="limit", pattern="^(limit|market)$")
    qty: int = Field(gt=0)
    price: Optional[float] = Field(default=None, gt=0)


class Hub:
    """Tracks WebSocket clients and pushes snapshots to them."""

    def __init__(self):
        self.clients: Dict[WebSocket, Optional[Account]] = {}

    async def connect(self, ws: WebSocket, account: Optional[Account]) -> None:
        await ws.accept()
        self.clients[ws] = account

    def disconnect(self, ws: WebSocket) -> None:
        self.clients.pop(ws, None)

    async def broadcast(self, exchange: Exchange, new_trades, leaderboard) -> None:
        if not self.clients:
            return
        public = {
            "type": "market",
            "time": time.time(),
            "books": {s: exchange.book_snapshot(s) for s in exchange.books},
            "trades": [exchange.trade_view(t) for t in new_trades],
            "news": list(exchange.news)[:10],
            "leaderboard": leaderboard,
        }
        dead = []
        for ws, account in list(self.clients.items()):
            message = dict(public)
            if account is not None:
                message["account"] = exchange.account_view(account)
                message["orders"] = exchange.open_orders(account)
            try:
                await asyncio.wait_for(ws.send_json(message), timeout=1.0)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


def create_app(config: Optional[Settings] = None) -> FastAPI:
    config = config or default_settings
    store = Store(config.db_path)
    exchange = Exchange(config, store=store)
    simulation = MarketSimulation(exchange, seed=config.seed)
    hub = Hub()

    # Bring back accounts that registered in earlier sessions.
    for name, api_key in store.load_accounts():
        if api_key in exchange.by_key:
            continue
        try:
            exchange.register(name, api_key=api_key, persist=False)
        except RejectError:
            pass  # a bot now uses this name, or it was saved twice

    async def market_loop():
        last_board = 0.0
        board = exchange.leaderboard()
        while True:
            started = time.monotonic()
            try:
                simulation.step()
                simulation.ensure_liquidity()
                trades = exchange.drain_trades()
                if trades:
                    store.save_trades(trades, exchange)
                if started - last_board > 1.0:
                    board = exchange.leaderboard()
                    last_board = started
                await hub.broadcast(exchange, trades, board)
            except asyncio.CancelledError:
                raise
            except Exception:
                # One bad step must not freeze the whole market.
                log.exception("market loop step failed")
            elapsed = time.monotonic() - started
            await asyncio.sleep(max(0.0, config.tick_seconds - elapsed))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = None
        if config.run_simulation:
            task = asyncio.create_task(market_loop())
        yield
        if task is not None:
            task.cancel()

    app = FastAPI(title="Realtime Trading Exchange", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
    )
    app.state.exchange = exchange
    app.state.simulation = simulation
    app.state.store = store
    app.state.hub = hub

    async def current_account(x_api_key: Optional[str] = Header(default=None)) -> Account:
        try:
            return exchange.authenticate(x_api_key)
        except PermissionError:
            raise HTTPException(status_code=401, detail="missing or unknown X-API-Key header")

    # ---------------- Public market data ----------------
    @app.get("/api/health")
    async def health():
        return {"status": "ok", "symbols": list(exchange.books)}

    @app.get("/api/symbols")
    async def symbols():
        return [
            {"symbol": s, "tick_size": config.tick_size, "last": exchange.to_price(exchange.last_price[s])}
            for s in exchange.books
        ]

    def check_symbol(symbol: str) -> str:
        if symbol not in exchange.books:
            raise HTTPException(status_code=404, detail=f"unknown symbol {symbol}")
        return symbol

    @app.get("/api/book/{symbol}")
    async def book(symbol: str, levels: int = Query(default=10, ge=1, le=50)):
        return exchange.book_snapshot(check_symbol(symbol), levels)

    @app.get("/api/trades/{symbol}")
    async def trades(symbol: str, limit: int = Query(default=50, ge=1, le=200)):
        recent = list(exchange.trades[check_symbol(symbol)])[-limit:]
        return [exchange.trade_view(t) for t in reversed(recent)]

    @app.get("/api/candles/{symbol}")
    async def candles(symbol: str):
        return exchange.candle_view(check_symbol(symbol))

    @app.get("/api/news")
    async def news():
        return list(exchange.news)

    @app.get("/api/leaderboard")
    async def leaderboard():
        return exchange.leaderboard()

    # ---------------- Accounts and trading ----------------
    @app.post("/api/register")
    async def register(request: RegisterRequest):
        try:
            account = exchange.register(request.name)
        except RejectError as error:
            raise HTTPException(status_code=400, detail=str(error))
        return {"trader_id": account.trader_id, "name": account.name, "api_key": account.api_key}

    @app.get("/api/me")
    async def me(account: Account = Depends(current_account)):
        return exchange.account_view(account)

    @app.get("/api/orders")
    async def my_orders(account: Account = Depends(current_account)):
        return exchange.open_orders(account)

    @app.post("/api/orders")
    async def place(request: OrderRequest, account: Account = Depends(current_account)):
        try:
            return exchange.place_order(
                account, request.symbol, request.side, request.type, request.qty, request.price
            )
        except RejectError as error:
            raise HTTPException(status_code=400, detail=str(error))

    @app.delete("/api/orders/{order_id}")
    async def cancel(order_id: int, account: Account = Depends(current_account)):
        if not exchange.cancel(account, order_id):
            raise HTTPException(status_code=404, detail="no open order with that id")
        return {"cancelled": order_id}

    @app.delete("/api/orders")
    async def cancel_all(symbol: Optional[str] = None, account: Account = Depends(current_account)):
        if symbol is not None:
            check_symbol(symbol)
        return {"cancelled": exchange.cancel_all(account, symbol)}

    # ---------------- Streaming ----------------
    @app.websocket("/ws")
    async def websocket(ws: WebSocket, api_key: Optional[str] = None):
        account = None
        if api_key:
            account = exchange.by_key.get(api_key)
        await hub.connect(ws, account)
        try:
            while True:
                await ws.receive_text()   # clients may send pings; we ignore them
        except WebSocketDisconnect:
            hub.disconnect(ws)

    # ---------------- Web app ----------------
    dist = os.path.abspath(WEB_DIST)
    if os.path.isdir(dist):
        app.mount("/assets", StaticFiles(directory=os.path.join(dist, "assets")), name="assets")

        @app.get("/")
        async def index():
            return FileResponse(os.path.join(dist, "index.html"))

    return app


app = create_app()
