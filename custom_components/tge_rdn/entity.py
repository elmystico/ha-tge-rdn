"""Base entity."""

from __future__ import annotations

from datetime import date, timedelta

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN, NAME
from .coordinator import TgeRdnCoordinator, now_pl


class TgeRdnEntity(CoordinatorEntity[TgeRdnCoordinator]):
    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    _platform = "sensor"

    def __init__(self, entry, key: str) -> None:
        super().__init__(entry.runtime_data.coordinator)
        self.rt = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        # Stable, language-independent entity_id for automations (user can rename).
        self.entity_id = f"{self._platform}.tge_rdn_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=NAME,
            manufacturer="Towarowa Giełda Energii",
            model="RDN Fixing I",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://tge.pl/energia-elektryczna-rdn",
        )

    @property
    def book(self):
        return self.coordinator.data.book

    @staticmethod
    def today() -> date:
        return now_pl().date()

    @staticmethod
    def tomorrow() -> date:
        return now_pl().date() + timedelta(days=1)
