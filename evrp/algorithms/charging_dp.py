"""Label-setting dynamic programming on a time-expanded fixed-order graph.

Targets are discretized, but actual energy and nonlinear charging durations
remain physical. Each edge ends at a time-grid boundary; the rounding delay is
an explicit wait action. A* priority uses only a triangle-inequality travel
lower bound, so the first terminal label is optimal in this restricted graph.
The graph restricts station candidates and forbids repeat stations within a
customer gap. Caps/timeouts return 'search_limit', not proof of infeasibility.
"""
from __future__ import annotations

import heapq
import itertools
import math
import time
from dataclasses import dataclass

from evrp.charging.calendar import StationCalendar
from evrp.charging.model import charging_action, discharge_transition
from evrp.config import Config
from evrp.domain import Action, Instance, RoutePlan, VehicleState
from evrp.metrics import action_score


@dataclass
class Label:
    progress: int
    node: int
    slot: int
    energy: float
    low: bool
    visited_stations: tuple[int, ...]
    charged_here: bool
    score: float
    parent: "Label | None"
    actions: tuple[Action, ...]

    @property
    def key(self):
        return (self.progress, self.node, self.slot, round(self.energy, 8), self.low,
                self.visited_stations, self.charged_here)


@dataclass
class DPResult:
    plan: RoutePlan | None
    status: str
    expanded: int


