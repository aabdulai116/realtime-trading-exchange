"""Small Python client for writing trading bots against the exchange.

    from exchange_client import ExchangeClient

    client = ExchangeClient("http://localhost:8000")
    client.register("my_bot")
    client.buy("ACME", qty=10, price=99.95)
    for update in client.stream():
        print(update["books"]["ACME"]["mid"])
"""

import json
from typing import Iterator, Optional

import httpx


class ExchangeError(Exception):
    pass


class ExchangeClient:
    def __init__(self, base_url: str = "http://localhost:8000", api_key: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.http = httpx.Client(base_url=self.base_url, timeout=5.0)

    # ---------------- helpers ----------------
    def _headers(self):
        if not self.api_key:
            raise ExchangeError("call register() or pass api_key first")
        return {"X-API-Key": self.api_key}

    def _check(self, response):
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail")
            except ValueError:
                detail = response.text
            raise ExchangeError(f"{response.status_code}: {detail}")
        return response.json()

    # ---------------- account ----------------
    def register(self, name: str) -> str:
        data = self._check(self.http.post("/api/register", json={"name": name}))
        self.api_key = data["api_key"]
        return self.api_key

    def account(self) -> dict:
        return self._check(self.http.get("/api/me", headers=self._headers()))

    def position(self, symbol: str) -> int:
        for row in self.account()["positions"]:
            if row["symbol"] == symbol:
                return row["qty"]
        return 0

    # ---------------- market data ----------------
    def book(self, symbol: str, levels: int = 10) -> dict:
        return self._check(self.http.get(f"/api/book/{symbol}", params={"levels": levels}))

    def trades(self, symbol: str, limit: int = 50) -> list:
        return self._check(self.http.get(f"/api/trades/{symbol}", params={"limit": limit}))

    def news(self) -> list:
        return self._check(self.http.get("/api/news"))

    # ---------------- orders ----------------
    def order(self, symbol: str, side: str, qty: int, price: Optional[float] = None) -> dict:
        body = {"symbol": symbol, "side": side, "qty": qty}
        if price is None:
            body["type"] = "market"
        else:
            body["type"] = "limit"
            body["price"] = round(price, 2)
        return self._check(self.http.post("/api/orders", json=body, headers=self._headers()))

    def buy(self, symbol: str, qty: int, price: Optional[float] = None) -> dict:
        return self.order(symbol, "buy", qty, price)

    def sell(self, symbol: str, qty: int, price: Optional[float] = None) -> dict:
        return self.order(symbol, "sell", qty, price)

    def cancel(self, order_id: int) -> dict:
        return self._check(self.http.delete(f"/api/orders/{order_id}", headers=self._headers()))

    def cancel_all(self, symbol: Optional[str] = None) -> int:
        params = {"symbol": symbol} if symbol else None
        data = self._check(self.http.delete("/api/orders", params=params, headers=self._headers()))
        return data["cancelled"]

    def open_orders(self) -> list:
        return self._check(self.http.get("/api/orders", headers=self._headers()))

    # ---------------- streaming ----------------
    def stream(self) -> Iterator[dict]:
        """Yield every market update pushed over the WebSocket."""
        from websockets.sync.client import connect

        ws_url = self.base_url.replace("http", "ws", 1) + "/ws"
        if self.api_key:
            ws_url += f"?api_key={self.api_key}"
        with connect(ws_url) as socket:
            for raw in socket:
                yield json.loads(raw)
