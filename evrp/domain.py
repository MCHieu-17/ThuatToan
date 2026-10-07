from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import hypot, isfinite


@dataclass(frozen=True)
class Node:
    id: int
    kind: str
    x: float
    y: float
    service_hours: float = 0.0
    station_type: str = ""


@dataclass(frozen=True)
class Curve:
    """Cumulative (energy in kWh, charging time in hours) breakpoints."""
    points: tuple[tuple[float, float], ...]

    def segments(self, before: float, after: float, power_cap: float):
        """Yield (energy increment, effective kW), using min(curve slope, cap)."""
        if after < before - 1e-9 or before < -1e-9 or after > self.points[-1][0] + 1e-8:
            raise ValueError("Charging energy outside curve domain")
        if power_cap <= 0:
            raise ValueError("Charging power must be positive")
        for (q0, t0), (q1, t1) in zip(self.points, self.points[1:]):
            lo, hi = max(before, q0), min(after, q1)
            if hi > lo + 1e-10:
                yield hi - lo, min((q1 - q0) / (t1 - t0), power_cap)


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
    source: str = ""
    energy_unit: str = "Wh"
    _travel: dict[tuple[int, int], tuple[float, float]] = field(default_factory=dict, repr=False)

    @property
    def customers(self) -> list[int]:
        return sorted(n.id for n in self.nodes.values() if n.kind == "customer")

    @property
    def stations(self) -> list[int]:
        return sorted(n.id for n in self.nodes.values() if n.kind == "station")

    def travel(self, origin: int, destination: int) -> tuple[float, float]:
        key = origin, destination
        if key not in self._travel:
            a, b = self.nodes[origin], self.nodes[destination]
            distance = hypot(a.x - b.x, a.y - b.y)
            self._travel[key] = distance / self.speed_kmh, distance * self.consumption_kwh_km
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
    kind: str  # drive, wait, charge, service
    start: float
    end: float
    origin: int
    destination: int
    energy_before: float
    energy_after: float
    electricity: float = 0.0
    deep_charge: int = 0
    deep_discharge: int = 0
    allocated_kw: float = 0.0
    # Actual power segments: (start hour, end hour, kW).
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
    status: str = "optimal_discrete"
    expanded_labels: int = 0


@dataclass
class Solution:
    routes: dict[int, list[int]]
    plans: dict[int, RoutePlan]
    unassigned: list[int]
    score: float
    runtime: float = 0.0
    evaluations: int = 0
    history: list[dict] = field(default_factory=list)
    diagnostics: dict = field(default_factory=dict)

    @property
    def rank(self) -> tuple[int, int, float]:
        # Incomplete service is explicitly worse than any complete feasible solution.
        return int(not isfinite(self.score)), len(self.unassigned), self.score
