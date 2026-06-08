"""Shared helpers for the Hanchu ESS integration."""

from __future__ import annotations

from typing import Any


def serial_list(data: dict[str, Any], list_key: str, single_key: str) -> list[str]:
    """Return configured serial numbers from list fields or a legacy single field."""
    values = data.get(list_key)
    if isinstance(values, list):
        return [str(value).strip() for value in values if str(value).strip()]

    single = str(data.get(single_key, "")).strip()
    return [single] if single else []
