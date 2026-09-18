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
    CONF_BATTERY_SNS,
    CONF_INCLUDE_SN_IN_NAME,
    CONF_INVERTER_SN,
    CONF_INVERTER_SNS,
    DOMAIN,
    INVERTER_SENSORS,
    HanchuSensorDescription,
    WORK_MODES,
)
from .coordinator import HanchuBatteryCoordinator, HanchuPowerCoordinator
from .entity import HanchuBatteryEntity, HanchuInverterEntity
from .helpers import serial_list


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hanchu sensors from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    include_sn: bool = entry.data.get(CONF_INCLUDE_SN_IN_NAME, False)

    entities: list[SensorEntity] = []

    inverter_sns = serial_list(entry.data, CONF_INVERTER_SNS, CONF_INVERTER_SN)
    show_inverter_sn = include_sn or len(inverter_sns) > 1
    for inverter_sn in inverter_sns:
        power_coordinator: HanchuPowerCoordinator = data["power_coordinators"][inverter_sn]
        inverter_name = (
            f"Hanchu Inverter {inverter_sn}" if show_inverter_sn else "Hanchu Inverter"
        )
        entities.extend(
            HanchuInverterSensor(power_coordinator, inverter_sn, desc, inverter_name)
            for desc in INVERTER_SENSORS
        )
        entities.append(
            HanchuEnergySettingsSensor(power_coordinator, inverter_sn, inverter_name)
        )

    battery_sns = serial_list(entry.data, CONF_BATTERY_SNS, CONF_BATTERY_SN)
    show_battery_sn = include_sn or len(battery_sns) > 1
    for battery_sn in battery_sns:
        battery_coordinator: HanchuBatteryCoordinator = data["battery_coordinators"][battery_sn]
        battery_name = f"Hanchu Battery {battery_sn}" if show_battery_sn else "Hanchu Battery"
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
        if self.entity_description.value_map is not None:
            try:
                key = int(float(raw))
            except (TypeError, ValueError):
                return str(raw)
            return self.entity_description.value_map.get(key, str(raw))
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


class HanchuEnergySettingsSensor(HanchuInverterEntity, SensorEntity):
    """Read-only snapshot of the inverter energy settings."""

    _attr_name = "Energy Settings"
    _attr_icon = "mdi:home-battery-outline"

    _SETTING_KEYS = (
        "WORK_MODE_CMB",
        "CHG_PWR_LMT",
        "DSCHG_PWR_LMT",
        "DTU_AC_CHG_SOC_LMT",
        "CHG_BAT_SOC_LMT",
        "DSCHG_BAT_SOC_LMT",
        "OFF_GRID_SOC_L",
        "TCT_START_1",
        "TCT_END_1",
        "TCT_START_2",
        "TCT_END_2",
        "TCT_START_3",
        "TCT_END_3",
        "TDT_START_1",
        "TDT_END_1",
        "TDT_START_2",
        "TDT_END_2",
        "TDT_START_3",
        "TDT_END_3",
    )

    def __init__(
        self,
        coordinator: HanchuPowerCoordinator,
        inverter_sn: str,
        device_name: str = "Hanchu Inverter",
    ) -> None:
        super().__init__(coordinator, inverter_sn, "energy_settings", device_name)

    @property
    def native_value(self) -> str | None:
        settings = self.coordinator.get("_energy_settings", {})
        raw = None
        if isinstance(settings, dict):
            raw = settings.get("WORK_MODE_CMB", settings.get("workModeCmb"))
        try:
            return WORK_MODES.get(int(float(raw))) if raw is not None else None
        except (TypeError, ValueError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        settings = self.coordinator.get("_energy_settings", {})
        if isinstance(settings, dict):
            attributes = {
                str(key): value
                for key, value in settings.items()
                if value is None or isinstance(value, (bool, int, float, str))
            }
            error = self.coordinator.get("_energy_settings_error")
            if error:
                attributes["api_error"] = str(error)
            return attributes
        return {
            key.lower(): self.coordinator.get(key)
            for key in self._SETTING_KEYS
            if self.coordinator.get(key) is not None
        }


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
