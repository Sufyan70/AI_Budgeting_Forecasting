import warnings
import logging
import numpy as np
import pandas as pd

from feature_engine import FeatureEngineer

warnings.filterwarnings("ignore")
logging.getLogger("prophet").setLevel(logging.ERROR)
logging.getLogger("cmdstanpy").setLevel(logging.ERROR)


class NaiveModel:
    def __init__(self):
        self.last_value = None
        self.std = 0.0

    def fit(self, df, freq="MS"):
        y = df["y"].values
        self.last_value = float(y[-1]) if len(y) else 0.0
        self.std = float(np.std(y[-min(len(y), 12):])) if len(y) else 0.0
        self.history = df.copy()

    def predict(self, periods, last_date, freq="MS"):
        future = pd.date_range(start=pd.to_datetime(last_date) + pd.tseries.frequencies.to_offset(freq), periods=periods, freq=freq)
        preds = np.repeat(self.last_value, periods)
        return pd.DataFrame({"ds": future, "yhat": preds, "yhat_lower": preds - 1.28 * self.std, "yhat_upper": preds + 1.28 * self.std})

    def fitted_values(self, df):
        vals = pd.Series(df["y"]).shift(1).bfill()
        return pd.DataFrame({"ds": df["ds"].values, "yhat": vals.values})


class ProphetModel:
    def __init__(self, events_df=None):
        self.available = True
        self.events_df = events_df
        try:
            from prophet import Prophet
            self.model = Prophet(
                yearly_seasonality=True,
                weekly_seasonality="auto",
                daily_seasonality=False,
                seasonality_mode="multiplicative",
                changepoint_prior_scale=0.05,
                seasonality_prior_scale=10.0,
                holidays_prior_scale=10.0,
                interval_width=0.80,
            )
            if events_df is not None and len(events_df) > 0:
                self.model.holidays = events_df
        except Exception:
            self.available = False
            self.model = None
            self.fallback = NaiveModel()

    def fit(self, df):
        if not self.available:
            self.fallback.fit(df)
            return
        self.model.fit(df[["ds", "y"]])

    def predict(self, periods, freq="MS"):
        if not self.available:
            return self.fallback.predict(periods, self.fallback.history["ds"].iloc[-1], freq)
        future = self.model.make_future_dataframe(periods=periods, freq=freq)
        fc = self.model.predict(future)
        return fc[["ds", "yhat", "yhat_lower", "yhat_upper"]]

    def fitted_values(self, df):
        if not self.available:
            return self.fallback.fitted_values(df)
        fc = self.model.predict(self.model.history)
        return fc[["ds", "yhat"]].head(len(df))


class SARIMAModel:
    def __init__(self):
        self.model = None
        self.order = None
        self.seasonal_order = None
        self.fallback = None

    def fit(self, df, freq="MS"):
        y = df["y"].values
        try:
            import pmdarima as pm
            smap = {"D": 7, "W": 52, "MS": 12, "M": 12, "QS": 4, "YS": 1}
            m = smap.get(freq, 12)
            use_s = m > 1 and len(y) >= 2 * m
            self.model = pm.auto_arima(
                y, seasonal=use_s, m=m if use_s else 1,
                stepwise=True, suppress_warnings=True, error_action="ignore",
                max_p=3, max_q=3, max_P=2, max_Q=2, max_d=2, max_D=1,
                trace=False, n_fits=30,
            )
            self.order = self.model.order
            self.seasonal_order = getattr(self.model, "seasonal_order", (0, 0, 0, 0))
        except Exception:
            self.fallback = NaiveModel()
            self.fallback.fit(df, freq)
            self.order = (0, 0, 0)
            self.seasonal_order = (0, 0, 0, 0)

    def predict(self, periods, last_date, freq="MS"):
        if self.fallback is not None:
            return self.fallback.predict(periods, last_date, freq)
        fc, ci = self.model.predict(n_periods=periods, return_conf_int=True, alpha=0.2)
        future = pd.date_range(start=last_date + pd.tseries.frequencies.to_offset(freq), periods=periods, freq=freq)
        return pd.DataFrame({"ds": future, "yhat": fc, "yhat_lower": ci[:, 0], "yhat_upper": ci[:, 1]})

    def fitted_values(self, df):
        if self.fallback is not None:
            return self.fallback.fitted_values(df)
        vals = self.model.predict_in_sample()
        n = min(len(vals), len(df))
        return pd.DataFrame({"ds": df["ds"].values[:n], "yhat": vals[:n]})


