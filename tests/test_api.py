"""Tests for HanchuApi response parsing."""
from __future__ import annotations

import pytest
import aiohttp
from aioresponses import aioresponses

from custom_components.hanchu.api import HanchuApi, HanchuApiError
from custom_components.hanchu.const import (
    API_ENERGY_FLOW,
    API_PARALLEL_POWER_CHART,
    API_POWER_MINUTE_CHART,
    API_RACK_DATA,
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
