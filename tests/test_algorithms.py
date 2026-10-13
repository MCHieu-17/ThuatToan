from __future__ import annotations

import math
import random

from evrp.algorithms.evaluator import FleetEvaluator
from evrp.algorithms.ga import Chromosome, _adjust_station, encode, station_genes
from evrp.algorithms.ga_vns import run_ga_vns, run_pure_ga
from evrp.algorithms.greedy import greedy_insert
from evrp.domain import VehicleState


def _evaluator(instance, config):
    releases = {c: instance.nodes[c].release_hours for c in instance.customers}
    states = {v: VehicleState(v, instance.depot, 0.0, instance.capacity_kwh) for v in range(instance.vehicles)}
    return FleetEvaluator(instance, config, releases, states, instance.customers)


def _assert_plans_feasible(instance, config, solution):
    for vehicle, plan in solution.plans.items():
        for action in plan.actions:
            assert action.energy_after >= instance.capacity_kwh * config.reserve_soc - 1e-6
            assert action.energy_after <= instance.capacity_kwh + 1e-6
            assert action.end <= instance.horizon_hours + 1e-6
            assert action.start <= action.end + 1e-9


def test_greedy_completes_and_is_feasible(tiny_instance, tiny_config):
    evaluator = _evaluator(tiny_instance, tiny_config)
    solution = greedy_insert(evaluator)
    assert not solution.unassigned
    assert solution.score > 0
    _assert_plans_feasible(tiny_instance, tiny_config, solution)


def test_pure_ga_and_hybrid_are_deterministic(tiny_instance, tiny_config):
    first = run_pure_ga(_evaluator(tiny_instance, tiny_config), seed=7)
    second = run_pure_ga(_evaluator(tiny_instance, tiny_config), seed=7)
    assert first.score == second.score
    hybrid = run_ga_vns(_evaluator(tiny_instance, tiny_config), seed=7)
    _assert_plans_feasible(tiny_instance, tiny_config, hybrid)


def test_hybrid_not_worse_than_pure_ga_on_tiny(tiny_instance, tiny_config):
    pure = run_pure_ga(_evaluator(tiny_instance, tiny_config), seed=3)
    hybrid = run_ga_vns(_evaluator(tiny_instance, tiny_config), seed=3)
    assert hybrid.rank <= pure.rank


def test_route_order_preserved_in_plan(tiny_instance, tiny_config):
    evaluator = _evaluator(tiny_instance, tiny_config)
    solution = greedy_insert(evaluator)
    for vehicle, plan in solution.plans.items():
        assert plan.customers == solution.routes[vehicle]


def test_battery_bounds_hold_for_single_customer(tiny_instance, tiny_config):
    releases = {1: 0.0}
    states = {v: VehicleState(v, tiny_instance.depot, 0.0, tiny_instance.capacity_kwh)
              for v in range(tiny_instance.vehicles)}
    evaluator = FleetEvaluator(tiny_instance, tiny_config, releases, states, [1])
    solution = evaluator.evaluate({0: [1], 1: []})
    assert not solution.unassigned
    _assert_plans_feasible(tiny_instance, tiny_config, solution)


def test_pareto_selection_exports_front(tiny_instance, tiny_config):
    config = tiny_config
    config.pareto_selection = True
    solution = run_ga_vns(_evaluator(tiny_instance, config), seed=5)
    assert solution.pareto_front
    assert all(point["unassigned"] == min(p["unassigned"] for p in solution.pareto_front)
               for point in solution.pareto_front)


def test_scalar_selection_still_feasible(tiny_instance, tiny_config):
    config = tiny_config
    config.pareto_selection = False
    solution = run_pure_ga(_evaluator(tiny_instance, config), seed=5)
    _assert_plans_feasible(tiny_instance, config, solution)


def test_station_gene_roundtrip():
    rng = random.Random(0)
    routes = {0: [1, 2], 1: [3]}
    chromosome = encode(routes, [1, 2, 3], [0, 1], rng, preferred={2: 4})
    genes = dict(zip(chromosome.order, station_genes(chromosome)))
    assert genes[2] == 4
    assert genes[1] == -1
    decoded_routes, preferred = chromosome.decode_plan([0, 1])
    assert decoded_routes[0] == [1, 2]
    assert preferred == {2: 4}


def test_charge_adjust_neighborhood_changes_station():
    chromosome = encode({0: [1, 2]}, [1, 2], [0], random.Random(0))
    results = [_adjust_station(chromosome, random.Random(seed), (4, 9)) for seed in range(10)]
    assert any(value in (4, 9) for result in results for value in station_genes(result))


def test_ga_with_station_genes_is_feasible(tiny_instance, tiny_config):
    config = tiny_config
    config.use_station_genes = True
    solution = run_ga_vns(_evaluator(tiny_instance, config), seed=11)
    _assert_plans_feasible(tiny_instance, config, solution)