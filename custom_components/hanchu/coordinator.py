"""Data coordinators for the Hanchu ESS integration."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import HanchuApi, HanchuApiError
from .const import (
    DOMAIN,
    UPDATE_INTERVAL_BATTERY,
    UPDATE_INTERVAL_POWER,
)

_LOGGER = logging.getLogger(__name__)


class HanchuPowerCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls parallelPowerChart every UPDATE_INTERVAL_POWER seconds.

    Exposes:
        data  – the ``mainPower`` dict from the API response
    """

    def __init__(
        self, hass: HomeAssistant, api: HanchuApi, inverter_sn: str
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_power",
            update_interval=timedelta(seconds=UPDATE_INTERVAL_POWER),
        )
        self.api = api
        self.inverter_sn = inverter_sn

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.api.async_fetch_power(self.inverter_sn)
        except HanchuApiError as err:
            raise UpdateFailed(f"parallelPowerChart fetch failed: {err}") from err

    def get(self, field: str, default: Any = None) -> Any:
        """Return a field value from the latest power data."""
        if self.data is None:
            return default
        raw = self.data.get(field, default)
        if raw is None:
            return default
        # Numeric strings are common in this API
        if isinstance(raw, str):
            try:
                return float(raw)
            except ValueError:
                return raw
        return raw


class HanchuBatteryCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls queryRackDataDivisions every UPDATE_INTERVAL_BATTERY seconds.

    Exposes:
        data  – the top-level ``data`` dict from the API response
    """

    def __init__(
        self, hass: HomeAssistant, api: HanchuApi, battery_sn: str
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_battery",
            update_interval=timedelta(seconds=UPDATE_INTERVAL_BATTERY),
        )
        self.api = api
        self.battery_sn = battery_sn

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            data = await self.api.async_fetch_battery(self.battery_sn)
            _LOGGER.warning("Hanchu battery raw payload: %s", data)
            return data
        except HanchuApiError as err:
            raise UpdateFailed(f"queryRackDataDivisions fetch failed: {err}") from err

    def get(self, field: str, default: Any = None) -> Any:
        """Return a field value from the latest battery data."""
        if self.data is None:
            return default
        raw = self.data.get(field, default)
        if raw is None:
            return default
        if isinstance(raw, str):
            try:
                return float(raw)
            except ValueError:
                return raw
        return raw
