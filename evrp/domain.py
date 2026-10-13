"""Core data structures shared by every module.

Units are fixed: energy kWh, time hours, distance km, speed km/h.
Coordinates are plain Euclidean km, not latitude/longitude.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import hypot, isfinite


DEPOT = "depot"
CUSTOMER = "customer"
STATION = "station"


@dataclass(frozen=True)
class Node:
    id: int
    kind: str
    x: float
    y: float
    service_hours: float = 0.0
    station_type: str = ""
    release_hours: float = 0.0


@dataclass(frozen=True)
class Curve:
    """Cumulative charging curve: (energy kWh, elapsed hours) breakpoints."""

    points: tuple[tuple[float, float], ...]

    def segments(self, before: float, after: float, power_cap: float):
        """Yield (energy_kwh, effective_kw) pieces between two SoC levels."""
        if after < before - 1e-9 or before < -1e-9 or after > self.points[-1][0] + 1e-8:
            raise ValueError("charging energy outside curve domain")
        if power_cap <= 0:
            raise ValueError("charging power must be positive")
        for (q0, t0), (q1, t1) in zip(self.points, self.points[1:]):
            lo, hi = max(before, q0), min(after, q1)
            if hi > lo + 1e-10:
                yield hi - lo, min((q1 - q0) / (t1 - t0), power_cap)

    def duration(self, before: float, after: float, power_cap: float) -> float:
        return sum(energy / power for energy, power in self.segments(before, after, power_cap))


@dataclass(frozen=True)
class StationInfo:
    ports: int
    power_kw: float
    charger_kw: float


@dataclass
class Instance:
    name: str
    nodes: dict[int, Node]
    depot: int
    capacity_kwh: float
    consumption_kwh_km: float
    speed_kmh: float
    horizon_hours: float
    curves: dict[str, Curve]
    stations_info: dict[int, StationInfo]
    vehicles: int
    source: str = ""
    energy_unit: str = "Wh"
    _travel: dict[tuple[int, int], tuple[float, float]] = field(default_factory=dict, repr=False)

    @property
    def customers(self) -> list[int]:
        return sorted(n.id for n in self.nodes.values() if n.kind == CUSTOMER)

    @property
    def stations(self) -> list[int]:
        return sorted(n.id for n in self.nodes.values() if n.kind == STATION)

    def travel(self, origin: int, destination: int) -> tuple[float, float]:
        key = (origin, destination)
        if key not in self._travel:
            a, b = self.nodes[origin], self.nodes[destination]
            distance = hypot(a.x - b.x, a.y - b.y)
            self._travel[key] = (distance / self.speed_kmh, distance * self.consumption_kwh_km)
        return self._travel[key]


@dataclass(frozen=True)
class VehicleState:
    vehicle: int
    node: int
    time: float
    energy: float
    low_episode: bool = False
    charged_here: bool = False


@dataclass(frozen=True)
class Action:
    vehicle: int
    kind: str
    start: float
    end: float
    origin: int
    destination: int
    energy_before: float
    energy_after: float
    electricity_cost: float = 0.0
    deep_charge: int = 0
    deep_discharge: int = 0
    allocated_kw: float = 0.0
    power_segments: tuple[tuple[float, float, float], ...] = ()
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RoutePlan:
    vehicle: int
    customers: list[int]
    actions: list[Action]
    score: float
    status: str = "optimal"
    expanded_labels: int = 0
    dp_calls: int = 0


@dataclass
class Solution:
    routes: dict[int, list[int]]
    plans: dict[int, RoutePlan]
    unassigned: list[int]
    score: float
    runtime: float = 0.0
    evaluations: int = 0
    time_cost: float = 0.0
    electricity_cost: float = 0.0
    degradation_cost: float = 0.0
    pareto_front: list[dict] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return isfinite(self.score) and not self.unassigned

    @property
    def rank(self) -> tuple[int, int, float]:
        return (int(not isfinite(self.score)), len(self.unassigned), self.score)

    @property
    def objectives(self) -> tuple[int, float, float, float]:
        """Minimization vector used by the Pareto ranking.

        Unserved customers come first so feasibility dominates the trade-off,
        then the raw (unweighted) time, electricity and degradation terms.
        """
        return (len(self.unassigned), self.time_cost, self.electricity_cost,
                self.degradation_cost)