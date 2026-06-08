"""Button platform for Hanchu ESS inverter fast charge/discharge controls."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import (
    FAST_CHARGE_ACTION,
    FAST_DISCHARGE_ACTION,
    STOP_FAST_CHARGE_ACTION,
    STOP_FAST_DISCHARGE_ACTION,
    HanchuApiError,
)
from .const import (
    CONF_INCLUDE_SN_IN_NAME,
    CONF_INVERTER_SN,
    CONF_INVERTER_SNS,
    DOMAIN,
)
from .coordinator import HanchuPowerCoordinator
from .entity import HanchuInverterEntity


@dataclass(frozen=True)
class HanchuButtonDescription(ButtonEntityDescription):
    """Hanchu button description with API action metadata."""

    action: str = ""
    requires_duration: bool = False
    dynamic_stop: bool = False


FAST_CHARGE_BUTTONS: tuple[HanchuButtonDescription, ...] = (
    HanchuButtonDescription(
        key="start_fast_charge",
        name="Start Fast Charge",
        icon="mdi:battery-arrow-up",
        action=FAST_CHARGE_ACTION,
        requires_duration=True,
    ),
    HanchuButtonDescription(
        key="start_fast_discharge",
        name="Start Fast Discharge",
        icon="mdi:battery-arrow-down",
        action=FAST_DISCHARGE_ACTION,
        requires_duration=True,
    ),
    HanchuButtonDescription(
        key="stop_fast_charge_discharge",
        name="Stop Fast Charge/Discharge",
        icon="mdi:battery-remove",
        dynamic_stop=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hanchu button entities from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    inverter_sns = _serial_list(entry.data, CONF_INVERTER_SNS, CONF_INVERTER_SN)
    if not inverter_sns:
        return

    include_sn: bool = entry.data.get(CONF_INCLUDE_SN_IN_NAME, False)
    show_inverter_sn = include_sn or len(inverter_sns) > 1

    entities: list[HanchuFastChargeButton] = []
    for inverter_sn in inverter_sns:
        device_name = (
            f"Hanchu Inverter {inverter_sn}" if show_inverter_sn else "Hanchu Inverter"
        )
        entities.extend(
            HanchuFastChargeButton(
                data["power_coordinators"][inverter_sn],
                inverter_sn,
                desc,
                data,
                device_name,
            )
            for desc in FAST_CHARGE_BUTTONS
        )

    async_add_entities(entities)


class HanchuFastChargeButton(HanchuInverterEntity, ButtonEntity):
    """Button entity for fast charge/discharge actions."""

    entity_description: HanchuButtonDescription

    def __init__(
        self,
        coordinator: HanchuPowerCoordinator,
        inverter_sn: str,
        description: HanchuButtonDescription,
        entry_data: dict,
        device_name: str = "Hanchu Inverter",
    ) -> None:
        super().__init__(coordinator, inverter_sn, description.key, device_name)
        self.entity_description = description
        self._entry_data = entry_data

    async def async_press(self) -> None:
        """Send the selected fast charge/discharge action."""
        action = self.entity_description.action
        duration = None

        if self.entity_description.dynamic_stop:
            await self.coordinator.async_request_refresh()
            try:
                status = int(float(self.coordinator.get("deviceStatusOfTestFastChg", 0)))
            except (TypeError, ValueError):
                status = 0

            if status == 1:
                action = STOP_FAST_CHARGE_ACTION
            elif status == 2:
                action = STOP_FAST_DISCHARGE_ACTION
            else:
                return

        if self.entity_description.requires_duration:
            duration = int(
                self._entry_data.setdefault("fast_duration_minutes", {}).get(
                    self._inverter_sn, 10
                )
            )

        try:
            success = await self.coordinator.api.async_fast_charge_discharge(
                self._inverter_sn,
                action,
                duration,
            )
        except HanchuApiError as err:
            raise HomeAssistantError(f"Hanchu fast charge/discharge failed: {err}") from err

        if not success:
            raise HomeAssistantError("Hanchu fast charge/discharge command reported a failure")

        await self.coordinator.async_request_refresh()


def _serial_list(data: dict, list_key: str, single_key: str) -> list[str]:
    """Return configured serial numbers from new list fields or legacy single fields."""
    values = data.get(list_key)
    if isinstance(values, list):
        return [str(value).strip() for value in values if str(value).strip()]

    single = str(data.get(single_key, "")).strip()
    return [single] if single else []
