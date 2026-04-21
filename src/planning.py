import numpy as np
import pandas as pd


class RollingForecaster:
    def __init__(self, events_df=None, model_name="prophet"):
        self.events_df = events_df
        self.model_name = model_name

    def _model(self):
        from models import ProphetModel, SARIMAModel, LGBMModel, EnsembleModel, NaiveModel
        if self.model_name == "prophet":
            return ProphetModel(self.events_df)
        if self.model_name == "sarima":
            return SARIMAModel()
        if self.model_name == "lightgbm":
            return LGBMModel(events_df=self.events_df)
        if self.model_name == "naive":
            return NaiveModel()
        return EnsembleModel(self.events_df, use_lgbm=True)

    def run(self, df, horizon=3, min_train=12, freq="MS"):
        results = []
        total = max(1, len(df) - min_train - horizon + 1)
        print(f"  Rolling: {total} steps, horizon={horizon}")
        for i in range(total):
            train = df.iloc[: min_train + i].copy()
            test = df.iloc[min_train + i : min_train + i + horizon].copy()
            if len(test) == 0:
                break
            print(f"\r  Step {i + 1}/{total}", end="", flush=True)
            try:
                m = self._model()
                if self.model_name == "prophet":
                    m.fit(train)
                    pred = m.predict(horizon, freq)
                    pred = pred[pred["ds"] > train["ds"].max()].head(horizon).reset_index(drop=True)
                else:
                    m.fit(train, freq)
                    pred = m.predict(horizon, train["ds"].max(), freq)
                for j in range(min(len(test), len(pred))):
                    results.append({"ds": test.iloc[j]["ds"], "actual": test.iloc[j]["y"], "forecast": pred.iloc[j]["yhat"]})
            except Exception:
                pass
        print()
        if not results:
            return pd.DataFrame()
        rdf = pd.DataFrame(results)
        rdf["error"] = rdf["actual"] - rdf["forecast"]
        rdf["abs_error"] = rdf["error"].abs()
        rdf["pct_error"] = rdf["abs_error"] / rdf["actual"].abs().clip(lower=1) * 100
        mae = rdf["abs_error"].mean()
        mape = rdf["pct_error"].mean()
        rmse = float(np.sqrt(np.mean(np.square(rdf["error"]))))
        bias_pct = float((rdf["error"].sum() / rdf["actual"].abs().clip(lower=1).sum()) * 100)
        print(f"  MAE: {mae:,.2f} | MAPE: {mape:.1f}% | RMSE: {rmse:,.2f} | Bias%: {bias_pct:.1f}%")
        return rdf


class ScenarioPlanner:
    @staticmethod
    def _apply_multiplier(df, multiplier):
        out = df.copy()
        for c in ["yhat", "yhat_lower", "yhat_upper"]:
            if c in out.columns:
                out[c] = out[c] * multiplier
        return out

    @classmethod
    def generate(cls, forecast, hist_std, growth_pct=0.0, ramzan_uplift_pct=0.0, event_uplift_pct=0.0,
                 management_override_pct=0.0, churn_pct=0.0, new_branch_pct=0.0):
        scenarios = {"Base": forecast.copy()}
        mean = forecast["yhat"].mean() if len(forecast) else 0
        factor = hist_std / mean if mean > 0 else 0.1
        scenarios["Optimistic"] = cls._apply_multiplier(forecast, 1.0 + factor + growth_pct / 100.0)
        scenarios["Pessimistic"] = cls._apply_multiplier(forecast, max(0.5, 1.0 - factor + growth_pct / 100.0))

        driver_multiplier = 1.0 + growth_pct / 100.0 + ramzan_uplift_pct / 100.0 + event_uplift_pct / 100.0 + management_override_pct / 100.0 + new_branch_pct / 100.0 - churn_pct / 100.0
        scenarios["Driver_Based"] = cls._apply_multiplier(forecast, max(0.1, driver_multiplier))

        if management_override_pct:
            scenarios["Management_Override"] = cls._apply_multiplier(forecast, 1.0 + management_override_pct / 100.0)
        if ramzan_uplift_pct or event_uplift_pct:
            scenarios["Event_Push"] = cls._apply_multiplier(forecast, 1.0 + ramzan_uplift_pct / 100.0 + event_uplift_pct / 100.0)
        return scenarios


class VarianceAnalyzer:
    @staticmethod
    def decompose_variance(actuals, fitted, budget_data=None):
        merged = actuals[["ds", "y"]].merge(
            fitted[["ds", "yhat"]].rename(columns={"yhat": "forecast"}), on="ds", how="inner"
        ).sort_values("ds")
        merged["total_variance"] = merged["y"] - merged["forecast"]
        merged["volume_variance"] = merged["total_variance"]
        merged["trend_variance"] = merged["forecast"].diff().fillna(0)
        merged["seasonality_variance"] = merged["y"].rolling(3, min_periods=1).mean() - merged["forecast"].rolling(3, min_periods=1).mean()
        merged["event_variance"] = merged["total_variance"] - merged["trend_variance"] - merged["seasonality_variance"]
        if budget_data is not None and len(budget_data) > 0:
            b = budget_data.copy()
            if "budget_amount" in b.columns and "budget" not in b.columns:
                b = b.rename(columns={"budget_amount": "budget"})
            merged = merged.merge(b[["ds", "budget"]], on="ds", how="left")
            merged["budget_variance"] = merged["y"] - merged["budget"]
        return merged

    @classmethod
    def run(cls, actuals, fitted, budget_data=None):
        merged = cls.decompose_variance(actuals, fitted, budget_data)
        merged["fc_var_pct"] = merged["total_variance"] / merged["forecast"].abs().clip(lower=1) * 100
        stats = {
            "fc_mae": float(merged["total_variance"].abs().mean()),
            "fc_mape": float(merged["fc_var_pct"].abs().mean()),
            "trend_var_mean": float(merged["trend_variance"].mean()),
            "seasonality_var_mean": float(merged["seasonality_variance"].mean()),
            "event_var_mean": float(merged["event_variance"].mean()),
        }
        if "budget_variance" in merged.columns:
            stats["bgt_mae"] = float(merged["budget_variance"].abs().mean())
        return merged, stats


class BudgetGenerator:
    @staticmethod
    def generate(forecast, adj_pct=0.0, event_uplift_pct=0.0, management_target_pct=0.0):
        b = forecast[["ds", "yhat"]].copy()
        b.columns = ["ds", "budget"]
        multiplier = 1 + adj_pct / 100 + event_uplift_pct / 100 + management_target_pct / 100
        b["budget"] = b["budget"] * multiplier
        return b
