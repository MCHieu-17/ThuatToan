"""Reader for the original Montoya et al. (2017) XML instances.

The files use Wh, Wh/km and hours. Energy is converted to kWh here once so the
rest of the code never has to guess units. No charging time is recomputed: the
piecewise-linear curves are kept as breakpoints.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from evrp.config import DEFAULT_STATIONS
from evrp.domain import CUSTOMER, DEPOT, STATION, Curve, Instance, Node, StationInfo


def _tag(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _find(element: ET.Element, name: str) -> ET.Element | None:
    for child in element:
        if _tag(child) == name:
            return child
    return None


def _findall(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in element if _tag(child) == name]


def _child_text(element: ET.Element, name: str, default: str | None = None) -> str | None:
    child = _find(element, name)
    if child is None or child.text is None:
        return default
    return child.text.strip()


def discover_instances(directory: str | Path) -> list[Path]:
    root = Path(directory)
    if not root.exists():
        return []
    return sorted(root.rglob("*.xml"))


def load_original(path: str | Path, energy_unit: str = "Wh") -> Instance:
    tree = ET.parse(path)
    root = tree.getroot()
    if _tag(root) != "instance":
        raise ValueError(f"{path}: expected <instance> root")
    name_node = _find(_find(root, "info"), "name")
    name = name_node.text.strip() if name_node is not None and name_node.text else Path(path).stem

    network = _find(root, "network")
    if network is None:
        raise ValueError(f"{path}: missing <network>")
    nodes_elem = _find(network, "nodes")
    if nodes_elem is None:
        raise ValueError(f"{path}: missing <nodes>")

    requests_elem = _find(root, "requests")
    requests = {}
    if requests_elem is not None:
        for req in _findall(requests_elem, "request"):
            node_id = req.get("node")
            if node_id is None:
                continue
            requests[int(node_id)] = float(_child_text(req, "service_time", "0") or 0)

    nodes: dict[int, Node] = {}
    depot: int | None = None
    for element in _findall(nodes_elem, "node"):
        node_id = int(element.get("id"))
        node_type = element.get("type")
        x = float(_child_text(element, "cx", "0"))
        y = float(_child_text(element, "cy", "0"))
        if node_type == "0":
            kind = DEPOT
            if depot is None:
                depot = node_id
        elif node_type == "1":
            kind = CUSTOMER
        elif node_type == "2":
            kind = STATION
        else:
            raise ValueError(f"{path}: unknown node type {node_type!r} at node {node_id}")
        station_type = ""
        if kind == STATION:
            custom = _find(element, "custom")
            station_type = (_child_text(custom, "cs_type", "normal") if custom is not None else "normal")
        nodes[node_id] = Node(
            id=node_id,
            kind=kind,
            x=x,
            y=y,
            service_hours=requests.get(node_id, 0.0) if kind == CUSTOMER else 0.0,
            station_type=station_type,
        )
    if depot is None:
        raise ValueError(f"{path}: no depot node")

    fleet = _find(root, "fleet")
    profile = _find(fleet, "vehicle_profile") if fleet is not None else None
    if profile is None:
        raise ValueError(f"{path}: missing vehicle profile")
    custom = _find(profile, "custom")

    def _number(container: ET.Element | None, tag: str, default: float) -> float:
        text = _child_text(container, tag) if container is not None else None
        return float(text) if text is not None else default

    speed = _number(profile, "speed_factor", 40.0)
    horizon = _number(profile, "max_travel_time", 10.0)
    scale = 1000.0 if energy_unit == "Wh" else 1.0
    capacity = _number(custom, "battery_capacity", 16000.0) / scale
    consumption = _number(custom, "consumption_rate", 125.0) / scale

    curves: dict[str, Curve] = {}
    functions = _find(custom, "charging_functions") if custom is not None else None
    for function in _findall(functions, "function") if functions is not None else []:
        cs_type = function.get("cs_type") or "normal"
        points = []
        for bp in _findall(function, "breakpoint"):
            level = float(_child_text(bp, "battery_level", "0")) / scale
            time = float(_child_text(bp, "charging_time", "0"))
            points.append((level, time))
        points.sort()
        if not points or points[0][0] > 1e-9:
            points.insert(0, (0.0, 0.0))
        curves[cs_type] = Curve(tuple(points))
    if not curves:
        curves["normal"] = Curve(((0.0, 0.0), (capacity, 1.0)))

    stations_info: dict[int, StationInfo] = {}
    for node in nodes.values():
        if node.kind != STATION:
            continue
        params = DEFAULT_STATIONS.get(node.station_type, DEFAULT_STATIONS["normal"])
        stations_info[node.id] = StationInfo(
            ports=int(params["ports"]),
            power_kw=float(params["power_kw"]),
            charger_kw=float(params["charger_kw"]),
        )

    return Instance(
        name=name,
        nodes=nodes,
        depot=depot,
        capacity_kwh=capacity,
        consumption_kwh_km=consumption,
        speed_kmh=speed,
        horizon_hours=horizon,
        curves=curves,
        stations_info=stations_info,
        vehicles=0,
        source=str(path),
        energy_unit=energy_unit,
    )