"""Config flow for Hanchu ESS integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import HanchuApi, HanchuApiError
from .const import (
    CONF_BATTERY_INTERVAL,
    CONF_BATTERY_SN,
    CONF_INCLUDE_SN_IN_NAME,
    CONF_INVERTER_SN,
    CONF_POWER_INTERVAL,
    DOMAIN,
    UPDATE_INTERVAL_BATTERY,
    UPDATE_INTERVAL_POWER,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_INVERTER_SN): str,
        vol.Optional(CONF_BATTERY_SN, default=""): str,
        vol.Optional(CONF_INCLUDE_SN_IN_NAME, default=False): bool,
    }
)


class HanchuConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Hanchu ESS."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD]
            inverter_sn = user_input[CONF_INVERTER_SN].strip()
            battery_sn = user_input.get(CONF_BATTERY_SN, "").strip()
            include_sn = user_input.get(CONF_INCLUDE_SN_IN_NAME, False)

            session = async_get_clientsession(self.hass)
            api = HanchuApi(session, username, password)

            try:
                await api.async_test_connection(inverter_sn)
            except HanchuApiError as err:
                _LOGGER.error("Hanchu connection test failed: %s", err)
                errors["base"] = "cannot_connect"
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error in Hanchu config flow")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(inverter_sn)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"Hanchu ESS ({inverter_sn})",
                    data={
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                        CONF_INVERTER_SN: inverter_sn,
                        CONF_BATTERY_SN: battery_sn,
                        CONF_INCLUDE_SN_IN_NAME: include_sn,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> HanchuOptionsFlowHandler:
        """Return the options flow handler."""
        return HanchuOptionsFlowHandler()


class HanchuOptionsFlowHandler(OptionsFlow):
    """Handle Hanchu ESS options (poll intervals)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_POWER_INTERVAL,
                    default=current.get(CONF_POWER_INTERVAL, UPDATE_INTERVAL_POWER),
                ): vol.All(int, vol.Range(min=10, max=3600)),
                vol.Optional(
                    CONF_BATTERY_INTERVAL,
                    default=current.get(CONF_BATTERY_INTERVAL, UPDATE_INTERVAL_BATTERY),
                ): vol.All(int, vol.Range(min=10, max=3600)),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
