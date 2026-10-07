from pathlib import Path

import pytest

from evrp.config import Config
from evrp.io.montoya import load_instance


@pytest.fixture
def demo():
    return load_instance(Path(__file__).parents[1] / "data/demo.xml")


@pytest.fixture
def config():
    return Config(vehicles=3, dynamic_fraction=0.5, release_until_fraction=0.1,
                  station_power_kw=6, charger_power_kw=8, solver_budget_seconds=2,
                  dp_budget_seconds=1, population=4, generations=2, elite_size=1,
                  vns_iterations=2).validate()
