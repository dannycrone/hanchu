"""Hanchu ESS integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import HanchuApi, HanchuApiError
from .const import CONF_BATTERY_SN, CONF_INVERTER_SN, DOMAIN
from .coordinator import HanchuBatteryCoordinator, HanchuPowerCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SELECT,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Hanchu ESS from a config entry."""
    username: str = entry.data[CONF_USERNAME]
    password: str = entry.data[CONF_PASSWORD]
    inverter_sn: str = entry.data[CONF_INVERTER_SN]
    battery_sn: str = entry.data.get(CONF_BATTERY_SN, "").strip()

    session = async_get_clientsession(hass)
    api = HanchuApi(session, username, password)

    # Power coordinator (inverter)
    power_coordinator = HanchuPowerCoordinator(hass, api, inverter_sn)
    await power_coordinator.async_config_entry_first_refresh()

    data: dict = {
        "api": api,
        "power_coordinator": power_coordinator,
    }

    # Battery coordinator (optional)
    if battery_sn:
        battery_coordinator = HanchuBatteryCoordinator(hass, api, battery_sn)
        await battery_coordinator.async_config_entry_first_refresh()
        data["battery_coordinator"] = battery_coordinator

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = data

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
