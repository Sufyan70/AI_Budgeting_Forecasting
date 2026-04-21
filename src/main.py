import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
from tabulate import tabulate

from calibration import ForecastCalibrator
from comparison import compute_kpis, merge_bfa
from config import merge_config, validate_config
from data_engine import DataEngine
from events import EventManager
from models import EnsembleModel, ProphetModel, SARIMAModel, LGBMModel, NaiveModel
from planning import RollingForecaster, ScenarioPlanner, VarianceAnalyzer, BudgetGenerator
from recalc_engine import RecalculationEngine
from reporting import ReportExporter


def inp(prompt, default=None):
    val = input(prompt).strip()
    return val if val else default


def pick(prompt, options):
    for i, o in enumerate(options, 1):
        print(f"  {i}. {o}")
    choice = inp(f"{prompt} [{len(options)}]: ", str(len(options)))
    idx = int(choice) - 1
    return options[max(0, min(idx, len(options) - 1))]



def load_config(config_path=None):
    if not config_path:
        return None
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg = merge_config(cfg)
    validate_config(cfg)
    return cfg



def build_events(config, series_df):
    evt_cfg = config.get("events", {})
    if not evt_cfg.get("enabled", True):
        return None
    mgr = EventManager()
    mgr.load_auto_calendar(
        start_date=series_df["ds"].min(),
        end_date=series_df["ds"].max() + pd.tseries.frequencies.to_offset("365D"),
        country=evt_cfg.get("country", "PK"),
        include_ramzan=evt_cfg.get("include_ramzan", True),
        include_eid=evt_cfg.get("include_eid", True),
        custom_events=evt_cfg.get("custom_events", []),
    )
    return mgr.get_dataframe()



def fit_model(model_name, sdf, freq, periods, events_df=None):
    key = (model_name or "ensemble").lower()
    if key == "prophet":
        model = ProphetModel(events_df)
        model.fit(sdf)
        fc = model.predict(periods, freq)
        fc = fc[fc["ds"] > sdf["ds"].max()].head(periods).reset_index(drop=True)
        fitted = model.fitted_values(sdf)
        return model, fc, fitted
    if key == "sarima":
        model = SARIMAModel()
        model.fit(sdf, freq)
        return model, model.predict(periods, sdf["ds"].iloc[-1], freq), model.fitted_values(sdf)
    if key == "lightgbm":
        model = LGBMModel(events_df=events_df)
        model.fit(sdf, freq)
        return model, model.predict(periods, sdf["ds"].iloc[-1], freq), model.fitted_values(sdf)
    if key == "naive":
        model = NaiveModel()
        model.fit(sdf, freq)
        return model, model.predict(periods, sdf["ds"].iloc[-1], freq), model.fitted_values(sdf)
    model = EnsembleModel(events_df, use_lgbm=(len(sdf) >= 24))
    model.fit(sdf, freq)
    return model, model.predict(periods, sdf["ds"].iloc[-1], freq), model.fitted_values(sdf)



