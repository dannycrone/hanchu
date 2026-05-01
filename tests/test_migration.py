"""Tests for async_migrate_entry v1 → v2 (strip serial numbers from entity IDs)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from custom_components.hanchu import async_migrate_entry

INV_SN_UPPER = "H03TESTINVTEST"
BAT_SN_UPPER = "B0BTESTBATTEST"
INV_SN = INV_SN_UPPER.lower()
BAT_SN = BAT_SN_UPPER.lower()


def _entity(entity_id: str) -> MagicMock:
    e = MagicMock()
    e.entity_id = entity_id
    return e


def _entry(version: int = 1) -> MagicMock:
    entry = MagicMock()
    entry.version = version
    entry.entry_id = "test_entry"
    entry.data = {"inverter_sn": INV_SN_UPPER, "battery_sn": BAT_SN_UPPER}
    return entry


def _hass() -> MagicMock:
    hass = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()
    return hass


def _patch_registry(entities):
    entity_reg = MagicMock()
    return (
        entity_reg,
        patch("custom_components.hanchu.er.async_get", return_value=entity_reg),
        patch("custom_components.hanchu.er.async_entries_for_config_entry", return_value=entities),
    )


async def test_strips_inverter_sn_from_entity_ids():
    entities = [
        _entity(f"sensor.hanchu_{INV_SN}_solar_power"),
        _entity(f"sensor.hanchu_{INV_SN}_load_power"),
    ]
    reg, p1, p2 = _patch_registry(entities)
    with p1, p2:
        result = await async_migrate_entry(_hass(), _entry())
    assert result is True
    reg.async_update_entity.assert_any_call(
        f"sensor.hanchu_{INV_SN}_solar_power",
        new_entity_id="sensor.hanchu_solar_power",
    )
    reg.async_update_entity.assert_any_call(
        f"sensor.hanchu_{INV_SN}_load_power",
        new_entity_id="sensor.hanchu_load_power",
    )


async def test_strips_battery_sn_from_entity_ids():
    entities = [_entity(f"sensor.hanchu_{BAT_SN}_rack_temperature_1")]
    reg, p1, p2 = _patch_registry(entities)
    with p1, p2:
        result = await async_migrate_entry(_hass(), _entry())
    assert result is True
    reg.async_update_entity.assert_called_once_with(
        f"sensor.hanchu_{BAT_SN}_rack_temperature_1",
        new_entity_id="sensor.hanchu_rack_temperature_1",
    )


async def test_clean_entity_ids_are_not_touched():
    entities = [
        _entity("sensor.hanchu_solar_power"),
        _entity("sensor.hanchu_grid_power"),
    ]
    reg, p1, p2 = _patch_registry(entities)
    with p1, p2:
        await async_migrate_entry(_hass(), _entry())
    reg.async_update_entity.assert_not_called()


async def test_entry_version_is_updated_to_2():
    reg, p1, p2 = _patch_registry([])
    hass = _hass()
    entry = _entry()
    with p1, p2:
        await async_migrate_entry(hass, entry)
    hass.config_entries.async_update_entry.assert_called_once_with(entry, version=2)


async def test_migration_skipped_when_already_v2():
    """Entries at version 2+ pass through without any changes."""
    reg, p1, p2 = _patch_registry([_entity(f"sensor.hanchu_{INV_SN}_solar_power")])
    hass = _hass()
    with p1, p2:
        result = await async_migrate_entry(hass, _entry(version=2))
    assert result is True
    reg.async_update_entity.assert_not_called()
    hass.config_entries.async_update_entry.assert_not_called()


async def test_returns_true_even_when_rename_raises():
    """A failing rename should be logged but not abort the migration."""
    entities = [_entity(f"sensor.hanchu_{INV_SN}_solar_power")]
    reg, p1, p2 = _patch_registry(entities)
    reg.async_update_entity.side_effect = Exception("registry conflict")
    hass = _hass()
    entry = _entry()
    with p1, p2:
        result = await async_migrate_entry(hass, entry)
    assert result is True
    hass.config_entries.async_update_entry.assert_called_once_with(entry, version=2)
