"""Shared test setup.

Stubs out homeassistant (and voluptuous) before any integration code is
imported.  This lets the tests run on Windows without the full HA install,
since homeassistant.runner imports the Linux-only `fcntl` module.
"""
from __future__ import annotations

import base64
import json
import os
import sys

# Ensure repo root is on sys.path so `custom_components` is importable.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
import time
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock


# ── JWT helper ────────────────────────────────────────────────────────────────

def make_jwt(exp_offset: int = 86400 * 30) -> str:
    """Return a syntactically valid JWT with a future expiry."""
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(
        json.dumps({"exp": int(time.time()) + exp_offset}).encode()
    ).rstrip(b"=").decode()
    return f"{header}.{payload}.fakesig"


# ── Stub classes that are used as base classes ────────────────────────────────
# These must be real Python classes, not MagicMocks, because the integration
# code subclasses them with `class Foo(Base)`.

@dataclass(frozen=True)
class _EntityDescription:
    key: str = ""
    name: str | None = None
    icon: str | None = None
    entity_registry_enabled_default: bool = True
    entity_registry_visible_default: bool = True
    entity_category: Any = None
    has_entity_name: bool = False


@dataclass(frozen=True)
class _SensorEntityDescription(_EntityDescription):
    device_class: Any = None
    state_class: Any = None
    native_unit_of_measurement: Any = None
    unit_of_measurement: Any = None
    suggested_display_precision: int | None = None
    suggested_unit_of_measurement: Any = None
    last_reset: Any = None
    options: Any = None


class _SensorEntity:
    pass


class _BinarySensorEntity:
    pass


class _SelectEntity:
    pass


class _DataUpdateCoordinator:
    def __init__(self, hass=None, logger=None, *, name="", update_interval=None, **kw):
        self.hass = hass
        self.data = None

    def __class_getitem__(cls, item):
        return cls


class _UpdateFailed(Exception):
    pass


class _CoordinatorEntity:
    def __init__(self, coordinator=None, **kw):
        self.coordinator = coordinator


@dataclass
class _StatisticData:
    start: Any = None
    state: Any = None
    sum: Any = None
    mean: Any = None


@dataclass
class _StatisticMetaData:
    has_sum: bool = False
    name: Any = None
    source: str = ""
    statistic_id: str = ""
    unit_of_measurement: Any = None
    unit_class: Any = None
    mean_type: Any = None
    has_mean: Any = None


# ── Build stub modules ────────────────────────────────────────────────────────

_ha_const = MagicMock()
_ha_const.CONF_PASSWORD = "password"
_ha_const.CONF_USERNAME = "username"
_ha_const.PERCENTAGE = "%"
_ha_const.UnitOfEnergy.KILO_WATT_HOUR = "kWh"
_ha_const.UnitOfPower.WATT = "W"
_ha_const.UnitOfPower.KILO_WATT = "kW"
_ha_const.UnitOfTemperature.CELSIUS = "°C"
_ha_const.UnitOfElectricPotential.VOLT = "V"
_ha_const.UnitOfElectricCurrent.AMPERE = "A"
_ha_const.Platform.SENSOR = "sensor"
_ha_const.Platform.BINARY_SENSOR = "binary_sensor"
_ha_const.Platform.SELECT = "select"

_ha_sensor = MagicMock()
_ha_sensor.SensorEntityDescription = _SensorEntityDescription
_ha_sensor.SensorDeviceClass = MagicMock()
_ha_sensor.SensorStateClass = MagicMock()
_ha_sensor.SensorEntity = _SensorEntity

_ha_binary_sensor = MagicMock()
_ha_binary_sensor.BinarySensorEntity = _BinarySensorEntity

_ha_select = MagicMock()
_ha_select.SelectEntity = _SelectEntity

_ha_recorder_models = MagicMock()
_ha_recorder_models.StatisticData = _StatisticData
_ha_recorder_models.StatisticMetaData = _StatisticMetaData
_ha_recorder_models.StatisticMeanType = MagicMock()

_ha_update_coordinator = MagicMock()
_ha_update_coordinator.DataUpdateCoordinator = _DataUpdateCoordinator
_ha_update_coordinator.UpdateFailed = _UpdateFailed
_ha_update_coordinator.CoordinatorEntity = _CoordinatorEntity


class _ConfigEntryAuthFailed(Exception):
    pass


_ha_exceptions = MagicMock()
_ha_exceptions.ConfigEntryAuthFailed = _ConfigEntryAuthFailed

# ── Register in sys.modules before any integration import ─────────────────────

_stubs: dict[str, Any] = {
    "homeassistant": MagicMock(),
    "homeassistant.const": _ha_const,
    "homeassistant.components": MagicMock(),
    "homeassistant.components.sensor": _ha_sensor,
    "homeassistant.components.binary_sensor": _ha_binary_sensor,
    "homeassistant.components.select": _ha_select,
    "homeassistant.components.recorder": MagicMock(),
    "homeassistant.components.recorder.models": _ha_recorder_models,
    "homeassistant.components.recorder.statistics": MagicMock(),
    "homeassistant.exceptions": _ha_exceptions,
    "homeassistant.config_entries": MagicMock(),
    "homeassistant.core": MagicMock(),
    "homeassistant.helpers": MagicMock(),
    "homeassistant.helpers.config_validation": MagicMock(),
    "homeassistant.helpers.entity_registry": MagicMock(),
    "homeassistant.helpers.aiohttp_client": MagicMock(),
    "homeassistant.helpers.update_coordinator": _ha_update_coordinator,
    "homeassistant.helpers.entity": MagicMock(),
    "homeassistant.helpers.entity_platform": MagicMock(),
    "homeassistant.helpers.device_registry": MagicMock(),
    "homeassistant.util": MagicMock(),
    "homeassistant.util.dt": MagicMock(),
    "voluptuous": MagicMock(),
}

for _mod_name, _stub in _stubs.items():
    sys.modules.setdefault(_mod_name, _stub)
