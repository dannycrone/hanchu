"""Tests for _compute_hourly_fractions."""
from __future__ import annotations

import datetime as dt

from custom_components.hanchu import _compute_hourly_fractions

UTC = dt.timezone.utc


def _point(hour: int, pv: float = 0, bat: float = 0, meter: float = 0, load: float = 0) -> dict:
    ts_ms = int(dt.datetime(2024, 1, 15, hour, 0, tzinfo=UTC).timestamp() * 1000)
    return {"dataTimeTs": ts_ms, "pvTtPwr": pv, "batP": bat, "meterPPwr": meter, "loadEpsPwr": load}


class TestComputeHourlyFractions:
    def test_empty_data_returns_uniform(self):
        result = _compute_hourly_fractions([], UTC)
        for key in ("pv", "load", "batCharge", "batDisCharge", "gridImport", "gridExport"):
            fracs = result[key]
            assert len(fracs) == 24
            assert abs(sum(fracs) - 1.0) < 1e-9
            assert all(abs(f - 1 / 24) < 1e-9 for f in fracs)

    def test_all_fractions_sum_to_one(self):
        data = [_point(h, pv=float(h + 1), load=100.0) for h in range(24)]
        result = _compute_hourly_fractions(data, UTC)
        for key, fracs in result.items():
            assert abs(sum(fracs) - 1.0) < 1e-9, f"{key} fractions don't sum to 1"

    def test_pv_concentrated_in_midday_hours(self):
        data = [_point(h, pv=3000.0 if 10 <= h <= 14 else 0.0, load=500.0) for h in range(24)]
        result = _compute_hourly_fractions(data, UTC)
        pv = result["pv"]
        for h in range(24):
            if 10 <= h <= 14:
                assert pv[h] > 0
            else:
                assert pv[h] == 0.0

    def test_battery_charge_and_discharge_split_correctly(self):
        """Positive batP means charging; negative means discharging."""
        data = [_point(10, bat=500.0), _point(20, bat=-300.0)]
        result = _compute_hourly_fractions(data, UTC)
        assert result["batCharge"][10] > 0
        assert result["batDisCharge"][10] == 0.0
        assert result["batDisCharge"][20] > 0
        assert result["batCharge"][20] == 0.0

    def test_grid_import_and_export_split_correctly(self):
        """Positive meterPPwr means importing; negative means exporting."""
        data = [_point(8, meter=1000.0), _point(12, meter=-500.0)]
        result = _compute_hourly_fractions(data, UTC)
        assert result["gridImport"][8] > 0
        assert result["gridExport"][8] == 0.0
        assert result["gridExport"][12] > 0
        assert result["gridImport"][12] == 0.0

    def test_uniform_fallback_when_field_is_all_zero(self):
        data = [_point(h, load=0.0) for h in range(24)]
        result = _compute_hourly_fractions(data, UTC)
        assert all(abs(f - 1 / 24) < 1e-9 for f in result["load"])

    def test_points_without_dataTimets_are_skipped(self):
        data = [
            {"pvTtPwr": 9999},  # no dataTimeTs — must be ignored
            _point(12, pv=2000.0),
        ]
        result = _compute_hourly_fractions(data, UTC)
        assert abs(sum(result["pv"]) - 1.0) < 1e-9
        assert result["pv"][12] == 1.0  # all PV in hour 12

    def test_multiple_readings_per_hour_are_averaged(self):
        data = [
            {"dataTimeTs": int(dt.datetime(2024, 1, 15, 10, 0, tzinfo=UTC).timestamp() * 1000), "pvTtPwr": 1000, "batP": 0, "meterPPwr": 0, "loadEpsPwr": 0},
            {"dataTimeTs": int(dt.datetime(2024, 1, 15, 10, 30, tzinfo=UTC).timestamp() * 1000), "pvTtPwr": 2000, "batP": 0, "meterPPwr": 0, "loadEpsPwr": 0},
        ]
        result = _compute_hourly_fractions(data, UTC)
        # Both readings land in hour 10; mean = 1500 W → 100% of PV
        assert result["pv"][10] == 1.0

    def test_returns_all_six_keys(self):
        result = _compute_hourly_fractions([], UTC)
        assert set(result.keys()) == {"pv", "load", "batCharge", "batDisCharge", "gridImport", "gridExport"}
