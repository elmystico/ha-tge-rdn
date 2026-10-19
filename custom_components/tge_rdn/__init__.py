"""TGE RDN (Fixing I) day-ahead electricity prices for Home Assistant."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change

from .const import CONF_UNIT, DEFAULT_UNIT, LEGACY_UNITS
from .coordinator import TgeRdnCoordinator

PLATFORMS = [Platform.SENSOR]


@dataclass
class TgeRdnRuntime:
    coordinator: TgeRdnCoordinator
    unit: str


type TgeRdnConfigEntry = ConfigEntry[TgeRdnRuntime]


async def async_setup_entry(hass: HomeAssistant, entry: TgeRdnConfigEntry) -> bool:
    legacy = entry.options.get(CONF_UNIT)
    if legacy in LEGACY_UNITS:
        hass.config_entries.async_update_entry(
            entry, options={**entry.options, CONF_UNIT: LEGACY_UNITS[legacy]}
        )
    coordinator = TgeRdnCoordinator(hass, entry)
    await coordinator.async_load_cache()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = TgeRdnRuntime(
        coordinator=coordinator,
        unit=entry.options.get(CONF_UNIT, DEFAULT_UNIT),
    )

    @callback
    def _tick(_now: datetime) -> None:
        # Prices are piecewise constant; refresh entity states on every quarter.
        coordinator.async_update_listeners()

    entry.async_on_unload(
        async_track_time_change(hass, _tick, minute=[0, 15, 30, 45], second=1)
    )
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: TgeRdnConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
