from __future__ import annotations

import pytest

from evrp.charging import tariff
from evrp.charging.calendar import StationCalendar
from evrp.charging.model import charging_action, discharge_transition
from evrp.config import Config
from evrp.domain import Curve


def test_curve_duration_across_segments():
    curve = Curve(((0.0, 0.0), (8.0, 0.5), (10.0, 0.7)))
    assert curve.duration(0.0, 8.0, 100.0) == pytest.approx(0.5)
    assert curve.duration(8.0, 10.0, 100.0) == pytest.approx(0.2)
    assert curve.duration(0.0, 10.0, 100.0) == pytest.approx(0.7)


def test_curve_power_cap_tapers():
    curve = Curve(((0.0, 0.0), (8.0, 0.5), (10.0, 0.7)))
    assert curve.duration(0.0, 8.0, 8.0) == pytest.approx(1.0)


def test_tou_integration_wraps_midnight():
    config = Config()
    config.start_clock_hour = 22.0
    config.tou = [
        {"start": 0.0, "end": 6.0, "price": 0.1},
        {"start": 6.0, "end": 18.0, "price": 0.5},
        {"start": 18.0, "end": 24.0, "price": 0.2},
    ]
    cost = tariff.integrate(config, 0.0, 4.0, 10.0)
    assert cost == pytest.approx(10.0 * (2.0 * 0.2 + 2.0 * 0.1))


def test_discharge_events():
    config = Config()
    capacity = 10.0
    low, events = discharge_transition(5.0, 1.0, False, capacity, config)
    assert low is True and events == 1
    low, events = discharge_transition(1.0, 0.5, low, capacity, config)
    assert low is True and events == 0
    low, events = discharge_transition(3.0, 4.0, low, capacity, config)
    assert low is False and events == 0


def test_charging_action_cost_and_deep_charge():
    from evrp.domain import Instance, Node, StationInfo
    config = Config()
    instance = Instance(
        name="t", nodes={0: Node(0, "depot", 0, 0), 4: Node(4, "station", 0, 0, station_type="fast")},
        depot=0, capacity_kwh=10.0, consumption_kwh_km=0.1, speed_kmh=20.0, horizon_hours=12.0,
        curves={"fast": Curve(((0.0, 0.0), (8.0, 0.5), (10.0, 0.7)))},
        stations_info={4: StationInfo(1, 30.0, 30.0)}, vehicles=1)
    action = charging_action(instance, config, 0, 4, 1.0, 1.0, 8.0, 30.0)
    assert action.end == pytest.approx(1.0 + 7.0 / 16.0)
    assert action.deep_charge == 1
    assert action.electricity_cost > 0


def test_calendar_ports_and_power():
    calendar = StationCalendar()
    assert calendar.available(4, 0.0, 1.0, 20.0, ports=1, total_power_kw=30.0)
    calendar.reserve(4, 0.0, 1.0, 20.0)
    assert not calendar.available(4, 0.5, 1.5, 20.0, ports=1, total_power_kw=30.0)
    assert not calendar.available(4, 0.5, 1.5, 20.0, ports=2, total_power_kw=30.0)
    assert calendar.available(4, 1.0, 2.0, 20.0, ports=1, total_power_kw=30.0)