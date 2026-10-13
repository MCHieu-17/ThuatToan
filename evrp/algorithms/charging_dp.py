"""Label-setting / A* dynamic program for the charging decision subproblem.

The customer order is fixed. Between two consecutive required points the DP may
insert charging stations, choose a SoC target and a reserved power. Continuous
physical energy is kept; the clock is rounded up to the time grid with an
explicit wait action so the search graph stays finite. The first terminal label
popped from the A* queue is optimal on this restricted graph. Label caps return
status "search_limit", which is not a proof of infeasibility.
"""
from __future__ import annotations

import heapq
import itertools
import math
import time
from dataclasses import dataclass, field

from evrp.charging.calendar import StationCalendar
from evrp.charging.model import charging_action, discharge_transition
from evrp.config import Config
from evrp.domain import Action, Instance, RoutePlan, VehicleState
from evrp.metrics import OperationCounters, action_score


@dataclass
class Label:
    leg: int
    node: int
    slot: int
    energy: float
    low: bool
    visited: tuple[int, ...]
    charged_here: bool
    score: float
    parent: "Label | None" = None
    actions: tuple[Action, ...] = field(default_factory=tuple)

    def prefix(self) -> list[Action]:
        chain = []
        cursor: Label | None = self
        while cursor is not None and cursor.parent is not None:
            chain.append(cursor.actions)
            cursor = cursor.parent
        chain.reverse()
        return [action for batch in chain for action in batch]


