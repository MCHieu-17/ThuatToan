from __future__ import annotations

import pytest

from evrp.domain import CUSTOMER, DEPOT, STATION, Curve, Instance, Node, StationInfo
from evrp.simulation import simulate


def _realtime_instance(vehicles=2):
    nodes = {
        0: Node(0, DEPOT, 0.0, 0.0),
        1: Node(1, CUSTOMER, 12.0, 0.0, service_hours=0.1, release_hours=0.0),
        2: Node(2, CUSTOMER, 0.0, 12.0, service_hours=0.1, release_hours=2.0),
        3: Node(3, CUSTOMER, 8.0, 8.0, service_hours=0.1, release_hours=4.0),
        4: Node(4, STATION, 6.0, 0.0, station_type="fast"),
    }
    return Instance(
        name="rt", nodes=nodes, depot=0, capacity_kwh=10.0, consumption_kwh_km=0.1,
        speed_kmh=20.0, horizon_hours=12.0,
        curves={"fast": Curve(((0.0, 0.0), (8.0, 0.5), (10.0, 0.7)))},
        stations_info={4: StationInfo(1, 30.0, 30.0)}, vehicles=vehicles, source="synthetic")


def test_static_mode_serves_all(tiny_config):
    instance = _realtime_instance()
    result = simulate(instance, tiny_config, "greedy", seed=1, mode="static")
    assert result.served == result.total_customers


def test_dynamic_mode_does_not_serve_before_release(tiny_config):
    instance = _realtime_instance()
    tiny_config.replan_interval_hours = 1.0
    result = simulate(instance, tiny_config, "greedy", seed=1, mode="dynamic")
    release = {n.id: n.release_hours for n in instance.nodes.values() if n.kind == CUSTOMER}
    served_at = {}
    for action in result.actions:
        if action["kind"] == "service":
            served_at.setdefault(action["destination"], action["start"])
    for customer, start in served_at.items():
        assert start >= release[customer] - 1e-6


def test_all_algorithms_run_dynamic(tiny_config):
    instance = _realtime_instance()
    tiny_config.replan_interval_hours = 2.0
    for algorithm in ("greedy", "ga", "ga_vns"):
        result = simulate(instance, tiny_config, algorithm, seed=2, mode="dynamic")
        assert result.total_customers == 3
        assert 0 <= result.served <= result.total_customers


def test_unknown_algorithm_rejected(tiny_config):
    instance = _realtime_instance()
    with pytest.raises(ValueError):
        simulate(instance, tiny_config, "nope", seed=1)