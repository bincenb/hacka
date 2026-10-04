"""Independent fact check for every number HeatSignal NYC states.

Recomputes the data claims straight from the raw Health Department files with plain pandas
(no shared code with model.py), checks the model claims against data/results.json, and
lists the outside facts with their sources. Writes FACTS.md. Exits non-zero if any check fails.
"""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
R = json.loads((ROOT / "data" / "results.json").read_text())
EHDP = "NYC DOHMH Environment & Health Data Portal, github.com/nychealth/EHDP-data"

checks = []


def claim(text, stated, computed, source, tol=0.0):
    ok = (abs(stated - computed) <= tol) if isinstance(stated, (int, float)) else stated == computed
    checks.append({"claim": text, "stated": stated, "computed": computed, "source": source, "ok": ok})


# ---------- raw data, recomputed from scratch ----------
def read(name):
    t = pd.read_csv(RAW / name)
    t.columns = [c.strip('"') for c in t.columns]
    t["date"] = pd.to_datetime(t.END_DATE, format="mixed")
    return t[["date", "HEAT_ED_VISIT_COUNT", "MAX_DAILY_TEMP"]].set_axis(["date", "v", "hi"], axis=1)


ed = pd.concat([read("previous_years.csv"), read("edheat2026_live.csv")]).drop_duplicates("date").sort_values("date").reset_index(drop=True)
ed["y"] = ed.date.dt.year
src_ed = f"{EHDP}, key-topics/heat-syndrome (daily heat-related ED visits; max heat index at LaGuardia)"

claim("Days in the data (May-Sep 2017-2026)", 1520, len(ed), src_ed)
claim("Summers in the data", 10, ed.y.nunique(), src_ed)
claim("Heat-related ER visits, 2017-2026", 7619, int(ed.v.sum()), src_ed)

# NWS rule, written independently: HI >= 100 any day, or >= 95 on 2+ consecutive days
flag = pd.Series(False, index=ed.index)
for _, s in ed.groupby("y"):
    h = s.hi.tolist()
    for k, ix in enumerate(s.index):
        two = h[k] >= 95 and ((k > 0 and h[k - 1] >= 95) or (k + 1 < len(h) and h[k + 1] >= 95))
        flag[ix] = h[k] >= 100 or two
claim("Days meeting the NWS advisory rule", 118, int(flag.sum()), src_ed)
claim("Share of heat ER visits on days without an advisory (%)", 56,
      round(100 * ed.v[~flag].sum() / ed.v.sum()), src_ed)
hb = ed.v >= ed.v.quantile(0.9)
claim("High-burden cutoff (top 10% of days), visits", 13, int(ed.v.quantile(0.9)), src_ed)
claim("High-burden days", 158, int(hb.sum()), src_ed)
claim("High-burden days the advisory rule covers", 97, int((hb & flag).sum()), src_ed)
claim("High-burden days with no advisory", 61, int((hb & ~flag).sum()), src_ed)
claim("Missed high-burden days that fell in May or June", 26, int((hb & ~flag & ed.date.dt.month.isin([5, 6])).sum()), src_ed)

prior = ed.groupby("y").hi.transform(lambda s: (s >= 90).astype(int).cumsum().shift(1).fillna(0))
mid = ed[ed.hi.between(91, 97)]
early, late = mid[prior[mid.index] < 5].v.mean(), mid[prior[mid.index] >= 5].v.mean()
claim("Mean heat ER visits at 91-97F before the summer's 5th 90F+ day", 15.3, round(early, 1), src_ed)
claim("Mean heat ER visits at 91-97F later in summer", 11.3, round(late, 1), src_ed)
claim("Early-season excess at the same heat (%)", 35, round(100 * (early / late - 1)), src_ed)

