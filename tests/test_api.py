"""Tests for HanchuApi response parsing."""
from __future__ import annotations

import pytest
import aiohttp
from aioresponses import aioresponses

from custom_components.hanchu.api import HanchuApi, HanchuApiError
from custom_components.hanchu.const import (
    API_BMS_LIST,
    API_ENERGY_FLOW,
    API_FAST_CHARGE_DISCHARGE,
    API_PARALLEL_POWER_CHART,
    API_PCS_LIST,
    API_POWER_CHART,
    API_POWER_MINUTE_CHART,
    API_RACK_DATA,
    API_STATION_LIST,
)

from .conftest import make_jwt


@pytest.fixture
async def api():
    async with aiohttp.ClientSession() as session:
        client = HanchuApi(session, "user@example.com", "password")
        client._token = make_jwt()
        yield client


# ── async_fetch_power ────────────────────────────────────────────────────────

async def test_fetch_power_returns_main_power(api):
    with aioresponses() as m:
        m.post(
            API_PARALLEL_POWER_CHART,
            payload={"success": True, "data": {"mainPower": {"pvPower": 1500}, "other": "x"}},
        )
        result = await api.async_fetch_power("SN123")
    assert result == {"pvPower": 1500}


async def test_fetch_power_falls_back_to_data_when_no_main_power(api):
    with aioresponses() as m:
        m.post(
            API_PARALLEL_POWER_CHART,
            payload={"success": True, "data": {"pvPower": 500}},
        )
        result = await api.async_fetch_power("SN123")
    assert result == {"pvPower": 500}


async def test_fetch_power_raises_on_api_error(api):
    with aioresponses() as m:
        m.post(API_PARALLEL_POWER_CHART, payload={"success": False, "message": "bad sn"})
        with pytest.raises(HanchuApiError):
            await api.async_fetch_power("SN123")


async def test_fetch_power_status_returns_data(api):
    with aioresponses() as m:
        m.post(
            API_POWER_CHART,
            payload={
                "success": True,
                "data": {
                    "deviceStatusOfTestFastChg": 1,
                    "testTimeRemain": 592,
                },
            },
        )
        result = await api.async_fetch_power_status("SN123")

    assert result == {
        "deviceStatusOfTestFastChg": 1,
        "testTimeRemain": 592,
    }


async def test_fetch_power_status_raises_on_api_error(api):
    with aioresponses() as m:
        m.post(API_POWER_CHART, payload={"success": False, "message": "bad sn"})
        with pytest.raises(HanchuApiError):
            await api.async_fetch_power_status("SN123")


# ── async_fetch_battery ──────────────────────────────────────────────────────

async def test_fetch_battery_returns_data(api):
    with aioresponses() as m:
        m.post(
            API_RACK_DATA,
            payload={"success": True, "data": {"soc": 85, "voltage": 400}},
        )
        result = await api.async_fetch_battery("BSNSN")
    assert result == {"soc": 85, "voltage": 400}


async def test_fetch_battery_raises_on_api_error(api):
    with aioresponses() as m:
        m.post(API_RACK_DATA, payload={"success": False})
        with pytest.raises(HanchuApiError):
            await api.async_fetch_battery("BSNSN")


# ── async_fetch_energy_flow ──────────────────────────────────────────────────

async def test_test_battery_connection_returns_true(api):
    with aioresponses() as m:
        m.post(
            API_RACK_DATA,
            payload={"success": True, "data": {"soc": 85}},
        )
        result = await api.async_test_battery_connection("BSNSN")
    assert result is True


async def test_discover_batteries_returns_station_bms_devices(api):
    with aioresponses() as m:
        m.post(
            API_STATION_LIST,
            payload={
                "success": True,
                "data": {"records": [{"stationId": "ST1", "stationName": "Home"}]},
            },
        )
        m.post(
            API_BMS_LIST,
            payload={
                "success": True,
                "data": [
                    {
                        "sn": "B0B3484B80009",
                        "onlineStatus": "1",
                        "packList": ["B0232453A0089"],
                    }
                ],
            },
        )
        result = await api.async_discover_batteries()

    assert result == [
        {
            "sn": "B0B3484B80009",
            "station_id": "ST1",
            "station_name": "Home",
            "online_status": "1",
            "pack_list": ["B0232453A0089"],
        }
    ]


async def test_discover_inverters_returns_station_pcs_devices(api):
    with aioresponses() as m:
        m.post(
            API_STATION_LIST,
            payload={
                "success": True,
                "data": {"records": [{"stationId": "ST1", "stationName": "Home"}]},
            },
        )
        m.post(
            API_PCS_LIST,
            payload={
                "success": True,
                "data": [
                    {
                        "pcsSn": "H03Y8447L0128",
                        "onlineStatus": "1",
                        "machineType": "HESS-HY-T-12K",
                    }
                ],
            },
        )
        result = await api.async_discover_inverters()

    assert result == [
        {
            "sn": "H03Y8447L0128",
            "station_id": "ST1",
            "station_name": "Home",
            "online_status": "1",
            "model": "HESS-HY-T-12K",
        }
    ]


