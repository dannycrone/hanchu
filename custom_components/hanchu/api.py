"""Hanchu ESS API client."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from typing import Any

import aiohttp

from .const import (
    AES_KEY,
    API_ENERGY_FLOW,
    API_LOGIN,
    API_PARALLEL_POWER_CHART,
    API_POWER_MINUTE_CHART,
    API_RACK_DATA,
    API_SET_WORK_MODE,
    APP_HEADERS,
    PUBKEY_PEM,
)

_LOGGER = logging.getLogger(__name__)


class HanchuApiError(Exception):
    """Raised when the Hanchu API returns an error."""


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
            raise HanchuApiError(f"Login failed: {data}")

        token = data.get("data")
        if not token:
            raise HanchuApiError("Login response contained no token")

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
            "content-type": "text/plain",
            "access-token": token,
        }

        async with self._session.post(
            url, headers=headers, data=body, timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            resp.raise_for_status()
            return await resp.json(content_type=None)

    async def async_test_connection(self, inverter_sn: str) -> bool:
        """Verify credentials and SN by fetching one parallelPowerChart response."""
        result = await self.async_fetch_power(inverter_sn)
        return result is not None

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

    async def async_fetch_battery(self, battery_sn: str) -> dict[str, Any]:
        """Fetch queryRackDataDivisions for *battery_sn*.

        Returns the top-level ``data`` dict from the response.
        """
        result = await self._post(API_RACK_DATA, {"sn": battery_sn})
        if not result.get("success"):
            raise HanchuApiError(f"queryRackDataDivisions failed: {result}")
        return result.get("data", {})

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
