from dataclasses import replace

import pytest

from evrp.charging.calendar import Booking, StationCalendar
from evrp.charging.model import charging_action, discharge_transition
from evrp.charging.tariff import electricity_cost
from evrp.domain import Action
from evrp.metrics import summarize


def test_nonlinear_taper_and_power_cap(demo, config):
    action = charging_action(demo, config, 0, 7, 0, 0, 5, 100)
    assert action.end == pytest.approx(1)
    assert [p for _, _, p in action.power_segments] == pytest.approx([8, 3, 1])
    limited = charging_action(demo, config, 0, 7, 0, 0, 5, 4)
    assert limited.end == pytest.approx(1.5)
    assert max(p for _, _, p in limited.power_segments) <= 4
    assert sum((end-start)*p for start,end,p in limited.power_segments) == pytest.approx(5)


def test_tou_split_across_boundary_and_midnight(config):
    config.start_clock_hour = 0
    config.tou = [{"start":0,"end":1,"price":1}, {"start":1,"end":24,"price":3}]
    assert electricity_cost(.5, 1.5, 2, config) == pytest.approx(4)
    assert electricity_cost(23.5, 24.5, 2, config) == pytest.approx(4)


def test_ports_and_total_power_are_separate(config):
    config.station_ports, config.station_power_kw, config.charger_power_kw = 2, 6, 8
    calendar = StationCalendar(config, [Booking(7,0,0,1,4)])
    assert calendar.available(7,0,1,2)
    assert not calendar.available(7,0,1,3)  # a free port but insufficient total kW
    calendar.bookings.append(Booking(7,1,0,1,1))
    assert not calendar.available(7,0,1,1)  # enough kW but no free port
    assert calendar.available(7,1,2,6)  # half-open intervals: touching is allowed
    assert calendar.available(8,0,1,6)


def test_calendar_clones_do_not_leak_candidate_bookings(config):
    calendar = StationCalendar(config)
    clone = calendar.clone()
    clone.reserve(Action(0,"charge",0,1,7,7,0,1,allocated_kw=2))
    assert not calendar.bookings and len(clone.bookings) == 1


def test_deep_discharge_counted_once_per_excursion(config):
    low, count = discharge_transition(1.0, .5, False, 5, config)
    assert (low, count) == (True, 1)
    low, count = discharge_transition(.5, .3, low, 5, config)
    assert (low, count) == (True, 0)


def test_service_not_in_objective_and_no_normalization(config):
    actions = [Action(0,"drive",0,1,0,1,5,3,deep_discharge=1),
               Action(0,"service",1,11,1,1,3,3),
               Action(0,"charge",11,13,7,7,1,4,electricity=7,deep_charge=1),
               Action(0,"wait",13,14,7,7,4,4)]
    config.w_time, config.w_electricity, config.w_degradation = 2,3,4
    metrics = summarize(actions, config)
    assert metrics["T_total"] == 4
    assert metrics["service_hours"] == 10
    assert metrics["D_battery_degradation"] == pytest.approx(1.4)
    assert metrics["F"] == pytest.approx(2*4 + 3*7 + 4*1.4)
