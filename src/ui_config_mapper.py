from __future__ import annotations

import os
from datetime import datetime

from config import merge_config


def auto_run_label(prefix: str = "run") -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def map_breakdown_level_to_group_dims(breakdown_level: str) -> list[str]:
    if breakdown_level == "Total Business":
        return []
    if breakdown_level == "By Location":
        return ["location"]
    if breakdown_level == "By Location & Category":
        return ["location", "category"]
    return []


def suggest_aggregation_method(value_column: str) -> str:
    value = (value_column or "").strip().lower()

    sum_metrics = {
        "gross_amount",
        "transactions",
        "revenue",
        "sales",
        "gross_member_count",
        "monthly_amortization",
        "day_wise_amortization",
    }

    mean_metrics = {
        "price",
        "rate",
        "avg_price",
        "average_price",
        "avg_ticket",
    }

    last_metrics = {
        "inventory",
        "inventory_snapshot",
        "headcount_snapshot",
        "closing_balance",
    }

    if value in sum_metrics:
        return "sum"
    if value in mean_metrics:
        return "mean"
    if value in last_metrics:
        return "last"

    return "sum"


def build_output_dir(base_dir: str, run_label: str) -> str:
    return os.path.join(base_dir, run_label)


def build_config_from_ui_inputs(
    *,
    data_file: str,
    value_column: str,
    periods: int,
    breakdown_level: str,
    include_ramzan: bool,
    include_eid: bool,
    custom_events: list[dict] | None = None,
    forecast_grain: str = "monthly",
    base_output_dir: str = "output",
    run_label: str | None = None,
) -> dict:
    run_label = run_label or auto_run_label("forecast")
    group_dims = map_breakdown_level_to_group_dims(breakdown_level)
    aggregation_method = suggest_aggregation_method(value_column)
    output_dir = build_output_dir(base_output_dir, run_label)

    user_config = {
        "data_file": data_file,
        "value_column": value_column,
        "group_dims": group_dims,
        "model": "ensemble",
        "periods": int(periods),
        "forecast_grain": forecast_grain,
        "aggregation_method": aggregation_method,

        "budget_seasonal_weight": 0.5,
        "budget_rolling_weight": 0.3,
        "budget_trend_weight": 0.2,
        "budget_rolling_window": 6,
        "save_learning_history": True,

        "budget_adjustment_pct": 0.0,
        "use_calibration": True,
        "calibration_window": 6,

        "scenario_growth_pct": 0.0,
        "ramzan_uplift_pct": 0.0,
        "event_uplift_pct": 0.0,
        "management_override_pct": 0.0,
        "churn_pct": 0.0,
        "new_branch_pct": 0.0,
        "management_target_pct": 0.0,

        "rolling_forecast": False,
        "rolling_horizon": 3,
        "min_train": 12,

        "output_dir": output_dir,
        "run_label": run_label,

        "recalc": {
            "enabled": False,
            "assumption_sets": [],
            "save_manifest": True,
        },

        "events": {
            "enabled": True,
            "country": "PK",
            "include_ramzan": bool(include_ramzan),
            "include_eid": bool(include_eid),
            "include_black_friday": False,
            "custom_events": custom_events or [],
        },
    }

    return merge_config(user_config)