def _single_run(config):
    filepath = config["data_file"]
    engine = DataEngine(filepath)
    engine.load()
    engine.print_info()
    value_col = config.get("value_column") or (engine.value_cols[0] if engine.value_cols else None)
    if not value_col:
        raise ValueError("No usable numeric value column found")
    group_dims = config.get("group_dims") or []
    output_dir = config.get("output_dir", "./output")
    os.makedirs(output_dir, exist_ok=True)
    exporter = ReportExporter(output_dir)
    series_list = engine.get_series_list(value_col, group_dims, freq=engine.freq)
    all_forecasts, all_budgets, all_bfa, all_scenarios, all_variances, all_calibration = [], [], [], [], [], []
    run_summary = []
    print(f"\nSeries to forecast: {len(series_list)}")
    for label_name, sdf in series_list:
        print(f"\n--- {label_name} ---")
        info = engine.analyze(sdf)
        continuity = engine.validate_time_continuity(sdf)
        print(f"  Points: {info['n']} | Mean: {info['mean']:,.2f} | Trend: {info['trend_pct']:+.1f}% | Missing periods: {continuity['missing_periods']}")
        if len(sdf) < 6:
            print("  Too few data points, skipping.")
            continue
        events_df = build_events(config, sdf)
        if events_df is not None and len(events_df) > 0:
            print(f"  Auto events loaded: {len(events_df)}")
        model_name = config.get("model", "ensemble")
        periods = int(config.get("periods", 12))
        _, fc, fitted = fit_model(model_name, sdf, engine.freq, periods, events_df)
        calibration_profile = None
        if config.get("use_calibration", True) and fitted is not None and len(fitted) > 0:
            calibrator = ForecastCalibrator(window=int(config.get("calibration_window", 6)))
            calibration_profile = calibrator.fit_calibrator(sdf, fitted, events_df)
            fc = calibrator.apply_calibration(fc, events_df)
            row = ForecastCalibrator.calibration_summary(calibration_profile)
            row["series"] = label_name
            all_calibration.append(pd.DataFrame([row]))
            print(f"  Calibration: {row}")
        fc["series"] = label_name
        all_forecasts.append(fc)
        tbl = fc[["ds", "yhat", "yhat_lower", "yhat_upper"]].copy()
        tbl["ds"] = tbl["ds"].dt.strftime("%Y-%m-%d")
        tbl.columns = ["Date", "Forecast", "Lower", "Upper"]
        print(tabulate(tbl.head(10), headers="keys", tablefmt="simple", showindex=False))
        scenarios = ScenarioPlanner.generate(
            fc,
            sdf["y"].std(),
            growth_pct=config.get("scenario_growth_pct", 0.0),
            ramzan_uplift_pct=config.get("ramzan_uplift_pct", 0.0),
            event_uplift_pct=config.get("event_uplift_pct", 0.0),
            management_override_pct=config.get("management_override_pct", 0.0),
            churn_pct=config.get("churn_pct", 0.0),
            new_branch_pct=config.get("new_branch_pct", 0.0),
        )
        for sname, sc in scenarios.items():
            sc2 = sc.copy()
            sc2["series"] = label_name
            sc2["scenario"] = sname
            all_scenarios.append(sc2)
        budget = BudgetGenerator.generate(
            fc,
            config.get("budget_adjustment_pct", 0.0),
            config.get("event_uplift_pct", 0.0),
            config.get("management_target_pct", 0.0),
        )
        budget["series"] = label_name
        all_budgets.append(budget)
        variance_stats = {}
        if fitted is not None and len(fitted) > 0:
            variance_df, variance_stats = VarianceAnalyzer.run(sdf, fitted, budget)
            variance_df["series"] = label_name
            all_variances.append(variance_df)
            print(f"  Fit accuracy -> MAE: {variance_stats['fc_mae']:,.2f} | MAPE: {variance_stats['fc_mape']:.1f}%")
            print(f"  Variance drivers -> Trend: {variance_stats['trend_var_mean']:,.2f} | Seasonality: {variance_stats['seasonality_var_mean']:,.2f} | Event: {variance_stats['event_var_mean']:,.2f}")
        bfa = merge_bfa(sdf, fc, budget, series_key=label_name)
        all_bfa.append(bfa)
        kpis = compute_kpis(bfa)
        if kpis:
            print(f"  KPIs: {kpis}")
        run_summary.append({
            "run_label": config.get("run_label", "base_run"),
            "series": label_name,
            "points": len(sdf),
            "missing_periods": continuity["missing_periods"],
            "forecast_periods": periods,
            "fc_mae": kpis.get("fc_mae"),
            "fc_mape": kpis.get("fc_mape"),
            "budget_mae": kpis.get("budget_mae"),
            "budget_mape": kpis.get("budget_mape"),
            "calibration_multiplier": None if calibration_profile is None else calibration_profile.get("final_multiplier"),
            "trend_var_mean": variance_stats.get("trend_var_mean"),
            "seasonality_var_mean": variance_stats.get("seasonality_var_mean"),
            "event_var_mean": variance_stats.get("event_var_mean"),
        })
        if config.get("rolling_forecast") and len(sdf) >= 18:
            print("\n  Rolling forecast:")
            roller = RollingForecaster(events_df, model_name=model_name)
            roller.run(sdf, horizon=int(config.get("rolling_horizon", 3)), min_train=max(int(config.get("min_train", 12)), len(sdf) // 3), freq=engine.freq)

    sheets = {}
    if all_forecasts:
        sheets["forecast"] = pd.concat(all_forecasts, ignore_index=True)
        exporter.export_csv("forecast", sheets["forecast"])
    if all_budgets:
        sheets["budget"] = pd.concat(all_budgets, ignore_index=True)
        exporter.export_csv("budget", sheets["budget"])
    if all_scenarios:
        sheets["scenarios"] = pd.concat(all_scenarios, ignore_index=True)
        exporter.export_csv("scenarios", sheets["scenarios"])
    if all_bfa:
        sheets["bfa"] = pd.concat(all_bfa, ignore_index=True)
        exporter.export_csv("budget_forecast_actual", sheets["bfa"])
        exporter.export_bfa_summary(sheets["bfa"])
    if all_variances:
        sheets["variance"] = pd.concat(all_variances, ignore_index=True)
        exporter.export_csv("variance", sheets["variance"])
    if all_calibration:
        sheets["calibration"] = pd.concat(all_calibration, ignore_index=True)
        exporter.export_csv("calibration", sheets["calibration"])
    if sheets:
        exporter.export_excel_bundle(sheets)
    exporter.export_run_summary(run_summary)
    print(f"\nDone. Output: {output_dir}/")
    for f in sorted(os.listdir(output_dir)):
        print(f"  {f}")
    return {
        "run_label": config.get("run_label", "base_run"),
        "output_dir": output_dir,
        "series_count": len(run_summary),
        "summary": run_summary,
        "sheets": list(sheets.keys()),
    }



def run_pipeline(config):
    engine = RecalculationEngine(_single_run)
    base_result = engine.run_pipeline(config)
    recalc_cfg = config.get("recalc", {}) or {}
    if not recalc_cfg.get("enabled"):
        return base_result
    assumption_sets = recalc_cfg.get("assumption_sets", []) or []
    if not assumption_sets:
        return base_result
    runs = [base_result]
    for idx, assumptions in enumerate(assumption_sets, start=1):
        run_label = assumptions.get("run_label", f"recalc_{idx}")
        output_dir = os.path.join(config.get("output_dir", "./output"), run_label)
        overrides = assumptions.copy()
        overrides["run_label"] = run_label
        overrides["output_dir"] = output_dir
        print(f"\n===== RECALC RUN: {run_label} =====")
        runs.append(engine.recalculate(config, overrides))
    if recalc_cfg.get("save_manifest", True):
        manifest_path = engine.save_run_manifest(config.get("output_dir", "./output"), runs)
        print(f"Manifest saved: {manifest_path}")
    return {"base_run": base_result, "recalc_runs": runs[1:]}



def interactive_main():
    print("\n  Budget & Forecasting Tool\n")
    filepath = inp("Data file path: ")
    if not filepath or not os.path.exists(filepath):
        print(f"Not found: {filepath}")
        return
    engine = DataEngine(filepath)
    engine.load()
    engine.print_info()
    if not engine.value_cols:
        print("No numeric columns found.")
        return
    value_col = engine.value_cols[0] if len(engine.value_cols) == 1 else pick("Value column:", engine.value_cols)
    group_dims = []
    if engine.dimension_cols and inp("Group by dimensions? (y/n) [n]: ", "n").lower() == "y":
        print("Available dimensions:")
        for i, d in enumerate(engine.dimension_cols, 1):
            print(f"  {i}. {d} ({len(engine.raw[d].unique())} values)")
        dim_input = inp("Select dimensions (comma-sep numbers, or 'all'): ", "")
        if dim_input.lower() == "all":
            group_dims = engine.dimension_cols
        elif dim_input:
            indices = [int(x.strip()) - 1 for x in dim_input.split(",")]
            group_dims = [engine.dimension_cols[i] for i in indices if 0 <= i < len(engine.dimension_cols)]
    model_choice = pick("Select model:", ["ensemble", "prophet", "sarima", "lightgbm", "naive"])
    cfg = merge_config({
        "data_file": filepath,
        "value_column": value_col,
        "group_dims": group_dims,
        "model": model_choice,
        "periods": int(inp("Forecast periods [12]: ", "12")),
        "budget_adjustment_pct": float(inp("Budget adjustment % [0]: ", "0")),
        "output_dir": inp("Output dir [./output]: ", "./output"),
    })
    validate_config(cfg)
    run_pipeline(cfg)


if __name__ == "__main__":
    config_path = sys.argv[1] if len(sys.argv) > 1 else None
    if config_path:
        cfg = load_config(config_path)
        run_pipeline(cfg)
    else:
        interactive_main()
