from __future__ import annotations

import math
import random
import time
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Iterable


DATA_URL = "https://www.vrp-rep.org/datasets/download/montoya-et-al-2017.zip"
DEFAULT_ARCHIVE = Path(__file__).resolve().parents[1] / "data/raw/montoya-et-al-2017.zip"
EPS = 1e-8


@dataclass(frozen=True)
class Node:
    id: int
    kind: int  # 0 depot, 1 customer, 2 charging station
    x: float
    y: float
    station_type: str = ""
    service_time: float = 0.0


@dataclass(frozen=True)
class Instance:
    name: str
    nodes: dict[int, Node]
    customers: tuple[int, ...]
    stations: tuple[int, ...]
    speed_kmh: float
    consumption_wh_km: float
    battery_wh: float
    max_route_hours: float
    curves: dict[str, tuple[tuple[float, float], ...]]  # (energy Wh, elapsed hours)

    def distance(self, a: int, b: int) -> float:
        x, y = self.nodes[a], self.nodes[b]
        return math.hypot(x.x - y.x, x.y - y.y)

    def energy(self, a: int, b: int) -> float:
        return self.distance(a, b) * self.consumption_wh_km


def load_instance(name: str, archive: Path = DEFAULT_ARCHIVE) -> Instance:
    """Read one original XML instance directly from the official ZIP."""
    if not name.replace("_", "").isalnum():
        raise ValueError("Instance name must be alphanumeric")
    with zipfile.ZipFile(archive) as zf:
        root = ET.fromstring(zf.read(f"{name}.xml"))
    nodes: dict[int, Node] = {}
    requests = {int(r.attrib["node"]): float(r.findtext("service_time", "0"))
                for r in root.findall("./requests/request")}
    for raw in root.findall("./network/nodes/node"):
        node_id, kind = int(raw.attrib["id"]), int(raw.attrib["type"])
        nodes[node_id] = Node(node_id, kind, float(raw.findtext("cx")),
                              float(raw.findtext("cy")),
                              raw.findtext("./custom/cs_type", ""), requests.get(node_id, 0.0))
    profile = root.find("./fleet/vehicle_profile")
    if profile is None:
        raise ValueError("Missing vehicle profile")
    curves = {}
    for raw in profile.findall("./custom/charging_functions/function"):
        points = tuple((float(p.findtext("battery_level")), float(p.findtext("charging_time")))
                       for p in raw.findall("breakpoint"))
        if len(points) < 2 or any(points[i][0] >= points[i + 1][0] or
                                   points[i][1] >= points[i + 1][1]
                                   for i in range(len(points) - 1)):
            raise ValueError("Invalid charging curve")
        curves[raw.attrib["cs_type"]] = points
    stations = tuple(i for i, n in nodes.items() if n.kind == 2)
    if any(nodes[i].station_type not in curves for i in stations):
        raise ValueError("Charging station without a matching curve")
    return Instance(name, nodes, tuple(i for i, n in nodes.items() if n.kind == 1), stations,
                    float(profile.findtext("speed_factor")),
                    float(profile.findtext("./custom/consumption_rate")),
                    float(profile.findtext("./custom/battery_capacity")),
                    float(profile.findtext("max_travel_time")), curves)


def interpolate(points: tuple[tuple[float, float], ...], value: float, inverse: bool = False) -> float:
    """Piecewise linear charging curve: energy to hours, or hours to energy."""
    if inverse:
        points = tuple((t, e) for e, t in points)
    value = min(max(value, points[0][0]), points[-1][0])
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if value <= x1 + EPS:
            return y0 + (value - x0) * (y1 - y0) / (x1 - x0)
    return points[-1][1]


def electricity_price(hour: float) -> float:
    """Synthetic tariff in relative cost units per kWh, repeating every day."""
    hour %= 24.0
    return 1.0 if hour < 2.0 else 3.0 if hour < 5.0 else 1.5