async def test_resolve_battery_sn_accepts_pack_sn(api):
    with aioresponses() as m:
        m.post(
            API_STATION_LIST,
            payload={
                "success": True,
                "data": {"records": [{"stationId": "ST1", "stationName": "Home"}]},
            },
        )
        m.post(
            API_BMS_LIST,
            payload={
                "success": True,
                "data": [
                    {
                        "sn": "B0B3484B80009",
                        "packList": ["B0232453A0089", "B0232453A0111"],
                    }
                ],
            },
        )
        result = await api.async_resolve_battery_sn("b0232453a0111")

    assert result == "B0B3484B80009"


async def test_fetch_energy_flow_returns_sum_data(api):
    with aioresponses() as m:
        m.post(
            API_ENERGY_FLOW,
            payload={
                "success": True,
                "data": {"sumData": {"pv": 12.5, "gridImport": 3.0}, "detail": []},
            },
        )
        result = await api.async_fetch_energy_flow("SN123", "2024-01-15")
    assert result == {"pv": 12.5, "gridImport": 3.0}


async def test_fetch_energy_flow_falls_back_to_data_dict_when_no_sum_data(api):
    with aioresponses() as m:
        m.post(
            API_ENERGY_FLOW,
            payload={"success": True, "data": {"data": {"pv": 5.0}}},
        )
        result = await api.async_fetch_energy_flow("SN123", "2024-01-15")
    assert result == {"pv": 5.0}


async def test_fetch_energy_flow_raises_on_api_error(api):
    with aioresponses() as m:
        m.post(API_ENERGY_FLOW, payload={"success": False})
        with pytest.raises(HanchuApiError):
            await api.async_fetch_energy_flow("SN123", "2024-01-15")


# ── async_fetch_power_minute_chart ───────────────────────────────────────────

async def test_fetch_power_minute_chart_list_response(api):
    minutes = [{"dataTimeTs": 1700000000000, "pvTtPwr": 1200}]
    with aioresponses() as m:
        m.post(API_POWER_MINUTE_CHART, payload={"success": True, "data": minutes})
        result = await api.async_fetch_power_minute_chart("SN123", 0, 1)
    assert result == minutes


async def test_fetch_power_minute_chart_dict_response(api):
    minutes = [{"dataTimeTs": 1700000000000, "pvTtPwr": 900}]
    with aioresponses() as m:
        m.post(
            API_POWER_MINUTE_CHART,
            payload={"success": True, "data": {"data": minutes}},
        )
        result = await api.async_fetch_power_minute_chart("SN123", 0, 1)
    assert result == minutes


async def test_fetch_power_minute_chart_empty_data_returns_empty_list(api):
    with aioresponses() as m:
        m.post(API_POWER_MINUTE_CHART, payload={"success": True, "data": None})
        result = await api.async_fetch_power_minute_chart("SN123", 0, 1)
    assert result == []


async def test_fetch_power_minute_chart_raises_on_api_error(api):
    with aioresponses() as m:
        m.post(API_POWER_MINUTE_CHART, payload={"success": False})
        with pytest.raises(HanchuApiError):
            await api.async_fetch_power_minute_chart("SN123", 0, 1)


# ── JWT helpers ──────────────────────────────────────────────────────────────

async def test_fast_discharge_sends_duration_seconds(api):
    with aioresponses() as m:
        m.post(
            API_FAST_CHARGE_DISCHARGE,
            payload={"success": True, "data": {"failCount": 0}},
        )
        result = await api.async_fast_charge_discharge("SN123", "fast_discharge", 5)
    assert result is True


async def test_stop_fast_charge_sends_stop_action(api):
    with aioresponses() as m:
        m.post(
            API_FAST_CHARGE_DISCHARGE,
            payload={"success": True, "data": {"failCount": 0}},
        )
        result = await api.async_fast_charge_discharge("SN123", "stop_fast_charge")
    assert result is True


async def test_fast_charge_discharge_raises_on_api_error(api):
    with aioresponses() as m:
        m.post(API_FAST_CHARGE_DISCHARGE, payload={"success": False})
        with pytest.raises(HanchuApiError):
            await api.async_fast_charge_discharge("SN123", "fast_charge", 10)


def test_jwt_exp_decodes_expiry():
    import time
    token = make_jwt(exp_offset=3600)
    exp = HanchuApi._jwt_exp(token)
    assert abs(exp - (int(time.time()) + 3600)) < 5


def test_token_valid_returns_false_when_no_token():
    import aiohttp
    client = HanchuApi.__new__(HanchuApi)
    client._token = None
    assert client._token_valid() is False


def test_token_valid_returns_false_for_expired_token():
    import aiohttp
    client = HanchuApi.__new__(HanchuApi)
    client._token = make_jwt(exp_offset=-1)
    assert client._token_valid() is False


def test_token_valid_returns_true_for_fresh_token():
    import aiohttp
    client = HanchuApi.__new__(HanchuApi)
    client._token = make_jwt(exp_offset=86400 * 30)
    assert client._token_valid() is True
