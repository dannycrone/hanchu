"""Config flow for Hanchu ESS integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import HanchuApi, HanchuApiError, HanchuAuthError
from .const import (
    CONF_BATTERY_INTERVAL,
    CONF_BATTERY_SN,
    CONF_BATTERY_SNS,
    CONF_INCLUDE_SN_IN_NAME,
    CONF_INVERTER_SN,
    CONF_INVERTER_SNS,
    CONF_POWER_INTERVAL,
    DOMAIN,
    UPDATE_INTERVAL_BATTERY,
    UPDATE_INTERVAL_POWER,
)

_LOGGER = logging.getLogger(__name__)

DISCOVERY_BATTERY_SN = "discovery_battery_sn"
DISCOVERY_INVERTER_SN = "discovery_inverter_sn"

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_INVERTER_SN, default=""): str,
        vol.Optional(CONF_BATTERY_SN, default=""): str,
        vol.Optional(CONF_INCLUDE_SN_IN_NAME, default=False): bool,
    }
)


class HanchuConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Hanchu ESS."""

    VERSION = 2

    def __init__(self) -> None:
        """Initialize discovery state."""
        super().__init__()
        self._pending_entry_data: dict[str, Any] | None = None
        self._inverter_choices: dict[str, str] | None = None
        self._battery_choices: dict[str, str] | None = None

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
                if inverter_sn:
                    await api.async_test_connection(inverter_sn)
                    if battery_sn:
                        battery_sn = await self._async_validate_or_resolve_battery_sn(
                            api, battery_sn
                        )
                elif battery_sn:
                    battery_sn = await self._async_validate_or_resolve_battery_sn(
                        api, battery_sn
                    )
                else:
                    inverters = await api.async_discover_inverters()
                    batteries = await api.async_discover_batteries()
                    if not inverters and not batteries:
                        errors["base"] = "no_devices_found"
                        return self.async_show_form(
                            step_id="user",
                            data_schema=STEP_USER_SCHEMA,
                            errors=errors,
                        )

                    inverter_sn = inverters[0]["sn"] if len(inverters) == 1 else ""
                    battery_sn = batteries[0]["sn"] if len(batteries) == 1 else ""

                    if len(inverters) > 1 or len(batteries) > 1:
                        self._pending_entry_data = {
                            CONF_USERNAME: username,
                            CONF_PASSWORD: password,
                            CONF_INCLUDE_SN_IN_NAME: include_sn,
                        }
                        self._inverter_choices = _build_inverter_choices(inverters, batteries)
                        self._battery_choices = {
                            battery["sn"]: _format_battery_choice(battery)
                            for battery in batteries
                        }
                        return await self.async_step_devices()

                    if inverter_sn:
                        await api.async_test_connection(inverter_sn)
                    if battery_sn:
                        await api.async_test_battery_connection(battery_sn)
            except HanchuApiError as err:
                _LOGGER.error("Hanchu connection test failed: %s", err)
                errors["base"] = "cannot_connect"
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error in Hanchu config flow")
                errors["base"] = "unknown"
            else:
                return await self._async_create_hanchu_entry(
                    username=username,
                    password=password,
                    inverter_sn=inverter_sn,
                    battery_sn=battery_sn,
                    include_sn=include_sn,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    async def async_step_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user choose between discovered devices."""
        errors: dict[str, str] = {}

        if not self._pending_entry_data:
            return await self.async_step_user()

        if user_input is not None:
            inverter_sns = _selected_serials(user_input.get(DISCOVERY_INVERTER_SN, []))
            battery_sns = _selected_serials(user_input.get(DISCOVERY_BATTERY_SN, []))
            data = self._pending_entry_data

            if not inverter_sns and not battery_sns:
                errors["base"] = "missing_serial"
            else:
                session = async_get_clientsession(self.hass)
                api = HanchuApi(session, data[CONF_USERNAME], data[CONF_PASSWORD])

                try:
                    for inverter_sn in inverter_sns:
                        await api.async_test_connection(inverter_sn)
                    for battery_sn in battery_sns:
                        await api.async_test_battery_connection(battery_sn)
                except HanchuApiError as err:
                    _LOGGER.error("Hanchu discovered device validation failed: %s", err)
                    errors["base"] = "cannot_connect"
                except aiohttp.ClientError:
                    errors["base"] = "cannot_connect"
                except Exception:  # noqa: BLE001
                    _LOGGER.exception("Unexpected error validating discovered devices")
                    errors["base"] = "unknown"

            if errors:
                return self._show_devices_form(errors)

            return await self._async_create_hanchu_entry(
                username=data[CONF_USERNAME],
                password=data[CONF_PASSWORD],
                inverter_sn=inverter_sns[0] if inverter_sns else "",
                battery_sn=battery_sns[0] if battery_sns else "",
                inverter_sns=inverter_sns,
                battery_sns=battery_sns,
                include_sn=data.get(CONF_INCLUDE_SN_IN_NAME, False),
            )

        return self._show_devices_form(errors)

    def _show_devices_form(self, errors: dict[str, str]) -> ConfigFlowResult:
        """Show discovered device choices."""
        schema: dict = {}
        if self._inverter_choices:
            schema[
                vol.Optional(
                    DISCOVERY_INVERTER_SN,
                    default=list(self._inverter_choices),
                )
            ] = cv.multi_select(self._inverter_choices)
        if self._battery_choices:
            schema[
                vol.Optional(
                    DISCOVERY_BATTERY_SN,
                    default=list(self._battery_choices),
                )
            ] = cv.multi_select(self._battery_choices)

        return self.async_show_form(
            step_id="devices",
            data_schema=vol.Schema(schema),
            errors=errors,
        )

    async def _async_validate_or_resolve_battery_sn(
        self, api: HanchuApi, battery_sn: str
    ) -> str:
        """Validate a battery SN, resolving pack SNs to their rack/BMS SN when possible."""
        try:
            await api.async_test_battery_connection(battery_sn)
            return battery_sn
        except HanchuApiError as original_err:
            resolved_sn = await api.async_resolve_battery_sn(battery_sn)
            if resolved_sn and resolved_sn != battery_sn:
                await api.async_test_battery_connection(resolved_sn)
                return resolved_sn
            raise original_err

    async def _async_create_hanchu_entry(
        self,
        *,
        username: str,
        password: str,
        inverter_sn: str,
        battery_sn: str,
        include_sn: bool,
        inverter_sns: list[str] | None = None,
        battery_sns: list[str] | None = None,
    ) -> ConfigFlowResult:
        """Create a Hanchu config entry."""
        inverter_sns = inverter_sns or ([inverter_sn] if inverter_sn else [])
        battery_sns = battery_sns or ([battery_sn] if battery_sn else [])
        unique_id = _entry_unique_id(inverter_sns, battery_sns)
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=f"Hanchu ESS ({unique_id})",
            data={
                CONF_USERNAME: username,
                CONF_PASSWORD: password,
                CONF_INVERTER_SN: inverter_sn,
                CONF_BATTERY_SN: battery_sn,
                CONF_INVERTER_SNS: inverter_sns,
                CONF_BATTERY_SNS: battery_sns,
                CONF_INCLUDE_SN_IN_NAME: include_sn,
            },
        )

    async def async_step_reauth(self, entry_data: dict) -> ConfigFlowResult:
        """Triggered by HA when credentials are rejected during a poll."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show a form to collect the new password and validate it."""
        reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        errors: dict[str, str] = {}

        if user_input is not None:
            password = user_input[CONF_PASSWORD]
            session = async_get_clientsession(self.hass)
            api = HanchuApi(session, reauth_entry.data[CONF_USERNAME], password)

            try:
                inverter_sn = reauth_entry.data.get(CONF_INVERTER_SN, "").strip()
                battery_sn = reauth_entry.data.get(CONF_BATTERY_SN, "").strip()
                if inverter_sn:
                    await api.async_test_connection(inverter_sn)
                else:
                    await api.async_test_battery_connection(battery_sn)
            except HanchuAuthError:
                errors["base"] = "invalid_auth"
            except (HanchuApiError, aiohttp.ClientError):
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during Hanchu re-auth")
                errors["base"] = "unknown"
            else:
                self.hass.config_entries.async_update_entry(
                    reauth_entry,
                    data={**reauth_entry.data, CONF_PASSWORD: password},
                )
                await self.hass.config_entries.async_reload(reauth_entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            description_placeholders={"username": reauth_entry.data[CONF_USERNAME]},
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


def _format_battery_choice(battery: dict[str, Any]) -> str:
    """Return a human-friendly label for a discovered battery rack."""
    label = battery["sn"]
    station_name = battery.get("station_name")
    pack_count = len(battery.get("pack_list") or [])
    details = []
    if station_name:
        details.append(str(station_name))
    if pack_count:
        details.append(f"{pack_count} pack(s)")
    return f"{label} ({', '.join(details)})" if details else label


def _build_inverter_choices(
    inverters: list[dict[str, Any]], batteries: list[dict[str, Any]]
) -> dict[str, str]:
    """Return inverter choices."""
    return {inverter["sn"]: _format_inverter_choice(inverter) for inverter in inverters}


def _format_inverter_choice(inverter: dict[str, Any]) -> str:
    """Return a human-friendly label for a discovered inverter."""
    label = inverter["sn"]
    station_name = inverter.get("station_name")
    model = inverter.get("model")
    details = []
    if station_name:
        details.append(str(station_name))
    if model:
        details.append(str(model))
    return f"{label} ({', '.join(details)})" if details else label


def _selected_serials(value: Any) -> list[str]:
    """Return selected serial numbers from a multi-select value."""
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _entry_unique_id(inverter_sns: list[str], battery_sns: list[str]) -> str:
    """Return a stable unique ID for one or more selected devices."""
    if len(inverter_sns) == 1 and not battery_sns:
        return inverter_sns[0]
    if len(battery_sns) == 1 and not inverter_sns:
        return battery_sns[0]
    if len(inverter_sns) == 1 and len(battery_sns) == 1:
        return inverter_sns[0]
    return "hanchu:" + "|".join(
        [
            "inv=" + ",".join(sorted(inverter_sns)),
            "bat=" + ",".join(sorted(battery_sns)),
        ]
    )