def charge_cost(curve: tuple[tuple[float, float], ...], before: float,
                after: float, start: float) -> float:
    elapsed = interpolate(curve, before)
    finish = start + interpolate(curve, after) - elapsed
    now, cost = start, 0.0
    while now < finish - EPS:
        # Tariff boundaries are at 2, 5 and 24 hours of each simulated day.
        day = math.floor(now / 24) * 24
        boundary = next((b for b in (day + 2, day + 5, day + 24) if b > now + EPS), day + 26)
        end = min(finish, boundary)
        e0 = interpolate(curve, elapsed + now - start, inverse=True)
        e1 = interpolate(curve, elapsed + end - start, inverse=True)
        cost += (e1 - e0) / 1000.0 * electricity_price(now)
        now = end
    return cost


@dataclass(frozen=True)
class State:
    node: int
    time: float
    battery: float
    departure: float


@dataclass(frozen=True)
class Event:
    kind: str
    node: int
    start: float
    end: float
    battery_after: float
    distance_km: float = 0.0
    charge_wh: float = 0.0
    cost: float = 0.0
    wear_wh: float = 0.0


@dataclass
class Vehicle:
    id: int
    state: State
    schedule: list[Event] = field(default_factory=list)
    history: list[Event] = field(default_factory=list)


def discharge_wear(before: float, after: float, capacity: float) -> float:
    threshold = 0.2 * capacity
    return max(0.0, min(before, threshold) - after)


def charge_wear(before: float, after: float, capacity: float) -> float:
    return max(0.0, after - max(before, 0.8 * capacity))


def escape_energy(instance: Instance, target: int) -> float:
    if target == 0:
        return 0.0
    return min(instance.energy(target, node) for node in (*instance.stations, 0))


def station_path(instance: Instance, state: State, target: int) -> list[int] | None:
    """Shortest feasible geometric path via stations; target gets an escape reserve."""
    import heapq

    reserve = max(escape_energy(instance, target), 0.1 * instance.battery_wh) if target else 0.0
    candidates = [s for s in instance.stations if s != state.node] + [target]
    best = {state.node: 0.0}
    parent: dict[int, int] = {}
    heap = [(0.0, state.node)]
    while heap:
        length, node = heapq.heappop(heap)
        if length > best[node] + EPS:
            continue
        if node == target:
            path = []
            while node != state.node:
                path.append(node)
                node = parent[node]
            return path[::-1]
        available = instance.battery_wh if node in instance.stations else state.battery
        for nxt in candidates:
            if nxt == node:
                continue
            need = instance.energy(node, nxt) + (reserve if nxt == target else 0.0)
            if need > available + EPS:
                continue
            cost = length + instance.distance(node, nxt)
            if cost + EPS < best.get(nxt, math.inf):
                best[nxt], parent[nxt] = cost, node
                heapq.heappush(heap, (cost, nxt))
    return None


def travel(instance: Instance, state: State, target: int, kind: str) -> tuple[State, Event]:
    distance = instance.distance(state.node, target)
    used = instance.energy(state.node, target)
    after = state.battery - used
    if after < -EPS:
        raise ValueError("Insufficient battery")
    end = state.time + distance / instance.speed_kmh
    if kind == "visit":
        end += instance.nodes[target].service_time
    event = Event(kind, target, state.time, end, max(0.0, after), distance_km=distance,
                  wear_wh=discharge_wear(state.battery, after, instance.battery_wh))
    return State(target, end, max(0.0, after), state.departure), event


