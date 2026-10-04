"""HeatSignal NYC: a health-based heat warning, tested on 10 summers of real ER data.

Data: NYC Health Department syndromic surveillance, daily heat-related emergency
department visits and the daily max heat index at LaGuardia, May-September 2017-2026.

Question: the city's heat advisory follows the National Weather Service rule
(heat index >= 100F, or >= 95F two days running). How many heat ER visits happen on
days with no advisory, and would a lower, health-calibrated "Heat Watch" tier catch them?

Method: Poisson regression of daily visits on the heat index (hinge terms at 85/90/95F),
yesterday's heat, consecutive hot days, early-season heat (before the city's 5th day
at 90F+), weekend, and the visit count two days earlier (the latest count the Health
Department has when it issues a warning the day before). Tested by leave-one-summer-out
cross-validation: each summer is predicted by a model that never saw it.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import PoissonRegressor

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load import add_features, load, nws_advisory

OUT = Path(__file__).resolve().parent.parent / "data"
WATCH_BUDGET = 0.13      # Heat Watch on ~13% of summer days, about 20 days a summer
HIGH_BURDEN_Q = 0.90     # high-burden day: top 10% of summer days by heat ER visits
FEATURES = ["hi", "hi_over_85", "hi_over_90", "hi_over_95", "lag1_over_85",
            "hot_run", "early_x_heat", "weekend", "log_visits_lag2"]


def prepare():
    d = add_features(load())
    d["visits_lag2"] = d.groupby("year").visits.shift(2).fillna(0)
    d["early"] = d.prior_hot_days < 5
    d["nws"] = nws_advisory(d)
    return d


def design(d):
    hi = d.hi
    X = pd.DataFrame({
        "hi": hi,
        "hi_over_85": np.clip(hi - 85, 0, None),
        "hi_over_90": np.clip(hi - 90, 0, None),
        "hi_over_95": np.clip(hi - 95, 0, None),
        "lag1_over_85": np.clip(d.hi_lag1.fillna(hi) - 85, 0, None),
        "hot_run": np.minimum(d.hot_run, 5),
        "early_x_heat": d.early * np.clip(hi - 85, 0, None),
        "weekend": d.weekend,
        "log_visits_lag2": np.log1p(d.visits_lag2),
    }, index=d.index)
    return X[FEATURES]


def fit(train):
    X = design(train)
    mu, sd = X.mean(), X.std().replace(0, 1)
    m = PoissonRegressor(alpha=1e-3, max_iter=5000).fit((X - mu) / sd, train.visits)
    return m, mu, sd


def predict(model, d):
    m, mu, sd = model
    return m.predict((design(d) - mu) / sd)


def cross_validate(d, hi_noise_sd=0.0, seed=0):
    rng = np.random.default_rng(seed)
    pred = pd.Series(np.nan, index=d.index)
    watch = pd.Series(False, index=d.index)
    hi_only = pd.Series(False, index=d.index)
    for y in sorted(d.year.unique()):
        tr, te = d[d.year != y], d[d.year == y].copy()
        model = fit(tr)
        if hi_noise_sd:  # day-ahead forecasts miss the max heat index by a few degrees
            te["hi"] = np.round(te.hi + rng.normal(0, hi_noise_sd, len(te)))
            keep = te[["date", "visits", "hi", "year", "visits_lag2"]]
            te = add_features(keep)
            te["early"] = te.prior_hot_days < 5
        p = predict(model, te)
        pred[te.index] = p
        tau = np.quantile(predict(model, tr), 1 - WATCH_BUDGET)  # threshold set on training summers only
        watch[te.index] = p >= tau
        hi_only[te.index] = te.hi.values >= np.quantile(tr.hi, 1 - WATCH_BUDGET)
    return pred, watch, hi_only


def score(d, flag, hb):
    tot = d.visits.sum()
    return {
        "alert_days": int(flag.sum()),
        "high_burden_caught": int((flag & hb).sum()),
        "high_burden_total": int(hb.sum()),
        "sensitivity": round(float((flag & hb).sum() / hb.sum()), 3),
        "precision": round(float((flag & hb).sum() / max(1, flag.sum())), 3),
        "share_of_visits_on_alert_days": round(float(d.loc[flag, "visits"].sum() / tot), 3),
        "early_season_high_burden_caught": int((flag & hb & d.early).sum()),
        "early_season_high_burden_total": int((hb & d.early).sum()),
    }


def episodes(d):
    """Runs of consecutive high-burden days. A system 'warns from day one' if it flags a day
    on or before the episode's first day (looking back up to 3 days)."""
    rows = []
    for _, s in d.groupby("year"):
        s = s.reset_index(drop=True)
        i = 0
        while i < len(s):
            if not s.hb[i]:
                i += 1
                continue
            j = i
            while j + 1 < len(s) and s.hb[j + 1]:
                j += 1
            win = s.iloc[max(0, i - 3):j + 1]
            start = s.date[i]
            first = lambda f: win[f].date.min()
            rows.append({"start": start, "days": j - i + 1, "visits": int(s.visits[i:j + 1].sum()),
                         "nws_first": first(win.nws), "hs_first": first(win.nws | win.watch)})
            i = j + 1
    e = pd.DataFrame(rows)
    out = {"n_episodes": len(e)}
    for k in ("nws", "hs"):
        warned = e[f"{k}_first"].notna()
        day_one = warned & (e[f"{k}_first"] <= e.start)
        out[f"{k}_warned_at_all"] = int(warned.sum())
        out[f"{k}_warned_from_day_one"] = int(day_one.sum())
        out[f"{k}_visits_in_day_one_episodes"] = int(e.loc[day_one, "visits"].sum())
    out["hs_earlier_than_nws"] = int(((e.hs_first < e.nws_first) | (e.hs_first.notna() & e.nws_first.isna())).sum())
    out["total_episode_visits"] = int(e.visits.sum())
    return out


