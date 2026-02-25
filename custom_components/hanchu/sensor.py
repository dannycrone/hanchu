"""Sensor platform for Hanchu ESS."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    BATTERY_SENSORS,
    CONF_BATTERY_SN,
    CONF_INVERTER_SN,
    DOMAIN,
    INVERTER_SENSORS,
    HanchuSensorDescription,
)
from .coordinator import HanchuBatteryCoordinator, HanchuPowerCoordinator
from .entity import HanchuBatteryEntity, HanchuInverterEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hanchu sensors from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    power_coordinator: HanchuPowerCoordinator = data["power_coordinator"]
    inverter_sn: str = entry.data[CONF_INVERTER_SN]

    entities: list[SensorEntity] = [
        HanchuInverterSensor(power_coordinator, inverter_sn, desc)
        for desc in INVERTER_SENSORS
    ]

    battery_sn: str = entry.data.get(CONF_BATTERY_SN, "").strip()
    if battery_sn:
        battery_coordinator: HanchuBatteryCoordinator = data["battery_coordinator"]
        entities.extend(
            HanchuBatterySensor(battery_coordinator, battery_sn, desc)
            for desc in BATTERY_SENSORS
        )

    async_add_entities(entities)


class HanchuInverterSensor(HanchuInverterEntity, SensorEntity):
    """A sensor reading from the power coordinator."""

    entity_description: HanchuSensorDescription

    def __init__(
        self,
        coordinator: HanchuPowerCoordinator,
        inverter_sn: str,
        description: HanchuSensorDescription,
    ) -> None:
        super().__init__(coordinator, inverter_sn, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | str | None:
        raw = self.coordinator.get(self.entity_description.field)
        if raw is None:
            return None
        try:
            value = float(raw) * self.entity_description.scale
            return round(value, 6)  # HA will apply suggested_display_precision
        except (TypeError, ValueError):
            return raw

    @property
    def entity_registry_enabled_default(self) -> bool:
        return self.entity_description.entity_registry_enabled_default


class HanchuBatterySensor(HanchuBatteryEntity, SensorEntity):
    """A sensor reading from the battery coordinator."""

    entity_description: HanchuSensorDescription

    def __init__(
        self,
        coordinator: HanchuBatteryCoordinator,
        battery_sn: str,
        description: HanchuSensorDescription,
    ) -> None:
        super().__init__(coordinator, battery_sn, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | str | None:
        raw = self.coordinator.get(self.entity_description.field)
        if raw is None:
            return None
        try:
            value = float(raw) * self.entity_description.scale
            return round(value, 6)
        except (TypeError, ValueError):
            return raw

    @property
    def entity_registry_enabled_default(self) -> bool:
        return self.entity_description.entity_registry_enabled_default
