"""Sensor platform for Hanchu ESS."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
    BATTERY_SENSORS,
    CONF_BATTERY_SN,
    CONF_INCLUDE_SN_IN_NAME,
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
    include_sn: bool = entry.data.get(CONF_INCLUDE_SN_IN_NAME, False)
    inverter_name = f"Hanchu Inverter {inverter_sn}" if include_sn else "Hanchu Inverter"

    entities: list[SensorEntity] = [
        HanchuInverterSensor(power_coordinator, inverter_sn, desc, inverter_name)
        for desc in INVERTER_SENSORS
    ]

    battery_sn: str = entry.data.get(CONF_BATTERY_SN, "").strip()
    if battery_sn:
        battery_coordinator: HanchuBatteryCoordinator = data["battery_coordinator"]
        battery_name = f"Hanchu Battery {battery_sn}" if include_sn else "Hanchu Battery"
        entities.extend(
            HanchuBatterySensor(battery_coordinator, battery_sn, desc, battery_name)
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
        device_name: str = "Hanchu Inverter",
    ) -> None:
        super().__init__(coordinator, inverter_sn, description.key, device_name)
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
    def last_reset(self) -> datetime | None:
        if self.entity_description.resets_daily:
            return dt_util.now().replace(hour=0, minute=0, second=0, microsecond=0)
        return None

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
        device_name: str = "Hanchu Battery",
    ) -> None:
        super().__init__(coordinator, battery_sn, description.key, device_name)
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
    def last_reset(self) -> datetime | None:
        if self.entity_description.resets_daily:
            return dt_util.now().replace(hour=0, minute=0, second=0, microsecond=0)
        return None

    @property
    def entity_registry_enabled_default(self) -> bool:
        return self.entity_description.entity_registry_enabled_default
