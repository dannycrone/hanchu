"""Binary sensor platform for Hanchu ESS."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    BATTERY_BINARY_SENSORS,
    CONF_BATTERY_SN,
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
    battery_sn: str = entry.data.get(CONF_BATTERY_SN, "").strip()
    if not battery_sn:
        return

    data = hass.data[DOMAIN][entry.entry_id]
    battery_coordinator: HanchuBatteryCoordinator = data["battery_coordinator"]

    async_add_entities(
        HanchuRelayBinarySensor(battery_coordinator, battery_sn, desc)
        for desc in BATTERY_BINARY_SENSORS
    )


class HanchuRelayBinarySensor(HanchuBatteryEntity, BinarySensorEntity):
    """Binary sensor for a battery relay state (1 = closed/on)."""

    def __init__(
        self,
        coordinator: HanchuBatteryCoordinator,
        battery_sn: str,
        description: HanchuBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator, battery_sn, description.key)
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
