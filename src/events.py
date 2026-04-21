import pandas as pd
from event_calendar import EventCalendar


class EventManager:

    def __init__(self):
        self.events = []

    def add(self, name, dates, lower_window=0, upper_window=0):
        for d in dates:
            self.events.append({
                "holiday": name,
                "ds": pd.to_datetime(d),
                "lower_window": lower_window,
                "upper_window": upper_window,
            })

    def add_recurring(self, name, month, day, years, lower_window=0, upper_window=0):
        for yr in years:
            try:
                self.events.append({
                    "holiday": name,
                    "ds": pd.Timestamp(yr, month, day),
                    "lower_window": lower_window,
                    "upper_window": upper_window,
                })
            except Exception:
                pass

    def add_range(self, name, start, end):
        for d in pd.date_range(start, end):
            self.events.append({
                "holiday": name,
                "ds": d,
                "lower_window": 0,
                "upper_window": 0,
            })

    def load_auto_calendar(self, start_date, end_date, country="PK", include_ramzan=True, include_eid=True, custom_events=None):
        cal = EventCalendar.build_event_calendar(
            start_date=start_date,
            end_date=end_date,
            country=country,
            include_ramzan=include_ramzan,
            include_eid=include_eid,
            custom_events=custom_events,
        )
        if cal is not None and len(cal) > 0:
            self.events.extend(cal.to_dict("records"))
        return cal

    def get_dataframe(self):
        if not self.events:
            return None
        out = pd.DataFrame(self.events).drop_duplicates().sort_values(["holiday", "ds"]).reset_index(drop=True)
        return out

    def count(self):
        return len(self.events)

    def summary(self):
        if not self.events:
            print("  No events added.")
            return
        edf = pd.DataFrame(self.events)
        for name, grp in edf.groupby("holiday"):
            print(f"  {name}: {len(grp)} entries ({grp['ds'].min().strftime('%Y-%m-%d')} to {grp['ds'].max().strftime('%Y-%m-%d')})")

    def tag_events(self, df):
        events_df = self.get_dataframe()
        if events_df is None or len(events_df) == 0:
            out = df.copy()
            out["event_name"] = None
            return out
        out = df.merge(events_df[["holiday", "ds"]].rename(columns={"holiday": "event_name"}), on="ds", how="left")
        return out
