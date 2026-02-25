# Hanchu ESS

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

A Home Assistant custom integration for the **Hanchu IESS3** solar inverter and battery storage system.

Connects directly to the Hanchu cloud portal (`iess3.hanchuess.com`) — no local proxy add-on required.

## Features

- Real-time power monitoring (solar, load, grid, battery)
- Per-phase grid power (L1, L2, L3)
- Today's energy totals from the inverter's own counters (no Riemann-sum estimation)
- Battery state: SOC, voltage, current, power, temperature (6 probes)
- Per-pack voltages and temperatures (8 packs, disabled by default)
- Battery relay states as binary sensors
- **Work mode selector**: Self-consumption / User-defined / Off-grid / Backup power
- Two separate HA devices: Inverter + Battery Rack
- Battery is optional — works with inverter-only setups

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots → **Custom repositories**
3. Add this repository URL and select **Integration** as the category
4. Install **Hanchu ESS**
5. Restart Home Assistant

### Manual

1. Copy the `custom_components/hanchu/` folder to your HA config's `custom_components/` directory
2. Restart Home Assistant

## Configuration

Go to **Settings → Devices & Services → Add Integration** and search for **Hanchu ESS**.

| Field | Required | Description |
|-------|----------|-------------|
| Username | Yes | Your iess3.hanchuess.com login email |
| Password | Yes | Your iess3.hanchuess.com password |
| Inverter Serial Number | Yes | Found on the inverter label, e.g. `H03Y8447L0128` |
| Battery Serial Number | No | Found on the battery rack label, e.g. `B0B3484B80009`. Leave blank for inverter-only. |

## Entities

### Inverter device

| Entity | Unit | Description |
|--------|------|-------------|
| Solar Power | W | Total PV generation |
| Load Power | W | Home consumption |
| Grid Power | W | Net grid power (negative = export) |
| Battery Power | W | Battery power (negative = charging) |
| Grid L1/L2/L3 Power | W | Per-phase grid power |
| Battery State of Charge | % | Battery SOC from inverter |
| Solar Energy Today | kWh | Today's PV generation |
| Grid Import Today | kWh | Today's grid import |
| Grid Export Today | kWh | Today's grid export |
| Battery Charge Today | kWh | Today's battery charge throughput |
| Battery Discharge Today | kWh | Today's battery discharge throughput |
| Load Energy Today | kWh | Today's home consumption |
| BMS Design Capacity | kWh | Battery nameplate capacity |
| Work Mode | — | Select: Self-consumption / User-defined / Off-grid / Backup power |

### Battery device (if battery SN provided)

| Entity | Unit | Description |
|--------|------|-------------|
| State of Charge | % | Battery rack SOC |
| Battery Power | kW | Rack power |
| Battery Voltage | V | Total rack voltage |
| Battery Current | A | Rack current |
| Capacity Remaining | % | Usable capacity remaining |
| Temperature Max / Min | °C | Rack temperature extremes |
| Rack Temperature 1–6 | °C | Individual temperature probes (disabled by default) |
| Today Charge / Discharge | kWh | Today's throughput from BMS |
| Total Charge / Discharge | kWh | Lifetime throughput |
| Cycle Count | cycles | Lifetime cycle count (disabled by default) |
| Battery Capacity | kWh | Rack capacity (disabled by default) |
| Pack 1–8 Voltage | V | Per-pack voltage (disabled by default) |
| Pack 1–8 Avg Temperature | °C | Per-pack temperature (disabled by default) |
| Charging Relay | on/off | Charging relay state |
| Discharging Relay | on/off | Discharging relay state |
| Negative / Shunt / Pre-charge Relay | on/off | Additional relay states (disabled by default) |

## Update Intervals

- Inverter power data: every **30 seconds**
- Battery rack data: every **60 seconds**

## Notes

- The energy "today" sensors (`Solar Energy Today`, `Grid Import Today`, etc.) use the inverter's own
  internal daily counters. They reset at midnight device time. Use the HA **Energy Dashboard** with
  these sensors directly — no Riemann-sum integration helper needed.
- The `Grid Power` sensor is signed: **positive = import**, **negative = export**. You can use
  template sensors to split it into separate import/export values if your energy dashboard requires it.
- Work mode changes are sent to the cloud API. The inverter applies them within one poll cycle (~30s).

## Supported Hardware

Tested with:
- Hanchu IESS3 inverter (`H03Y8447L0128`)
- Hanchu HOME-ESS-HV battery rack (`B0B3484B80009`, 8 packs, 41 kWh)

Other Hanchu IESS3 inverters and battery configurations should work provided they appear on
`iess3.hanchuess.com`.

## License

MIT
