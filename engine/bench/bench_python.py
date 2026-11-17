"""Same message mix as bench_order_book.cpp, driven from Python through the
pybind11 bindings. Shows the cost of crossing from Python into C++."""

import random
import time

import matching_engine as me


def main(messages=300_000):
    rng = random.Random(42)
    book = me.OrderBook()
    live = []
    mid = 10_000
    start = time.perf_counter()
    for i in range(messages):
        u = rng.random()
        if u < 0.60 or not live:
            side = me.Side.BUY if rng.random() < 0.5 else me.Side.SELL
            if side == me.Side.BUY:
                price = mid - rng.randint(0, 20)
            else:
                price = mid + rng.randint(0, 20)
            result = book.add_limit(rng.randint(1, 50), side, price, rng.randint(1, 10))
            if result.id:
                live.append(result.id)
        elif u < 0.92:
            k = rng.randrange(len(live))
            book.cancel(live[k])
            live[k] = live[-1]
            live.pop()
        else:
            side = me.Side.BUY if rng.random() < 0.5 else me.Side.SELL
            book.add_market(rng.randint(1, 50), side, rng.randint(1, 10))
        if i % 1000 == 0:
            mid += 1 if rng.random() < 0.5 else -1
    seconds = time.perf_counter() - start
    print(f"messages     {messages}")
    print(f"trades       {book.trade_count}")
    print(f"throughput   {messages / seconds / 1e6:.2f} million msgs/sec (from Python)")


if __name__ == "__main__":
    main()
