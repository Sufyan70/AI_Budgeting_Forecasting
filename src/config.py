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
    validate_assumptions(config)
