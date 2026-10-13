"""Time-of-use electricity tariff integration.

The simulation clock is elapsed hours from the start of the day; the tariff is
defined on the 24-hour wall clock. `start_clock_hour` links the two.
"""
from __future__ import annotations

from evrp.config import Config


def band_at(config: Config, clock_hour: float) -> dict:
    clock = clock_hour % 24.0
    for band in config.tou:
        if band["start"] <= clock < band["end"] - 1e-12:
            return band
    return config.tou[-1]


def price_at(config: Config, clock_hour: float) -> float:
    return band_at(config, clock_hour)["price"]


def integrate(config: Config, start: float, end: float, power_kw: float) -> float:
    """Cost of drawing `power_kw` over elapsed interval [start, end) in hours."""
    if power_kw <= 0 or end <= start:
        return 0.0
    total = 0.0
    t = start
    while t < end - 1e-12:
        clock = (config.start_clock_hour + t) % 24.0
        band = band_at(config, clock)
        boundary = band["end"] % 24.0
        if boundary == 0.0:
            boundary = 24.0
        step = min(end - t, (boundary - clock) % 24.0 or 24.0)
        total += power_kw * step * band["price"]
        t += step
    return total


def cost_of_segments(config: Config, segments) -> float:
    return sum(integrate(config, start, end, power) for start, end, power in segments)