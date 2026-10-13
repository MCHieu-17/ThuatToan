"""Nonlinear charging and battery-degradation event model."""
from __future__ import annotations

from evrp.charging import tariff
from evrp.config import Config
from evrp.domain import Action, Instance


def charging_action(instance: Instance, config: Config, vehicle: int, station: int,
                    start: float, before: float, target: float, allocated_kw: float) -> Action:
    """Build a charging action from `before` to `target` kWh at constant reservation."""
    node = instance.nodes[station]
    curve = instance.curves[node.station_type or "normal"]
    segments = []
    t = start
    for energy, power in curve.segments(before, target, allocated_kw):
        duration = energy / power
        segments.append((t, t + duration, power))
        t += duration
    delta_soc = (target - before) / instance.capacity_kwh
    deep_charge = 1 if delta_soc >= config.deep_charge_delta_soc - 1e-9 else 0
    cost = tariff.cost_of_segments(config, segments)
    charge_energy = target - before
    return Action(
        vehicle=vehicle,
        kind="charge",
        start=start,
        end=t,
        origin=station,
        destination=station,
        energy_before=before,
        energy_after=target,
        electricity_cost=cost,
        deep_charge=deep_charge,
        allocated_kw=allocated_kw,
        power_segments=tuple(segments),
        note=f"charge {charge_energy:.3f} kWh",
    )


def discharge_transition(before: float, after: float, low_episode: bool,
                         capacity: float, config: Config) -> tuple[bool, int]:
    """Return (new low-episode flag, deep-discharge event count) for one drive."""
    low = low_episode
    events = 0
    threshold = capacity * config.deep_discharge_soc
    reset = capacity * config.discharge_reset_soc
    if not low and before >= threshold - 1e-9 and after < threshold - 1e-9:
        events = 1
        low = True
    elif low and after >= reset - 1e-9:
        low = False
    return low, events


def event_costs(actions, config: Config) -> tuple[int, int, float]:
    """Aggregate (deep charges, deep discharges, degradation cost) over actions."""
    charges = sum(action.deep_charge for action in actions)
    discharges = sum(action.deep_discharge for action in actions)
    cost = charges * config.deep_charge_cost + discharges * config.deep_discharge_cost
    return charges, discharges, cost