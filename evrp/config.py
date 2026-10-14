"""Scenario configuration: TOU, degradation, fleet, DP and GA parameters."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from math import isfinite
from pathlib import Path


DEFAULT_TOU = [
    {"start": 0.0, "end": 9.0, "price": 0.12},
    {"start": 9.0, "end": 12.0, "price": 0.25},
    {"start": 12.0, "end": 17.0, "price": 0.45},
    {"start": 17.0, "end": 24.0, "price": 0.18},
]

DEFAULT_STATIONS = {
    "fast": {"ports": 2, "power_kw": 50.0, "charger_kw": 44.0},
    "normal": {"ports": 2, "power_kw": 22.0, "charger_kw": 22.0},
    "slow": {"ports": 1, "power_kw": 7.0, "charger_kw": 7.0},
}


@dataclass
class Config:
    seed: int = 42
    vehicles: int = 0
    customers_per_vehicle: int = 5
    min_vehicles: int = 2
    fleet_clustering_discount: float = 1.0
    fleet_time_utilization: float = 0.75
    dynamic_fraction: float = 0.5
    release_until_fraction: float = 0.35
    start_clock_hour: float = 8.0
    horizon_factor: float = 1.0
    stations_by_type: dict[str, dict] = field(
        default_factory=lambda: {k: dict(v) for k, v in DEFAULT_STATIONS.items()}
    )
    tou: list[dict] = field(default_factory=lambda: [dict(b) for b in DEFAULT_TOU])
    w_time: float = 1.0
    w_electricity: float = 0.3
    w_degradation: float = 0.2
    deep_charge_delta_soc: float = 0.6
    deep_discharge_soc: float = 0.15
    discharge_reset_soc: float = 0.25
    deep_charge_cost: float = 0.8
    deep_discharge_cost: float = 0.6
    reserve_soc: float = 0.02
    power_fractions: list[float] = field(default_factory=lambda: [0.5, 1.0])
    time_step_hours: float = 1 / 12
    soc_step: float = 0.1
    energy_quantum_kwh: float = 0.01
    candidate_stations: int = 3
    max_station_hops: int = 2
    max_labels: int = 12000
    dp_budget_seconds: float = 0.8
    solver_budget_seconds: float = 30.0
    population: int = 12
    generations: int = 25
    mutation_probability: float = 0.3
    elite_size: int = 2
    vns_iterations: int = 10
    pareto_selection: bool = True
    use_station_genes: bool = True
    replan_interval_hours: float = 0.5

    def validate(self) -> "Config":
        if not _finite(asdict(self)):
            raise ValueError("config values must be finite")
        for key in ("customers_per_vehicle", "min_vehicles"):
            if type(getattr(self, key)) is not int or getattr(self, key) < 1:
                raise ValueError(f"{key} must be a positive integer")
        for key in ("population", "generations", "max_station_hops", "candidate_stations",
                    "max_labels", "vns_iterations"):
            value = getattr(self, key)
            if type(value) is not int or value < 0:
                raise ValueError(f"{key} must be a nonnegative integer")
        if self.population < 2 or not 1 <= self.elite_size < self.population:
            raise ValueError("require population >= 2 and 1 <= elite_size < population")
        for key in ("time_step_hours", "soc_step", "energy_quantum_kwh", "dp_budget_seconds",
                    "solver_budget_seconds", "replan_interval_hours", "horizon_factor",
                    "fleet_clustering_discount"):
            if getattr(self, key) <= 0:
                raise ValueError(f"{key} must be positive")
        if not 0 < self.fleet_time_utilization <= 1:
            raise ValueError("fleet_time_utilization must lie in (0, 1]")
        for key in ("dynamic_fraction", "release_until_fraction", "mutation_probability"):
            if not 0 <= getattr(self, key) <= 1:
                raise ValueError(f"{key} must lie in [0, 1]")
        if not 0 < self.soc_step <= 1:
            raise ValueError("soc_step must lie in (0, 1]")
        if not 0 < self.deep_charge_delta_soc <= 1:
            raise ValueError("deep_charge_delta_soc must lie in (0, 1]")
        if not (0 <= self.reserve_soc <= self.deep_discharge_soc < self.discharge_reset_soc <= 1):
            raise ValueError("require reserve_soc <= deep_discharge_soc < discharge_reset_soc <= 1")
        if min(self.w_time, self.w_electricity, self.w_degradation,
               self.deep_charge_cost, self.deep_discharge_cost) < 0:
            raise ValueError("weights and degradation costs must be nonnegative")
        if self.w_time + self.w_electricity + self.w_degradation <= 0:
            raise ValueError("at least one objective weight must be positive")
        if not self.power_fractions or any(not 0 < p <= 1 for p in self.power_fractions):
            raise ValueError("power_fractions must contain values in (0, 1]")
        self._validate_tou()
        for kind, params in self.stations_by_type.items():
            if set(params) != {"ports", "power_kw", "charger_kw"}:
                raise ValueError(f"station type '{kind}' must define ports, power_kw, charger_kw")
            if type(params["ports"]) is not int or params["ports"] < 1:
                raise ValueError("station ports must be a positive integer")
            if params["power_kw"] <= 0 or params["charger_kw"] <= 0:
                raise ValueError("station power values must be positive")
        return self

    def _validate_tou(self) -> None:
        end = 0.0
        for band in self.tou:
            if band["start"] != end or band["end"] <= end or band["price"] < 0:
                raise ValueError("TOU bands must cover [0, 24] consecutively with prices >= 0")
            end = band["end"]
        if abs(end - 24.0) > 1e-9:
            raise ValueError("TOU bands must end at hour 24")

    def tou_price(self, hour: float) -> float:
        clock = hour % 24.0
        for band in self.tou:
            if band["start"] <= clock < band["end"] - 1e-12:
                return band["price"]
        return self.tou[-1]["price"]

    def to_dict(self) -> dict:
        return asdict(self)


def _finite(value) -> bool:
    if isinstance(value, (int, float)):
        return isfinite(value)
    if isinstance(value, dict):
        return all(_finite(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return all(_finite(v) for v in value)
    return True


def load_config(path: str | Path | None = None) -> Config:
    if path is None:
        return Config().validate()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    config = Config(**data)
    defaults = Config()
    for item in fields(config):
        if isinstance(getattr(defaults, item.name), float):
            setattr(config, item.name, float(getattr(config, item.name)))
    return config.validate()