from __future__ import annotations

import os
import pandas as pd

from comparison import build_monthly_bfa_table


class ReportExporter:
    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def export_csv(self, name: str, df: pd.DataFrame) -> str:
        path = os.path.join(self.output_dir, f"{name}.csv")
        df.to_csv(path, index=False)
        return path

    def export_excel_bundle(self, sheets: dict) -> str:
        path = os.path.join(self.output_dir, "planning_bundle.xlsx")
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            for name, df in sheets.items():
                if df is not None and len(df) > 0:
                    df.to_excel(writer, sheet_name=name[:31], index=False)
        return path

    def export_run_summary(self, summary_rows: list[dict]) -> str | None:
        if not summary_rows:
            return None
        df = pd.DataFrame(summary_rows)
        return self.export_csv("run_summary", df)

    def export_bfa_summary(self, bfa_df: pd.DataFrame) -> str | None:
        if bfa_df is None or len(bfa_df) == 0:
            return None
        monthly = build_monthly_bfa_table(bfa_df)
        return self.export_csv("budget_forecast_actual_monthly", monthly)
