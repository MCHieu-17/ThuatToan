"""Shared fleet evaluator: routes -> charging plans -> objective value.

Vehicles are solved in increasing id order. Each confirmed charging session is
written to the shared station calendar so later vehicles see the reservation.
A route whose charging subproblem has no feasible plan is left unassigned; the
solution rank then prefers serving more customers before lower F.
"""
from __future__ import annotations

import time
from math import isfinite

from evrp.algorithms.charging_dp import solve_charging
from evrp.charging.calendar import StationCalendar
from evrp.config import Config
from evrp.domain import Instance, RoutePlan, Solution, VehicleState
from evrp.metrics import OperationCounters, action_score, component_costs


class FleetEvaluator:
    def __init__(self, instance: Instance, config: Config, releases: dict[int, float],
                 states: dict[int, VehicleState], customers, counters: OperationCounters | None = None):
        self.instance = instance
        self.config = config
        self.releases = releases
        self.states = states
        self.customers = set(customers)
        self.counters = counters if counters is not None else OperationCounters()
        self.deadline: float | None = None

    def evaluate(self, routes: dict[int, list[int]], deadline: float | None = None,
                 preferred: dict[int, int] | None = None) -> Solution:
        self.counters.evaluations += 1
        effective_deadline = self.deadline
        if deadline is not None:
            effective_deadline = deadline if effective_deadline is None else min(deadline, effective_deadline)

        planned: dict[int, list[int]] = {}
        taken: set[int] = set()
        for vehicle in sorted(self.states):
            planned[vehicle] = []
            for customer in routes.get(vehicle, ()):
                if customer in self.customers and customer not in taken:
                    planned[vehicle].append(customer)
                    taken.add(customer)

        calendar = StationCalendar()
        plans: dict[int, RoutePlan] = {}
        actions = []
        unassigned = set(self.customers) - taken
        started = time.perf_counter()
        for vehicle in sorted(self.states):
            route = planned[vehicle]
            if not route:
                plans[vehicle] = RoutePlan(vehicle, [], [], 0.0)
                continue
            plan = solve_charging(self.instance, self.config, vehicle, route,
                                  self.states[vehicle], calendar, self.releases,
                                  self.counters, effective_deadline, preferred)
            plans[vehicle] = plan
            if plan.status == "optimal" and isfinite(plan.score):
                for action in plan.actions:
                    if action.kind == "charge":
                        calendar.reserve(action.origin, action.start, action.end, action.allocated_kw)
                actions.extend(plan.actions)
            else:
                unassigned.update(route)
        score = sum(action_score(action, self.config) for action in actions)
        time_cost, electricity_cost, degradation_cost = component_costs(actions, self.config)
        return Solution(routes=planned, plans=plans, unassigned=sorted(unassigned), score=score,
                        runtime=time.perf_counter() - started,
                        evaluations=self.counters.evaluations,
                        time_cost=time_cost, electricity_cost=electricity_cost,
                        degradation_cost=degradation_cost)

    def empty_solution(self) -> Solution:
        return Solution(routes={v: [] for v in self.states}, plans={}, unassigned=sorted(self.customers),
                        score=0.0, evaluations=self.counters.evaluations)

    def calendar_before(self, plans: dict[int, RoutePlan], vehicle: int) -> StationCalendar:
        calendar = StationCalendar()
        for other in sorted(self.states):
            if other >= vehicle:
                break
            plan = plans.get(other)
            if plan is None:
                continue
            for action in plan.actions:
                if action.kind == "charge":
                    calendar.reserve(action.origin, action.start, action.end, action.allocated_kw)
        return calendar

    def solve_vehicle(self, calendar: StationCalendar, vehicle: int, route: list[int],
                      deadline: float | None = None,
                      preferred: dict[int, int] | None = None) -> RoutePlan:
        return solve_charging(self.instance, self.config, vehicle, route, self.states[vehicle],
                              calendar, self.releases, self.counters, deadline, preferred)