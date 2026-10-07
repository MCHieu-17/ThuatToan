from evrp.charging.tariff import electricity_cost
from evrp.config import Config
from evrp.domain import Action, Instance


def charging_action(instance: Instance, config: Config, vehicle: int, station: int,
                    start: float, before: float, target: float, allocated_kw: float) -> Action:
    curve = instance.curves[instance.nodes[station].station_type]
    current, cost, segments = start, 0.0, []
    for energy, power in curve.segments(before, target, allocated_kw):
        end = current + energy / power
        segments.append((current, end, power))
        cost += electricity_cost(current, end, power, config)
        current = end
    deep = int((target - before) / instance.capacity_kwh >= config.deep_charge_delta_soc - 1e-9)
    return Action(vehicle, "charge", start, current, station, station, before, target,
                  electricity=cost, deep_charge=deep, allocated_kw=allocated_kw,
                  power_segments=tuple(segments))


def discharge_transition(before: float, after: float, low_episode: bool,
                         capacity: float, config: Config) -> tuple[bool, int]:
    # Rearm only after a recharge above the reset threshold. Count an excursion,
    # not every edge or every simulation tick spent below the low threshold.
    crossed = not low_episode and before / capacity >= config.deep_discharge_soc - 1e-9 \
        and after / capacity < config.deep_discharge_soc - 1e-9
    return low_episode or crossed, int(crossed)
