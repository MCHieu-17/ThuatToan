import random
from dataclasses import replace

import pytest

from evrp.algorithms.charging_dp import solve_charging
from evrp.algorithms.ga_vns import Chromosome, crossover, mutate, neighbor
from evrp.charging.calendar import StationCalendar
from evrp.config import Config
from evrp.domain import Curve, Instance, Node, VehicleState
from evrp.validation import validate_trace


def tiny_instance():
    return Instance("tiny", {0:Node(0,"depot",0,0), 1:Node(1,"station",3,0,station_type="fast"),
                             2:Node(2,"customer",6,0)},0,2,.25,10,5,
                    {"fast":Curve(((0,0),(1.6,.2),(2,.4)))})


def test_dp_inserts_station_and_partial_charge():
    instance = tiny_instance()
    config = Config(vehicles=1,dynamic_fraction=0,time_step_hours=.05,soc_step=.1,
                    candidate_stations=0,max_labels=0,dp_budget_seconds=5,
                    w_time=1,w_electricity=1,w_degradation=0).validate()
    result = solve_charging(instance,config,[2],VehicleState(0,0,0,2),StationCalendar(config),{2:0})
    assert result.status == "optimal_discrete"
    charge = [a for a in result.plan.actions if a.kind == "charge"]
    assert charge and any(a.energy_after < 2 - 1e-8 for a in charge)
    assert validate_trace(instance,config,{2:0},result.plan.actions)["valid"]


def test_dp_waits_for_cheaper_tou():
    instance = tiny_instance()
    config = Config(vehicles=1,dynamic_fraction=0,time_step_hours=.05,soc_step=.1,
                    candidate_stations=0,max_labels=0,dp_budget_seconds=5,
                    start_clock_hour=0,tou=[{"start":0,"end":1,"price":10},
                                           {"start":1,"end":24,"price":.1}],
                    w_time=.01,w_electricity=1,w_degradation=0).validate()
    result = solve_charging(instance,config,[2],VehicleState(0,0,0,2),StationCalendar(config),{2:0})
    assert result.plan is not None
    assert all(a.start >= 1-1e-8 for a in result.plan.actions if a.kind == "charge")
    assert any(a.kind == "wait" and a.note == "station_or_TOU_wait" for a in result.plan.actions)


def test_dp_timeout_is_not_infeasibility(demo, config):
    config.max_labels = 1
    result = solve_charging(demo,config,[6],VehicleState(0,0,0,5),StationCalendar(config),{6:0})
    assert result.plan is None and result.status == "search_limit"


def test_genetic_operators_preserve_all_customers():
    rng = random.Random(12)
    a = Chromosome((1,2,3,4,5),(0,1,0,1,0))
    b = Chromosome((5,3,1,4,2),(1,0,0,1,1))
    for i in range(100):
        child = crossover(a,b,rng)
        child = mutate(child,[0,1],rng)
        child = neighbor(child,[0,1],i%3,rng)
        flat = [n for route in child.decode([0,1]).values() for n in route]
        assert sorted(flat) == [1,2,3,4,5]
        assert len(child.order) == len(child.vehicles) == 5
        a = child
