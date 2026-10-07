import random
from dataclasses import dataclass

from evrp.config import Config
from evrp.domain import Instance


@dataclass
class Scenario:
    releases: dict[int, float]
    seed: int

    def known(self, time: float) -> list[int]:
        return sorted(n for n, release in self.releases.items() if release <= time + 1e-9)


def generate_scenario(instance: Instance, config: Config, seed: int | None = None) -> Scenario:
    seed = config.seed if seed is None else seed
    rng = random.Random(seed)
    customers = instance.customers
    dynamic = set(rng.sample(customers, round(len(customers) * config.dynamic_fraction)))
    latest = instance.horizon_hours * config.release_until_fraction
    releases = {n: (round(rng.uniform(0.001, max(0.001, latest)), 6)
                    if n in dynamic and latest > 0 else 0.0) for n in customers}
    return Scenario(releases, seed)
