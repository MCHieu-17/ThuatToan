from __future__ import annotations

import math
import time

from evrp.algorithms.charging_dp import solve_charging
from evrp.charging.calendar import StationCalendar
from evrp.config import Config
from evrp.domain import Instance, Solution, VehicleState


class FleetEvaluator:
    """Decode routes in fixed vehicle-ID priority; cache only completed DP searches."""
    def __init__(self, instance: Instance, config: Config, states: dict[int, VehicleState],
                 calendar: StationCalendar, releases: dict[int, float], customers: list[int],
                 deadline: float):
        self.instance, self.config = instance, config
        self.states, self.calendar, self.releases = states, calendar, releases
        self.customers, self.deadline = set(customers), deadline
        self.cache = {}
        self.evaluations = 0
        self.dp_calls = 0
        self.dp_statuses: dict[str, int] = {}

    def evaluate(self, routes: dict[int, list[int]]) -> Solution:
        self.evaluations += 1
        flattened = [n for route in routes.values() for n in route]
        if len(flattened) != len(set(flattened)) or not set(flattened) <= self.customers:
            raise ValueError("Routes must contain distinct, currently known customers")
        calendar = self.calendar.clone()
        plans, accepted = {}, {}
        unassigned = self.customers - set(flattened)
        score = 0.0
        for vehicle in sorted(self.states):
            route = list(routes.get(vehicle, []))
            state = self.states[vehicle]
            key = (vehicle, tuple(route), state, calendar.fingerprint())
            result = self.cache.get(key)
            if result is None:
                self.dp_calls += 1
                result = solve_charging(self.instance, self.config, route, state, calendar,
                                        self.releases, self.deadline)
                self.dp_statuses[result.status] = self.dp_statuses.get(result.status, 0) + 1
                if result.status != "search_limit":
                    self.cache[key] = result
            if result.plan is None:
                unassigned.update(route)
                accepted[vehicle] = []
                # Away from depot with no feasible return is not a usable candidate.
                if state.node != self.instance.depot:
                    score = math.inf
                continue
            plans[vehicle], accepted[vehicle] = result.plan, route
            score += result.plan.score
            for action in result.plan.actions:
                calendar.reserve(action)
        return Solution(accepted, plans, sorted(unassigned), score,
                        evaluations=self.evaluations, diagnostics=self.diagnostics())

    def diagnostics(self):
        return {"dp_calls": self.dp_calls, "dp_statuses": dict(self.dp_statuses),
                "deadline_reached": time.perf_counter() >= self.deadline}
