"""Select platform for Hanchu ESS (work mode selector)."""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_INCLUDE_SN_IN_NAME,
    CONF_INVERTER_SN,
    CONF_INVERTER_SNS,
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
    inverter_sns = _serial_list(entry.data, CONF_INVERTER_SNS, CONF_INVERTER_SN)
    if not inverter_sns:
        return

    include_sn: bool = entry.data.get(CONF_INCLUDE_SN_IN_NAME, False)
    show_inverter_sn = include_sn or len(inverter_sns) > 1

    async_add_entities(
        HanchuWorkModeSelect(
            data["power_coordinators"][inverter_sn],
            inverter_sn,
            f"Hanchu Inverter {inverter_sn}" if show_inverter_sn else "Hanchu Inverter",
        )
        for inverter_sn in inverter_sns
    )


class HanchuWorkModeSelect(HanchuInverterEntity, SelectEntity):
    """Select entity for the inverter work mode."""

    _attr_name = "Work Mode"
    _attr_options = list(WORK_MODES.values())
    _attr_icon = "mdi:solar-power"

    def __init__(
        self,
        coordinator: HanchuPowerCoordinator,
        inverter_sn: str,
        device_name: str = "Hanchu Inverter",
    ) -> None:
        super().__init__(coordinator, inverter_sn, "work_mode", device_name)

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


def _serial_list(data: dict, list_key: str, single_key: str) -> list[str]:
    """Return configured serial numbers from new list fields or legacy single fields."""
    values = data.get(list_key)
    if isinstance(values, list):
        return [str(value).strip() for value in values if str(value).strip()]

    single = str(data.get(single_key, "")).strip()
    return [single] if single else []
