"""Constants for TGE RDN."""

from __future__ import annotations

from datetime import time, timedelta
from typing import Final

DOMAIN: Final = "tge_rdn"
NAME: Final = "TGE RDN"
ATTRIBUTION: Final = "Dane: Towarowa Giełda Energii S.A. (tge.pl), RDN Fixing I"

UPDATE_INTERVAL: Final = timedelta(minutes=5)
# Fixing I results appear after ~10:30-11:05 local time; don't hit tge.pl before.
PUBLISH_EARLIEST: Final = time(10, 15)
HTTP_TIMEOUT: Final = 30
CACHE_DAYS_BACK: Final = 2
STORAGE_VERSION: Final = 1

CONF_UNIT: Final = "unit"

# Kody walut wg ISO 4217 (wymóg HA dla monetary i cen w panelu Energia).
UNIT_ZL_MWH: Final = "PLN/MWh"
UNIT_ZL_KWH: Final = "PLN/kWh"
UNIT_GR_KWH: Final = "gr/kWh"
UNITS: Final = [UNIT_ZL_MWH, UNIT_ZL_KWH, UNIT_GR_KWH]
DEFAULT_UNIT: Final = UNIT_ZL_MWH
# Jednostki z wersji <= 0.1.x, migrowane przy starcie wpisu.
LEGACY_UNITS: Final = {"zł/MWh": UNIT_ZL_MWH, "zł/kWh": UNIT_ZL_KWH}

RES_HOUR: Final = "hour"
RES_QUARTER: Final = "quarter"
