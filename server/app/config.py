"""Exchange settings. Override any of them with environment variables,
for example EXCHANGE_TICK_SECONDS=0.5."""

import os
from dataclasses import dataclass, field
from typing import List


def _env(name, default, cast):
    value = os.environ.get(name)
    if value is None:
        return default
    return cast(value)


@dataclass
class Settings:
    symbols: List[str] = field(default_factory=lambda: ["ACME", "ZEUS"])
    start_prices: List[float] = field(default_factory=lambda: [100.00, 50.00])
    tick_size: float = 0.01

    # How often the market simulation steps and pushes updates (seconds).
    tick_seconds: float = _env("EXCHANGE_TICK_SECONDS", 0.25, float)
    run_simulation: bool = _env("EXCHANGE_RUN_SIM", True, lambda v: v.lower() != "false")
    seed: int = _env("EXCHANGE_SEED", 7, int)

    # Risk limits for every account, bots included.
    max_order_qty: int = 100
    position_limit: int = 500
    bot_position_limit: int = 5000
    price_band_pct: float = 0.10       # limit prices must be within 10% of mid
    orders_per_second: float = 20.0    # token bucket refill rate per account
    order_burst: int = 40

    # Market environment.
    fundamental_vol: float = 0.6       # ticks per step
    news_prob: float = 0.004           # chance of a news event each step
    news_impact_ticks: float = 60.0    # std dev of a news move

    db_path: str = _env("EXCHANGE_DB", "exchange.db", str)
    candle_seconds: int = 5
    history_candles: int = 400


settings = Settings()
