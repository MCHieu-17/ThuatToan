"""Feasible minimum-increment insertion, evaluated by the shared charging DP."""
from __future__ import annotations

import time
from math import isfinite

from evrp.algorithms.evaluator import FleetEvaluator
from evrp.domain import Solution


def greedy_insert(evaluator: FleetEvaluator, seed_routes: dict[int, list[int]] | None = None,
                  deadline: float | None = None) -> Solution:
    started = time.perf_counter()
    deadline = min(deadline or evaluator.deadline, evaluator.deadline)
    routes = {v: list((seed_routes or {}).get(v, [])) for v in evaluator.states}
    solution = evaluator.evaluate(routes)
    remaining = sorted(solution.unassigned,
                       key=lambda n: (evaluator.releases.get(n, 0),
                                      evaluator.instance.travel(evaluator.instance.depot, n)[0], n))
    history = []
    for customer in remaining:
        if time.perf_counter() >= deadline:
            break
        best = None
        previously = set(evaluator.customers) - set(solution.unassigned)
        for vehicle in sorted(evaluator.states):
            route = solution.routes.get(vehicle, [])
            for position in range(len(route) + 1):
                if time.perf_counter() >= deadline:
                    break
                candidate_routes = {v: list(r) for v, r in solution.routes.items()}
                candidate_routes[vehicle] = route[:position] + [customer] + route[position:]
                candidate = evaluator.evaluate(candidate_routes)
                if not isfinite(candidate.score):
                    continue
                assigned = evaluator.customers - set(candidate.unassigned)
                if customer not in assigned or not previously <= assigned:
                    continue
                if best is None or candidate.rank < best.rank:
                    best = candidate
        if best is not None:
            solution = best
            history.append({"step": len(history), "phase": "greedy",
                            "F_remaining": solution.score, "unassigned": len(solution.unassigned)})
    solution.runtime = time.perf_counter() - started
    solution.evaluations = evaluator.evaluations
    solution.history = history
    solution.diagnostics = evaluator.diagnostics()
    return solution
