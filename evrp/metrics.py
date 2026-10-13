"""Objective terms and operation counters.

F = w1 * (drive + wait + charge time) + w2 * electricity + w3 * degradation.
Service time advances the vehicle clock but is not part of F.
"""
from __future__ import annotations

from dataclasses import dataclass

from evrp.config import Config


@dataclass
class OperationCounters:
    dp_calls: int = 0
    labels_expanded: int = 0
    evaluations: int = 0
    insertion_candidates: int = 0

    def reset(self) -> None:
        self.dp_calls = 0
        self.labels_expanded = 0
        self.evaluations = 0
        self.insertion_candidates = 0

    def to_dict(self) -> dict:
        return {
            "dp_calls": self.dp_calls,
            "labels_expanded": self.labels_expanded,
            "evaluations": self.evaluations,
            "insertion_candidates": self.insertion_candidates,
        }


def degradation_cost(actions, config: Config) -> float:
    charges = sum(a.deep_charge for a in actions)
    discharges = sum(a.deep_discharge for a in actions)
    return charges * config.deep_charge_cost + discharges * config.deep_discharge_cost


def action_score(action, config: Config) -> float:
    time_terms = 0.0
    if action.kind in ("drive", "wait", "charge"):
        time_terms = action.end - action.start
    deg = action.deep_charge * config.deep_charge_cost + action.deep_discharge * config.deep_discharge_cost
    return (config.w_time * time_terms
            + config.w_electricity * action.electricity_cost
            + config.w_degradation * deg)


def component_costs(actions, config: Config) -> tuple[float, float, float]:
    """Raw, unweighted objective components (time hours, electricity, degradation).

    These feed the multi-objective Pareto ranking; the scalar `score` used for
    reporting is the weighted sum of exactly these three terms.
    """
    time_terms = 0.0
    electricity = 0.0
    degradation = 0.0
    for action in actions:
        if action.kind in ("drive", "wait", "charge"):
            time_terms += action.end - action.start
        electricity += action.electricity_cost
        degradation += (action.deep_charge * config.deep_charge_cost
                        + action.deep_discharge * config.deep_discharge_cost)
    return time_terms, electricity, degradation


def summarize(actions, config: Config) -> dict:
    drive = sum(a.end - a.start for a in actions if a.kind == "drive")
    wait = sum(a.end - a.start for a in actions if a.kind == "wait")
    charge = sum(a.end - a.start for a in actions if a.kind == "charge")
    service = sum(a.end - a.start for a in actions if a.kind == "service")
    electricity = sum(a.electricity_cost for a in actions)
    deep_charge = sum(a.deep_charge for a in actions)
    deep_discharge = sum(a.deep_discharge for a in actions)
    deg = deep_charge * config.deep_charge_cost + deep_discharge * config.deep_discharge_cost
    total_time = drive + wait + charge
    return {
        "F": config.w_time * total_time + config.w_electricity * electricity + config.w_degradation * deg,
        "T": total_time,
        "drive": drive,
        "wait": wait,
        "charge": charge,
        "service": service,
        "electricity": electricity,
        "degradation": deg,
        "deep_charge": deep_charge,
        "deep_discharge": deep_discharge,
        "makespan": max((a.end for a in actions), default=0.0),
    }