def solve_charging(instance: Instance, config: Config, vehicle: int, customers: list[int],
                   state: VehicleState, calendar: StationCalendar,
                   releases: dict[int, float], counters: OperationCounters | None = None,
                   deadline: float | None = None,
                   preferred: dict[int, int] | None = None) -> RoutePlan:
    if counters is not None:
        counters.dp_calls += 1
    preferred = preferred or {}
    hard_deadline = time.perf_counter() + config.dp_budget_seconds
    if deadline is not None:
        hard_deadline = min(hard_deadline, deadline)

    destinations = list(customers) + [instance.depot]
    capacity = instance.capacity_kwh
    step = config.time_step_hours
    if not customers and state.node == instance.depot:
        return RoutePlan(vehicle, [], [], 0.0, status="optimal")

    def align(node: int, end: float, energy: float) -> tuple[int, float, list[Action]]:
        slot = math.ceil((end - 1e-9) / step)
        aligned = slot * step
        actions: list[Action] = []
        if aligned > end + 1e-12:
            actions.append(Action(vehicle, "wait", end, aligned, node, node, energy, energy,
                                  note="grid_alignment"))
        return slot, aligned, actions

    suffix_drive = [0.0] * len(destinations)
    suffix_energy = [0.0] * len(destinations)
    suffix_service = [0.0] * (len(destinations) + 1)
    for i in range(len(destinations) - 2, -1, -1):
        drive, energy = instance.travel(destinations[i], destinations[i + 1])
        suffix_drive[i] = suffix_drive[i + 1] + drive
        suffix_energy[i] = suffix_energy[i + 1] + energy
    for i in range(len(destinations) - 1, -1, -1):
        suffix_service[i] = suffix_service[i + 1] + instance.nodes[destinations[i]].service_hours

    curve_max = max(((q1 - q0) / (t1 - t0) for curve in instance.curves.values()
                     for (q0, t0), (q1, t1) in zip(curve.points, curve.points[1:])), default=1.0)
    station_max = max((min(instance.stations_info[s].charger_kw, instance.stations_info[s].power_kw)
                       for s in instance.stations), default=curve_max)
    fastest_power = max(1e-6, min(curve_max, station_max))
    cheapest_price = min(band["price"] for band in config.tou)

    init_slot, _, init_actions = align(state.node, state.time, state.energy)
    initial = Label(0, state.node, init_slot, state.energy, state.low_episode, (),
                    state.charged_here, sum(action_score(a, config) for a in init_actions),
                    None, tuple(init_actions))

    def bounds(label: Label) -> tuple[float, float]:
        if label.leg >= len(destinations):
            return 0.0, 0.0
        target = destinations[label.leg]
        drive, energy = instance.travel(label.node, target)
        needed = max(0.0, energy + suffix_energy[label.leg] + capacity * config.reserve_soc - label.energy)
        return drive + suffix_drive[label.leg], needed

    def lower_bound(label: Label) -> float:
        if label.leg >= len(destinations):
            return 0.0
        drive, needed = bounds(label)
        service = suffix_service[label.leg]
        return (config.w_time * (drive + needed / fastest_power + service)
                + config.w_electricity * cheapest_price * needed)

    counter = itertools.count()
    heap = [(initial.score + lower_bound(initial), next(counter), initial)]
    best = {_key(initial, step, config.energy_quantum_kwh): initial.score}
    expanded = 0

    def push(label: Label) -> None:
        if label.slot * step > instance.horizon_hours + 1e-9:
            return
        if label.energy < capacity * config.reserve_soc - 1e-8:
            return
        if label.leg < len(destinations):
            drive, needed = bounds(label)
            if label.slot * step + drive + needed / fastest_power + suffix_service[label.leg] > instance.horizon_hours + 1e-9:
                return
        key = _key(label, step, config.energy_quantum_kwh)
        if label.score + 1e-9 < best.get(key, math.inf):
            best[key] = label.score
            heapq.heappush(heap, (label.score + lower_bound(label), next(counter), label))

    def extend(label: Label, next_leg: int, node: int, energy: float, low: bool,
               visited: tuple[int, ...], charged: bool, actions: list[Action], end: float) -> None:
        slot, _, tail = align(node, end, energy)
        push(Label(next_leg, node, slot, energy, low, visited, charged,
                   label.score + sum(action_score(a, config) for a in actions + tail),
                   label, tuple(actions + tail)))

    while heap:
        if time.perf_counter() >= hard_deadline or (config.max_labels and expanded >= config.max_labels):
            return RoutePlan(vehicle, list(customers), [], math.inf, status="search_limit",
                             expanded_labels=expanded, dp_calls=1)
        _, _, label = heapq.heappop(heap)
        if label.score > best.get(_key(label, step, config.energy_quantum_kwh), math.inf) + 1e-9:
            continue
        expanded += 1
        if label.leg >= len(destinations):
            if counters is not None:
                counters.labels_expanded += expanded
            return RoutePlan(vehicle, list(customers), label.prefix(), label.score,
                             status="optimal", expanded_labels=expanded, dp_calls=1)

        current = label.slot * step
        target = destinations[label.leg]
        candidates: list[int] = []
        if len(label.visited) < config.max_station_hops:
            candidates = [s for s in instance.stations if s != label.node and s not in label.visited]
            candidates.sort(key=lambda s: (instance.travel(label.node, s)[0]
                                           + instance.travel(s, target)[0], s))
            if config.candidate_stations:
                candidates = candidates[:config.candidate_stations]
            hint = preferred.get(target)
            if (hint is not None and hint not in candidates and hint != label.node
                    and hint not in label.visited):
                candidates.append(hint)

        for destination in [target] + candidates:
            drive_time, consumed = instance.travel(label.node, destination)
            after = label.energy - consumed
            if after < capacity * config.reserve_soc - 1e-9:
                continue
            low, deep = discharge_transition(label.energy, after, label.low, capacity, config)
            end = current + drive_time
            actions: list[Action] = []
            if destination != label.node:
                actions.append(Action(vehicle, "drive", current, end, label.node, destination,
                                      label.energy, after, deep_discharge=deep))
            next_leg, visited = label.leg, tuple(sorted(label.visited + (destination,)))
            if destination == target:
                ready = releases.get(destination, 0.0)
                if end < ready:
                    actions.append(Action(vehicle, "wait", end, ready, destination, destination,
                                          after, after, note="order_release"))
                    end = ready
                if destination in customers:
                    service = instance.nodes[destination].service_hours
                    actions.append(Action(vehicle, "service", end, end + service, destination,
                                          destination, after, after))
                    end += service
                next_leg = label.leg + 1
                visited = ()
            extend(label, next_leg, destination, after, low, visited, False, actions, end)

        if instance.nodes[label.node].kind == "station" and not label.charged_here:
            info = instance.stations_info[label.node]
            base_power = min(info.charger_kw, info.power_kw)
            curve = instance.curves[instance.nodes[label.node].station_type or "normal"]
            top = curve.points[-1][0]
            targets = {top}
            steps = math.ceil(1 / config.soc_step)
            targets.update(min(top, i * config.soc_step * capacity) for i in range(1, steps + 1))
            targets.update(q for q, _ in curve.points)
            for q in sorted(targets):
                if q <= label.energy + 1e-8:
                    continue
                for fraction in config.power_fractions:
                    allocated = base_power * fraction
                    action = charging_action(instance, config, vehicle, label.node, current,
                                             label.energy, q, allocated)
                    if action.end > instance.horizon_hours + 1e-9:
                        continue
                    if not calendar.available(label.node, current, action.end, allocated,
                                              info.ports, info.power_kw):
                        continue
                    low = label.low and q < capacity * config.discharge_reset_soc - 1e-9
                    extend(label, label.leg, label.node, q, low, label.visited, True,
                           [action], action.end)
            end = current + step
            wait = Action(vehicle, "wait", current, end, label.node, label.node,
                          label.energy, label.energy, note="station_wait")
            extend(label, label.leg, label.node, label.energy, label.low, label.visited,
                   label.charged_here, [wait], end)

    if counters is not None:
        counters.labels_expanded += expanded
    return RoutePlan(vehicle, list(customers), [], math.inf, status="no_path",
                     expanded_labels=expanded, dp_calls=1)


def _key(label: Label, step: float, quantum: float):
    return (label.leg, label.node, label.slot, round(label.energy / quantum),
            label.low, label.visited, label.charged_here)