def bootstrap(d, hb, n=2000, seed=1):
    """Resample whole summers with replacement: a 95% interval for each rule's catch rate."""
    rng = np.random.default_rng(seed)
    years = d.year.unique()
    flags = {"nws": d.nws, "heatsignal": d.nws | d.watch}
    stats = {k: [] for k in flags}
    stats["difference"] = []
    for _ in range(n):
        ys = rng.choice(years, len(years), replace=True)
        idx = np.concatenate([d.index[d.year == y] for y in ys])
        h = hb[idx].values
        sens = {k: f[idx].values[h].mean() for k, f in flags.items()}
        for k in flags:
            stats[k].append(sens[k])
        stats["difference"].append(sens["heatsignal"] - sens["nws"])
    return {k: [round(float(np.quantile(v, 0.025)), 3), round(float(np.quantile(v, 0.975)), 3)] for k, v in stats.items()}


def calibration(d):
    bins = [0, 2, 5, 10, 20, 50, 1000]
    g = d.groupby(pd.cut(d.pred, bins, right=False), observed=True)
    return [{"predicted_range": f"{int(iv.left)}-{int(iv.right) if iv.right < 1000 else '+'}",
             "days": int(len(s)), "mean_predicted": round(float(s.pred.mean()), 1),
             "mean_observed": round(float(s.visits.mean()), 1)} for iv, s in g]


def interval_ratios(d):
    """80% range for a forecast: empirical 10th/90th percentile of observed/predicted, by forecast size."""
    out = []
    for lo, hi in ((0, 3), (3, 10), (10, 1e9)):
        s = d[(d.pred >= lo) & (d.pred < hi)]
        r = (s.visits / s.pred)
        out.append({"from": lo, "to": None if hi > 1e8 else hi,
                    "low": round(float(r.quantile(0.10)), 2), "high": round(float(r.quantile(0.90)), 2),
                    "coverage_check": round(float(((s.visits >= s.pred * r.quantile(0.10)) & (s.visits <= s.pred * r.quantile(0.90))).mean()), 2)})
    return out


