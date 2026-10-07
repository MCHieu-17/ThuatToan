from dataclasses import replace
import json

import pytest

from evrp.domain import Action, Solution
from evrp.io.results import save_result, write_summary
from evrp.metrics import summarize
from evrp.scenario import generate_scenario
from evrp.simulation.engine import commit_until, simulate
from evrp.validation import validate_trace


def test_commit_started_delivery_and_charge_without_splitting():
    drive = Action(0,"drive",0,1,0,1,5,4)
    service = Action(0,"service",1,1.5,1,1,4,4)
    charge = Action(0,"charge",2,3,7,7,1,4,deep_charge=1,allocated_kw=3)
    prefix, suffix = commit_until([drive,service,charge],.5)
    assert prefix == [drive,service] and suffix == [charge]
    prefix, suffix = commit_until([charge],2.5)
    assert prefix == [charge] and not suffix and prefix[0].deep_charge == 1


@pytest.mark.parametrize("algorithm",["baseline","ga_vns"])
def test_online_trace_and_roundtrip_exports(demo,config,tmp_path,algorithm):
    scenario = generate_scenario(demo,config,13)
    result = simulate(demo,config,scenario,algorithm)
    assert result.validation["valid"], result.validation["errors"]
    for decision in result.decisions:
        assert all(scenario.releases[n] <= decision["time"]+1e-9 for n in decision["known_customers"])
        assert set(decision["pending_customers"]) <= set(decision["known_customers"])
    services = [a.destination for a in result.actions if a.kind == "service"]
    assert len(services) == len(set(services))
    assert summarize(result.actions,config)["F"] == pytest.approx(result.metrics["F"])
    path = save_result(result,tmp_path)
    stored = json.loads(path.read_text())
    assert stored["config"] == config.to_dict()
    assert {int(k):v for k,v in stored["releases"].items()} == scenario.releases
    write_summary([result],tmp_path)
    assert (tmp_path/"comparison.csv").is_file() and (tmp_path/"statistics.csv").is_file()


def test_independent_checker_detects_corruption(demo,config):
    config.dynamic_fraction = 0
    result = simulate(demo,config,generate_scenario(demo,config),"baseline")
    actions = list(result.actions)
    index = next(i for i,a in enumerate(actions) if a.kind == "drive")
    actions[index] = replace(actions[index],energy_after=actions[index].energy_after+.3)
    check = validate_trace(demo,config,result.releases,actions)
    assert not check["valid"]
    assert any("energy" in e for e in check["errors"])


def test_scenario_never_silently_drops_unserved_orders(demo,config):
    config.vehicles = 1
    config.release_until_fraction = 0
    config.solver_budget_seconds = .2
    result = simulate(demo,config,generate_scenario(demo,config),"baseline")
    assert result.metrics["served"]+len(result.metrics["unserved"]) == len(demo.customers)
    assert result.metrics["objective_valid"] == (result.validation["valid"] and not result.metrics["unserved"])


def test_unusable_return_plan_cannot_beat_feasible_partial_plan():
    invalid = Solution({}, {}, [], float("inf"))
    fallback = Solution({}, {}, [1], 3.0)
    assert fallback.rank < invalid.rank
