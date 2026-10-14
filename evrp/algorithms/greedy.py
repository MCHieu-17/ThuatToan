"""Baseline: feasible minimum-increment greedy insertion + charging DP.

Each insertion candidate only re-solves the vehicle that receives the customer;
other vehicles are unchanged. The chosen candidate is then re-evaluated for the
whole fleet so the accepted solution stays consistent (station reservations are
solved in increasing vehicle id order).

A customer may be incompatible with the rest of a vehicle's route (the charging
DP cannot fit them together). The cheapest local insertion can therefore push
other customers out of the route. To avoid discarding a customer that a feasible
route does exist for, candidates are ranked by how many customers they keep:
  * first prefer candidates that leave every previously-served customer served
    (non-regressing), minimizing the local fleet score among those;
  * otherwise fall back to the cheapest candidate that at least still serves the
    new customer and does not reduce the served count.

The served count of a candidate is first estimated from the per-vehicle DP status
rather than a full fleet re-evaluation: only the modified vehicle changes, and its
plan serves the whole route when it is optimal. The estimate ignores reservations
that a higher-id vehicle inherits, so ranked candidates are confirmed with a real
fleet evaluation, cheapest first, until one truly keeps the served count. Only a
bounded number of confirmations is attempted to keep the baseline fast.
"""

from __future__ import annotations

import time
from math import isfinite

from evrp.algorithms.evaluator import FleetEvaluator
from evrp.domain import RoutePlan, Solution

CONFIRM_LIMIT = 6


def _served_by(plan: RoutePlan, route: list[int]) -> int:
    return len(route) if plan.status == "optimal" and isfinite(plan.score) else 0


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
        base_served = len(evaluator.customers) - len(base.unassigned)

        nonregressing: list[tuple[float, dict[int, list[int]]]] = []
        fallback: list[tuple[tuple[int, float], dict[int, list[int]]]] = []

        for vehicle in sorted(evaluator.states):
            route = base.routes.get(vehicle, [])
            calendar = evaluator.calendar_before(base.plans, vehicle)
            base_plan = base.plans.get(vehicle, RoutePlan(vehicle, [], [], 0.0))
            base_vehicle_score = base_plan.score
            other_score = base.score - (base_vehicle_score if isfinite(base_vehicle_score) else 0.0)
            other_served = base_served - _served_by(base_plan, route)
            for position in range(len(route) + 1):
                evaluator.counters.insertion_candidates += 1
                candidate_route = route[:position] + [customer] + route[position:]
                plan = evaluator.solve_vehicle(calendar, vehicle, candidate_route, limit)
                if plan.status != "optimal" or not isfinite(plan.score):
                    continue
                total = other_score + plan.score
                served = other_served + len(candidate_route)
                if served < base_served:
                    continue
                candidate_routes = {v: list(r) for v, r in base.routes.items()}
                candidate_routes[vehicle] = candidate_route
                if served > base_served:
                    nonregressing.append((total, candidate_routes))
                else:
                    fallback.append(((-served, total), candidate_routes))

        nonregressing.sort(key=lambda item: item[0])
        fallback.sort(key=lambda item: item[0])

        accepted = False
        for _, candidate_routes in nonregressing[:CONFIRM_LIMIT]:
            candidate = evaluator.evaluate(candidate_routes, limit)
            if len(candidate.unassigned) < len(base.unassigned):
                solution = candidate
                accepted = True
                break
        if accepted:
            continue
        for _, candidate_routes in fallback[:CONFIRM_LIMIT]:
            candidate = evaluator.evaluate(candidate_routes, limit)
            if len(candidate.unassigned) < len(base.unassigned):
                solution = candidate
                break

    solution.runtime = time.perf_counter() - started
    solution.evaluations = evaluator.counters.evaluations
    return solution