def main():
    d = prepare()
    hb = d.visits >= d.visits.quantile(HIGH_BURDEN_Q)
    pred, watch, hi_only = cross_validate(d)
    d["pred"], d["watch"], d["hb"] = pred.round(2), watch, hb

    any_alert = d.nws | d.watch
    res = {
        "n_days": len(d), "n_summers": int(d.year.nunique()), "total_visits": int(d.visits.sum()),
        "high_burden_threshold_visits": int(d.visits.quantile(HIGH_BURDEN_Q)),
        "visits_on_days_without_nws_advisory": round(float(d.loc[~d.nws, "visits"].sum() / d.visits.sum()), 3),
        "nws_advisory": score(d, d.nws, hb),
        "heatsignal_watch_or_advisory": score(d, any_alert, hb),
        "heatsignal_watch_alone": score(d, d.watch, hb),
        "heat_index_threshold_same_budget": score(d, hi_only, hb),
        "spearman_pred_vs_observed": round(float(d.pred.corr(d.visits, method="spearman")), 3),
        "mae_visits_per_day": round(float((d.pred - d.visits).abs().mean()), 2),
        "mean_visits_hi_91_97": {
            ("before 5th hot day" if k else "later in summer"): round(float(v), 1)
            for k, v in d[d.hi.between(91, 97)].groupby("early").visits.mean().items()},
    }
    sens = [score(d, d.nws | cross_validate(d, 2.5, s)[1], hb)["sensitivity"] for s in range(20)]
    res["watch_or_advisory_sensitivity_with_2.5F_forecast_error"] = {
        "mean": round(float(np.mean(sens)), 3), "min": round(min(sens), 3), "max": round(max(sens), 3)}

    by_year = []
    for y, s in d.groupby("year"):
        h = s.hb
        by_year.append({"year": int(y), "visits": int(s.visits.sum()), "high_burden_days": int(h.sum()),
                        "nws_caught": int((s.nws & h).sum()), "heatsignal_caught": int(((s.nws | s.watch) & h).sum()),
                        "nws_days": int(s.nws.sum()), "watch_days": int((s.watch & ~s.nws).sum())})
    res["by_year"] = by_year

    res["episodes"] = episodes(d)
    res["bootstrap_95ci_sensitivity"] = bootstrap(d, hb)
    res["calibration"] = calibration(d)
    res["interval_ratios_80pct"] = interval_ratios(d)
    res["visits_on_warned_days_gain"] = int(d.loc[any_alert, "visits"].sum() - d.loc[d.nws, "visits"].sum())

    print(json.dumps(res, indent=2))
    (OUT / "results.json").write_text(json.dumps(res, indent=2))
    d.to_csv(OUT / "cv_predictions.csv", index=False)

    # final model on all 10 summers, exported for the browser prototype
    final = fit(d)
    m, mu, sd = final
    p_all = predict(final, d)
    holdout = {}
    for y in (2024, 2025, 2026):
        hm, hmu, hsd = fit(d[d.year != y])
        holdout[str(y)] = {"intercept": float(hm.intercept_), "coef": [float(c) for c in hm.coef_],
                           "mu": [float(x) for x in hmu], "sd": [float(x) for x in hsd],
                           "watch_threshold": round(float(np.quantile(predict((hm, hmu, hsd), d[d.year != y]), 1 - WATCH_BUDGET)), 2)}
    (OUT / "model.json").write_text(json.dumps({
        "holdout": holdout, "interval_ratios": res["interval_ratios_80pct"],
        "features": FEATURES, "intercept": float(m.intercept_), "coef": [float(c) for c in m.coef_],
        "mu": [float(x) for x in mu], "sd": [float(x) for x in sd],
        "watch_threshold": round(float(np.quantile(p_all, 1 - WATCH_BUDGET)), 2),
        "high_burden_threshold": int(d.visits.quantile(HIGH_BURDEN_Q)),
    }, indent=2))


if __name__ == "__main__":
    main()
