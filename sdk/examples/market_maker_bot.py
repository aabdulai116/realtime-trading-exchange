"""Example bot: an inventory aware market maker.

It quotes a bid and an ask around the mid price and leans its quotes against
its position (the Avellaneda and Stoikov idea), so it sells when it is long
and buys when it is short.

    python sdk/examples/market_maker_bot.py --name my_mm --symbol ACME
"""

import argparse
import math
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from exchange_client import ExchangeClient, ExchangeError  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--name", default="example_mm")
    parser.add_argument("--symbol", default="ACME")
    parser.add_argument("--size", type=int, default=10)
    parser.add_argument("--half-spread", type=float, default=0.02, help="dollars")
    parser.add_argument("--skew", type=float, default=0.0005, help="dollars per share held")
    parser.add_argument("--max-position", type=int, default=200)
    parser.add_argument("--seconds", type=float, default=120)
    args = parser.parse_args()

    client = ExchangeClient(args.url)
    client.register(args.name)
    print(f"Registered {args.name}. Trading {args.symbol} for {args.seconds:.0f} seconds.")

    end = time.time() + args.seconds
    last_quote = None
    for update in client.stream():
        if time.time() > end:
            break
        book = update["books"][args.symbol]
        account = update["account"]
        position = 0
        for row in account["positions"]:
            if row["symbol"] == args.symbol:
                position = row["qty"]

        # Lean the quotes against inventory.
        reservation = book["mid"] - position * args.skew
        bid = math.floor((reservation - args.half_spread) * 100) / 100
        ask = math.ceil((reservation + args.half_spread) * 100) / 100
        if (bid, ask) == last_quote:
            continue
        last_quote = (bid, ask)

        try:
            client.cancel_all(args.symbol)
            if position < args.max_position:
                client.buy(args.symbol, args.size, bid)
            if position > -args.max_position:
                client.sell(args.symbol, args.size, ask)
        except ExchangeError as error:
            print("order rejected:", error)

        print(f"pos {position:5d}  bid {bid:.2f}  ask {ask:.2f}  pnl {account['pnl']:9.2f}")

    client.cancel_all()
    print("Final account:", client.account()["pnl"])


if __name__ == "__main__":
    main()
