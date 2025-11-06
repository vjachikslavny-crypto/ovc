from __future__ import annotations

import json
from typing import Any, Dict, Optional, Union

DEFAULT_SIZE_WEIGHT = 1.0
MIN_SIZE_WEIGHT = 0.3
MAX_SIZE_WEIGHT = 6.0


def clamp_size_weight(value: Any) -> float:
    """Convert incoming value to a sane float in the configured bounds."""
    try:
        weight = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        weight = DEFAULT_SIZE_WEIGHT
    if weight != weight:  # NaN guard
        weight = DEFAULT_SIZE_WEIGHT
    return max(MIN_SIZE_WEIGHT, min(MAX_SIZE_WEIGHT, weight))


def _coerce_dict(value: Union[str, Dict[str, Any], None]) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            data = json.loads(value)
            if isinstance(data, dict):
                return dict(data)
        except json.JSONDecodeError:
            return {}
    return {}


def normalize_layout_hints(hints: Union[str, Dict[str, Any], None]) -> Dict[str, Any]:
    data = _coerce_dict(hints)
    data["sizeWeight"] = clamp_size_weight(data.get("sizeWeight"))
    return data


def merge_layout_hints(
    current: Union[str, Dict[str, Any], None], updates: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    merged = normalize_layout_hints(current)
    if isinstance(updates, dict):
        for key, value in updates.items():
            if value is None:
                merged.pop(key, None)
            else:
                merged[key] = value
    merged["sizeWeight"] = clamp_size_weight(merged.get("sizeWeight"))
    return merged


def dumps_layout_hints(hints: Optional[Dict[str, Any]]) -> str:
    normalized = normalize_layout_hints(hints)
    return json.dumps(normalized, ensure_ascii=False)


def parse_layout_hints(raw: Union[str, Dict[str, Any], None]) -> Dict[str, Any]:
    return normalize_layout_hints(raw)
