"""Config flow for Hanchu ESS integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import HanchuApi, HanchuApiError
from .const import CONF_BATTERY_SN, CONF_INVERTER_SN, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_INVERTER_SN): str,
        vol.Optional(CONF_BATTERY_SN, default=""): str,
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
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )
