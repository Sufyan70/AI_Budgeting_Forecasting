import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats


class DataEngine:

    def __init__(self, filepath):
        self.filepath = filepath
        self.raw = None
        self.date_col = None
        self.value_cols = []
        self.dimension_cols = []
        self.freq = None

    def load(self):
        ext = Path(self.filepath).suffix.lower()
        if ext == ".csv":
            self.raw = pd.read_csv(self.filepath)
        elif ext in (".xlsx", ".xls"):
            self.raw = pd.read_excel(self.filepath)
        else:
            raise ValueError(f"Unsupported: {ext}")
        self._detect_structure()
        return self

    def _detect_structure(self):
        df = self.raw
        self.value_cols = []
        self.dimension_cols = []
        for col in df.columns:
            if col.lower() in ("date", "ds", "timestamp", "time", "period", "month", "year_month"):
                self.date_col = col
                break
        if self.date_col is None:
            for col in df.columns:
                try:
                    pd.to_datetime(df[col].head(20))
                    self.date_col = col
                    break
                except Exception:
                    continue

        for col in df.columns:
            if col == self.date_col:
                continue
            if pd.api.types.is_numeric_dtype(df[col]):
                self.value_cols.append(col)
            else:
                if df[col].nunique() < 50:
                    self.dimension_cols.append(col)

        self._detect_freq()

    def _detect_freq(self):
        if self.date_col is None:
            self.freq = "MS"
            return
        dates = pd.to_datetime(self.raw[self.date_col], errors="coerce").dropna().drop_duplicates().sort_values()
        if len(dates) < 2:
            self.freq = "MS"
            return
        diffs = dates.diff().dropna()
        median_days = diffs.median().days
        if median_days <= 2:
            self.freq = "D"
        elif median_days <= 8:
            self.freq = "W"
        elif median_days <= 35:
            self.freq = "MS"
        elif median_days <= 100:
            self.freq = "QS"
        else:
            self.freq = "YS"

    def aggregate_to_frequency(self, df, value_col, freq=None, group_dims=None):
        freq = freq or self.freq or "MS"
        group_dims = group_dims or []
        out = df.copy()
        out[self.date_col] = pd.to_datetime(out[self.date_col])
        if freq in {"MS", "QS", "YS"}:
            out[self.date_col] = out[self.date_col].dt.to_period(freq[0]).dt.to_timestamp()
        keys = [self.date_col] + group_dims
        grouped = out.groupby(keys, dropna=False)[value_col].sum().reset_index()
        return grouped

    def validate_time_continuity(self, df, date_col="ds", freq=None):
        freq = freq or self.freq or "MS"
        dates = pd.to_datetime(df[date_col]).drop_duplicates().sort_values()
        if len(dates) < 2:
            return {"is_continuous": True, "missing_periods": 0}
        full = pd.date_range(dates.min(), dates.max(), freq=freq)
        missing = len(set(full) - set(dates))
        return {"is_continuous": missing == 0, "missing_periods": int(missing)}

    def prepare(self, value_col, group_dims=None, freq=None):
        df = self.raw.copy()
        grouped = self.aggregate_to_frequency(df, value_col, freq=freq, group_dims=group_dims)
        grouped.columns = list(grouped.columns[:-1]) + ["y"]
        grouped = grouped.rename(columns={self.date_col: "ds"})
        grouped = grouped.sort_values("ds").reset_index(drop=True)
        grouped["y"] = grouped["y"].interpolate(method="linear").bfill().ffill()
        return grouped

    def prepare_actuals(self, value_col, group_dims=None, freq=None):
        return self.prepare(value_col, group_dims=group_dims, freq=freq)

    def prepare_budget(self, budget_df, date_col, value_col):
        out = budget_df.copy()
        out[date_col] = pd.to_datetime(out[date_col])
        out = out.rename(columns={date_col: "ds", value_col: "budget"})
        return out[["ds", "budget"]].sort_values("ds").reset_index(drop=True)

    def build_comparison_base(self, actuals, series_key="Total"):
        out = actuals[["ds", "y"]].copy()
        out["series"] = series_key
        return out

    def get_series_list(self, value_col, group_dims=None, freq=None):
        df = self.raw.copy()
        df[self.date_col] = pd.to_datetime(df[self.date_col])
        if not group_dims or len(group_dims) == 0:
            agg = self.aggregate_to_frequency(df, value_col, freq=freq, group_dims=[])
            agg.columns = ["ds", "y"]
            agg = agg.sort_values("ds").reset_index(drop=True)
            agg["y"] = agg["y"].interpolate().bfill().ffill()
            return [("Total", agg)]
        series = []
        grouped = df.groupby(group_dims, dropna=False)
        for keys, grp in grouped:
            if not isinstance(keys, tuple):
                keys = (keys,)
            label = " | ".join(f"{d}={k}" for d, k in zip(group_dims, keys))
            agg = self.aggregate_to_frequency(grp, value_col, freq=freq, group_dims=[])
            agg.columns = ["ds", "y"]
            agg = agg.sort_values("ds").reset_index(drop=True)
            agg["y"] = agg["y"].interpolate().bfill().ffill()
            if len(agg) >= 6:
                series.append((label, agg))
        return series

    def analyze(self, df):
        y = df["y"]
        x = np.arange(len(y))
        slope, _, r_value, _, _ = stats.linregress(x, y.values)
        trend_pct = (slope * len(y)) / y.mean() * 100 if y.mean() != 0 else 0
        result = {
            "n": len(y),
            "mean": y.mean(),
            "std": y.std(),
            "min": y.min(),
            "max": y.max(),
            "trend_pct": trend_pct,
            "r2": r_value ** 2,
            "start": df["ds"].min(),
            "end": df["ds"].max(),
        }
        if self.freq in ("MS", "M", "D", "W") and len(df) >= 24:
            monthly = df.copy()
            monthly["month"] = monthly["ds"].dt.month
            mavg = monthly.groupby("month")["y"].mean()
            result["seasonal_index"] = (mavg / y.mean()).to_dict()
        return result

    def print_info(self):
        print(f"\nFile: {self.filepath}")
        print(f"Rows: {len(self.raw)} | Freq: {self.freq}")
        print(f"Date column: {self.date_col}")
        print(f"Value columns: {self.value_cols}")
        if self.dimension_cols:
            print(f"Dimensions: {self.dimension_cols}")
            for d in self.dimension_cols:
                vals = self.raw[d].unique().tolist()
                if len(vals) <= 10:
                    print(f"  {d}: {vals}")
                else:
                    print(f"  {d}: {len(vals)} unique values")
def aggregate_series(df, date_col, value_col, group_dims=None, grain="monthly", method="sum"):
    import pandas as pd

    data = df.copy()
    data[date_col] = pd.to_datetime(data[date_col], errors="coerce")
    data = data.dropna(subset=[date_col])

    group_dims = group_dims or []

    if grain == "daily":
        freq = "D"
    elif grain == "weekly":
        freq = "W-MON"
    elif grain == "monthly":
        freq = "MS"
    else:
        raise ValueError(f"Unsupported grain: {grain}")

    if group_dims:
        grouper = [pd.Grouper(key=date_col, freq=freq)] + group_dims
    else:
        grouper = [pd.Grouper(key=date_col, freq=freq)]

    if method == "sum":
        out = data.groupby(grouper, dropna=False)[value_col].sum().reset_index()
    elif method == "mean":
        out = data.groupby(grouper, dropna=False)[value_col].mean().reset_index()
    elif method == "last":
        sort_cols = [date_col] + group_dims if group_dims else [date_col]
        data = data.sort_values(sort_cols)
        out = data.groupby(grouper, dropna=False)[value_col].last().reset_index()
    else:
        raise ValueError(f"Unsupported aggregation method: {method}")

    return out    
    