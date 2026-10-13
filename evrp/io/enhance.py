"""Build the enhanced dataset from the original Montoya XML files.

Enhancements added on top of the physical Montoya data:
  * realtime orders: a fraction of customers receive a release time;
  * limited station capacity: ports and total power per station;
  * TOU electricity tariff and battery-degradation parameters.

The result is a self-contained JSON file under data/enhanced so runs are
reproducible without re-reading the XML. The original XML files are untouched.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

from evrp.config import Config
from evrp.domain import CUSTOMER, STATION, Curve, Instance, Node, StationInfo
from evrp.io.montoya import discover_instances, load_original


FORMAT = "evrp-enhanced-1"


@dataclass
class ScenarioMeta:
    tou: list[dict]
    degradation: dict
    start_clock_hour: float
    dynamic_fraction: float
    release_until_fraction: float


def _vehicles_for(n_customers: int, config: Config) -> int:
    if config.vehicles > 0:
        return config.vehicles
    needed = -(-n_customers // config.customers_per_vehicle)
    return max(config.min_vehicles, needed)


def build_enhanced(instance: Instance, config: Config, seed: int) -> dict:
    rng = random.Random(seed)
    customers = list(instance.customers)
    horizon = instance.horizon_hours * config.horizon_factor
    dynamic_count = int(round(config.dynamic_fraction * len(customers)))
    release_until = config.release_until_fraction * horizon
    released = set(rng.sample(customers, dynamic_count)) if dynamic_count else set()
    releases = {c: (rng.uniform(1e-6, release_until) if c in released else 0.0) for c in customers}

    nodes = []
    for node in instance.nodes.values():
        entry = {
            "id": node.id,
            "kind": node.kind,
            "x": node.x,
            "y": node.y,
            "service_hours": node.service_hours,
            "station_type": node.station_type,
            "release_hours": round(releases.get(node.id, 0.0), 6),
        }
        nodes.append(entry)
    nodes.sort(key=lambda item: item["id"])

    stations = {}
    for station_id in instance.stations_info:
        params = config.stations_by_type.get(info_kind(instance, station_id),
                                             config.stations_by_type["normal"])
        stations[str(station_id)] = {
            "ports": int(params["ports"]),
            "power_kw": float(params["power_kw"]),
            "charger_kw": float(params["charger_kw"]),
        }

    return {
        "format": FORMAT,
        "name": instance.name,
        "source": instance.source,
        "seed": seed,
        "energy_unit": "kWh",
        "depot": instance.depot,
        "capacity_kwh": instance.capacity_kwh,
        "consumption_kwh_km": instance.consumption_kwh_km,
        "speed_kmh": instance.speed_kmh,
        "horizon_hours": horizon,
        "vehicles": _vehicles_for(len(customers), config),
        "start_clock_hour": config.start_clock_hour,
        "dynamic_fraction": config.dynamic_fraction,
        "release_until_fraction": config.release_until_fraction,
        "tou": [dict(b) for b in config.tou],
        "degradation": {
            "deep_charge_delta_soc": config.deep_charge_delta_soc,
            "deep_discharge_soc": config.deep_discharge_soc,
            "discharge_reset_soc": config.discharge_reset_soc,
            "deep_charge_cost": config.deep_charge_cost,
            "deep_discharge_cost": config.deep_discharge_cost,
            "reserve_soc": config.reserve_soc,
        },
        "curves": {name: [list(p) for p in curve.points] for name, curve in instance.curves.items()},
        "nodes": nodes,
        "stations": stations,
    }


def info_kind(instance: Instance, station_id: int) -> str:
    return instance.nodes[station_id].station_type or "normal"


def write_enhanced(payload: dict, out_dir: str | Path) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{payload['name']}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def prepare_dataset(data_dir: str | Path, out_dir: str | Path, config: Config,
                    energy_unit: str = "Wh") -> list[Path]:
    written = []
    for xml in discover_instances(data_dir):
        instance = load_original(xml, energy_unit)
        payload = build_enhanced(instance, config, config.seed)
        written.append(write_enhanced(payload, out_dir))
    return written


def discover_enhanced(directory: str | Path) -> list[Path]:
    root = Path(directory)
    if not root.exists():
        return []
    return sorted(root.glob("*.json"))


def load_enhanced(path: str | Path) -> tuple[Instance, ScenarioMeta]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("format") != FORMAT:
        raise ValueError(f"{path}: not an enhanced dataset (format={data.get('format')!r})")
    nodes: dict[int, Node] = {}
    for entry in data["nodes"]:
        nodes[entry["id"]] = Node(
            id=entry["id"],
            kind=entry["kind"],
            x=entry["x"],
            y=entry["y"],
            service_hours=entry.get("service_hours", 0.0),
            station_type=entry.get("station_type", ""),
            release_hours=entry.get("release_hours", 0.0),
        )
    stations_info = {
        int(key): StationInfo(int(value["ports"]), float(value["power_kw"]), float(value["charger_kw"]))
        for key, value in data["stations"].items()
    }
    curves = {name: Curve(tuple((float(q), float(t)) for q, t in points))
              for name, points in data["curves"].items()}
    instance = Instance(
        name=data["name"],
        nodes=nodes,
        depot=data["depot"],
        capacity_kwh=data["capacity_kwh"],
        consumption_kwh_km=data["consumption_kwh_km"],
        speed_kmh=data["speed_kmh"],
        horizon_hours=data["horizon_hours"],
        curves=curves,
        stations_info=stations_info,
        vehicles=data["vehicles"],
        source=data.get("source", str(path)),
        energy_unit=data.get("energy_unit", "kWh"),
    )
    meta = ScenarioMeta(
        tou=data["tou"],
        degradation=data["degradation"],
        start_clock_hour=data["start_clock_hour"],
        dynamic_fraction=data["dynamic_fraction"],
        release_until_fraction=data["release_until_fraction"],
    )
    return instance, meta


def apply_meta(config: Config, meta: ScenarioMeta) -> Config:
    config.tou = [dict(b) for b in meta.tou]
    config.start_clock_hour = meta.start_clock_hour
    config.dynamic_fraction = meta.dynamic_fraction
    config.release_until_fraction = meta.release_until_fraction
    for key, value in meta.degradation.items():
        setattr(config, key, value)
    return config.validate()


def release_map(instance: Instance) -> dict[int, float]:
    return {node.id: node.release_hours for node in instance.nodes.values() if node.kind == CUSTOMER}