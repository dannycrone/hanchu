"""Hanchu ESS API client."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import time
from typing import Any

import aiohttp

from .const import (
    AES_KEY,
    API_ENERGY_FLOW,
    API_FAST_CHARGE_DISCHARGE,
    API_BMS_BATTERY_DATA,
    API_BMS_LIST,
    API_BMS_UNION_INFO,
    API_LOGIN,
    API_PARALLEL_POWER_CHART,
    API_PCS_LIST,
    API_POWER_CHART,
    API_POWER_MINUTE_CHART,
    API_RACK_DATA,
    API_SET_WORK_MODE,
    API_STATION_LIST,
    APP_HEADERS,
    PLATFORM_HEADERS,
    PUBKEY_PEM,
)

_LOGGER = logging.getLogger(__name__)

FAST_CHARGE_ACTION = "fast_charge"
FAST_DISCHARGE_ACTION = "fast_discharge"
STOP_FAST_CHARGE_ACTION = "stop_fast_charge"
STOP_FAST_DISCHARGE_ACTION = "stop_fast_discharge"

FAST_CHARGE_ACTION_CODES: dict[str, int | str] = {
    FAST_CHARGE_ACTION: 2,
    FAST_DISCHARGE_ACTION: 3,
    STOP_FAST_CHARGE_ACTION: "-2",
    STOP_FAST_DISCHARGE_ACTION: "-3",
}


def _float_or_none(value: Any) -> float | None:
    """Return *value* as a float when possible."""
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalise_bms_battery_data(data: dict[str, Any]) -> dict[str, Any]:
    """Map BMS battery-only response fields onto existing rack entity fields."""
    normalised = dict(data)

    voltage = _float_or_none(data.get("vPack"))
    current = _float_or_none(data.get("iPack"))
    if voltage is not None and current is not None:
        normalised.setdefault("rackPwr", voltage * current)

    field_map = {
        "socPack": "rackSoc",
        "vPack": "rackTotalV",
        "iPack": "rackTotalA",
        "designCapacity": "rackCapacity",
        "stateFetCharging": "chargingRelay",
        "stateFetDischarging": "dischargingRelay",
    }
    for source, target in field_map.items():
        if source in data:
            normalised.setdefault(target, data[source])

    if "socPack" in data:
        normalised.setdefault("rackCapRemain", data["socPack"])

    temperatures: list[float] = []
    for index in range(1, 7):
        source = f"tBat{index}"
        target = f"rackT{index}"
        if source not in data:
            continue
        normalised.setdefault(target, data[source])
        temperature = _float_or_none(data[source])
        if temperature is not None:
            temperatures.append(temperature)

    if temperatures:
        normalised.setdefault("maxT", max(temperatures))
        normalised.setdefault("minT", min(temperatures))

    return normalised


def _append_unique(values: list[str], value: Any) -> None:
    """Append a non-empty value to *values* once, preserving order."""
    text = str(value or "").strip()
    if text and text not in values:
        values.append(text)


def _redact_identifier(value: Any) -> str:
    """Return a stable redacted label for serials/device IDs in logs."""
    text = str(value or "").strip()
    if not text:
        return "<empty>"
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    return f"len={len(text)} sha={digest}"


class HanchuApiError(Exception):
    """Raised when the Hanchu API returns an error."""


class HanchuAuthError(HanchuApiError):
    """Raised specifically when credentials are rejected by the API."""


class HanchuApi:
    """Async client for the Hanchu IESS3 cloud API."""

    def __init__(self, session: aiohttp.ClientSession, username: str, password: str) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._token: str | None = None

    # ──────────────────────────────────────────────────────────────────────────
    # Encryption helpers
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _rsa_encrypt(plaintext: str) -> str:
        """Encrypt *plaintext* with the Hanchu RSA public key (PKCS1 v1.5)."""
        from Crypto.PublicKey import RSA
        from Crypto.Cipher import PKCS1_v1_5

        key = RSA.import_key(PUBKEY_PEM)
        cipher = PKCS1_v1_5.new(key)
        ct = cipher.encrypt(plaintext.encode("utf-8"))
        return base64.b64encode(ct).decode("ascii")

    @staticmethod
    def _aes_encrypt(payload: dict[str, Any] | str) -> str:
        """AES-CBC encrypt *payload* with the Hanchu key/IV."""
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import pad

        if isinstance(payload, dict):
            plaintext = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        else:
            plaintext = payload.encode("utf-8")

        cipher = AES.new(AES_KEY, AES.MODE_CBC, iv=AES_KEY)
        ct = cipher.encrypt(pad(plaintext, AES.block_size))
        return base64.b64encode(ct).decode("ascii")

    # ──────────────────────────────────────────────────────────────────────────
    # Token management
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _jwt_exp(token: str) -> int:
        """Decode the JWT expiry timestamp without verifying the signature."""
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return int(payload["exp"])

    def _token_valid(self) -> bool:
        """Return True if the cached token has >24 h remaining."""
        if not self._token:
            return False
        try:
            return int(time.time()) < (self._jwt_exp(self._token) - 86400)
        except Exception:
            return False

    async def _ensure_token(self) -> str:
        """Return a valid JWT, re-authenticating if necessary."""
        if self._token_valid():
            return self._token  # type: ignore[return-value]

        pwd_enc = await asyncio.get_event_loop().run_in_executor(
            None, self._rsa_encrypt, self._password
        )
        body = await asyncio.get_event_loop().run_in_executor(
            None, self._aes_encrypt, {"account": self._username, "pwd": pwd_enc}
        )

        headers = {
            **APP_HEADERS,
            "content-type": "text/plain",
            "access-token": "",
        }

        async with self._session.post(
            API_LOGIN, headers=headers, data=body, timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            resp.raise_for_status()
            data = await resp.json(content_type=None)

        if not data.get("success") or data.get("code") != 200:
            raise HanchuAuthError(f"Login failed: {data}")

        token = data.get("data")
        if not token:
            raise HanchuAuthError("Login response contained no token")

        self._token = token
        _LOGGER.debug("Hanchu: authenticated, token expires %s", self._jwt_exp(token))
        return self._token

    # ──────────────────────────────────────────────────────────────────────────
    # API calls
    # ──────────────────────────────────────────────────────────────────────────

    async def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Encrypt *payload*, POST to *url*, return parsed JSON."""
        token = await self._ensure_token()
        body = await asyncio.get_event_loop().run_in_executor(
            None, self._aes_encrypt, payload
        )

        headers = {
            **APP_HEADERS,
            **self._browser_headers_for_url(url),
            "content-type": "text/plain",
            "access-token": token,
        }

        async with self._session.post(
            url, headers=headers, data=body, timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            resp.raise_for_status()
            return await resp.json(content_type=None)

    @staticmethod
    def _browser_headers_for_url(url: str) -> dict[str, str]:
        """Return browser compatibility headers for endpoints that require them."""
        if "/gateway/platform/" in url:
            return PLATFORM_HEADERS
        return {}

    async def async_test_connection(self, inverter_sn: str) -> bool:
        """Verify credentials and SN by fetching one parallelPowerChart response."""
        result = await self.async_fetch_power(inverter_sn)
        return result is not None

    async def async_test_battery_connection(self, battery_sn: str) -> bool:
        """Verify credentials and battery SN by fetching one rack response."""
        result = await self.async_fetch_battery(battery_sn)
        return result is not None

    async def async_fetch_stations(self) -> list[dict[str, Any]]:
        """Fetch stations available to the account."""
        result = await self._post(API_STATION_LIST, {"current": 1, "size": 100})
        if not result.get("success"):
            raise HanchuApiError(f"station queryList failed: {result}")
        data = result.get("data", {})
        records = data.get("records", [])
        return records if isinstance(records, list) else []

    async def async_fetch_bms_devices(self, station_id: str) -> list[dict[str, Any]]:
        """Fetch BMS/rack devices for a station."""
        result = await self._post(API_BMS_LIST, {"stationId": station_id})
        if not result.get("success"):
            raise HanchuApiError(f"bmsInfo queryAllList failed: {result}")
        data = result.get("data", [])
        return data if isinstance(data, list) else []

    async def async_fetch_bms_union_info(self, battery_sn: str) -> dict[str, Any]:
        """Fetch BMS unionInfo for *battery_sn*."""
        result = await self._post(API_BMS_UNION_INFO, {"sn": battery_sn})
        if not result.get("success"):
            raise HanchuApiError(f"bmsInfo unionInfo failed: {result}")
        data = result.get("data", {})
        return data if isinstance(data, dict) else {}

    async def async_fetch_pcs_devices(self, station_id: str) -> list[dict[str, Any]]:
        """Fetch inverter/PCS devices for a station."""
        result = await self._post(API_PCS_LIST, {"stationId": station_id})
        if not result.get("success"):
            raise HanchuApiError(f"pcs queryAllList failed: {result}")
        data = result.get("data", [])
        return data if isinstance(data, list) else []

    async def async_discover_inverters(self) -> list[dict[str, Any]]:
        """Discover inverter/PCS devices visible to the account."""
        inverters: list[dict[str, Any]] = []
        for station in await self.async_fetch_stations():
            station_id = station.get("stationId")
            if not station_id:
                continue
            station_name = station.get("stationName", station_id)
            for device in await self.async_fetch_pcs_devices(station_id):
                inverter_sn = device.get("pcsSn") or device.get("sn") or device.get("devId")
                if not inverter_sn:
                    continue
                inverters.append(
                    {
                        "sn": str(inverter_sn),
                        "station_id": station_id,
                        "station_name": station_name,
                        "online_status": device.get("onlineStatus"),
                        "model": device.get("machineType") or device.get("pcsModel"),
                    }
                )
        return inverters

    async def async_discover_batteries(self) -> list[dict[str, Any]]:
        """Discover battery rack/BMS devices visible to the account.

        Pack serial numbers are returned as metadata.  Some accounts expose
        rack-style devices that poll by serial number, while others expose BMS
        battery devices that poll by device ID.
        """
        batteries: list[dict[str, Any]] = []
        for station in await self.async_fetch_stations():
            station_id = station.get("stationId")
            if not station_id:
                continue
            station_name = station.get("stationName", station_id)
            for device in await self.async_fetch_bms_devices(station_id):
                battery_sn = device.get("sn") or device.get("devId") or device.get("dtuSn")
                polling_id = device.get("devId") or battery_sn
                if not battery_sn:
                    continue
                batteries.append(
                    {
                        "sn": str(battery_sn),
                        "polling_id": str(polling_id),
                        "device_id": str(device.get("devId") or ""),
                        "dtu_sn": str(device.get("dtuSn") or ""),
                        "station_id": station_id,
                        "station_name": station_name,
                        "online_status": device.get("onlineStatus"),
                        "pack_list": device.get("packList") or [],
                    }
                )
        return batteries

    async def async_resolve_battery_sn(self, candidate_sn: str) -> str | None:
        """Resolve a battery or pack serial number to the parent battery serial."""
        needle = candidate_sn.strip().upper()
        if not needle:
            return None

        for battery in await self.async_discover_batteries():
            serials = {
                str(battery.get("sn", "")).upper(),
                str(battery.get("device_id", "")).upper(),
                str(battery.get("dtu_sn", "")).upper(),
                *(str(sn).upper() for sn in battery.get("pack_list", [])),
            }
            if needle in serials:
                return str(battery["sn"])
        return None

    async def async_fetch_power(self, inverter_sn: str) -> dict[str, Any]:
        """Fetch parallelPowerChart data for *inverter_sn*.

        Returns the ``mainPower`` dict from the response.
        """
        result = await self._post(API_PARALLEL_POWER_CHART, {"sn": inverter_sn})
        if not result.get("success"):
            raise HanchuApiError(f"parallelPowerChart failed: {result}")
        data: dict[str, Any] = result.get("data", {})
        main_power: dict[str, Any] = data.get("mainPower", data)
        return main_power

    async def async_fetch_power_status(self, inverter_sn: str) -> dict[str, Any]:
        """Fetch fast charge/discharge status for *inverter_sn*."""
        result = await self._post(API_POWER_CHART, {"sn": inverter_sn})
        if not result.get("success"):
            raise HanchuApiError(f"powerChart failed: {result}")
        data = result.get("data", {})
        return data if isinstance(data, dict) else {}

    async def async_fetch_battery(self, battery_sn: str) -> dict[str, Any]:
        """Fetch battery data for *battery_sn*.

        Rack-style devices use queryRackDataDivisions by serial number.  BMS
        battery-only devices use queryBatteryDataDivisions by device ID.
        """
        try:
            result = await self._post(API_RACK_DATA, {"sn": battery_sn})
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            rack_error = HanchuApiError(f"queryRackDataDivisions request failed: {err}")
        else:
            if result.get("success"):
                return result.get("data", {})
            rack_error = HanchuApiError(f"queryRackDataDivisions failed: {result}")

        bms_errors: list[str] = []
        candidates = await self.async_resolve_bms_device_ids(battery_sn)
        _LOGGER.debug(
            "Hanchu battery fallback for %s resolved %d BMS candidate(s): %s",
            _redact_identifier(battery_sn),
            len(candidates),
            [_redact_identifier(candidate) for candidate in candidates],
        )
        for resolved_device_id in candidates:
            try:
                return await self.async_fetch_bms_battery(resolved_device_id)
            except (HanchuApiError, aiohttp.ClientError, asyncio.TimeoutError) as err:
                bms_errors.append(f"{_redact_identifier(resolved_device_id)}: {err}")

        if not bms_errors:
            bms_errors.append("no BMS battery detail candidates could be resolved")

        raise HanchuApiError(
            f"{rack_error}; queryBatteryDataDivisions failed for "
            f"{len(bms_errors)} candidate(s): {'; '.join(bms_errors)}"
        )

    async def async_resolve_bms_device_id(self, battery_sn: str) -> str | None:
        """Resolve a battery serial/pack serial to a BMS device ID when possible."""
        candidates = await self.async_resolve_bms_device_ids(battery_sn)
        return candidates[0] if candidates else None

    async def async_resolve_bms_device_ids(self, battery_sn: str) -> list[str]:
        """Return possible BMS battery detail identifiers for *battery_sn*."""
        seed_values: list[str] = []
        _append_unique(seed_values, battery_sn)

        try:
            for battery in await self.async_discover_batteries():
                battery_values: list[str] = []
                _append_unique(battery_values, battery.get("sn"))
                _append_unique(battery_values, battery.get("device_id"))
                _append_unique(battery_values, battery.get("polling_id"))
                _append_unique(battery_values, battery.get("dtu_sn"))
                for pack_sn in battery.get("pack_list", []):
                    _append_unique(battery_values, pack_sn)

                needle = battery_sn.strip().upper()
                if needle in {value.upper() for value in battery_values}:
                    for value in battery_values:
                        _append_unique(seed_values, value)
        except (HanchuApiError, aiohttp.ClientError, asyncio.TimeoutError):
            pass

        detail_ids: list[str] = []
        for seed in seed_values:
            try:
                union_info = await self.async_fetch_bms_union_info(seed)
            except (HanchuApiError, aiohttp.ClientError, asyncio.TimeoutError):
                pass
            else:
                dev_id = union_info.get("devId")
                if dev_id:
                    _LOGGER.debug(
                        "Hanchu BMS unionInfo resolved %s to %s",
                        _redact_identifier(seed),
                        _redact_identifier(dev_id),
                    )
                _append_unique(detail_ids, dev_id)

        for seed in seed_values:
            _append_unique(detail_ids, seed)

        return detail_ids

    async def async_fetch_bms_battery(self, device_id: str) -> dict[str, Any]:
        """Fetch BMS battery data for *device_id* and normalise it for HA entities."""
        result = await self._post(API_BMS_BATTERY_DATA, {"deviceId": device_id})
        if not result.get("success"):
            raise HanchuApiError(f"queryBatteryDataDivisions failed: {result}")

        data = result.get("data", {})
        if not isinstance(data, dict):
            return {}

        return _normalise_bms_battery_data(data)

    async def async_fetch_energy_flow(self, inverter_sn: str, date_str: str) -> dict[str, Any]:
        """Fetch energy/flow daily totals for *inverter_sn* on *date_str* (YYYY-MM-DD).

        Returns the ``sumData`` dict from the response, which contains:
        pv, gridImport, gridExport, batCharge, batDisCharge, load (all in kWh).
        """
        result = await self._post(
            API_ENERGY_FLOW,
            {"devId": inverter_sn, "detail": False, "date": date_str},
        )
        if not result.get("success"):
            raise HanchuApiError(f"energy/flow failed: {result}")
        data = result.get("data", {})
        return data.get("sumData") or data.get("data", {})

    async def async_fetch_power_minute_chart(
        self, sn: str, start_ts_ms: int, end_ts_ms: int
    ) -> list[dict[str, Any]]:
        """Fetch powerMinuteChart for *sn* over the given millisecond timestamp range.

        Returns a list of per-minute dicts containing fields such as
        dataTimeTs, pvTtPwr, batP, loadEpsPwr, meterPPwr, etc.
        """
        result = await self._post(
            API_POWER_MINUTE_CHART,
            {
                "sn": sn,
                "devType": "2",
                "maxCount": 1440,
                "dataTimeTsStart": start_ts_ms,
                "dataTimeTsEnd": end_ts_ms,
                "masterSum": True,
            },
        )
        if not result.get("success"):
            raise HanchuApiError(f"powerMinuteChart failed: {result}")
        data = result.get("data")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("data") or []
        return []

    async def async_set_work_mode(self, inverter_sn: str, mode: int) -> bool:
        """Set the work mode on the inverter.

        Returns True on success.
        """
        try:
            result = await self._post(API_SET_WORK_MODE, {"sn": inverter_sn, "workMode": mode})
            return bool(result.get("success"))
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Failed to set work mode: %s", err)
            return False

    async def async_fast_charge_discharge(
        self,
        inverter_sn: str,
        action: str,
        duration_minutes: int | None = None,
    ) -> bool:
        """Start or stop Hanchu fast charge/discharge mode."""
        action_code = FAST_CHARGE_ACTION_CODES[action]
        payload: dict[str, Any] = {"sn": inverter_sn, "act": action_code}
        if action in {FAST_CHARGE_ACTION, FAST_DISCHARGE_ACTION}:
            if duration_minutes is None:
                raise HanchuApiError("duration_minutes is required for start actions")
            payload["duration"] = duration_minutes * 60

        result = await self._post(API_FAST_CHARGE_DISCHARGE, payload)
        if not result.get("success"):
            raise HanchuApiError(f"fastChargeDischarge failed: {result}")

        data = result.get("data") or {}
        fail_count = data.get("failCount", 0)
        return int(fail_count or 0) == 0
