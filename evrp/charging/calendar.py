"""Station resource calendar: simultaneous ports and shared total power."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Reservation:
    station: int
    start: float
    end: float
    kw: float


class StationCalendar:
    def __init__(self) -> None:
        self.reservations: list[Reservation] = []

    def clear(self) -> None:
        self.reservations.clear()

    def available(self, station: int, start: float, end: float, kw: float,
                  ports: int, total_power_kw: float) -> bool:
        if end <= start:
            return True
        events: list[tuple[float, int, float]] = []
        for r in self.reservations:
            if r.station == station and r.start < end and start < r.end:
                events.append((r.start, -1, r.kw))
                events.append((r.end, 1, r.kw))
        events.append((start, -1, kw))
        events.append((end, 1, kw))
        events.sort(key=lambda item: (item[0], item[1]))
        count = 0
        power = 0.0
        max_count = 0
        max_power = 0.0
        for _, delta, value in events:
            count -= delta
            power -= delta * value
            max_count = max(max_count, count)
            max_power = max(max_power, power)
        return max_count <= ports and max_power <= total_power_kw + 1e-9

    def reserve(self, station: int, start: float, end: float, kw: float) -> None:
        if end > start:
            self.reservations.append(Reservation(station, start, end, kw))

    def power_profile(self) -> list[tuple[float, float, float]]:
        segments = []
        for r in self.reservations:
            segments.append((r.start, r.end, r.kw))
        return sorted(segments)