"""Online event-driven simulation. Exogenous future releases never enter a solver.

Actions already started are committed to completion. A drive to a customer
also commits its immediately following service, so replanning cannot leave a
customer visited but silently unserved. Committed charging sessions preserve
their full station reservations and degradation counts across replans.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

from evrp.algorithms.evaluator import FleetEvaluator
from evrp.algorithms.ga_vns import solve_ga_vns
from evrp.algorithms.greedy import greedy_insert
from evrp.charging.calendar import StationCalendar
from evrp.config import Config
from evrp.domain import Action, Instance, RoutePlan, Solution, VehicleState
from evrp.metrics import action_score, summarize
from evrp.scenario import Scenario


@dataclass
class RunResult:
    instance: str
    algorithm: str
    seed: int
    config: dict
    releases: dict[int, float]
    actions: list[Action]
    decisions: list[dict]
    metrics: dict
    validation: dict

    def to_dict(self) -> dict:
        def finite(value):
            if isinstance(value, float) and not math.isfinite(value):
                return None
            if isinstance(value, dict):
                return {k: finite(v) for k, v in value.items()}
            if isinstance(value, (tuple, list)):
                return [finite(v) for v in value]
            return value
        return finite({"instance": self.instance, "algorithm": self.algorithm, "seed": self.seed,
                "config": self.config, "releases": self.releases,
                "actions": [a.to_dict() for a in self.actions], "decisions": self.decisions,
                "metrics": self.metrics, "validation": self.validation})


def advance_state(state: VehicleState, actions: list[Action], config: Config,
                  instance: Instance) -> VehicleState:
    low, charged = state.low_episode, state.charged_here
    node, energy, at = state.node, state.energy, state.time
    for action in actions:
        node, energy, at = action.destination, action.energy_after, action.end
        if action.kind == "drive":
            low = low or bool(action.deep_discharge)
            charged = False
        elif action.kind == "charge":
            if energy / instance.capacity_kwh >= config.discharge_reset_soc - 1e-9:
                low = False
            charged = True
    return VehicleState(state.vehicle, node, at, energy, low, charged)


def commit_until(actions: list[Action], now: float) -> tuple[list[Action], list[Action]]:
    count = 0
    while count < len(actions):
        action = actions[count]
        if action.end <= now + 1e-9:
            count += 1
            continue
        if action.start < now - 1e-9:
            count += 1
            if action.kind == "drive":
                # Customer service belongs to the started delivery leg.
                following = count
                while following < len(actions) and actions[following].kind == "wait":
                    following += 1
                if following < len(actions) and actions[following].kind == "service" \
                        and actions[following].origin == action.destination:
                    count = following + 1
            break
        break
    return actions[:count], actions[count:]


def simulate(instance: Instance, config: Config, scenario: Scenario,
             algorithm: str = "baseline") -> RunResult:
    if algorithm not in {"baseline", "ga_vns"}:
        raise ValueError("algorithm must be baseline or ga_vns")
    if set(scenario.releases) != set(instance.customers):
        raise ValueError("Scenario must specify exactly one release for every customer")
    if any(not math.isfinite(t) or t < 0 or t > instance.horizon_hours for t in scenario.releases.values()):
        raise ValueError("Release times must lie inside the planning horizon")
    config.validate()
    start = time.perf_counter()
    states = {v: VehicleState(v, instance.depot, 0.0, instance.capacity_kwh)
              for v in range(config.vehicles)}
    committed = {v: [] for v in states}
    future = {v: [] for v in states}
    ticks = {0.0, instance.horizon_hours} | set(scenario.releases.values())
    ticks.update(i * config.replan_interval_hours
                 for i in range(1, math.ceil(instance.horizon_hours / config.replan_interval_hours)))
    previously_known = set()
    decisions = []
    for now in sorted(ticks):
        if now > instance.horizon_hours + 1e-9:
            continue
        for v in states:
            prefix, future[v] = commit_until(future[v], now)
            committed[v].extend(prefix)
            states[v] = advance_state(states[v], prefix, config, instance)
            if states[v].time < now:
                if states[v].node != instance.depot:
                    idle = Action(v, "wait", states[v].time, now, states[v].node, states[v].node,
                                  states[v].energy, states[v].energy, note="await_replanning")
                    committed[v].append(idle)
                # Off-duty depot parking is excluded from operational waiting time.
                states[v] = VehicleState(v, states[v].node, now, states[v].energy,
                                         states[v].low_episode, states[v].charged_here)
        served_locked = {a.destination for acts in committed.values() for a in acts if a.kind == "service"}
        known = set(scenario.known(now))
        pending = sorted(known - served_locked)
        planned = {a.destination for acts in future.values() for a in acts if a.kind == "service"}
        new = known - previously_known
        backlog = set(pending) - planned
        previously_known = known
        if now >= instance.horizon_hours - 1e-9 or not pending or (not new and not backlog):
            continue

        calendar = StationCalendar(config)
        for acts in committed.values():
            for action in acts:
                if action.kind == "charge" and action.end > now + 1e-9:
                    calendar.reserve(action)
        seed_routes = {v: [a.destination for a in future[v] if a.kind == "service"] for v in states}
        old_plans = {v: RoutePlan(v, seed_routes[v], future[v],
                                 sum(action_score(a, config) for a in future[v]), "preserved_plan")
                     for v in states}
        fallback = Solution(seed_routes, old_plans, sorted(set(pending) - planned),
                            sum(p.score for p in old_plans.values()))
        decision_start = time.perf_counter()
        deadline = decision_start + config.solver_budget_seconds
        # Explicitly pass ONLY releases that have been revealed by 'now'.
        revealed = {n: scenario.releases[n] for n in pending}
        evaluator = FleetEvaluator(instance, config, states, calendar, revealed, pending, deadline)
        if algorithm == "baseline":
            candidate = greedy_insert(evaluator, seed_routes)
        else:
            candidate = solve_ga_vns(evaluator, seed_routes, scenario.seed + len(decisions) * 1009)
        chosen = candidate if candidate.rank < fallback.rank else fallback
        for v in states:
            future[v] = list(chosen.plans[v].actions) if v in chosen.plans else []
        elapsed = time.perf_counter() - decision_start
        decisions.append({"time": now, "known_customers": sorted(known),
                          "locked_customers": sorted(served_locked), "new_customers": sorted(new),
                          "pending_customers": pending, "unassigned": chosen.unassigned,
                          "F_remaining": chosen.score, "runtime_seconds": elapsed,
                          "evaluations": evaluator.evaluations,
                          "diagnostics": evaluator.diagnostics(),
                          "kept_previous_plan": chosen is fallback,
                          "history": candidate.history})

    actions = sorted([a for v in states for a in committed[v] + future[v]],
                     key=lambda a: (a.start, a.vehicle, a.end))
    metrics = summarize(actions, config)
    served = {a.destination for a in actions if a.kind == "service"}
    unserved = sorted(set(instance.customers) - served)
    metrics.update({"served": len(served), "total_customers": len(instance.customers),
                    "unserved": unserved, "complete": not unserved,
                    "runtime_seconds": time.perf_counter() - start,
                    "solver_seconds": sum(d["runtime_seconds"] for d in decisions),
                    "replans": len(decisions),
                    "max_replan_seconds": max((d["runtime_seconds"] for d in decisions), default=0.0)})
    # F always reports the realized weighted components; objective_valid explains
    # whether it is a feasible full-service objective suitable for comparison.
    from evrp.validation import validate_trace
    validation = validate_trace(instance, config, scenario.releases, actions)
    metrics["objective_valid"] = not unserved and validation["valid"]
    return RunResult(instance.name, algorithm, scenario.seed, config.to_dict(),
                     dict(scenario.releases), actions, decisions, metrics, validation)
