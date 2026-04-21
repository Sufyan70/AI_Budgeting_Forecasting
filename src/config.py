from __future__ import annotations

from validators import (
    ensure_file_exists,
    validate_assumptions,
    validate_event_inputs,
    validate_group_dims,
    validate_model_name,
)

DEFAULT_CONFIG = {
    "data_file": "",
    "value_column": None,
    "group_dims": [],
    "model": "ensemble",
    "periods": 12,
    "forecast_grain": "monthly",
    "aggregation_method": "sum",
    "budget_seasonal_weight": 0.5,
    "budget_rolling_weight": 0.3,
    "budget_trend_weight": 0.2,
    "budget_rolling_window": 6,
    "save_learning_history":True,   
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
    "output_dir": "./output",
    "run_label": "base_run",
    "recalc": {
        "enabled": False,
        "assumption_sets": [],
        "save_manifest": True,
    },
    "events": {
        "enabled": True,
        "country": "PK",
        "include_ramzan": True,
        "include_eid": True,
        "include_black_friday": False,
        "custom_events": [],
    },
}



def merge_config(user_config: dict | None) -> dict:
    cfg = DEFAULT_CONFIG.copy()
    if not user_config:
        return cfg
    for k, v in user_config.items():
        if isinstance(v, dict) and isinstance(cfg.get(k), dict):
            nested = cfg[k].copy()
            nested.update(v)
            cfg[k] = nested
        else:
            cfg[k] = v
    return cfg



def validate_config(config: dict) -> None:
    ensure_file_exists(config.get("data_file", ""))
    if int(config.get("periods", 0)) <= 0:
        raise ValueError("config.periods must be > 0")
    validate_model_name(config.get("model", "ensemble"))
    validate_group_dims(config.get("group_dims"))
    validate_event_inputs(config.get("events"))

    grain = config.get("forecast_grain", "monthly")
    if grain not in {"daily", "weekly", "monthly"}:
        raise ValueError("config.forecast_grain must be one of: daily, weekly, monthly")

    agg = config.get("aggregation_method", "sum")
    if agg not in {"sum", "mean", "last"}:
        raise ValueError("config.aggregation_method must be one of: sum, mean, last")
    for k in ["budget_seasonal_weight", "budget_rolling_weight", "budget_trend_weight"]:
        v = float(config.get(k, 0))
        if v < 0:
            raise ValueError(f"{k} must be >= 0")
    validate_assumptions(config)
