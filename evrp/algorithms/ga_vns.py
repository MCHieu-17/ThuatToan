"""Hybrid GA-VNS: same engine as pure GA plus variable-neighborhood search."""
from __future__ import annotations

from evrp.algorithms.evaluator import FleetEvaluator
from evrp.algorithms.ga import run_ga
from evrp.domain import Solution


def run_ga_vns(evaluator: FleetEvaluator, seed: int = 42,
               seed_routes: dict[int, list[int]] | None = None,
               deadline: float | None = None) -> Solution:
    return run_ga(evaluator, seed=seed, use_vns=True, seed_routes=seed_routes, deadline=deadline)


def run_pure_ga(evaluator: FleetEvaluator, seed: int = 42,
                seed_routes: dict[int, list[int]] | None = None,
                deadline: float | None = None) -> Solution:
    return run_ga(evaluator, seed=seed, use_vns=False, seed_routes=seed_routes, deadline=deadline)