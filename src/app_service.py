from __future__ import annotations

from config import validate_config
from main import run_pipeline
from ui_config_mapper import build_config_from_ui_inputs


def run_forecasting_app(
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
    config = build_config_from_ui_inputs(
        data_file=data_file,
        value_column=value_column,
        periods=periods,
        breakdown_level=breakdown_level,
        include_ramzan=include_ramzan,
        include_eid=include_eid,
        custom_events=custom_events,
        forecast_grain=forecast_grain,
        base_output_dir=base_output_dir,
        run_label=run_label,
    )

    validate_config(config)
    result = run_pipeline(config)

    return {
        "status": "success",
        "config": config,
        "result": result,
        "output_dir": config["output_dir"],
        "run_label": config["run_label"],
    }