"""Data coordinator: fetch, validate and cache TGE RDN prices."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CACHE_DAYS_BACK,
    DOMAIN,
    HTTP_TIMEOUT,
    PUBLISH_EARLIEST,
    STORAGE_VERSION,
    UPDATE_INTERVAL,
)
from .prices import PriceBook
from .tge_parser import (
    TZ,
    DayPrices,
    TgeNotPublished,
    TgeParseError,
    parse_page,
    url_for_delivery,
)

_LOGGER = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) HomeAssistant tge_rdn",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "pl,en;q=0.8",
}


@dataclass
class TgeRdnData:
    book: PriceBook
    last_success: datetime | None = None
    last_error: str | None = None
    tomorrow_status: str = "pending"  # pending | waiting | available | error
    warnings: list[str] = field(default_factory=list)


def now_pl() -> datetime:
    """Current time in Polish market time, independent of HA's configured zone."""
    return dt_util.utcnow().astimezone(TZ)


class TgeRdnCoordinator(DataUpdateCoordinator[TgeRdnData]):
    """Fetches each delivery day once, validates it, keeps it on disk."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self._store: Store[dict] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self._cache: dict[date, DayPrices] = {}
        self._last_success: datetime | None = None
        self._last_error: str | None = None
        self._reported_error: str | None = None

    async def async_load_cache(self) -> None:
        raw = await self._store.async_load()
        if not raw:
            return
        for item in raw.get("days", []):
            try:
                day = DayPrices.from_dict(item)
                self._cache[day.delivery_date] = day
            except (KeyError, ValueError, TypeError) as err:
                _LOGGER.warning("Ignoring corrupt cached day: %s", err)
        if raw.get("last_success"):
            self._last_success = datetime.fromisoformat(raw["last_success"])
        _LOGGER.debug("Loaded %d cached day(s)", len(self._cache))

    async def _async_save_cache(self) -> None:
        await self._store.async_save(
            {
                "days": [d.to_dict() for d in self._cache.values()],
                "last_success": self._last_success.isoformat() if self._last_success else None,
            }
        )

    async def _fetch_day(self, delivery: date) -> DayPrices:
        session = async_get_clientsession(self.hass)
        url = url_for_delivery(delivery)
        async with asyncio.timeout(HTTP_TIMEOUT):
            async with session.get(url, headers=HEADERS) as resp:
                if resp.status != 200:
                    raise TgeParseError(f"HTTP {resp.status} for {url}")
                html = await resp.text()
        day = await self.hass.async_add_executor_job(parse_page, html, delivery)
        day.fetched_at = dt_util.utcnow()
        for w in day.warnings:
            _LOGGER.warning("TGE %s: %s", delivery.isoformat(), w)
        return day

    async def _async_update_data(self) -> TgeRdnData:
        now = now_pl()
        today = now.date()
        tomorrow = today + timedelta(days=1)

        # prune
        for d in [d for d in self._cache if d < today - timedelta(days=CACHE_DAYS_BACK)]:
            del self._cache[d]

        changed = False
        errors: list[str] = []
        tomorrow_status = "available" if tomorrow in self._cache else "pending"

        for delivery in (today, tomorrow):
            if delivery in self._cache:
                continue
            if delivery == tomorrow and now.time() < PUBLISH_EARLIEST:
                continue
            try:
                self._cache[delivery] = await self._fetch_day(delivery)
                changed = True
                self._last_success = dt_util.utcnow()
                _LOGGER.info("TGE RDN Fixing I for %s loaded", delivery.isoformat())
                if delivery == tomorrow:
                    tomorrow_status = "available"
            except TgeNotPublished:
                _LOGGER.debug("TGE RDN for %s not published yet", delivery.isoformat())
                if delivery == tomorrow:
                    tomorrow_status = "waiting"
                else:
                    errors.append(f"{delivery.isoformat()}: not published")
            except (TgeParseError, aiohttp.ClientError, TimeoutError) as err:
                msg = f"{delivery.isoformat()}: {err.__class__.__name__}: {err}"
                errors.append(msg)
                if delivery == tomorrow:
                    tomorrow_status = "error"

        if changed:
            await self._async_save_cache()

        self._last_error = "; ".join(errors) or None
        if self._last_error and self._last_error != self._reported_error:
            _LOGGER.warning("TGE RDN fetch problem: %s", self._last_error)
        if self._last_error is None and self._reported_error:
            _LOGGER.info("TGE RDN fetch recovered")
        self._reported_error = self._last_error

        if today not in self._cache:
            raise UpdateFailed(self._last_error or f"no data for {today.isoformat()}")

        warnings = [w for d in self._cache.values() for w in d.warnings]
        return TgeRdnData(
            book=PriceBook(dict(self._cache)),
            last_success=self._last_success,
            last_error=self._last_error,
            tomorrow_status=tomorrow_status,
            warnings=warnings,
        )
