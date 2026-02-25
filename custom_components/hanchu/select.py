"""Select platform for Hanchu ESS (work mode selector)."""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_INVERTER_SN,
    DOMAIN,
    WORK_MODE_TO_INT,
    WORK_MODES,
)
from .coordinator import HanchuPowerCoordinator
from .entity import HanchuInverterEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hanchu select entities from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    power_coordinator: HanchuPowerCoordinator = data["power_coordinator"]
    inverter_sn: str = entry.data[CONF_INVERTER_SN]

    async_add_entities([HanchuWorkModeSelect(power_coordinator, inverter_sn)])


class HanchuWorkModeSelect(HanchuInverterEntity, SelectEntity):
    """Select entity for the inverter work mode."""

    _attr_name = "Work Mode"
    _attr_options = list(WORK_MODES.values())
    _attr_icon = "mdi:solar-power"

    def __init__(
        self,
        coordinator: HanchuPowerCoordinator,
        inverter_sn: str,
    ) -> None:
        super().__init__(coordinator, inverter_sn, "work_mode")

    @property
    def current_option(self) -> str | None:
        raw = self.coordinator.get("workMode")
        if raw is None:
            return None
        try:
            mode_int = int(float(raw))
        except (TypeError, ValueError):
            return None
        return WORK_MODES.get(mode_int)

    async def async_select_option(self, option: str) -> None:
        mode_int = WORK_MODE_TO_INT.get(option)
        if mode_int is None:
            _LOGGER.error("Unknown work mode: %s", option)
            return

        api = self.coordinator.api
        success = await api.async_set_work_mode(self._inverter_sn, mode_int)
        if success:
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to set work mode to %s", option)