by = ed.groupby("y").v.sum()
claim("2026 heat ER visits", 1122, int(by[2026]), src_ed)
claim("2026 has the most heat ER visits of any summer 2017-2026", 2026, int(by.idxmax()), src_ed)
claim("2026 high-burden days", 20, int(hb[ed.y == 2026].sum()), src_ed)
claim("2026 high-burden days covered by the advisory rule", 13, int((hb & flag)[ed.y == 2026].sum()), src_ed)
day = ed.set_index("date")
claim("Heat ER visits on June 25, 2025 (news reports cite 141, the most since 2017)", 141,
      int(day.v["2025-06-25"]), src_ed + "; City Limits / The City, June 2026")
claim("Max heat index at LaGuardia, June 24, 2025 (Health Dept. report cites 103F peak; file shows the daily value)",
      100, int(day.hi["2025-06-24"]), src_ed)
claim("Heat ER visits June 30 / July 1 / July 2, 2026", "17/47/104",
      "/".join(str(int(day.v[x])) for x in ("2026-06-30", "2026-07-01", "2026-07-02")), src_ed)
claim("Heat ER visits June 19 / 20 / 21, 2024", "14/22/51",
      "/".join(str(int(day.v[x])) for x in ("2024-06-19", "2024-06-20", "2024-06-21")), src_ed)
claim("Single worst day: July 3, 2026", 156, int(ed.v.max()), src_ed)

hvi = pd.read_csv(RAW / "hvi-nta-2020.csv")
src_hvi = f"{EHDP}, key-topics/heat-vulnerability-index/hvi-nta-2020.csv"
claim("Neighborhoods (2020 NTAs) with an HVI score", 198, len(hvi), src_hvi)
claim("Neighborhoods with HVI 4 or 5", 81, int((hvi.HVI_RANK >= 4).sum()), src_hvi)
claim("Lowest AC coverage among HVI-5 neighborhoods (%)", 75.8, round(hvi[hvi.HVI_RANK == 5].PCT_HOUSEHOLDS_AC.min(), 1), src_hvi)
claim("Neighborhoods sharing that lowest AC figure (Claremont Village, Morrisania, Tremont, West Farms, Crotona Park East)", 5,
      int((hvi[hvi.HVI_RANK == 5].PCT_HOUSEHOLDS_AC.round(1) == 75.8).sum()), src_hvi)

# ---------- model claims, from the cross-validated run ----------
src_m = "analysis/model.py, leave-one-summer-out cross-validation (data/results.json)"
hs, nws, hio = R["heatsignal_watch_or_advisory"], R["nws_advisory"], R["heat_index_threshold_same_budget"]
claim("HeatSignal (Watch + Advisory) alert days", 200, hs["alert_days"], src_m)
claim("High-burden days warned with HeatSignal", 131, hs["high_burden_caught"], src_m)
claim("HeatSignal catch rate (%)", 83, round(100 * hs["sensitivity"]), src_m)
claim("Share of heat ER visits on HeatSignal-warned days (%)", 58, round(100 * hs["share_of_visits_on_alert_days"]), src_m)
claim("Share of heat ER visits on advisory days (%)", 44, round(100 * nws["share_of_visits_on_alert_days"]), src_m)
claim("Plain heat-index cutoff with a similar budget: bad days caught", 129, hio["high_burden_caught"], src_m)
claim("HeatSignal precision (%)", 66, round(100 * hs["precision"]), src_m)
claim("Advisory precision (%)", 82, round(100 * nws["precision"]), src_m)
claim("Heat-index cutoff precision (%)", 61, round(100 * hio["precision"]), src_m)
claim("Catch rate with +/-2.5F forecast error (%)", 82,
      round(100 * R["watch_or_advisory_sensitivity_with_2.5F_forecast_error"]["mean"]), src_m)
