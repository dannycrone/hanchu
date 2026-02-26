"""Constants for the Hanchu ESS integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfElectricPotential,
    UnitOfElectricCurrent,
    PERCENTAGE,
)

DOMAIN = "hanchu"

# API
API_BASE = "https://iess3.hanchuess.com"
API_LOGIN = f"{API_BASE}/gateway/identify/auth/login/account"
API_PARALLEL_POWER_CHART = f"{API_BASE}/gateway/platform/pcs/parallelPowerChart"
API_RACK_DATA = f"{API_BASE}/gateway/platform/rack/queryRackDataDivisions"
API_UNION_INFO = f"{API_BASE}/gateway/platform/rack/unionInfo"
API_ENERGY_FLOW = f"{API_BASE}/gateway/strategy/energy/flow"
API_POWER_MINUTE_CHART = f"{API_BASE}/gateway/platform/pcs/powerMinuteChart"

# RSA public key (embedded in web app bundle)
PUBKEY_PEM = (
    "-----BEGIN PUBLIC KEY-----\n"
    "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCVg7RFDLMGM4O98d1zWKI5RQan\n"
    "jci3iY4qlpgsH76fUn3GnZtqjbRk37lCQDv6AhgPNXRPpty81+g909/c4yzySKaP\n"
    "CcDZv7KdCRB1mVxkq+0z4EtKx9EoTXKnFSDBaYi2srdal1tM3gGOsNTDN58CzYPX\n"
    "nDGPX7+EHS1Mm4aVDQIDAQAB\n"
    "-----END PUBLIC KEY-----\n"
)

# AES key and IV (16 bytes, key = IV)
AES_KEY = b"9z64Qr8mZH7Pg8d1"

APP_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "appplat": "iess",
    "origin": "https://iess3.hanchuess.com",
    "referer": "https://iess3.hanchuess.com/",
}

# Update intervals (seconds)
UPDATE_INTERVAL_POWER = 30
UPDATE_INTERVAL_BATTERY = 60

# Config keys
CONF_INVERTER_SN = "inverter_sn"
CONF_BATTERY_SN = "battery_sn"

# Work modes
WORK_MODES: dict[int, str] = {
    1: "Self-consumption",
    2: "User-defined",
    3: "Off-grid",
    4: "Backup power",
}
WORK_MODE_TO_INT: dict[str, int] = {v: k for k, v in WORK_MODES.items()}


# ──────────────────────────────────────────────────────────────────────────────
# Sensor descriptions
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class HanchuSensorDescription(SensorEntityDescription):
    """Hanchu sensor description with source field name."""
    field: str = ""
    scale: float = 1.0  # multiply raw value by this factor
    resets_daily: bool = False  # True for today-counters that reset at midnight


# Inverter sensors (from parallelPowerChart mainPower)
INVERTER_SENSORS: tuple[HanchuSensorDescription, ...] = (
    HanchuSensorDescription(
        key="solar_power",
        field="pvTtPwr",
        name="Solar Power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
    ),
    HanchuSensorDescription(
        key="load_power",
        field="loadPwr",
        name="Load Power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
    ),
    HanchuSensorDescription(
        key="grid_power",
        field="pwrGridSum",
        name="Grid Power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
    ),
    HanchuSensorDescription(
        key="battery_power",
        field="batP",
        name="Battery Power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
    ),
    HanchuSensorDescription(
        key="grid_l1_power",
        field="pwrL1Grid",
        name="Grid L1 Power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
    ),
    HanchuSensorDescription(
        key="grid_l2_power",
        field="pwrL2Grid",
        name="Grid L2 Power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
    ),
    HanchuSensorDescription(
        key="grid_l3_power",
        field="pwrL3Grid",
        name="Grid L3 Power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
    ),
    HanchuSensorDescription(
        key="battery_soc",
        field="batSoc",
        name="Battery State of Charge",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        scale=100.0,  # 0-1 decimal → 0-100%
        suggested_display_precision=1,
    ),
    HanchuSensorDescription(
        key="solar_energy_today",
        field="pvDge",
        name="Solar Energy Today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        resets_daily=True,
    ),
    HanchuSensorDescription(
        key="grid_import_today",
        field="gridTdEe",
        name="Grid Import Today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        resets_daily=True,
    ),
    HanchuSensorDescription(
        key="grid_export_today",
        field="gridTdFe",
        name="Grid Export Today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        resets_daily=True,
    ),
    HanchuSensorDescription(
        key="battery_charge_today",
        field="batTdChg",
        name="Battery Charge Today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        resets_daily=True,
    ),
    HanchuSensorDescription(
        key="battery_discharge_today",
        field="batTdDschg",
        name="Battery Discharge Today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        resets_daily=True,
    ),
    HanchuSensorDescription(
        key="load_energy_today",
        field="loadTdEe",
        name="Load Energy Today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        resets_daily=True,
    ),
    HanchuSensorDescription(
        key="bms_design_capacity",
        field="bmsDesignCap",
        name="BMS Design Capacity",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
    ),
)

# Battery sensors (from queryRackDataDivisions)
BATTERY_SENSORS: tuple[HanchuSensorDescription, ...] = (
    HanchuSensorDescription(
        key="rack_soc",
        field="rackSoc",
        name="State of Charge",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
    ),
    HanchuSensorDescription(
        key="rack_power",
        field="rackPwr",
        name="Battery Power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        scale=0.001,  # rackPwr is in W; convert to kW
        suggested_display_precision=2,
    ),
    HanchuSensorDescription(
        key="rack_voltage",
        field="rackTotalV",
        name="Battery Voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=1,
    ),
    HanchuSensorDescription(
        key="rack_current",
        field="rackTotalA",
        name="Battery Current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=1,
    ),
    HanchuSensorDescription(
        key="rack_capacity_remaining",
        field="rackCapRemain",
        name="Capacity Remaining",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
    ),
    HanchuSensorDescription(
        key="rack_temp_max",
        field="maxT",
        name="Temperature Max",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
    ),
    HanchuSensorDescription(
        key="rack_temp_min",
        field="minT",
        name="Temperature Min",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
    ),
    HanchuSensorDescription(
        key="rack_t1",
        field="rackT1",
        name="Rack Temperature 1",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
    ),
    HanchuSensorDescription(
        key="rack_t2",
        field="rackT2",
        name="Rack Temperature 2",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
    ),
    HanchuSensorDescription(
        key="rack_t3",
        field="rackT3",
        name="Rack Temperature 3",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
    ),
    HanchuSensorDescription(
        key="rack_t4",
        field="rackT4",
        name="Rack Temperature 4",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
    ),
    HanchuSensorDescription(
        key="rack_t5",
        field="rackT5",
        name="Rack Temperature 5",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
    ),
    HanchuSensorDescription(
        key="rack_t6",
        field="rackT6",
        name="Rack Temperature 6",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
    ),
    HanchuSensorDescription(
        key="total_charge",
        field="rackTotalCharge",
        name="Total Charge",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
    ),
    HanchuSensorDescription(
        key="total_discharge",
        field="rackTotalDischarge",
        name="Total Discharge",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
    ),
    HanchuSensorDescription(
        key="cycle_count",
        field="rackTotalLoopNum",
        name="Cycle Count",
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement="cycles",
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
    ),
    HanchuSensorDescription(
        key="rack_capacity",
        field="rackCapacity",
        name="Battery Capacity",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
    ),
    # Per-pack sensors (pack1..pack8)
    *[
        HanchuSensorDescription(
            key=f"pack{n}_voltage",
            field=f"pack{n}V",
            name=f"Pack {n} Voltage",
            device_class=SensorDeviceClass.VOLTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfElectricPotential.VOLT,
            suggested_display_precision=2,
            entity_registry_enabled_default=False,
        )
        for n in range(1, 9)
    ],
    *[
        HanchuSensorDescription(
            key=f"pack{n}_avg_temp",
            field=f"pack{n}AvgT",
            name=f"Pack {n} Avg Temperature",
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            suggested_display_precision=1,
            entity_registry_enabled_default=False,
        )
        for n in range(1, 9)
    ],
)


# Binary sensor descriptions
@dataclass(frozen=True)
class HanchuBinarySensorDescription:
    """Binary sensor description."""
    key: str
    field: str
    name: str
    device_class: str | None = None
    entity_registry_enabled_default: bool = True


BATTERY_BINARY_SENSORS: tuple[HanchuBinarySensorDescription, ...] = (
    HanchuBinarySensorDescription(
        key="charging_relay",
        field="chargingRelay",
        name="Charging Relay",
        device_class="connectivity",
    ),
    HanchuBinarySensorDescription(
        key="discharging_relay",
        field="dischargingRelay",
        name="Discharging Relay",
        device_class="connectivity",
    ),
    HanchuBinarySensorDescription(
        key="neg_relay",
        field="negRelay",
        name="Negative Relay",
        device_class="connectivity",
        entity_registry_enabled_default=False,
    ),
    HanchuBinarySensorDescription(
        key="shunt_relay",
        field="shuntRelay",
        name="Shunt Relay",
        device_class="connectivity",
        entity_registry_enabled_default=False,
    ),
    HanchuBinarySensorDescription(
        key="pre_charge_relay",
        field="preChargeRelay",
        name="Pre-charge Relay",
        device_class="connectivity",
        entity_registry_enabled_default=False,
    ),
)
