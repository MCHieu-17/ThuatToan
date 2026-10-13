from __future__ import annotations

import pytest

from evrp.config import Config
from evrp.domain import CUSTOMER, DEPOT, STATION, Curve, Instance, Node, StationInfo


@pytest.fixture
def tiny_instance() -> Instance:
    nodes = {
        0: Node(0, DEPOT, 0.0, 0.0),
        1: Node(1, CUSTOMER, 12.0, 0.0, service_hours=0.1),
        2: Node(2, CUSTOMER, 0.0, 12.0, service_hours=0.1),
        3: Node(3, CUSTOMER, 8.0, 8.0, service_hours=0.1),
        4: Node(4, STATION, 6.0, 0.0, station_type="fast"),
    }
    return Instance(
        name="tiny",
        nodes=nodes,
        depot=0,
        capacity_kwh=10.0,
        consumption_kwh_km=0.1,
        speed_kmh=20.0,
        horizon_hours=12.0,
        curves={"fast": Curve(((0.0, 0.0), (8.0, 0.5), (10.0, 0.7)))},
        stations_info={4: StationInfo(ports=1, power_kw=30.0, charger_kw=30.0)},
        vehicles=2,
        source="synthetic",
    )


@pytest.fixture
def tiny_config() -> Config:
    config = Config()
    config.population = 6
    config.generations = 4
    config.vns_iterations = 3
    config.dp_budget_seconds = 2.0
    config.solver_budget_seconds = 5.0
    config.max_labels = 20000
    return config.validate()