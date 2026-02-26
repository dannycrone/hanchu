"""Hanchu ESS integration."""

from __future__ import annotations

import datetime as dt
import logging
from datetime import date, timedelta

import voluptuous as vol

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_import_statistics,
    statistics_during_period,
)

try:
    from homeassistant.components.recorder.models import StatisticMeanType
    _STAT_MEAN_NONE: dict = {"mean_type": StatisticMeanType.NONE}
    _STAT_MEAN_ARITH: dict = {"mean_type": StatisticMeanType.ARITHMETIC}
except ImportError:
    _STAT_MEAN_NONE = {"has_mean": False}
    _STAT_MEAN_ARITH = {"has_mean": True}
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.util.dt as dt_util

from .api import HanchuApi, HanchuApiError
from .const import CONF_BATTERY_SN, CONF_INVERTER_SN, DOMAIN
from .coordinator import HanchuBatteryCoordinator, HanchuPowerCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SELECT,
]

SERVICE_IMPORT_STATISTICS = "import_statistics"

# Maps energy/flow sumData keys → sensor description keys (in INVERTER_SENSORS)
_FLOW_TO_SENSOR: dict[str, str] = {
    "pv":           "solar_energy_today",
    "gridImport":   "grid_import_today",
    "gridExport":   "grid_export_today",
    "batCharge":    "battery_charge_today",
    "batDisCharge": "battery_discharge_today",
    "load":         "load_energy_today",
}