class LGBMModel:
    def __init__(self, events_df=None):
        self.model = None
        self.cols = None
        self._last_df = None
        self.feature_engineer = FeatureEngineer(events_df=events_df)
        self.fallback = None

    def _features(self, df):
        feat = self.feature_engineer.assemble_features(df)
        self.cols = feat.columns.tolist()
        return feat

    def fit(self, df, freq="MS"):
        feat = self._features(df)
        try:
            from lightgbm import LGBMRegressor
            self.model = LGBMRegressor(
                n_estimators=200, learning_rate=0.05, max_depth=6,
                num_leaves=31, subsample=0.8, verbose=-1, random_state=42,
            )
            mask = ~np.isnan(df["y"].values)
            self.model.fit(feat[mask], df["y"].values[mask])
            self._last_df = df.copy()
        except Exception:
            self.fallback = NaiveModel()
            self.fallback.fit(df, freq)
            self._last_df = df.copy()

    def predict(self, periods, last_date, freq="MS"):
        if self.fallback is not None:
            return self.fallback.predict(periods, last_date, freq)
        future = pd.date_range(start=last_date + pd.tseries.frequencies.to_offset(freq), periods=periods, freq=freq)
        combined = pd.concat([self._last_df[["ds", "y"]], pd.DataFrame({"ds": future, "y": np.nan})], ignore_index=True)
        preds = []
        for i in range(len(self._last_df), len(combined)):
            feat = self._features(combined.iloc[: i + 1].copy())
            p = self.model.predict(feat.iloc[[-1]])[0]
            combined.loc[i, "y"] = p
            preds.append(p)
        preds = np.array(preds)
        std = np.std(self._last_df["y"].values[-12:]) * 0.15 if len(self._last_df) else 0.0
        return pd.DataFrame({"ds": future, "yhat": preds, "yhat_lower": preds - 1.28 * std, "yhat_upper": preds + 1.28 * std})

    def fitted_values(self, df):
        if self.fallback is not None:
            return self.fallback.fitted_values(df)
        feat = self._features(df)
        p = self.model.predict(feat)
        return pd.DataFrame({"ds": df["ds"].values, "yhat": p})


class EnsembleModel:
    def __init__(self, events_df=None, use_lgbm=True):
        self.events_df = events_df
        self.use_lgbm = use_lgbm
        self.models = {}
        self.weights = {}

    def fit(self, df, freq="MS"):
        print("  Prophet...", end=" ", flush=True)
        self.models["prophet"] = ProphetModel(self.events_df)
        self.models["prophet"].fit(df)
        print("ok", flush=True)
        print("  SARIMA...", end=" ", flush=True)
        self.models["sarima"] = SARIMAModel()
        self.models["sarima"].fit(df, freq)
        print(f"ok {self.models['sarima'].order}x{self.models['sarima'].seasonal_order}", flush=True)
        if self.use_lgbm and len(df) >= 24:
            print("  LightGBM...", end=" ", flush=True)
            self.models["lgbm"] = LGBMModel(events_df=self.events_df)
            self.models["lgbm"].fit(df, freq)
            print("ok", flush=True)
        self._calc_weights(df, freq)

    def _calc_weights(self, df, freq):
        if len(df) < 15:
            n = len(self.models)
            self.weights = {k: 1.0 / n for k in self.models}
            return
        split = int(len(df) * 0.8)
        train, test = df.iloc[:split].copy(), df.iloc[split:].copy()
        n_test = len(test)
        errs = {}
        for name in self.models:
            try:
                m = self._clone(name)
                if name == "prophet":
                    m.fit(train)
                    p = m.predict(n_test, freq)
                    last = train["ds"].max()
                    p = p[p["ds"] > last].head(n_test)
                else:
                    m.fit(train, freq)
                    p = m.predict(n_test, train["ds"].iloc[-1], freq)
                pv = p["yhat"].values[:n_test]
                av = test["y"].values[:len(pv)]
                errs[name] = np.mean(np.abs(pv - av))
            except Exception:
                errs[name] = float("inf")
        valid = {k: v for k, v in errs.items() if 0 < v < float("inf")}
        if not valid:
            n = len(self.models)
            self.weights = {k: 1.0 / n for k in self.models}
        else:
            ti = sum(1.0 / v for v in valid.values())
            self.weights = {k: ((1.0 / valid[k]) / ti if k in valid else 0.0) for k in self.models}
        print(f"  Weights: {', '.join(f'{k}={v:.0%}' for k, v in self.weights.items())}")

    def _clone(self, name):
        if name == "prophet":
            return ProphetModel(self.events_df)
        if name == "sarima":
            return SARIMAModel()
        return LGBMModel(events_df=self.events_df)

    def predict(self, periods, last_date, freq="MS"):
        preds = {}
        for name, model in self.models.items():
            if name == "prophet":
                p = model.predict(periods, freq)
                p = p[p["ds"] > pd.to_datetime(last_date)].head(periods).reset_index(drop=True)
            else:
                p = model.predict(periods, last_date, freq)
            preds[name] = p
        ref = list(preds.values())[0]
        out = pd.DataFrame({"ds": ref["ds"].values[:periods]})
        yh = np.zeros(periods)
        yl = np.zeros(periods)
        yu = np.zeros(periods)
        for name, p in preds.items():
            w = self.weights.get(name, 0)
            n = min(periods, len(p))
            yh[:n] += w * p["yhat"].values[:n]
            yl[:n] += w * p["yhat_lower"].values[:n]
            yu[:n] += w * p["yhat_upper"].values[:n]
        out["yhat"] = yh
        out["yhat_lower"] = yl
        out["yhat_upper"] = yu
        return out

    def fitted_values(self, df):
        n = len(df)
        yh = np.zeros(n)
        for name, model in self.models.items():
            w = self.weights.get(name, 0)
            fv = model.fitted_values(df)
            v = fv["yhat"].values[:n]
            yh[:len(v)] += w * v
        return pd.DataFrame({"ds": df["ds"].values, "yhat": yh})