claim("Spearman correlation, forecast vs observed", 0.75, round(R["spearman_pred_vs_observed"], 2), src_m)
claim("2026 bad days warned with HeatSignal", 18, next(b for b in R["by_year"] if b["year"] == 2026)["heatsignal_caught"], src_m)
claim("Extra Watch days in 2026", 7, next(b for b in R["by_year"] if b["year"] == 2026)["watch_days"], src_m)
claim("Alert days per summer with HeatSignal (about)", 20, hs["alert_days"] / R["n_summers"], src_m)
claim("Extra alert days per summer vs. the advisory (about)", 8, round((hs["alert_days"] - nws["alert_days"]) / R["n_summers"]), src_m)
claim("Largest gap between mean forecast and mean actual in any range below 50 visits", 1.1,
      max(abs(c["mean_predicted"] - c["mean_observed"]) for c in R["calibration"] if c["mean_predicted"] < 50), src_m, tol=0.05)
claim("June 25, 2025: visits expected by the held-out model", 31,
      round(float(pd.read_csv(ROOT / "data" / "cv_predictions.csv").set_index("date").pred["2025-06-25"])), src_m)
ep = R["episodes"]
claim("Heat-illness episodes (runs of high-burden days)", 62, ep["n_episodes"], src_m)
claim("Episodes with the advisory in place from day one", 30, ep["nws_warned_from_day_one"], src_m)
claim("Episodes with HeatSignal in place from day one", 46, ep["hs_warned_from_day_one"], src_m)
claim("More heat ER visits that fell on warned days over 10 summers (approx.)", 1000, R["visits_on_warned_days_gain"], src_m, tol=20)
ci = R["bootstrap_95ci_sensitivity"]
claim("95% intervals for advisory and HeatSignal catch rates do not overlap", True, ci["nws"][1] < ci["heatsignal"][0], src_m)
claim("95% interval, catch-rate gain over the advisory (points)", "16 to 26",
      f"{round(100 * ci['difference'][0])} to {round(100 * ci['difference'][1])}", src_m + ", summer-level bootstrap")
claim("Watch trigger, expected visits per day", 9.35,
      json.loads((ROOT / "data" / "model.json").read_text())["watch_threshold"], "data/model.json", tol=0.005)

# ---------- outside facts (checked against the cited source; not recomputable here) ----------
EXTERNAL = [
    ("NWS NYC Heat Advisory: heat index 95-99F for 2+ consecutive days, or 100-104F for any length of time",
     "NWS New York, NY Extreme Heat page, weather.gov/okx/extremeheat; NYC Emergency Management Heat Emergency and Cooling Center Plan (2026)"),
    ("About 500 New Yorkers die prematurely from hot weather each summer (avg ~7 heat-stress + ~490 heat-exacerbated deaths)",
     "NYC DOHMH, 2026 Heat-Related Mortality Report, a816-dohbesp.nyc.gov/IndicatorPublic/data-features/heat-report/"),
    ("Extreme heat is NYC's deadliest weather hazard", "NYC Emergency Management, Be Ready New York; NYC DOHMH Hot Weather and Your Health"),
    ("Black New Yorkers die of heat stress at about twice the rate of white New Yorkers; lack of home AC is the most important risk factor; most heat-stress deaths were exposures in homes",
     "NYC DOHMH Heat-Related Mortality Reports (2025, 2026)"),
    ("June 22-25, 2025 heat wave: 19 heat-stress deaths; 141 heat ER visits on June 25",
     "NYC DOHMH 2026 Heat-Related Mortality Report; City Limits and The City coverage (June 2026)"),
    ("HVI combines surface temperature, green space, home AC, median income and percent of Black residents",
     "NYC DOHMH Heat Vulnerability Index (EHDP); hvi-nta-2020.csv fields"),
    ("Syndromic surveillance captures 100% of NYC ED visits (since 5/1/2016); counts are suspected, not confirmed, heat illness",
     f"{EHDP}, key-topics/heat-syndrome/README.md"),
    ("Daily heat ER visits are associated with excess non-external-cause deaths in NYC",
     "Mathes RW et al. PLoS One 2017;12(9):e0184364. doi:10.1371/journal.pone.0184364"),
    ("NYC's 95-100F alert range comes from a Health Department study of 1997-2006 deaths that recommended periodic re-analysis with recent data",
     "Metzger KB, Ito K, Matte TD. Environ Health Perspect 2010;118(1):80-86. doi:10.1289/ehp.0900906"),
    ("The first heat wave of summer raises mortality about twice as much as later ones (5.04% vs 2.65%, 43 US cities)",
     "Anderson GB, Bell ML. Environ Health Perspect 2011;119(2):210-218. doi:10.1289/ehp.1002313"),
    ("NWS HeatRisk (with CDC) rates heat 0-4 from local climatology, time of year and duration; it is not calibrated to a city's own ER visits",
     "NOAA news release 'NOAA expands availability of new heat forecast tool' (2024); CDC press release Apr 22, 2024"),
    ("Con Edison pauses residential shutoffs when the heat index is forecast to reach 90F+ (a sub-advisory trigger already in use)",
     "Con Edison, Special Protections During Cold or Hot Weather, coned.com"),
    ("Be a Buddy: Health Department program matching volunteers with at-risk neighbors in heat-vulnerable neighborhoods (Hunts Point, Brownsville, East Harlem pilots)",
     "NY1 (Mar 25, 2022); The POINT CDC Be A Buddy program page"),
    ("Heat emergencies trigger cooling centers and Notify NYC alerts", "NYC Emergency Management Heat Emergency and Cooling Center Plan (2026)"),
    ("About 85% of US emergency departments send data to CDC's National Syndromic Surveillance Program",
     "CDC, About NSSP, cdc.gov/nssp/php/about"),
    ("The city activated its Heat Emergency Plan on Monday, June 29, 2026, before the July 1-4 heat wave",
     "NYC Mayor's Office press release, July 2026 ('Mayor Mamdani Expands Emergency Heat Measures...')"),
]

