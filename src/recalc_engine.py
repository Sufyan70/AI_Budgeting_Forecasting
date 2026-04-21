from __future__ import annotations

import copy
import json
import os
from itertools import product

from config import merge_config, validate_config


class RecalculationEngine:
    def __init__(self, runner):
        self.runner = runner

    def run_pipeline(self, config: dict) -> dict:
        cfg = merge_config(config)
        validate_config(cfg)
        return self.runner(cfg)

    def recalculate(self, base_config: dict, overrides: dict | None = None) -> dict:
        cfg = merge_config(base_config)
        if overrides:
            for key, value in overrides.items():
                if isinstance(value, dict) and isinstance(cfg.get(key), dict):
                    nested = cfg[key].copy()
                    nested.update(value)
                    cfg[key] = nested
                else:
                    cfg[key] = value
        validate_config(cfg)
        return self.runner(cfg)

    def rerun_with_assumptions(self, base_config: dict, assumption_sets: list[dict]) -> list[dict]:
        results = []
        for idx, assumptions in enumerate(assumption_sets, start=1):
            result = self.recalculate(base_config, assumptions)
            result["run_index"] = idx
            result["assumptions"] = assumptions
            results.append(result)
        return results

    def batch_run(self, grid_config: dict, grid: dict[str, list]) -> list[dict]:
        keys = list(grid.keys())
        combinations = list(product(*[grid[k] for k in keys]))
        results = []
        for idx, combo in enumerate(combinations, start=1):
            overrides = dict(zip(keys, combo))
            result = self.recalculate(grid_config, overrides)
            result["run_index"] = idx
            result["assumptions"] = overrides
            results.append(result)
        return results

    @staticmethod
    def from_json(path: str) -> dict:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def save_run_manifest(output_dir: str, runs: list[dict]) -> str:
        os.makedirs(output_dir, exist_ok=True)
        path = os.path.join(output_dir, "recalc_manifest.json")
        safe_runs = []
        for run in runs:
            safe = copy.deepcopy(run)
            # keep manifest concise and serializable
            for noisy_key in ["sheets", "forecast_df", "budget_df", "bfa_df", "scenario_df", "variance_df", "calibration_df"]:
                safe.pop(noisy_key, None)
            safe_runs.append(safe)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(safe_runs, f, indent=2, default=str)
        return path