# Maps powerMinuteChart data fields → power sensor description keys
_MINUTE_FIELD_TO_SENSOR: dict[str, str] = {
    "pvTtPwr":    "solar_power",
    "batP":       "battery_power",
    "meterPPwr":  "grid_power",
    "loadEpsPwr": "load_power",
}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Hanchu ESS from a config entry."""
    username: str = entry.data[CONF_USERNAME]
    password: str = entry.data[CONF_PASSWORD]
    inverter_sn: str = entry.data[CONF_INVERTER_SN]
    battery_sn: str = entry.data.get(CONF_BATTERY_SN, "").strip()

    session = async_get_clientsession(hass)
    api = HanchuApi(session, username, password)

    # Power coordinator (inverter)
    power_coordinator = HanchuPowerCoordinator(hass, api, inverter_sn)
    await power_coordinator.async_config_entry_first_refresh()

    data: dict = {
        "api": api,
        "power_coordinator": power_coordinator,
    }

    # Battery coordinator (optional)
    if battery_sn:
        battery_coordinator = HanchuBatteryCoordinator(hass, api, battery_sn)
        await battery_coordinator.async_config_entry_first_refresh()
        data["battery_coordinator"] = battery_coordinator

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = data

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register service once (first entry to load wins).
    # Wrap the handler in a closure so hass is available without being
    # passed as an argument (HA only passes ServiceCall to handlers).
    if not hass.services.has_service(DOMAIN, SERVICE_IMPORT_STATISTICS):
        async def _handle_import(call: ServiceCall) -> None:
            await _async_handle_import_statistics(hass, call)

        hass.services.async_register(
            DOMAIN,
            SERVICE_IMPORT_STATISTICS,
            _handle_import,
            schema=vol.Schema({
                vol.Required("start_date"): cv.date,
                vol.Required("end_date"): cv.date,
                vol.Optional("include_power", default=False): cv.boolean,
            }),
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    # Remove service when the last entry is unloaded
    if not hass.data.get(DOMAIN):
        hass.services.async_remove(DOMAIN, SERVICE_IMPORT_STATISTICS)
    return unload_ok


def _compute_hourly_fractions(minute_data: list[dict], tz) -> dict[str, list[float]]:
    """Compute per-hour energy fractions from powerMinuteChart data.

    Returns a dict mapping each _FLOW_TO_SENSOR key to a 24-element list of
    fractions that sum to 1.0.  Falls back to uniform (1/24) for any flow key
    where the minute data provides no usable signal.
    """
    _uniform = [1.0 / 24.0] * 24

    # Bucket per-field readings by local hour
    hourly: dict[int, dict[str, list[float]]] = {
        h: {f: [] for f in _MINUTE_FIELD_TO_SENSOR} for h in range(24)
    }
    for point in minute_data:
        ts_ms = point.get("dataTimeTs")
        if not ts_ms:
            continue
        hour = dt.datetime.fromtimestamp(ts_ms / 1000, tz=tz).hour
        for field in _MINUTE_FIELD_TO_SENSOR:
            val = point.get(field)
            if val is not None:
                hourly[hour][field].append(float(val))

    # Mean power (W) per field per hour
    means: dict[str, list[float]] = {}
    for field in _MINUTE_FIELD_TO_SENSOR:
        means[field] = [
            (sum(hourly[h][field]) / len(hourly[h][field])) if hourly[h][field] else 0.0
            for h in range(24)
        ]

    def _norm(values: list[float]) -> list[float]:
        total = sum(values)
        return [v / total for v in values] if total > 0 else _uniform[:]

    return {
        "pv":           _norm(means["pvTtPwr"]),
        "load":         _norm(means["loadEpsPwr"]),
        "batCharge":    _norm([max(v, 0.0) for v in means["batP"]]),
        "batDisCharge": _norm([max(-v, 0.0) for v in means["batP"]]),
        "gridImport":   _norm([max(v, 0.0) for v in means["meterPPwr"]]),
        "gridExport":   _norm([max(-v, 0.0) for v in means["meterPPwr"]]),
    }


async def _async_handle_import_statistics(hass: HomeAssistant, call: ServiceCall) -> None:
    """Backfill energy statistics from the Hanchu cloud for a date range."""
    start_date: date = call.data["start_date"]
    end_date: date = call.data["end_date"]
    include_power: bool = call.data.get("include_power", False)

    # Grab the first available config entry
    domain_data = hass.data.get(DOMAIN, {})
    if not domain_data:
        _LOGGER.error("hanchu.import_statistics: no Hanchu entries loaded")
        return

    entry_data = next(iter(domain_data.values()))
    api: HanchuApi = entry_data["api"]

    # Resolve inverter and battery SNs from config entry
    inverter_sn: str | None = None
    battery_sn: str | None = None
    for config_entry in hass.config_entries.async_entries(DOMAIN):
        inverter_sn = config_entry.data.get(CONF_INVERTER_SN)
        battery_sn = config_entry.data.get(CONF_BATTERY_SN, "").strip() or None
        break
    if not inverter_sn:
        _LOGGER.error("hanchu.import_statistics: could not determine inverter SN")
        return

    # Look up energy entity IDs from the registry
    entity_reg = er.async_get(hass)
    sensor_entity_ids: dict[str, str] = {}
    for flow_key, sensor_key in _FLOW_TO_SENSOR.items():
        eid = entity_reg.async_get_entity_id("sensor", DOMAIN, f"{inverter_sn}_{sensor_key}")
        if eid:
            sensor_entity_ids[flow_key] = eid
        else:
            _LOGGER.warning("hanchu.import_statistics: no entity for %s_%s", inverter_sn, sensor_key)

    # Fetch one day at a time.
    # These sensors have state_class=total_increasing, so HA computes the daily
    # total as last_stat_sum − first_stat_sum. We write all 24 hourly slots with
    # a monotonically increasing running sum (no last_reset) so any conflicting
    # live-recorded slots are overwritten and future recordings base on our last
    # written sum.
    # When include_power=True the same minute-chart fetch is used both to shape
    # the hourly energy distribution (replaces uniform 1/24) and to build power
    # statistics for the Power Sources graph.
    tz = dt_util.get_time_zone(hass.config.time_zone)
    current = start_date
    start_dt = dt.datetime.combine(start_date, dt.time.min).replace(tzinfo=tz)
    running_sums: dict[str, float] = {k: 0.0 for k in _FLOW_TO_SENSOR}
    stats: dict[str, list[StatisticData]] = {k: [] for k in _FLOW_TO_SENSOR}
    power_stats: dict[str, list[StatisticData]] = (
        {k: [] for k in _MINUTE_FIELD_TO_SENSOR.values()} if include_power else {}
    )
    imported_days = 0
    power_days = 0

    # Seed running_sums from the last recorded stat before our import range.
    # Without this, the imported sums start at 0 while the live recorder has
    # been accumulating since the integration was first installed.  The result
    # would be sum_at_range_end < sum_just_before_range, making HA show
    # negative totals for any multi-day view that spans the import range.
    try:
        pre_range_stats = await get_instance(hass).async_add_executor_job(
            statistics_during_period,
            hass,
            start_dt - timedelta(days=7),
            start_dt,
            set(sensor_entity_ids.values()),
            "hour",
            None,
            {"sum"},
        )
        for flow_key, entity_id in sensor_entity_ids.items():
            stats_list = pre_range_stats.get(entity_id, [])
            if stats_list:
                last_stat = stats_list[-1]
                s = (
                    last_stat.get("sum")
                    if isinstance(last_stat, dict)
                    else getattr(last_stat, "sum", None)
                )
                if s is not None:
                    running_sums[flow_key] = float(s)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning(
            "hanchu.import_statistics: could not seed running sums (will start from 0): %s", err
        )

    while current <= end_date:
        date_str = current.isoformat()
        midnight = dt.datetime.combine(current, dt.time.min).replace(tzinfo=tz)

        try:
            day_data = await api.async_fetch_energy_flow(inverter_sn, date_str)
        except HanchuApiError as err:
            _LOGGER.warning("hanchu.import_statistics: skipping %s: %s", date_str, err)
            current += timedelta(days=1)
            continue

        # Optionally fetch minute-by-minute power data.  When available it is
        # used to shape the hourly energy distribution and build power stats.
        minute_data: list[dict] = []
        if include_power:
            start_ms = int(midnight.timestamp() * 1000)
            end_ms = int((midnight + timedelta(days=1)).timestamp() * 1000) - 1
            try:
                minute_data = await api.async_fetch_power_minute_chart(
                    inverter_sn, start_ms, end_ms
                )
                if minute_data:
                    _LOGGER.info(
                        "hanchu.import_statistics: powerMinuteChart %s: %d points, "
                        "sample fields: %s",
                        date_str,
                        len(minute_data),
                        sorted(minute_data[0].keys()),
                    )
                else:
                    _LOGGER.warning(
                        "hanchu.import_statistics: powerMinuteChart %s returned empty list",
                        date_str,
                    )
            except HanchuApiError as err:
                _LOGGER.warning(
                    "hanchu.import_statistics: no power data for %s: %s", date_str, err
                )

        hourly_fractions = _compute_hourly_fractions(minute_data, tz) if minute_data else {}

        # Energy stats: 24 hourly slots with monotonic running sum
        for flow_key in _FLOW_TO_SENSOR:
            daily_value = float(day_data.get(flow_key) or 0.0)
            sum_before = running_sums[flow_key]
            running_sums[flow_key] += daily_value
            fracs = hourly_fractions.get(flow_key)
            cum = 0.0
            for hour in range(24):
                frac = fracs[hour] if fracs else (1.0 / 24.0)
                hourly_value = daily_value * frac
                cum += hourly_value
                stats[flow_key].append(
                    StatisticData(
                        start=midnight + timedelta(hours=hour),
                        state=hourly_value,
                        sum=sum_before + cum,
                    )
                )
        imported_days += 1

        # Power stats: aggregate minute readings into hourly means
        if include_power and minute_data:
            hourly_buckets: dict[dt.datetime, dict[str, list[float]]] = {}
            for point in minute_data:
                ts_ms = point.get("dataTimeTs")
                if not ts_ms:
                    continue
                ts_dt = dt.datetime.fromtimestamp(ts_ms / 1000, tz=tz)
                hour_start = ts_dt.replace(minute=0, second=0, microsecond=0)
                if hour_start not in hourly_buckets:
                    hourly_buckets[hour_start] = {f: [] for f in _MINUTE_FIELD_TO_SENSOR}
                for field in _MINUTE_FIELD_TO_SENSOR:
                    val = point.get(field)
                    if val is not None:
                        hourly_buckets[hour_start][field].append(float(val))

            for hour_start, field_readings in hourly_buckets.items():
                for field, sensor_key in _MINUTE_FIELD_TO_SENSOR.items():
                    readings = field_readings.get(field, [])
                    if readings:
                        power_stats[sensor_key].append(
                            StatisticData(
                                start=hour_start,
                                mean=sum(readings) / len(readings),
                            )
                        )
            _LOGGER.info(
                "hanchu.import_statistics: power stats built for %s: %s",
                date_str,
                {sk: len(power_stats[sk]) for sk in power_stats},
            )
            power_days += 1

        current += timedelta(days=1)

    if not imported_days:
        _LOGGER.warning("hanchu.import_statistics: no data imported for %s – %s", start_date, end_date)
        return

    # Push energy stats into HA recorder
    for flow_key, entity_id in sensor_entity_ids.items():
        sensor_stats = stats.get(flow_key, [])
        if not sensor_stats:
            continue
        metadata = StatisticMetaData(
            **_STAT_MEAN_NONE,
            has_sum=True,
            name=None,
            source="recorder",
            statistic_id=entity_id,
            unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            unit_class="energy",
        )
        async_import_statistics(hass, metadata, sensor_stats)

    _LOGGER.info(
        "hanchu.import_statistics: imported %d days (%s to %s)",
        imported_days,
        start_date,
        end_date,
    )

    if not include_power:
        await hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": "Hanchu: import complete",
                "message": (
                    f"Imported {imported_days} day(s) of energy data"
                    f" ({start_date} → {end_date})."
                ),
                "notification_id": "hanchu_import_statistics",
            },
            blocking=False,
        )
        return

    # ── Power statistics ─────────────────────────────────────────────────────
    # Look up entity IDs for power sensors.  Battery power uses the battery
    # device entity ({battery_sn}_rack_power, unit kW) rather than the inverter
    # entity (unit W), because that is the entity configured in the Energy
    # dashboard's Power Sources section.
    power_entity_ids: dict[str, str] = {}
    for sensor_key in _MINUTE_FIELD_TO_SENSOR.values():
        eid = entity_reg.async_get_entity_id("sensor", DOMAIN, f"{inverter_sn}_{sensor_key}")
        if eid:
            power_entity_ids[sensor_key] = eid
        else:
            _LOGGER.warning(
                "hanchu.import_statistics: no entity for %s_%s", inverter_sn, sensor_key
            )

    # Override battery_power lookup with the battery device entity when present
    bat_power_eid_kw: str | None = None
    if battery_sn:
        bat_eid = entity_reg.async_get_entity_id("sensor", DOMAIN, f"{battery_sn}_rack_power")
        if bat_eid:
            power_entity_ids["battery_power"] = bat_eid
            bat_power_eid_kw = bat_eid

    for sensor_key, entity_id in power_entity_ids.items():
        sensor_pstats = power_stats.get(sensor_key, [])
        if not sensor_pstats:
            continue
        sensor_pstats.sort(key=lambda x: x["start"] if isinstance(x, dict) else x.start)

        # Battery entity lives in kW; batP readings from the minute chart are W
        if entity_id == bat_power_eid_kw:
            sensor_pstats = [
                StatisticData(
                    start=s["start"] if isinstance(s, dict) else s.start,
                    mean=(s["mean"] if isinstance(s, dict) else s.mean) / 1000.0,
                )
                for s in sensor_pstats
            ]
            unit = UnitOfPower.KILO_WATT
        else:
            unit = UnitOfPower.WATT

        _LOGGER.info(
            "hanchu.import_statistics: writing %d power stats → %s (unit: %s)",
            len(sensor_pstats),
            entity_id,
            unit,
        )
        metadata = StatisticMetaData(
            **_STAT_MEAN_ARITH,
            has_sum=False,
            name=None,
            source="recorder",
            statistic_id=entity_id,
            unit_of_measurement=unit,
            unit_class="power",
        )
        async_import_statistics(hass, metadata, sensor_pstats)

    _LOGGER.info(
        "hanchu.import_statistics: imported %d days of hourly power stats (%s to %s)",
        power_days,
        start_date,
        end_date,
    )

    await hass.services.async_call(
        "persistent_notification",
        "create",
        {
            "title": "Hanchu: import complete",
            "message": (
                f"Imported {imported_days} day(s) of energy data"
                f" ({start_date} → {end_date})."
                f" Power data: {power_days} day(s)."
            ),
            "notification_id": "hanchu_import_statistics",
        },
        blocking=False,
    )
