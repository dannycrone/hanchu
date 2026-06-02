"""Number platform for Hanchu ESS inverter controls."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_INCLUDE_SN_IN_NAME,
    CONF_INVERTER_SN,
    CONF_INVERTER_SNS,
    DOMAIN,
)
from .coordinator import HanchuPowerCoordinator
from .entity import HanchuInverterEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hanchu number entities from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    inverter_sns = _serial_list(entry.data, CONF_INVERTER_SNS, CONF_INVERTER_SN)
    if not inverter_sns:
        return

    include_sn: bool = entry.data.get(CONF_INCLUDE_SN_IN_NAME, False)
    show_inverter_sn = include_sn or len(inverter_sns) > 1

    async_add_entities(
        HanchuFastDurationNumber(
            data["power_coordinators"][inverter_sn],
            inverter_sn,
            data,
            f"Hanchu Inverter {inverter_sn}" if show_inverter_sn else "Hanchu Inverter",
        )
        for inverter_sn in inverter_sns
    )


class HanchuFastDurationNumber(HanchuInverterEntity, NumberEntity):
    """Duration used by the inverter fast charge/discharge buttons."""

    _attr_name = "Fast Charge/Discharge Duration"
    _attr_icon = "mdi:timer-outline"
    _attr_native_min_value = 1
    _attr_native_max_value = 1440
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        coordinator: HanchuPowerCoordinator,
        inverter_sn: str,
        entry_data: dict,
        device_name: str = "Hanchu Inverter",
    ) -> None:
        super().__init__(coordinator, inverter_sn, "fast_charge_discharge_duration", device_name)
        self._entry_data = entry_data

    @property
    def native_value(self) -> int:
        """Return the currently selected fast charge/discharge duration."""
        return int(
            self._entry_data.setdefault("fast_duration_minutes", {}).get(self._inverter_sn, 10)
        )

    async def async_set_native_value(self, value: float) -> None:
        """Set the fast charge/discharge duration."""
        duration = max(1, min(1440, int(value)))
        self._entry_data.setdefault("fast_duration_minutes", {})[self._inverter_sn] = duration
        self.async_write_ha_state()


def _serial_list(data: dict, list_key: str, single_key: str) -> list[str]:
    """Return configured serial numbers from new list fields or legacy single fields."""
    values = data.get(list_key)
    if isinstance(values, list):
        return [str(value).strip() for value in values if str(value).strip()]

    single = str(data.get(single_key, "")).strip()
    return [single] if single else []
