"""Conservative constant-power reservations with half-open time intervals.

A session reserves allocated kW even when its battery taper draws less. This
keeps all earlier plans unchanged and guarantees the grid limit without a
coupled continuous power-sharing optimization.
"""
from dataclasses import dataclass

from evrp.config import Config
from evrp.domain import Action


@dataclass(frozen=True)
class Booking:
    station: int
    vehicle: int
    start: float
    end: float
    power_kw: float


class StationCalendar:
    def __init__(self, config: Config, bookings: list[Booking] | None = None):
        self.config = config
        self.bookings = list(bookings or [])

    def clone(self) -> "StationCalendar":
        return StationCalendar(self.config, self.bookings)

    def available(self, station: int, start: float, end: float, power: float) -> bool:
        limits = self.config.station(station)
        if end <= start or power <= 0 or power > min(limits["charger_kw"], limits["power_kw"]) + 1e-9:
            return False
        overlap = [b for b in self.bookings if b.station == station
                   and b.start < end - 1e-9 and b.end > start + 1e-9]
        boundaries = sorted({start, end} | {max(start, b.start) for b in overlap}
                            | {min(end, b.end) for b in overlap})
        for left, right in zip(boundaries, boundaries[1:]):
            midpoint = (left + right) / 2
            active = [b for b in overlap if b.start <= midpoint < b.end]
            if len(active) >= limits["ports"]:
                return False
            if sum(b.power_kw for b in active) + power > limits["power_kw"] + 1e-8:
                return False
        return True

    def reserve(self, action: Action) -> None:
        if action.kind == "charge":
            if not self.available(action.origin, action.start, action.end, action.allocated_kw):
                raise ValueError("Invalid charging reservation")
            self.bookings.append(Booking(action.origin, action.vehicle, action.start,
                                         action.end, action.allocated_kw))

    def fingerprint(self) -> tuple:
        return tuple(sorted((b.station, b.vehicle, round(b.start, 8), round(b.end, 8),
                             round(b.power_kw, 8)) for b in self.bookings))
