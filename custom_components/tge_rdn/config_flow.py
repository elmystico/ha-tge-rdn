"""Config and options flow for TGE RDN."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import CONF_UNIT, DEFAULT_UNIT, DOMAIN, NAME, UNITS


def _schema(o: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_UNIT, default=o.get(CONF_UNIT, DEFAULT_UNIT)): selector.SelectSelector(
                selector.SelectSelectorConfig(options=UNITS, mode=selector.SelectSelectorMode.DROPDOWN)
            ),
        }
    )


class TgeRdnConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(title=NAME, data={}, options=user_input)
        return self.async_show_form(step_id="user", data_schema=_schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return TgeRdnOptionsFlow()


class TgeRdnOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(step_id="init", data_schema=_schema(dict(self.config_entry.options)))