def go_to(instance: Instance, state: State, target: int) -> tuple[State, list[Event]] | None:
    """Reach a customer/depot, inserting necessary partial station charges."""
    if state.node == target and target == 0:
        return state, []
    path = station_path(instance, state, target)
    if path is None:
        return None
    events: list[Event] = []
    current = state
    for index, nxt in enumerate(path):
        if current.node in instance.stations:
            subsequent = path[index + 1] if index + 1 < len(path) else None
            needed = instance.energy(current.node, nxt)
            if nxt == target and target != 0:
                needed += max(escape_energy(instance, target), 0.1 * instance.battery_wh)
            elif subsequent is not None:
                needed += 0.1 * instance.battery_wh
            if needed > instance.battery_wh + EPS:
                return None
            if current.battery + EPS < needed:
                curve = instance.curves[instance.nodes[current.node].station_type]
                end = current.time + interpolate(curve, needed) - interpolate(curve, current.battery)
                event = Event("charge", current.node, current.time, end, needed,
                              charge_wh=needed - current.battery,
                              cost=charge_cost(curve, current.battery, needed, current.time),
                              wear_wh=charge_wear(current.battery, needed, instance.battery_wh))
                events.append(event)
                current = State(current.node, end, needed, current.departure)
        kind = "visit" if nxt == target and target != 0 else "depot" if nxt == 0 else "station"
        current, event = travel(instance, current, nxt, kind)
        events.append(event)
    return current, events


def plan_route(instance: Instance, state: State, customers: Iterable[int]) -> list[Event] | None:
    current = state
    events: list[Event] = []
    for customer in (*customers, 0):
        result = go_to(instance, current, customer)
        if result is None:
            return None
        current, leg = result
        events.extend(leg)
    if current.time - state.departure > instance.max_route_hours + EPS:
        return None
    return events


def make_releases(instance: Instance, dynamic_ratio: float, seed: int) -> dict[int, float]:
    if not 0 <= dynamic_ratio <= 1:
        raise ValueError("dynamic_ratio must be in [0, 1]")
    rng = random.Random(seed)
    ids = list(instance.customers)
    rng.shuffle(ids)
    count = round(len(ids) * dynamic_ratio)
    releases = {i: 0.0 for i in ids}
    for i in ids[:count]:
        releases[i] = rng.uniform(0.0, instance.max_route_hours / 2)
    return releases


def advance(vehicle: Vehicle, now: float) -> tuple[State, list[Event]]:
    """Complete past operations, keeping an operation in progress committed."""
    while vehicle.schedule and vehicle.schedule[0].end <= now + EPS:
        event = vehicle.schedule.pop(0)
        vehicle.history.append(event)
        vehicle.state = State(event.node, event.end, event.battery_after, vehicle.state.departure)
        if event.kind == "depot":
            vehicle.state = State(0, event.end, vehicle.state.battery, event.end)
    if vehicle.schedule and vehicle.schedule[0].start < now - EPS:
        event = vehicle.schedule[0]
        committed = [event]
        state = State(event.node, event.end, event.battery_after, vehicle.state.departure)
        if event.kind == "depot":
            state = State(0, event.end, state.battery, event.end)
        return state, committed
    return State(vehicle.state.node, max(now, vehicle.state.time),
                 vehicle.state.battery, vehicle.state.departure), []


def metrics(events: Iterable[Event]) -> tuple[float, float, float]:
    items = list(events)
    # Travel, service and charging time, excluding idle time between releases.
    return (sum(e.end - e.start for e in items), sum(e.cost for e in items),
            sum(e.wear_wh for e in items) / 1000.0)


@dataclass
class Solution:
    routes: dict[int, list[Event]]
    failed: tuple[int, ...]
    values: tuple[float, float, float]
    vehicle_count: int
    score: float = math.inf


