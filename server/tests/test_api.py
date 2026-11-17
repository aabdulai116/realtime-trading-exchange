def best_prices(client, symbol="ACME"):
    book = client.get(f"/api/book/{symbol}").json()
    return book["bids"][0]["price"], book["asks"][0]["price"]


def test_public_market_data(client):
    assert client.get("/api/health").json()["status"] == "ok"
    symbols = [row["symbol"] for row in client.get("/api/symbols").json()]
    assert symbols == ["ACME", "ZEUS"]
    book = client.get("/api/book/ACME?levels=5").json()
    assert len(book["bids"]) == 5
    assert book["bids"][0]["price"] < book["asks"][0]["price"]
    assert client.get("/api/book/NOPE").status_code == 404


def test_trading_needs_an_api_key(client):
    response = client.post("/api/orders", json={"symbol": "ACME", "side": "buy", "qty": 1, "price": 99})
    assert response.status_code == 401


def test_market_buy_fills_at_best_ask_and_updates_account(client, trader):
    alice = trader("alice")
    _, ask = best_prices(client)
    response = client.post("/api/orders", headers=alice,
                           json={"symbol": "ACME", "side": "buy", "type": "market", "qty": 3})
    assert response.status_code == 200
    body = response.json()
    assert body["filled"] == 3
    assert body["fills"][0]["price"] == ask

    me = client.get("/api/me", headers=alice).json()
    acme = [p for p in me["positions"] if p["symbol"] == "ACME"][0]
    assert acme["qty"] == 3
    assert me["cash"] < 0
    assert me["trades"] >= 1


def test_two_humans_trade_with_each_other(client, trader):
    alice = trader("alice")
    bob = trader("bob")
    bid, ask = best_prices(client)
    # Alice improves the bid inside the spread, Bob hits it.
    price = round(bid + 0.01, 2)
    if price >= ask:
        price = bid
    posted = client.post("/api/orders", headers=alice,
                         json={"symbol": "ACME", "side": "buy", "qty": 5, "price": price}).json()
    assert posted["resting"] == 5
    hit = client.post("/api/orders", headers=bob,
                      json={"symbol": "ACME", "side": "sell", "type": "market", "qty": 5}).json()
    assert hit["fills"][0]["price"] == price

    alice_view = client.get("/api/me", headers=alice).json()
    bob_view = client.get("/api/me", headers=bob).json()
    assert alice_view["positions"][0]["qty"] == 5
    assert bob_view["positions"][0]["qty"] == -5
    assert alice_view["cash"] == -bob_view["cash"]


def test_cancel_only_your_own_orders(client, trader):
    alice = trader("alice")
    bob = trader("bob")
    bid, _ = best_prices(client)
    order = client.post("/api/orders", headers=alice,
                        json={"symbol": "ACME", "side": "buy", "qty": 2, "price": round(bid - 0.05, 2)}).json()
    order_id = order["order_id"]
    assert client.delete(f"/api/orders/{order_id}", headers=bob).status_code == 404
    assert len(client.get("/api/orders", headers=alice).json()) == 1
    assert client.delete(f"/api/orders/{order_id}", headers=alice).status_code == 200
    assert client.get("/api/orders", headers=alice).json() == []


def test_risk_checks(client, trader):
    alice = trader("alice")
    bid, _ = best_prices(client)
    too_big = client.post("/api/orders", headers=alice,
                          json={"symbol": "ACME", "side": "buy", "qty": 1000, "price": bid})
    assert too_big.status_code == 400

    far_away = client.post("/api/orders", headers=alice,
                           json={"symbol": "ACME", "side": "buy", "qty": 1, "price": 10.0})
    assert "too far" in far_away.json()["detail"]

    # Five resting orders of 100 reach the 500 share limit; the sixth is rejected.
    for _ in range(5):
        ok = client.post("/api/orders", headers=alice,
                         json={"symbol": "ACME", "side": "buy", "qty": 100, "price": round(bid - 0.5, 2)})
        assert ok.status_code == 200
    blocked = client.post("/api/orders", headers=alice,
                          json={"symbol": "ACME", "side": "buy", "qty": 1, "price": round(bid - 0.5, 2)})
    assert "position limit" in blocked.json()["detail"]


def test_rate_limit(client, trader, app):
    alice = trader("alice")
    bid, _ = best_prices(client)
    app.state.exchange.settings.orders_per_second = 0.0
    statuses = []
    for _ in range(45):
        response = client.post("/api/orders", headers=alice,
                               json={"symbol": "ACME", "side": "buy", "qty": 1, "price": round(bid - 1, 2)})
        statuses.append(response.status_code)
    assert statuses.count(200) == app.state.exchange.settings.order_burst
    assert statuses[-1] == 400


def test_self_trade_prevention(client, trader):
    alice = trader("alice")
    bid, ask = best_prices(client)
    mine = client.post("/api/orders", headers=alice,
                       json={"symbol": "ACME", "side": "sell", "qty": 2, "price": round(ask - 0.01, 2)}).json()
    if mine["order_id"] is None:
        return  # spread was one tick, nothing to test
    result = client.post("/api/orders", headers=alice,
                         json={"symbol": "ACME", "side": "buy", "type": "market", "qty": 1}).json()
    assert mine["order_id"] in result["self_trade_cancels"]
    assert result["fills"][0]["price"] >= ask


