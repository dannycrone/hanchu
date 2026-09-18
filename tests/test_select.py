"""Tests for the Hanchu work-mode select."""

from unittest.mock import MagicMock

from custom_components.hanchu.select import HanchuWorkModeSelect


def _select_with_values(values: dict[str, object]) -> HanchuWorkModeSelect:
    entity = object.__new__(HanchuWorkModeSelect)
    entity.coordinator = MagicMock()
    entity.coordinator.get.side_effect = values.get
    return entity


def test_current_option_uses_current_portal_field():
    entity = _select_with_values({"WORK_MODE_CMB": "3", "workMode": "1"})

    assert entity.current_option == "User-defined"


def test_current_option_falls_back_to_legacy_field():
    entity = _select_with_values({"workMode": 2})

    assert entity.current_option == "Backup power"