def solve_charging(instance: Instance, config: Config, customers: list[int],
                   state: VehicleState, calendar: StationCalendar,
                   releases: dict[int, float], deadline: float | None = None) -> DPResult:
    deadline = min(deadline or math.inf, time.perf_counter() + config.dp_budget_seconds)
    step, capacity = config.time_step_hours, instance.capacity_kwh
    destinations = customers + [instance.depot]
    if not customers and state.node == instance.depot:
        return DPResult(RoutePlan(state.vehicle, [], [], 0.0), "optimal_discrete", 0)

    def slot_at(t):
        return math.ceil((t - 1e-10) / step)

    def align(actions: list[Action], node: int, end: float, energy: float):
        slot = slot_at(end)
        if slot * step > end + 1e-9:
            actions.append(Action(state.vehicle, "wait", end, slot * step, node, node,
                                  energy, energy, note="time_grid_alignment"))
        return slot

    initial_actions: list[Action] = []
    slot = align(initial_actions, state.node, state.time, state.energy)
    initial = Label(0, state.node, slot, state.energy, state.low_episode, (), state.charged_here,
                    sum(action_score(a, config) for a in initial_actions), None, tuple(initial_actions))
    suffix = [0.0] * (len(destinations) + 1)
    suffix_energy = [0.0] * (len(destinations) + 1)
    suffix_service = [0.0] * (len(destinations) + 1)
    for i in range(len(destinations) - 2, -1, -1):
        suffix[i] = suffix[i + 1] + instance.travel(destinations[i], destinations[i + 1])[0]
        suffix_energy[i] = suffix_energy[i + 1] + instance.travel(destinations[i], destinations[i + 1])[1]
    for i in range(len(destinations) - 1, -1, -1):
        suffix_service[i] = suffix_service[i + 1] + instance.nodes[destinations[i]].service_hours
    curve_max = max(((q1-q0)/(t1-t0) for curve in instance.curves.values()
                     for (q0,t0),(q1,t1) in zip(curve.points,curve.points[1:])), default=1.0)
    station_max = max((min(config.station(s)["charger_kw"], config.station(s)["power_kw"])
                       for s in instance.stations), default=curve_max)
    fastest_power = min(curve_max, station_max)
    cheapest_price = min(b["price"] for b in config.tou)

    def remaining_bounds(label: Label):
        if label.progress == len(destinations):
            return 0.0, 0.0
        drive, energy = instance.travel(label.node, destinations[label.progress])
        charge_needed = max(0.0, energy + suffix_energy[label.progress]
                            + capacity * config.reserve_soc - label.energy)
        return drive + suffix[label.progress], charge_needed

    def lower_bound(label: Label):
        if label.progress == len(destinations):
            return 0.0
        drive, charge_needed = remaining_bounds(label)
        return config.w_time * (drive + charge_needed / fastest_power) \
            + config.w_electricity * cheapest_price * charge_needed

    counter = itertools.count()
    heap = [(initial.score + lower_bound(initial), next(counter), initial)]
    best = {initial.key: initial.score}
    expanded = 0

    def push(label: Label):
        if label.slot * step > instance.horizon_hours + 1e-9:
            return
        if label.energy < capacity * config.reserve_soc - 1e-8:
            return
        # Feasibility lower bound includes mandatory remaining service times.
        travel_lb, needed = remaining_bounds(label)
        if label.slot * step + travel_lb + needed / fastest_power + suffix_service[label.progress] > instance.horizon_hours + 1e-9:
            return
        if label.score + 1e-9 < best.get(label.key, math.inf):
            best[label.key] = label.score
            heapq.heappush(heap, (label.score + lower_bound(label), next(counter), label))

    def successor(label: Label, progress: int, node: int, energy: float, low: bool,
                  visited: tuple, charged: bool, actions: list[Action], end: float):
        next_slot = align(actions, node, end, energy)
        push(Label(progress, node, next_slot, energy, low, visited, charged,
                   label.score + sum(action_score(a, config) for a in actions), label, tuple(actions)))

    while heap:
        if time.perf_counter() >= deadline or (config.max_labels and expanded >= config.max_labels):
            return DPResult(None, "search_limit", expanded)
        _, _, label = heapq.heappop(heap)
        if label.score > best.get(label.key, math.inf) + 1e-9:
            continue
        expanded += 1
        if label.progress == len(destinations):
            batches = []
            cursor = label
            while cursor is not None:
                batches.append(cursor.actions)
                cursor = cursor.parent
            actions = [a for batch in reversed(batches) for a in batch]
            return DPResult(RoutePlan(state.vehicle, list(customers), actions, label.score,
                                      expanded_labels=expanded), "optimal_discrete", expanded)
        current = label.slot * step
        target = destinations[label.progress]

        # Drive directly to the next fixed customer/depot, or insert a station.
        candidates = []
        if len(label.visited_stations) < config.max_station_hops:
            candidates = [s for s in instance.stations
                          if s != label.node and s not in label.visited_stations
                          and not (label.progress == 0 and state.charged_here and s == state.node)]
            candidates.sort(key=lambda s: (instance.travel(label.node, s)[0]
                                          + instance.travel(s, target)[0], s))
            if config.candidate_stations:
                candidates = candidates[:config.candidate_stations]
        # An inserted station stop must include charging. Pure transit via a
        # station is dominated by a direct Euclidean arc. Initial station states
        # may depart without charging (including a just-committed session).
        destinations_to_try = [] if label.visited_stations and not label.charged_here else [target] + candidates
        for destination in destinations_to_try:
            drive_time, consumed = instance.travel(label.node, destination)
            after = label.energy - consumed
            if after < capacity * config.reserve_soc - 1e-9:
                continue
            low, deep = discharge_transition(label.energy, after, label.low, capacity, config)
            end = current + drive_time
            actions = []
            if destination != label.node:
                actions.append(Action(state.vehicle, "drive", current, end, label.node,
                                      destination, label.energy, after, deep_discharge=deep))
            progress, visited = label.progress, tuple(sorted(label.visited_stations + (destination,)))
            if destination == target:
                ready = releases.get(destination, 0.0)
                if end < ready:
                    actions.append(Action(state.vehicle, "wait", end, ready, destination,
                                          destination, after, after, note="order_release"))
                    end = ready
                service = instance.nodes[destination].service_hours
                if destination in customers:
                    # Keep zero-duration service events: they mark a completed customer.
                    actions.append(Action(state.vehicle, "service", end, end + service,
                                          destination, destination, after, after))
                    end += service
                progress += 1
                visited = ()
            successor(label, progress, destination, after, low, visited, False, actions, end)

        if instance.nodes[label.node].kind == "station":
            if not label.charged_here:
                limits = config.station(label.node)
                base_power = min(limits["charger_kw"], limits["power_kw"])
                targets = {capacity}
                count = math.ceil(1 / config.soc_step)
                targets.update(min(capacity, i * config.soc_step * capacity) for i in range(1, count + 1))
                curve = instance.curves[instance.nodes[label.node].station_type]
                targets.update(q for q, _ in curve.points)
                for q in sorted(targets):
                    if q <= label.energy + 1e-8:
                        continue
                    for fraction in config.power_fractions:
                        action = charging_action(instance, config, state.vehicle, label.node,
                                                 current, label.energy, q, base_power * fraction)
                        if action.end > instance.horizon_hours + 1e-9:
                            continue
                        if not calendar.available(label.node, current, action.end, action.allocated_kw):
                            continue
                        low = label.low and q / capacity < config.discharge_reset_soc - 1e-9
                        successor(label, label.progress, label.node, q, low,
                                  label.visited_stations, True, [action], action.end)
                # Waiting is available at each time slot, covering TOU and occupied ports.
                end = current + step
                action = Action(state.vehicle, "wait", current, end, label.node, label.node,
                                label.energy, label.energy, note="station_or_TOU_wait")
                successor(label, label.progress, label.node, label.energy, label.low,
                          label.visited_stations, False, [action], end)
    return DPResult(None, "no_path_in_discrete_graph", expanded)
