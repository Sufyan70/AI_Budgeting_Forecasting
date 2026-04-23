from __future__ import annotations

import os
from typing import Iterable

import pandas as pd


SUPPORTED_MODELS = {"prophet", "sarima", "lightgbm", "ensemble", "naive"}
SUPPORTED_FREQ = {"D", "W", "MS", "QS", "YS"}


def ensure_file_exists(path: str) -> None:
    if not path:
        raise ValueError("data_file is required")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Data file not found: {path}")



def validate_numeric_range(name: str, value, low: float = -1000.0, high: float = 1000.0) -> None:
    if value is None:
        return
    try:
        numeric = float(value)
    except Exception as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if numeric < low or numeric > high:
        raise ValueError(f"{name} must be between {low} and {high}")



def validate_columns_exist(df: pd.DataFrame, columns: Iterable[str], label: str = "input") -> None:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in {label}: {missing}")



def validate_model_name(model_name: str) -> None:
    if model_name not in SUPPORTED_MODELS:
        raise ValueError(f"Unsupported model: {model_name}")



def validate_frequency(freq: str | None) -> None:
    if freq is None:
        return
    if freq not in SUPPORTED_FREQ:
        raise ValueError(f"Unsupported frequency: {freq}")



def validate_group_dims(group_dims) -> None:
    if group_dims is None:
        return
    if not isinstance(group_dims, list):
        raise ValueError("group_dims must be a list")



def validate_event_inputs(events_cfg: dict | None) -> None:
    if not events_cfg:
        return

    for key in ["enabled", "include_ramzan", "include_eid", "include_black_friday"]:
        if key in events_cfg and not isinstance(events_cfg[key], bool):
            raise ValueError(f"events.{key} must be True or False")

    if "country" in events_cfg and not isinstance(events_cfg["country"], str):
        raise ValueError("events.country must be a string")

    custom = events_cfg.get("custom_events", [])
    if not isinstance(custom, list):
        raise ValueError("events.custom_events must be a list")

    for idx, row in enumerate(custom):
        if not isinstance(row, dict):
            raise ValueError(f"custom event #{idx + 1} must be an object")

        if "name" not in row:
            raise ValueError(f"custom event #{idx + 1} must include 'name'")

        start = row.get("start_date", row.get("start"))
        end = row.get("end_date", row.get("end", start))

        if start is None:
            raise ValueError(f"custom event #{idx + 1} must include start_date/start")

        try:
            start_dt = pd.to_datetime(start)
        except Exception as exc:
            raise ValueError(f"custom event #{idx + 1} has invalid start date: {start}") from exc

        try:
            end_dt = pd.to_datetime(end)
        except Exception as exc:
            raise ValueError(f"custom event #{idx + 1} has invalid end date: {end}") from exc

        if end_dt < start_dt:
            raise ValueError(
                f"custom event #{idx + 1} has end date before start date"
            )



def validate_assumptions(config: dict) -> None:
    pct_keys = [
        "budget_adjustment_pct",
        "scenario_growth_pct",
        "ramzan_uplift_pct",
        "event_uplift_pct",
        "management_override_pct",
        "churn_pct",
        "new_branch_pct",
        "management_target_pct",
    ]
    for key in pct_keys:
        validate_numeric_range(key, config.get(key), -200.0, 500.0)
    validate_numeric_range("calibration_window", config.get("calibration_window", 6), 1, 120)
    validate_numeric_range("periods", config.get("periods", 12), 1, 120)
    validate_numeric_range("rolling_horizon", config.get("rolling_horizon", 3), 1, 36)
    validate_numeric_range("min_train", config.get("min_train", 12), 3, 240)
