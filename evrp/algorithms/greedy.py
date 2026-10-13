"""Baseline: feasible minimum-increment greedy insertion + charging DP.

Each insertion candidate only re-solves the vehicle that receives the customer;
other vehicles are unchanged. The chosen candidate is then re-evaluated for the
whole fleet so the accepted solution stays consistent (station reservations are
solved in increasing vehicle id order).
"""
from __future__ import annotations

import time
from math import isfinite

from evrp.algorithms.evaluator import FleetEvaluator
from evrp.domain import RoutePlan, Solution


def greedy_insert(evaluator: FleetEvaluator, seed_routes: dict[int, list[int]] | None = None,
                  deadline: float | None = None) -> Solution:
    started = time.perf_counter()
    limit = evaluator.deadline if deadline is None else (deadline if evaluator.deadline is None
                                                         else min(deadline, evaluator.deadline))

    routes = {vehicle: list((seed_routes or {}).get(vehicle, [])) for vehicle in evaluator.states}
    solution = evaluator.evaluate(routes, limit)
    remaining = sorted(solution.unassigned,
                       key=lambda c: (evaluator.releases.get(c, 0.0),
                                      evaluator.instance.travel(evaluator.instance.depot, c)[0], c))

    for customer in remaining:
        if limit is not None and time.perf_counter() >= limit:
            break
        base = solution
        best_routes: dict[int, list[int]] | None = None
        best_cost = float("inf")
        for vehicle in sorted(evaluator.states):
            route = base.routes.get(vehicle, [])
            calendar = evaluator.calendar_before(base.plans, vehicle)
            base_vehicle_score = base.plans.get(vehicle, RoutePlan(vehicle, [], [], 0.0)).score
            other_score = base.score - (base_vehicle_score if isfinite(base_vehicle_score) else 0.0)
            for position in range(len(route) + 1):
                evaluator.counters.insertion_candidates += 1
                candidate_route = route[:position] + [customer] + route[position:]
                plan = evaluator.solve_vehicle(calendar, vehicle, candidate_route, limit)
                if plan.status != "optimal" or not isfinite(plan.score):
                    continue
                total = other_score + plan.score
                if total < best_cost - 1e-12:
                    best_cost = total
                    best_routes = {v: list(r) for v, r in base.routes.items()}
                    best_routes[vehicle] = candidate_route
        if best_routes is None:
            continue
        candidate = evaluator.evaluate(best_routes, limit)
        previously_served = evaluator.customers - set(base.unassigned)
        served = evaluator.customers - set(candidate.unassigned)
        if customer in served and previously_served <= served:
            solution = candidate

    solution.runtime = time.perf_counter() - started
    solution.evaluations = evaluator.counters.evaluations
    return solution