"""Base entity for the Hanchu ESS integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HanchuBatteryCoordinator, HanchuPowerCoordinator


class HanchuInverterEntity(CoordinatorEntity[HanchuPowerCoordinator]):
    """Base class for inverter entities backed by HanchuPowerCoordinator."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HanchuPowerCoordinator,
        inverter_sn: str,
        unique_suffix: str,
    ) -> None:
        super().__init__(coordinator)
        self._inverter_sn = inverter_sn
        self._attr_unique_id = f"{inverter_sn}_{unique_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, inverter_sn)},
            name=f"Hanchu Inverter {inverter_sn}",
            manufacturer="Hanchu",
            model="IESS Inverter",
        )


class HanchuBatteryEntity(CoordinatorEntity[HanchuBatteryCoordinator]):
    """Base class for battery entities backed by HanchuBatteryCoordinator."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HanchuBatteryCoordinator,
        battery_sn: str,
        unique_suffix: str,
    ) -> None:
        super().__init__(coordinator)
        self._battery_sn = battery_sn
        self._attr_unique_id = f"{battery_sn}_{unique_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, battery_sn)},
            name=f"Hanchu Battery {battery_sn}",
            manufacturer="Hanchu",
            model="IESS Battery Rack",
        )
