from __future__ import annotations

import pandas as pd


class EventCalendar:
    """Auto event generator for Pakistan-focused business seasonality.

    Ramzan/Eid values are an approximate built-in lookup for 2021-2030 so the
    framework remains runnable without external APIs. These dates should be
    replaced by an authoritative calendar in production.
    """

    RAMZAN_START = {
        2021: "2021-04-14", 2022: "2022-04-03", 2023: "2023-03-23",
        2024: "2024-03-11", 2025: "2025-03-01", 2026: "2026-02-18",
        2027: "2027-02-08", 2028: "2028-01-28", 2029: "2029-01-16",
        2030: "2030-01-06",
    }
    EID_FITR = {
        2021: "2021-05-13", 2022: "2022-05-02", 2023: "2023-04-21",
        2024: "2024-04-10", 2025: "2025-03-31", 2026: "2026-03-20",
        2027: "2027-03-10", 2028: "2028-02-27", 2029: "2029-02-15",
        2030: "2030-02-05",
    }
    EID_ADHA = {
        2021: "2021-07-21", 2022: "2022-07-10", 2023: "2023-06-29",
        2024: "2024-06-17", 2025: "2025-06-07", 2026: "2026-05-27",
        2027: "2027-05-17", 2028: "2028-05-05", 2029: "2029-04-24",
        2030: "2030-04-13",
    }

    @staticmethod
    def _years(years=None, start_year=None, end_year=None):
        if years:
            return sorted(set(int(y) for y in years))
        if start_year is None or end_year is None:
            raise ValueError("Provide years or start_year/end_year")
        return list(range(int(start_year), int(end_year) + 1))

    @classmethod
    def load_ramzan_calendar(cls, years=None, start_year=None, end_year=None, lower_window=0, upper_window=0):
        rows = []
        for year in cls._years(years, start_year, end_year):
            start = cls.RAMZAN_START.get(year)
            if not start:
                continue
            for d in pd.date_range(pd.to_datetime(start), periods=30, freq="D"):
                rows.append({
                    "holiday": "ramzan",
                    "ds": d,
                    "lower_window": lower_window,
                    "upper_window": upper_window,
                })
        return pd.DataFrame(rows)

    @classmethod
    def load_standard_events(cls, years=None, start_year=None, end_year=None, country="PK"):
        rows = []
        for year in cls._years(years, start_year, end_year):
            fitr = cls.EID_FITR.get(year)
            adha = cls.EID_ADHA.get(year)
            if fitr:
                rows.append({"holiday": "eid_fitr", "ds": pd.to_datetime(fitr), "lower_window": -3, "upper_window": 2})
            if adha:
                rows.append({"holiday": "eid_adha", "ds": pd.to_datetime(adha), "lower_window": -3, "upper_window": 2})
            if country.upper() == "PK":
                rows.append({"holiday": "new_year", "ds": pd.Timestamp(year, 1, 1), "lower_window": 0, "upper_window": 0})
                rows.append({"holiday": "year_end", "ds": pd.Timestamp(year, 12, 31), "lower_window": -2, "upper_window": 0})
        return pd.DataFrame(rows)

    @classmethod
    def build_event_calendar(cls, start_date, end_date, country="PK", include_ramzan=True, include_eid=True, custom_events=None):
        years = list(range(pd.to_datetime(start_date).year, pd.to_datetime(end_date).year + 1))
        frames = []
        if include_ramzan:
            frames.append(cls.load_ramzan_calendar(years=years))
        if include_eid:
            frames.append(cls.load_standard_events(years=years, country=country))
        if custom_events:
            frames.append(pd.DataFrame(custom_events))
        frames = [f for f in frames if f is not None and len(f) > 0]
        if not frames:
            return pd.DataFrame(columns=["holiday", "ds", "lower_window", "upper_window"])
        cal = pd.concat(frames, ignore_index=True)
        cal["ds"] = pd.to_datetime(cal["ds"])
        cal = cal[(cal["ds"] >= pd.to_datetime(start_date)) & (cal["ds"] <= pd.to_datetime(end_date))].copy()
        return cal.sort_values(["holiday", "ds"]).reset_index(drop=True)
