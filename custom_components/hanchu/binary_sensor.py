"""Binary sensor platform for Hanchu ESS."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    BATTERY_BINARY_SENSORS,
    CONF_BATTERY_SN,
    CONF_BATTERY_SNS,
    CONF_INCLUDE_SN_IN_NAME,
    DOMAIN,
    HanchuBinarySensorDescription,
)
from .coordinator import HanchuBatteryCoordinator
from .entity import HanchuBatteryEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hanchu binary sensors from a config entry."""
    battery_sns = _serial_list(entry.data, CONF_BATTERY_SNS, CONF_BATTERY_SN)
    if not battery_sns:
        return

    data = hass.data[DOMAIN][entry.entry_id]
    include_sn: bool = entry.data.get(CONF_INCLUDE_SN_IN_NAME, False)
    show_battery_sn = include_sn or len(battery_sns) > 1

    entities: list[BinarySensorEntity] = []
    for battery_sn in battery_sns:
        battery_coordinator: HanchuBatteryCoordinator = data["battery_coordinators"][battery_sn]
        battery_name = f"Hanchu Battery {battery_sn}" if show_battery_sn else "Hanchu Battery"
        entities.extend(
            HanchuRelayBinarySensor(battery_coordinator, battery_sn, desc, battery_name)
            for desc in BATTERY_BINARY_SENSORS
        )

    async_add_entities(entities)


class HanchuRelayBinarySensor(HanchuBatteryEntity, BinarySensorEntity):
    """Binary sensor for a battery relay state (1 = closed/on)."""

    def __init__(
        self,
        coordinator: HanchuBatteryCoordinator,
        battery_sn: str,
        description: HanchuBinarySensorDescription,
        device_name: str = "Hanchu Battery",
    ) -> None:
        super().__init__(coordinator, battery_sn, description.key, device_name)
        self._description = description
        self._attr_name = description.name
        if description.device_class:
            self._attr_device_class = BinarySensorDeviceClass(description.device_class)
        self._attr_entity_registry_enabled_default = description.entity_registry_enabled_default

    @property
    def is_on(self) -> bool | None:
        raw = self.coordinator.get(self._description.field)
        if raw is None:
            return None
        try:
            return int(float(raw)) == 1
        except (TypeError, ValueError):
            return None


def _serial_list(data: dict, list_key: str, single_key: str) -> list[str]:
    """Return configured serial numbers from new list fields or legacy single fields."""
    values = data.get(list_key)
    if isinstance(values, list):
        return [str(value).strip() for value in values if str(value).strip()]

    single = str(data.get(single_key, "")).strip()
    return [single] if single else []