def test_simulation_produces_trades_news_and_leaderboard(client, app):
    simulation = app.state.simulation
    simulation.settings.news_prob = 0.2
    for _ in range(200):
        simulation.step()
    assert client.get("/api/trades/ACME").json()
    assert client.get("/api/news").json()
    board = client.get("/api/leaderboard").json()
    assert board[0]["rank"] == 1
    assert client.get("/api/candles/ACME").json()


def test_websocket_streams_market_and_private_account(client, trader, app):
    alice = trader("alice")
    key = alice["X-API-Key"]
    client.post("/api/orders", headers=alice,
                json={"symbol": "ACME", "side": "buy", "type": "market", "qty": 2})
    exchange = app.state.exchange
    hub = app.state.hub

    with client.websocket_connect(f"/ws?api_key={key}") as ws:
        # The background loop is off in tests, so push one update by hand.
        trades = exchange.drain_trades()
        client.portal.call(hub.broadcast, exchange, trades, exchange.leaderboard())
        message = ws.receive_json()

    assert message["type"] == "market"
    assert set(message["books"]) == {"ACME", "ZEUS"}
    assert message["trades"][0]["buyer"] == "alice"
    assert message["account"]["name"] == "alice"
    assert message["account"]["positions"][0]["qty"] == 2


def test_anonymous_websocket_gets_no_account(client, app):
    exchange = app.state.exchange
    with client.websocket_connect("/ws") as ws:
        client.portal.call(app.state.hub.broadcast, exchange, [], [])
        message = ws.receive_json()
    assert "account" not in message


def test_names_are_unique(client, trader):
    trader("alice")
    response = client.post("/api/register", json={"name": "Alice"})
    assert response.status_code == 400
    assert client.post("/api/register", json={"name": "House MM"}).status_code == 400


def test_off_tick_prices_are_rejected(client, trader):
    alice = trader("alice")
    bid, _ = best_prices(client)
    response = client.post("/api/orders", headers=alice,
                           json={"symbol": "ACME", "side": "buy", "qty": 1, "price": bid - 0.005})
    assert response.status_code == 400
    assert "multiple" in response.json()["detail"]


def test_every_endpoint_runs_on_the_event_loop(app):
    """Plain def endpoints run in a thread pool and race the market loop."""
    import inspect

    from fastapi.routing import APIRoute

    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        assert inspect.iscoroutinefunction(route.endpoint), route.path
        for dependency in route.dependant.dependencies:
            assert inspect.iscoroutinefunction(dependency.call), route.path


def test_market_loop_survives_a_failing_step():
    import time as clock

    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app

    app = create_app(Settings(db_path=":memory:", run_simulation=True, tick_seconds=0.01))
    simulation = app.state.simulation
    real_step = simulation.step
    calls = {"n": 0}

    def flaky_step():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        real_step()

    simulation.step = flaky_step
    with TestClient(app):
        clock.sleep(0.5)
    assert calls["n"] > 5


def test_shares_and_cash_are_conserved(client, trader, app):
    """Every trade has a buyer and a seller, so totals across accounts stay at zero."""
    exchange = app.state.exchange
    simulation = app.state.simulation
    alice = trader("alice")
    for step in range(300):
        simulation.step()
        if step % 10 == 0:
            client.post("/api/orders", headers=alice,
                        json={"symbol": "ZEUS", "side": "buy" if step % 20 else "sell",
                              "type": "market", "qty": 3})
    for symbol in exchange.books:
        total_shares = 0
        for account in exchange.accounts.values():
            total_shares += account.positions.get(symbol, 0)
        assert total_shares == 0
    total_cash = 0
    for account in exchange.accounts.values():
        total_cash += account.cash_ticks
    assert total_cash == 0
    assert exchange.next_trade_id > 100


def test_order_ids_are_unique_across_symbols(client, trader, app):
    alice = trader("alice")
    acme_bid, _ = best_prices(client, "ACME")
    zeus_bid, _ = best_prices(client, "ZEUS")
    acme = client.post("/api/orders", headers=alice,
                       json={"symbol": "ACME", "side": "buy", "qty": 1, "price": round(acme_bid - 0.5, 2)}).json()
    zeus = client.post("/api/orders", headers=alice,
                       json={"symbol": "ZEUS", "side": "buy", "qty": 1, "price": round(zeus_bid - 0.5, 2)}).json()
    assert acme["order_id"] != zeus["order_id"]

    # Cancelling the ZEUS order must leave the ACME order alone.
    assert client.delete(f"/api/orders/{zeus['order_id']}", headers=alice).status_code == 200
    remaining = client.get("/api/orders", headers=alice).json()
    assert [o["symbol"] for o in remaining] == ["ACME"]


def test_every_resting_order_can_be_found_after_trading(app):
    exchange = app.state.exchange
    simulation = app.state.simulation
    for _ in range(500):
        simulation.step()
        simulation.ensure_liquidity()
    live = {}
    for symbol, book in exchange.books.items():
        for account in exchange.accounts.values():
            for order in book.orders_for(account.trader_id):
                assert order.id not in live, "duplicate order id"
                live[order.id] = symbol
    assert live == exchange.order_symbol
