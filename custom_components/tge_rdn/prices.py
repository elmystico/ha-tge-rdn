"""Price conversion and per-day views. Pure Python, no HA imports."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from .const import RES_HOUR, UNIT_GR_KWH, UNIT_ZL_KWH, UNIT_ZL_MWH
from .tge_parser import DayPrices, Slot


def convert(zl_mwh: float, unit: str) -> float:
    if unit == UNIT_ZL_KWH:
        return round(zl_mwh / 1000, 5)
    if unit == UNIT_GR_KWH:
        return round(zl_mwh / 10, 3)
    return round(zl_mwh, 2)


def precision(unit: str) -> int:
    return {UNIT_ZL_MWH: 2, UNIT_ZL_KWH: 5, UNIT_GR_KWH: 3}.get(unit, 2)


class PriceBook:
    """Read-only view over cached days."""

    def __init__(self, days: dict[date, DayPrices]) -> None:
        self.days = days

    def slots(self, day: date, resolution: str = RES_HOUR) -> list[Slot]:
        d = self.days.get(day)
        if d is None:
            return []
        return d.hours if resolution == RES_HOUR else d.quarters

    def slot_at(self, t: datetime, resolution: str = RES_HOUR) -> Slot | None:
        for day in (t.date(), t.date() - timedelta(days=1)):
            for s in self.slots(day, resolution):
                if s.start <= t < s.end:
                    return s
        return None

    def next_slot(self, t: datetime, resolution: str = RES_HOUR) -> Slot | None:
        cur = self.slot_at(t, resolution)
        if cur is None:
            return None
        return self.slot_at(cur.end, resolution)


def stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "max": None, "avg": None}
    return {"min": min(values), "max": max(values), "avg": sum(values) / len(values)}
