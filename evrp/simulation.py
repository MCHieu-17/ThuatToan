"""Rolling-horizon simulation of the realtime EVRP.

Orders become available at their release time. At fixed epochs the solver
re-optimizes the currently released, unserved orders from each vehicle's state.
Actions that have begun by the epoch are executed completely; the remaining
schedule is discarded and re-planned. This keeps the run reproducible while
still exposing the solver to orders that appear over time.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass

from evrp.algorithms.evaluator import FleetEvaluator
from evrp.algorithms.ga_vns import run_ga_vns, run_pure_ga
from evrp.algorithms.greedy import greedy_insert
from evrp.config import Config
from evrp.domain import Instance, VehicleState
from evrp.io.enhance import vehicles_for
from evrp.metrics import OperationCounters, summarize


ALGORITHMS = ("greedy", "ga", "ga_vns")


@dataclass
class SimulationResult:
    name: str
    algorithm: str
    seed: int
    mode: str
    served: int
    total_customers: int
    complete: bool
    runtime_seconds: float
    replans: int
    metrics: dict
    counters: dict
    unserved: list[int]
    actions: list[dict]
    config: dict
    pareto_front: list[dict]


def _solve(evaluator: FleetEvaluator, algorithm: str, seed: int):
    if algorithm == "greedy":
        return greedy_insert(evaluator)
    if algorithm == "ga":
        return run_pure_ga(evaluator, seed=seed)
    if algorithm == "ga_vns":
        return run_ga_vns(evaluator, seed=seed)
    raise ValueError(f"unknown algorithm {algorithm!r}")


def simulate(instance: Instance, config: Config, algorithm: str, seed: int = 42,
             mode: str = "dynamic") -> SimulationResult:
    if algorithm not in ALGORITHMS:
        raise ValueError(f"algorithm must be one of {ALGORITHMS}")
    if mode not in ("static", "dynamic"):
        raise ValueError("mode must be 'static' or 'dynamic'")
    if config.vehicles > 0:
        instance.vehicles = config.vehicles
    elif instance.vehicles <= 0:
        instance.vehicles = vehicles_for(instance, config)
    started = time.perf_counter()
    counters = OperationCounters()
    customers = instance.customers
    releases = {node.id: node.release_hours for node in instance.nodes.values()
                if node.kind == "customer"}
    if mode == "static":
        releases = {c: 0.0 for c in customers}
        interval = instance.horizon_hours
    else:
        interval = config.replan_interval_hours

    vehicle_ids = list(range(instance.vehicles))
    states = {v: VehicleState(v, instance.depot, 0.0, instance.capacity_kwh, False, False)
              for v in vehicle_ids}
    served: set[int] = set()
    executed = []
    replans = 0
    now = 0.0
    pareto_front: list[dict] = []

    while now < instance.horizon_hours - 1e-9:
        active = sorted(c for c in customers if releases[c] <= now + 1e-9 and c not in served)
        plans: dict = {}
        if active:
            evaluator = FleetEvaluator(instance, config, releases, states, active, counters)
            evaluator.deadline = time.perf_counter() + config.solver_budget_seconds
            solution = _solve(evaluator, algorithm, seed)
            plans = solution.plans
            pareto_front = solution.pareto_front or pareto_front
            replans += 1

        epoch_end = min(now + interval, instance.horizon_hours)
        for vehicle in vehicle_ids:
            plan = plans.get(vehicle)
            state = states[vehicle]
            if plan is None:
                continue
            for action in plan.actions:
                if action.start > epoch_end + 1e-9:
                    break
                executed.append(action)
                low = state.low_episode
                if action.kind == "drive" and action.deep_discharge:
                    low = True
                if action.kind == "charge" and action.energy_after >= instance.capacity_kwh * config.discharge_reset_soc - 1e-9:
                    low = False
                state = VehicleState(vehicle, action.destination, action.end, action.energy_after,
                                     low, action.kind == "charge")
                if action.kind == "service":
                    served.add(action.destination)
            states[vehicle] = state

        now = max(epoch_end, max((s.time for s in states.values()), default=now))
        for vehicle in vehicle_ids:
            if states[vehicle].time < now:
                states[vehicle] = VehicleState(vehicle, states[vehicle].node, now,
                                               states[vehicle].energy, states[vehicle].low_episode,
                                               states[vehicle].charged_here)

    metrics = summarize(executed, config)
    complete = len(served) == len(customers)
    if not pareto_front:
        pareto_front = [{
            "unassigned": len(customers) - len(served),
            "time": metrics["T"],
            "electricity": metrics["electricity"],
            "degradation": metrics["degradation"],
            "score": metrics["F"],
            "complete": complete,
        }]
    return SimulationResult(
        name=instance.name,
        algorithm=algorithm,
        seed=seed,
        mode=mode,
        served=len(served),
        total_customers=len(customers),
        complete=complete,
        runtime_seconds=time.perf_counter() - started,
        replans=replans,
        metrics=metrics,
        counters=counters.to_dict(),
        unserved=sorted(set(customers) - served),
        actions=[action.to_dict() for action in executed],
        config=config.to_dict(),
        pareto_front=pareto_front,
    )


def result_to_dict(result: SimulationResult) -> dict:
    return asdict(result)