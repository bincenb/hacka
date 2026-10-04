"""Load NYC Health Department daily heat-illness ED visits (May-Sep, 2017-2026)."""
import pandas as pd
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "raw"


def _read(name):
    d = pd.read_csv(DATA / name)
    d.columns = [c.strip('"') for c in d.columns]
    d["date"] = pd.to_datetime(d["END_DATE"], format="mixed")
    return d[["date", "HEAT_ED_VISIT_COUNT", "MAX_DAILY_TEMP"]].rename(
        columns={"HEAT_ED_VISIT_COUNT": "visits", "MAX_DAILY_TEMP": "hi"})


def load():
    # previous_years.csv uses the revised 2023 case definition for 2017-2025;
    # 2026 comes from the live file, which uses the same definition.
    d = pd.concat([_read("previous_years.csv"), _read("edheat2026_live.csv")])
    d = d.drop_duplicates("date").sort_values("date").reset_index(drop=True)
    d["year"] = d.date.dt.year
    return d


def add_features(d):
    d = d.copy()
    g = d.groupby("year")
    d["hi_lag1"] = g.hi.shift(1)
    d["hi_lag2"] = g.hi.shift(2)
    # consecutive days at or above 90F ending today
    hot = (d.hi >= 90).astype(int)
    run = []
    for y, s in hot.groupby(d.year):
        r, out = 0, []
        for v in s:
            r = r + 1 if v else 0
            out.append(r)
        run += out
    d["hot_run"] = run
    # acclimatization: how many 90F+ days the city has already had this season (before today)
    d["prior_hot_days"] = g.hi.transform(lambda s: (s >= 90).astype(int).cumsum().shift(1).fillna(0))
    d["doy"] = d.date.dt.dayofyear
    d["dow"] = d.date.dt.dayofweek
    d["weekend"] = (d.dow >= 5).astype(int)
    return d


def nws_advisory(d):
    """NWS New York City heat advisory criteria applied to the daily max heat index:
    heat index >= 100F on any day, or >= 95F on two or more consecutive days."""
    flags = []
    for y, s in d.groupby("year"):
        hi = s.hi.values
        f = []
        for i, v in enumerate(hi):
            prev = hi[i - 1] if i > 0 else -1
            nxt = hi[i + 1] if i + 1 < len(hi) else -1
            f.append(v >= 100 or (v >= 95 and (prev >= 95 or nxt >= 95)))
        flags += f
    return pd.Series(flags, index=d.index)
