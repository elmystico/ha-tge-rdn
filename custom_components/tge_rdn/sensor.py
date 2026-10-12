"""Sensors for TGE RDN."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import RES_HOUR, RES_QUARTER
from .coordinator import now_pl
from .entity import TgeRdnEntity
from .prices import convert, precision, stats

# Price lists are useful live (charts, templates) but must not bloat the recorder.
LIST_ATTRS = frozenset({"prices", "prices_today", "prices_tomorrow"})


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities(
        [
            FixingSensor(entry, "fixing_1", RES_HOUR),
            NextHourSensor(entry),
            FixingSensor(entry, "fixing_1_quarter", RES_QUARTER, enabled=False),
            LastUpdateSensor(entry),
        ]
    )


def _series(slots, unit: str) -> list[dict[str, Any]]:
    return [{"time": s.start.isoformat(), "price": convert(s.fixing1, unit)} for s in slots]


class FixingSensor(TgeRdnEntity, SensorEntity):
    """Current Fixing I price. Attributes compatible with PiotrMachowski TGE / PGE-TGE."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:cash"
    _unrecorded_attributes = LIST_ATTRS

    def __init__(self, entry, key: str, resolution: str, enabled: bool = True) -> None:
        super().__init__(entry, key)
        self._attr_translation_key = key
        self._res = resolution
        self._attr_entity_registry_enabled_default = enabled
        self._attr_native_unit_of_measurement = self.rt.unit
        self._attr_suggested_display_precision = precision(self.rt.unit)

    @property
    def native_value(self) -> float | None:
        slot = self.book.slot_at(now_pl(), self._res)
        return convert(slot.fixing1, self.rt.unit) if slot else None

    @property
    def available(self) -> bool:
        return super().available and self.native_value is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        unit = self.rt.unit
        t_slots = self.book.slots(self.today(), self._res)
        n_slots = self.book.slots(self.tomorrow(), self._res)
        pt, pn = _series(t_slots, unit), _series(n_slots, unit)
        attrs: dict[str, Any] = {"prices_today": pt, "prices_tomorrow": pn, "prices": pt + pn}
        for label, slots in (("today", t_slots), ("tomorrow", n_slots)):
            for k, v in stats([s.fixing1 for s in slots]).items():
                attrs[f"{k}_{label}"] = convert(v, unit) if v is not None else None
        attrs["tomorrow_available"] = bool(n_slots)
        return attrs


class NextHourSensor(TgeRdnEntity, SensorEntity):
    _attr_translation_key = "fixing_1_next_hour"
    _attr_icon = "mdi:cash-fast"

    def __init__(self, entry) -> None:
        super().__init__(entry, "fixing_1_next_hour")
        self._attr_native_unit_of_measurement = self.rt.unit
        self._attr_suggested_display_precision = precision(self.rt.unit)

    @property
    def native_value(self) -> float | None:
        s = self.book.next_slot(now_pl(), RES_HOUR)
        return convert(s.fixing1, self.rt.unit) if s else None


class LastUpdateSensor(TgeRdnEntity, SensorEntity):
    _attr_translation_key = "last_update"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:update"

    def __init__(self, entry) -> None:
        super().__init__(entry, "last_update")

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.data.last_success

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self.coordinator.data
        return {
            "tomorrow_status": d.tomorrow_status,
            "last_error": d.last_error,
            "cached_days": sorted(x.isoformat() for x in d.book.days),
            "warnings": d.warnings[-10:],
        }
