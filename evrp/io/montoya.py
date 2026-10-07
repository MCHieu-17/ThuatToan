"""Strict reader for Montoya 2017 VRP-REP XML, including XML namespaces.

The original dataset stores Wh, hours and km/h. Never infer energy units from
the magnitude: --energy-unit is an explicit override for converted XML files.
"""
from __future__ import annotations

from math import isfinite
from pathlib import Path
import xml.etree.ElementTree as ET

from evrp.domain import Curve, Instance, Node


def discover_instances(directory: str | Path = "data/montoya-et-al-2017") -> list[Path]:
    root = Path(directory)
    if not root.is_dir():
        raise FileNotFoundError(f"Dataset directory does not exist: {root.resolve()}")
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() == ".xml")


def load_instance(path: str | Path, energy_unit: str = "Wh") -> Instance:
    if energy_unit not in {"Wh", "kWh"}:
        raise ValueError("energy_unit must be Wh or kWh")
    scale = 0.001 if energy_unit == "Wh" else 1.0
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise ValueError(f"{Path(path).name}: invalid XML: {exc}") from exc
    for el in root.iter():
        el.tag = el.tag.rsplit("}", 1)[-1]

    def number(parent, tag: str, default=None):
        value = parent.findtext(tag) if parent is not None else None
        if value is None:
            if default is not None:
                return default
            raise ValueError(f"{Path(path).name}: missing <{tag}>")
        result = float(value)
        if not isfinite(result):
            raise ValueError(f"Nonfinite <{tag}>")
        return result

    profiles = root.findall("./fleet/vehicle_profile")
    if len(profiles) != 1:
        raise ValueError("Only a single homogeneous vehicle profile is supported")
    profile = profiles[0]
    depot = int(number(profile, "departure_node"))
    if int(number(profile, "arrival_node")) != depot:
        raise ValueError("Departure and arrival depot must be identical")
    capacity = number(profile, "./custom/battery_capacity") * scale
    consumption = number(profile, "./custom/consumption_rate") * scale
    speed = number(profile, "speed_factor")
    horizon = number(profile, "max_travel_time")
    if min(capacity, consumption, speed, horizon) <= 0:
        raise ValueError("Battery, consumption, speed and horizon must be positive")
    if root.find("./network/euclidean") is None:
        raise ValueError("This reader requires a Euclidean Montoya network")

    services: dict[int, float] = {}
    for request in root.findall("./requests/request"):
        node = int(request.attrib["node"])
        if node in services:
            raise ValueError("Multiple requests at the same node are not supported")
        service = number(request, "service_time", 0.0)
        if service < 0:
            raise ValueError("Service time cannot be negative")
        services[node] = service
    nodes: dict[int, Node] = {}
    kinds = {"0": "depot", "1": "customer", "2": "station"}
    for item in root.findall("./network/nodes/node"):
        node_id = int(item.attrib["id"])
        if node_id in nodes or item.attrib.get("type") not in kinds:
            raise ValueError("Duplicate node ID or unsupported node type")
        kind = kinds[item.attrib["type"]]
        if kind == "customer" and node_id not in services:
            raise ValueError(f"Customer {node_id} has no request")
        nodes[node_id] = Node(node_id, kind, number(item, "cx"), number(item, "cy"),
                              services.get(node_id, 0.0), item.findtext("./custom/cs_type", ""))
    if depot not in nodes or nodes[depot].kind != "depot":
        raise ValueError("Depot is missing or has an invalid node type")
    if any(n not in nodes or nodes[n].kind != "customer" for n in services):
        raise ValueError("Request references an unknown or noncustomer node")

    curves = {}
    for function in profile.findall("./custom/charging_functions/function"):
        name = function.attrib["cs_type"]
        points = tuple((number(b, "battery_level") * scale, number(b, "charging_time"))
                       for b in function.findall("breakpoint"))
        if len(points) < 2 or points[0] != (0.0, 0.0):
            raise ValueError(f"Curve {name} must start at (0,0) and have >= 2 points")
        if any(q1 <= q0 or t1 <= t0 for (q0, t0), (q1, t1) in zip(points, points[1:])):
            raise ValueError(f"Curve {name} must be strictly increasing")
        if abs(points[-1][0] - capacity) > 1e-6:
            raise ValueError(f"Curve {name} must end at battery capacity")
        curves[name] = Curve(points)
    if any(n.station_type not in curves for n in nodes.values() if n.kind == "station"):
        raise ValueError("A charging station references a missing charging function")
    return Instance(root.findtext("./info/name", Path(path).stem), nodes, depot,
                    capacity, consumption, speed, horizon, curves, str(Path(path)), energy_unit)
