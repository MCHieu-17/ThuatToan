"""Independent physical and scheduling validation of the executed trace."""
from __future__ import annotations

from collections import Counter

from evrp.charging.calendar import StationCalendar
from evrp.charging.model import charging_action, discharge_transition
from evrp.config import Config
from evrp.domain import Action, Instance


def validate_trace(instance: Instance, config: Config, releases: dict[int, float],
                   actions: list[Action]) -> dict:
    errors = []
    tol = 1e-6
    calendar = StationCalendar(config)
    services = Counter()
    for v in range(config.vehicles):
        # Stable ordering preserves zero-duration service events at a drive endpoint.
        trace = sorted((a for a in actions if a.vehicle == v), key=lambda a: (a.start, a.end))
        node, energy, at, low = instance.depot, instance.capacity_kwh, 0.0, False
        charged_here = False
        for a in trace:
            if a.start < at - tol or a.end < a.start - tol:
                errors.append(f"Vehicle {v}: overlapping or negative action interval")
            if a.origin != node or abs(a.energy_before - energy) > tol:
                errors.append(f"Vehicle {v}: discontinuous position or energy")
            if a.start > at + tol and node != instance.depot:
                errors.append(f"Vehicle {v}: unaccounted waiting time away from depot")
            if a.end > instance.horizon_hours + tol:
                errors.append(f"Vehicle {v}: action exceeds horizon")
            if not instance.capacity_kwh * config.reserve_soc - tol <= a.energy_after <= instance.capacity_kwh + tol:
                errors.append(f"Vehicle {v}: SoC bound violation")
            if a.kind == "drive":
                charged_here = False
                duration, used = instance.travel(a.origin, a.destination)
                if abs(a.end - a.start - duration) > tol or abs(a.energy_before - used - a.energy_after) > tol:
                    errors.append(f"Vehicle {v}: incorrect travel time/energy")
                low, count = discharge_transition(energy, a.energy_after, low, instance.capacity_kwh, config)
                if count != a.deep_discharge:
                    errors.append(f"Vehicle {v}: incorrect deep-discharge count")
            elif a.kind == "charge":
                if charged_here:
                    errors.append(f"Vehicle {v}: charging session split without leaving station")
                charged_here = True
                if instance.nodes[a.origin].kind != "station":
                    errors.append(f"Vehicle {v}: charging outside a station")
                else:
                    reference = charging_action(instance, config, v, a.origin, a.start,
                                                a.energy_before, a.energy_after, a.allocated_kw)
                    if abs(reference.end - a.end) > tol or abs(reference.electricity - a.electricity) > tol \
                            or reference.deep_charge != a.deep_charge:
                        errors.append(f"Vehicle {v}: inconsistent nonlinear charging / TOU / degradation")
                    if len(reference.power_segments) != len(a.power_segments) or any(
                        any(abs(x - y) > tol for x, y in zip(left, right))
                        for left, right in zip(reference.power_segments, a.power_segments)
                    ):
                        errors.append(f"Vehicle {v}: inconsistent actual power trace")
                if energy != a.energy_after and a.energy_after / instance.capacity_kwh >= config.discharge_reset_soc - tol:
                    low = False
                try:
                    calendar.reserve(a)
                except ValueError:
                    errors.append(f"Station {a.origin}: port or shared-power violation")
            elif a.kind == "service":
                services[a.origin] += 1
                if instance.nodes[a.origin].kind != "customer":
                    errors.append(f"Vehicle {v}: service at noncustomer node")
                if a.start < releases.get(a.origin, 0) - tol:
                    errors.append(f"Customer {a.origin}: served before release")
                if abs(a.end - a.start - instance.nodes[a.origin].service_hours) > tol:
                    errors.append(f"Customer {a.origin}: incorrect service duration")
            elif a.kind != "wait":
                errors.append(f"Unknown action kind {a.kind}")
            if a.kind in {"wait", "service"} and abs(a.energy_after - a.energy_before) > tol:
                errors.append(f"Vehicle {v}: energy changed during waiting/service")
            if a.kind != "drive" and a.origin != a.destination:
                errors.append(f"Vehicle {v}: stationary action changes position")
            if a.kind != "charge" and (a.electricity or a.deep_charge):
                errors.append(f"Vehicle {v}: unexpected charging cost/count")
            if a.kind != "drive" and a.deep_discharge:
                errors.append(f"Vehicle {v}: unexpected deep-discharge count")
            node, energy, at = a.destination, a.energy_after, a.end
        if trace and node != instance.depot:
            errors.append(f"Vehicle {v}: does not return to depot")
    duplicates = sorted(n for n, count in services.items() if count > 1)
    if duplicates:
        errors.append(f"Customers served more than once: {duplicates}")
    if any(a.vehicle not in range(config.vehicles) for a in actions):
        errors.append("Trace references an unknown vehicle")
    return {"valid": not errors, "errors": errors, "checked_actions": len(actions),
            "served_once": sorted(n for n, count in services.items() if count == 1)}
