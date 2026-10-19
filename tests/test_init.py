"""End-to-end tests against a real Home Assistant core (pytest-homeassistant-custom-component)."""

from datetime import date, timedelta

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.tge_rdn.const import DOMAIN
from custom_components.tge_rdn.tge_parser import url_for_delivery
from tests.tge_html import build_page

D13 = date(2026, 10, 13)
D14 = date(2026, 10, 14)


async def _done(hass):
    await hass.async_block_till_done(wait_background_tasks=True)


@pytest.fixture
async def setup(hass: HomeAssistant, aioclient_mock, freezer):
    await hass.config.async_set_time_zone("Europe/Warsaw")
    freezer.move_to("2026-10-13 09:00:00+02:00")
    aioclient_mock.get(url_for_delivery(D13), text=build_page(D13))
    aioclient_mock.get(url_for_delivery(D14), text=build_page(D14, blank=True))
    entry = MockConfigEntry(domain=DOMAIN, title="TGE RDN", data={}, options={"unit": "PLN/MWh"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await _done(hass)
    return entry


async def test_sensors(hass: HomeAssistant, setup, aioclient_mock):
    st = hass.states.get("sensor.tge_rdn_fixing_1")
    assert float(st.state) == 794.39  # H10 = 09:00-10:00
    assert st.attributes["unit_of_measurement"] == "PLN/MWh"
    today = st.attributes["prices_today"]
    assert len(today) == 24
    assert today[0] == {"time": "2026-10-13T00:00:00+02:00", "price": 660.25}
    assert today[-1] == {"time": "2026-10-13T23:00:00+02:00", "price": 511.22}
    assert st.attributes["prices_tomorrow"] == []
    assert st.attributes["prices"] == today
    assert st.attributes["tomorrow_available"] is False
    assert st.attributes["min_today"] == 511.22
    assert st.attributes["max_today"] == 1341.35
    assert float(hass.states.get("sensor.tge_rdn_fixing_1_next_hour").state) == 612.67
    assert hass.states.get("sensor.tge_rdn_last_update").attributes["tomorrow_status"] == "pending"
    # tomorrow is not requested before publication time
    assert not any(str(c[1]).endswith("dateShow=13-10-2026") for c in aioclient_mock.mock_calls)


async def test_state_follows_clock_and_tomorrow_fetch(hass: HomeAssistant, setup, aioclient_mock, freezer):
    freezer.move_to("2026-10-13 10:00:01+02:00")
    async_fire_time_changed(hass)
    await _done(hass)
    assert float(hass.states.get("sensor.tge_rdn_fixing_1").state) == 612.67

    # after publication time the integration asks for tomorrow; still blank -> waiting
    freezer.move_to("2026-10-13 10:20:00+02:00")
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=6))
    await _done(hass)
    assert any(str(c[1]).endswith("dateShow=13-10-2026") for c in aioclient_mock.mock_calls)
    assert hass.states.get("sensor.tge_rdn_last_update").attributes["tomorrow_status"] == "waiting"

    # tomorrow gets published -> attributes contain 48 h
    aioclient_mock.clear_requests()
    aioclient_mock.get(url_for_delivery(D14), text=build_page(D14))
    freezer.move_to("2026-10-13 11:10:00+02:00")
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=6))
    await _done(hass)
    st = hass.states.get("sensor.tge_rdn_fixing_1")
    assert st.attributes["tomorrow_available"] is True
    assert len(st.attributes["prices"]) == 48
    assert st.attributes["prices_tomorrow"][0]["time"] == "2026-10-14T00:00:00+02:00"

    # midnight rolls over from cache, TGE down does not matter
    aioclient_mock.clear_requests()
    aioclient_mock.get(url_for_delivery(D14), status=500)
    freezer.move_to("2026-10-14 00:00:01+02:00")
    async_fire_time_changed(hass)
    await _done(hass)
    st = hass.states.get("sensor.tge_rdn_fixing_1")
    assert float(st.state) == 660.25  # H01 of the 14th (same fixture values)
    assert st.attributes["prices_today"][0]["time"].startswith("2026-10-14")


async def test_cache_survives_restart(hass: HomeAssistant, setup, aioclient_mock):
    entry = setup
    await hass.config_entries.async_unload(entry.entry_id)
    await _done(hass)
    aioclient_mock.clear_requests()
    aioclient_mock.get(url_for_delivery(D13), status=500)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await _done(hass)
    # today's prices come from disk while TGE is down
    assert float(hass.states.get("sensor.tge_rdn_fixing_1").state) == 794.39
    assert aioclient_mock.call_count == 0


async def test_options_change_unit(hass: HomeAssistant, setup):
    entry = setup
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"unit": "PLN/kWh"})
    assert result["type"] == "create_entry"
    await _done(hass)
    st = hass.states.get("sensor.tge_rdn_fixing_1")
    assert float(st.state) == 0.79439
    assert st.attributes["prices_today"][0]["price"] == 0.66025


async def test_config_flow(hass: HomeAssistant, aioclient_mock, freezer):
    freezer.move_to("2026-10-13 09:00:00+02:00")
    aioclient_mock.get(url_for_delivery(D13), text=build_page(D13))
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == "form"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"unit": "PLN/MWh"})
    assert result["type"] == "create_entry"
    await _done(hass)
    assert hass.states.get("sensor.tge_rdn_fixing_1") is not None


async def test_wrong_day_fails_setup(hass: HomeAssistant, aioclient_mock, freezer):
    freezer.move_to("2026-10-13 09:00:00+02:00")
    aioclient_mock.get(url_for_delivery(D13), text=build_page(D14))  # TGE shows another day
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await _done(hass)
    assert entry.state.name == "SETUP_RETRY"


async def test_legacy_unit_migrated(hass: HomeAssistant, aioclient_mock, freezer):
    await hass.config.async_set_time_zone("Europe/Warsaw")
    freezer.move_to("2026-10-13 09:00:00+02:00")
    aioclient_mock.get(url_for_delivery(D13), text=build_page(D13))
    aioclient_mock.get(url_for_delivery(D14), text=build_page(D14, blank=True))
    entry = MockConfigEntry(domain=DOMAIN, title="TGE RDN", data={}, options={"unit": "zł/MWh"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await _done(hass)
    assert entry.options["unit"] == "PLN/MWh"
    assert hass.states.get("sensor.tge_rdn_fixing_1").attributes["unit_of_measurement"] == "PLN/MWh"
