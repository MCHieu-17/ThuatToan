from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from math import isfinite
from pathlib import Path


@dataclass
class Config:
    vehicles: int = 5
    seed: int = 42
    dynamic_fraction: float = 0.5
    release_until_fraction: float = 0.35
    start_clock_hour: float = 8.0
    station_ports: int = 2
    station_power_kw: float = 40.0
    charger_power_kw: float = 44.0
    power_fractions: list[float] = field(default_factory=lambda: [0.5, 1.0])
    station_overrides: dict[str, dict] = field(default_factory=dict)
    tou: list[dict] = field(default_factory=lambda: [
        {"start": 0.0, "end": 9.0, "price": 0.12},
        {"start": 9.0, "end": 12.0, "price": 0.25},
        {"start": 12.0, "end": 17.0, "price": 0.45},
        {"start": 17.0, "end": 24.0, "price": 0.18},
    ])
    w_time: float = 1.0
    w_electricity: float = 0.3
    w_degradation: float = 0.2
    deep_charge_delta_soc: float = 0.6
    deep_discharge_soc: float = 0.15
    discharge_reset_soc: float = 0.25
    deep_charge_cost: float = 0.8
    deep_discharge_cost: float = 0.6
    reserve_soc: float = 0.02
    time_step_hours: float = 1 / 12
    soc_step: float = 0.1
    candidate_stations: int = 3  # 0 = all stations
    max_station_hops: int = 2
    max_labels: int = 12000  # 0 = no label count limit
    dp_budget_seconds: float = 0.8
    solver_budget_seconds: float = 10.0
    population: int = 10
    generations: int = 20
    mutation_probability: float = 0.3
    elite_size: int = 2
    vns_iterations: int = 8
    replan_interval_hours: float = 0.5

    def validate(self) -> "Config":
        def finite(value):
            if isinstance(value, (float, int)):
                return isfinite(value)
            if isinstance(value, dict):
                return all(finite(v) for v in value.values())
            if isinstance(value, list):
                return all(finite(v) for v in value)
            return True
        if not finite(asdict(self)):
            raise ValueError("Config values must be finite")
        for key in ("vehicles", "station_ports", "max_station_hops", "population", "generations"):
            value = getattr(self, key)
            if type(value) is not int or value < 1:
                raise ValueError(f"{key} must be a positive integer")
        for key in ("station_power_kw", "charger_power_kw", "time_step_hours", "soc_step",
                    "dp_budget_seconds", "solver_budget_seconds", "replan_interval_hours"):
            if getattr(self, key) <= 0:
                raise ValueError(f"{key} must be positive")
        for key in ("dynamic_fraction", "release_until_fraction", "mutation_probability"):
            if not 0 <= getattr(self, key) <= 1:
                raise ValueError(f"{key} must lie in [0, 1]")
        if not (0 <= self.reserve_soc <= self.deep_discharge_soc < self.discharge_reset_soc <= 1):
            raise ValueError("Require reserve_soc <= deep_discharge_soc < discharge_reset_soc <= 1")
        if not 0 < self.deep_charge_delta_soc <= 1 or not 0 < self.soc_step <= 1:
            raise ValueError("SoC steps and deep charge threshold must lie in (0, 1]")
        if self.population < 2 or not 1 <= self.elite_size < self.population:
            raise ValueError("Require population >= 2 and 1 <= elite_size < population")
        for key in ("max_labels", "candidate_stations", "vns_iterations"):
            if type(getattr(self, key)) is not int or getattr(self, key) < 0:
                raise ValueError(f"{key} must be a nonnegative integer")
        if min(self.w_time, self.w_electricity, self.w_degradation,
               self.deep_charge_cost, self.deep_discharge_cost) < 0:
            raise ValueError("Weights and degradation costs must be nonnegative")
        if self.w_time + self.w_electricity + self.w_degradation <= 0:
            raise ValueError("At least one weight must be positive")
        if not self.power_fractions or any(not 0 < p <= 1 for p in self.power_fractions):
            raise ValueError("power_fractions must contain values in (0, 1]")
        end = 0.0
        for band in self.tou:
            if band["start"] != end or band["end"] <= end or band["price"] < 0:
                raise ValueError("TOU bands must cover [0,24] consecutively with nonnegative prices")
            end = band["end"]
        if end != 24:
            raise ValueError("TOU bands must end at hour 24")
        for override in self.station_overrides.values():
            if any(k not in {"ports", "power_kw", "charger_kw"} for k in override):
                raise ValueError("Unknown station override key")
            if any(v <= 0 for v in override.values()):
                raise ValueError("Station override values must be positive")
            if "ports" in override and type(override["ports"]) is not int:
                raise ValueError("Station ports must be an integer")
        return self

    def station(self, node: int) -> dict:
        values = {"ports": self.station_ports, "power_kw": self.station_power_kw,
                  "charger_kw": self.charger_power_kw}
        values.update(self.station_overrides.get(str(node), {}))
        return values

    def to_dict(self) -> dict:
        return asdict(self)


def load_config(path: str | Path | None = None) -> Config:
    if path is None:
        return Config().validate()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    config, defaults = Config(**data), Config()
    # JSON 6 and 6.0 are equivalent physically; UI numeric controls require a
    # consistent type for defaults, bounds and steps.
    for item in fields(config):
        if isinstance(getattr(defaults, item.name), float):
            setattr(config, item.name, float(getattr(config, item.name)))
    return config.validate()