def decode(instance: Instance, order: tuple[int, ...], states: dict[int, State]) -> Solution:
    """Greedy route split for a GA chromosome; IDs >= 0 are existing vehicles."""
    routes: dict[int, list[Event]] = {}
    existing = sorted(states, key=lambda i: (i == -1, states[i].time, i))
    route_starts = dict(states)
    current_index = 0
    next_vehicle = max(existing, default=-1) + 1
    selected: dict[int, list[int]] = {}
    failed: list[int] = []
    for customer in order:
        placed = False
        while not placed:
            if current_index < len(existing):
                vehicle_id = existing[current_index]
                start = route_starts[vehicle_id]
            else:
                vehicle_id = next_vehicle
                start = State(0, min((s.time for s in states.values()), default=0.0),
                              instance.battery_wh, min((s.time for s in states.values()), default=0.0))
            candidate = selected.get(vehicle_id, []) + [customer]
            route = plan_route(instance, start, candidate)
            if route is not None:
                selected[vehicle_id] = candidate
                routes[vehicle_id] = route
                placed = True
            elif current_index < len(existing):
                current_index += 1
            elif selected.get(vehicle_id):
                next_vehicle += 1
            else:
                failed.append(customer)
                placed = True
    for vehicle_id, state in states.items():
        if vehicle_id not in routes and state.node != 0:
            route = plan_route(instance, state, ())
            if route is not None:
                routes[vehicle_id] = route
    # A newly dispatched vehicle starts full in the original benchmark. Account for
    # the energy purchased at the depot, without adding an invented charging delay.
    for vehicle_id, route in routes.items():
        if route and (vehicle_id == -1 or vehicle_id not in states):
            start = route_starts.get(vehicle_id)
            if start is None:
                start = State(0, min(s.time for s in states.values()), instance.battery_wh,
                              min(s.time for s in states.values()))
            route.insert(0, Event("dispatch", 0, start.time, start.time, instance.battery_wh,
                                  charge_wh=instance.battery_wh,
                                  cost=instance.battery_wh / 1000.0 * electricity_price(start.time),
                                  wear_wh=0.2 * instance.battery_wh))
    all_events = [e for route in routes.values() for e in route]
    return Solution(routes, tuple(failed), metrics(all_events), len(routes))


def score_solution(solution: Solution, reference: tuple[float, float, float]) -> float:
    t, c, w = solution.values
    rt, rc, rw = reference
    return (10000.0 * len(solution.failed) +
            0.5 * t / max(rt, 1.0) + 0.3 * c / max(rc, 1.0) +
            0.2 * w / max(rw, 1.0))


def greedy_order(instance: Instance, customers: Iterable[int], starts: dict[int, State]) -> tuple[int, ...]:
    remaining = set(customers)
    position = min(starts.values(), key=lambda s: s.time).node if starts else 0
    order = []
    while remaining:
        nxt = min(remaining, key=lambda c: (instance.distance(position, c), c))
        order.append(nxt)
        remaining.remove(nxt)
        position = nxt
    return tuple(order)


def order_crossover(a: tuple[int, ...], b: tuple[int, ...], rng: random.Random) -> tuple[int, ...]:
    if len(a) < 2:
        return a
    lo, hi = sorted(rng.sample(range(len(a)), 2))
    segment = a[lo:hi + 1]
    rest = [x for x in b if x not in segment]
    return tuple(rest[:lo] + list(segment) + rest[lo:])


def neighbor(order: tuple[int, ...], kind: int, rng: random.Random) -> tuple[int, ...]:
    if len(order) < 2:
        return order
    values = list(order)
    a, b = sorted(rng.sample(range(len(values)), 2))
    if kind == 0:  # relocate
        item = values.pop(a)
        values.insert(b, item)
    elif kind == 1:  # swap
        values[a], values[b] = values[b], values[a]
    else:  # reverse / 2-opt in chromosome order
        values[a:b + 1] = reversed(values[a:b + 1])
    return tuple(values)


