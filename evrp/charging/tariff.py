from evrp.config import Config


def price_and_boundary(time: float, config: Config) -> tuple[float, float]:
    """Price and next boundary in elapsed hours; TOU repeats every 24 hours."""
    absolute = config.start_clock_hour + time
    hour = absolute % 24
    for band in config.tou:
        if band["start"] <= hour < band["end"]:
            return band["price"], time + band["end"] - hour
    raise ValueError("TOU does not cover the current hour")


def electricity_cost(start: float, end: float, power_kw: float, config: Config) -> float:
    cost, current = 0.0, start
    while current < end - 1e-10:
        price, boundary = price_and_boundary(current, config)
        following = min(end, boundary)
        cost += power_kw * (following - current) * price
        current = following
    return cost