fails = [c for c in checks if not c["ok"]]
lines = ["# HeatSignal NYC: fact check", "",
         "Generated by `analysis/verify_facts.py`. Data claims are recomputed from the raw Health Department files; "
         "model claims are read from the cross-validated run; outside facts list the source each was checked against.", "",
         f"**{len(checks) - len(fails)} of {len(checks)} computed claims match.**", "",
         "## Numbers recomputed from data", "", "| Claim | Stated | Recomputed | Source | OK |", "|---|---|---|---|---|"]
for c in checks:
    lines.append(f"| {c['claim']} | {c['stated']} | {c['computed']} | {c['source']} | {'yes' if c['ok'] else '**NO**'} |")
lines += ["", "## Outside facts and their sources", "", "| Fact | Source |", "|---|---|"]
lines += [f"| {f} | {s} |" for f, s in EXTERNAL]
lines += ["", "## Corrections made after checking", "",
          "- Neighborhood count corrected from 197 to 198 (the HVI file has 198 scored 2020 NTAs).",
          "- The Watch trigger is stated as 9.35 expected visits a day; an earlier \"9.4\" was a rounding that the fact check flagged.",
          "- The Heat Vulnerability Index also includes the percent of Black residents. Earlier copy listed only heat, green space, AC and income.",
          "- \"Worst summer on record\" became \"most heat ER visits of 2017 to 2026\": the data start in 2017.",
          "- \"Pause utility shutoffs\" was listed as an advisory-day action. Con Edison already pauses them at a forecast heat index of 90F, below the advisory, so it is now cited as evidence that sub-advisory triggers already exist.",
          "- The planner's historical examples now use a model trained without that summer, so the demo is out-of-sample.",
          "- The \"alert cutoff rests on 1997-2006 deaths\" wording was softened to what Metzger 2010 supports: the 95-100F range matches that study."]
(ROOT / "FACTS.md").write_text("\n".join(lines) + "\n")
for c in fails:
    print("MISMATCH:", c)
print(f"{len(checks) - len(fails)}/{len(checks)} claims verified; wrote FACTS.md")
sys.exit(1 if fails else 0)