def optimize(instance: Instance, customers: tuple[int, ...], states: dict[int, State],
             method: str, seed: int, seconds: float,
             trace: dict | None = None) -> tuple[tuple[int, ...], Solution, int, float]:
    rng = random.Random(seed)
    started = time.perf_counter()
    baseline = greedy_order(instance, customers, states)
    base_solution = decode(instance, baseline, states)
    reference = base_solution.values
    base_solution.score = score_solution(base_solution, reference)
    evaluations = 1
    cache = {baseline: base_solution}
    if trace is not None:
        trace.update(baseline=list(baseline), generations=[], examples={})

    def evaluate(order: tuple[int, ...]) -> Solution:
        nonlocal evaluations
        if order not in cache:
            solution = decode(instance, order, states)
            solution.score = score_solution(solution, reference)
            cache[order] = solution
            evaluations += 1
        return cache[order]

    if method == "greedy" or len(customers) < 2:
        if trace is not None:
            trace["final_order"] = list(baseline)
        return baseline, base_solution, evaluations, time.perf_counter() - started

    population = [baseline]
    while len(population) < 30:
        values = list(customers)
        rng.shuffle(values)
        population.append(tuple(values))
    best = baseline
    for generation in range(40):
        if time.perf_counter() - started >= seconds:
            break
        population.sort(key=lambda x: evaluate(x).score)
        if evaluate(population[0]).score < evaluate(best).score:
            best = population[0]
        if method == "ga_vns":
            current, neighborhood = population[0], 0
            attempts = 0
            while neighborhood < 3 and attempts < 15 and time.perf_counter() - started < seconds:
                # Basic VNS: shake at radius k, then descend in a small local search.
                trial = neighbor(current, neighborhood, rng)
                if trace is not None and "vns" not in trace["examples"]:
                    trace["examples"]["vns"] = {
                        "before": list(current), "candidate": list(trial),
                        "neighborhood": ("relocate", "swap", "reverse")[neighborhood],
                    }
                attempts += 1
                for local_kind in range(3):
                    if attempts >= 15 or time.perf_counter() - started >= seconds:
                        break
                    local = neighbor(trial, local_kind, rng)
                    attempts += 1
                    if evaluate(local).score + EPS < evaluate(trial).score:
                        trial = local
                if evaluate(trial).score + EPS < evaluate(current).score:
                    current, neighborhood = trial, 0
                else:
                    neighborhood += 1
            population[0] = current
            if evaluate(current).score < evaluate(best).score:
                best = current
        next_population = population[:2]
        while len(next_population) < 30:
            def tournament() -> tuple[int, ...]:
                return min((rng.choice(population) for _ in range(3)), key=lambda x: evaluate(x).score)
            a, b = tournament(), tournament()
            child = order_crossover(a, b, rng) if rng.random() < 0.8 else a
            if trace is not None and "crossover" not in trace["examples"] and child != a:
                trace["examples"]["crossover"] = {
                    "parent_a": list(a), "parent_b": list(b), "child": list(child),
                }
            if rng.random() < 0.2:
                before_mutation = child
                child = neighbor(child, rng.randrange(3), rng)
                if trace is not None and "mutation" not in trace["examples"] and child != before_mutation:
                    trace["examples"]["mutation"] = {
                        "before": list(before_mutation), "after": list(child),
                    }
            next_population.append(child)
        population = next_population
        if trace is not None:
            trace["generations"].append({"generation": generation + 1,
                                         "best_score": evaluate(best).score,
                                         "evaluations": evaluations})
    for chromosome in population:
        if time.perf_counter() - started >= seconds:
            break
        if evaluate(chromosome).score < evaluate(best).score:
            best = chromosome
    if trace is not None:
        trace["final_order"] = list(best)
    return best, evaluate(best), evaluations, time.perf_counter() - started


def solve_online(instance: Instance, releases: dict[int, float], method: str = "ga_vns",
                 seed: int = 0, seconds: float = 2.0,
                 include_trace: bool = False,
                 on_progress: Callable[[int, int], None] | None = None) -> dict:
    if method not in {"greedy", "ga", "ga_vns"}:
        raise ValueError("method must be greedy, ga or ga_vns")
    if set(releases) != set(instance.customers):
        raise ValueError("Release times must cover exactly all customers")
    vehicles: dict[int, Vehicle] = {}
    replans = []
    event_times = sorted(set(releases.values()))
    snapshots = []
    for event_no, now in enumerate(event_times):
        starts: dict[int, State] = {}
        committed: dict[int, list[Event]] = {}
        for vehicle_id, vehicle in vehicles.items():
            starts[vehicle_id], committed[vehicle_id] = advance(vehicle, now)
        served = {e.node for v in vehicles.values() for e in v.history if e.kind == "visit"}
        served.update(e.node for events in committed.values() for e in events if e.kind == "visit")
        outstanding = tuple(c for c in instance.customers if releases[c] <= now + EPS and c not in served)
        # Include the event clock in new-vehicle start time even when there are no active vehicles.
        starts[-1] = State(0, now, instance.battery_wh, now)
        search_trace = {} if include_trace else None
        order, solution, evaluations, elapsed = optimize(
            instance, outstanding, starts, method, seed + event_no, seconds, search_trace)
        starts.pop(-1)
        # The virtual depot route gets the next available real vehicle ID.
        virtual = solution.routes.pop(-1, [])
        if virtual:
            new_id = max(vehicles, default=-1) + 1
            vehicles[new_id] = Vehicle(new_id, State(0, now, instance.battery_wh, now), virtual)
        for vehicle_id, vehicle in vehicles.items():
            if vehicle_id == max(vehicles) and virtual and vehicle_id not in starts:
                continue
            vehicle.schedule = committed.get(vehicle_id, []) + solution.routes.pop(vehicle_id, [])
        for temp_id, route in solution.routes.items():
            if not route:
                continue
            new_id = max(vehicles, default=-1) + 1
            vehicles[new_id] = Vehicle(new_id, State(0, now, instance.battery_wh, now), route)
        replans.append({"time": now, "revealed": sum(t <= now + EPS for t in releases.values()),
                        "outstanding": len(outstanding), "failed": list(solution.failed),
                        "evaluations": evaluations, "solve_seconds": elapsed,
                        "score": solution.score})
        if include_trace:
            snapshots.append({
                "time": now,
                "new_orders": sorted(c for c, t in releases.items() if abs(t - now) <= EPS),
                "outstanding": list(outstanding),
                "order": list(order),
                "failed": list(solution.failed),
                "vehicles": {str(i): {"origin_node": vehicle.state.node,
                                       "start_state": asdict(starts[i]) if i in starts else None,
                                       "committed": [asdict(e) for e in committed.get(i, [])],
                                       "planned": [asdict(e) for e in vehicle.schedule]}
                             for i, vehicle in vehicles.items()},
                "search": search_trace,
            })
        if on_progress is not None:
            on_progress(event_no + 1, len(event_times))
    for vehicle in vehicles.values():
        advance(vehicle, math.inf)
    all_events = [event for vehicle in vehicles.values() for event in vehicle.history]
    served = {event.node for event in all_events if event.kind == "visit"}
    t, c, w = metrics(all_events)
    result = {"instance": instance.name, "method": method, "seed": seed,
            "customers": len(instance.customers), "served": len(served),
            "unserved": sorted(set(instance.customers) - served), "vehicles": len(vehicles),
            "operating_hours": t, "electricity_cost": c, "wear_proxy_kwh": w,
            "replans": replans,
            "routes": {str(i): [asdict(event) for event in v.history] for i, v in vehicles.items()}}
    if include_trace:
        result["snapshots"] = snapshots
    return result


def mst_double_tree(instance: Instance, customers: Iterable[int]) -> tuple[list[int], float, float]:
    """2-approximation for the static, one-vehicle metric TSP special case only."""
    vertices = [0, *customers]
    if len(vertices) == 1:
        return [0, 0], 0.0, 0.0
    visited = {0}
    edges: dict[int, list[int]] = {v: [] for v in vertices}
    weight = 0.0
    while len(visited) < len(vertices):
        a, b = min(((a, b) for a in visited for b in vertices if b not in visited),
                   key=lambda pair: instance.distance(*pair))
        visited.add(b)
        edges[a].append(b)
        edges[b].append(a)
        weight += instance.distance(a, b)
    tour = []
    stack = [(0, -1)]
    while stack:
        node, parent = stack.pop()
        tour.append(node)
        stack.extend((child, node) for child in reversed(edges[node]) if child != parent)
    tour.append(0)
    length = sum(instance.distance(a, b) for a, b in zip(tour, tour[1:]))
    return tour, length, weight
