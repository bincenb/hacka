# HeatSignal NYC

A heat warning for New York City based on when people actually get sick from heat. Built for BioHack 2026, Public Health & Epidemiology stream.

New York issues a heat advisory when the heat index reaches 100°F, or 95°F two days in a row. We checked that rule against ten summers of the city Health Department's daily ER records for heat illness. Most heat ER visits happened on days with no advisory. HeatSignal turns the weather forecast into expected heat ER visits and adds a lower **Heat Watch** level that sends low-cost help to the neighborhoods most at risk.

## Try it

1. Download this repository (green **Code** button, then **Download ZIP**) and unzip it.
2. Double-click `index.html`. It opens in your web browser. No install, no account, no internet needed.
3. Use the planner, replay any summer from 2017 to 2026, and click neighborhoods on the map.

The **Load NWS forecast** button pulls today's National Weather Service forecast, so that one feature needs an internet connection.

To put the app online, go to **Settings → Pages**, choose **Deploy from a branch**, pick `main` and `/ (root)`, and save. GitHub will give you a link to the live page.

## What we found

Data: 1,520 summer days (May to September, 2017 to 2026) and 7,619 heat-related ER visits.

- 56% of heat ER visits happened on days with no heat advisory.
- The advisory missed 61 of the 158 worst days (13 or more heat ER visits). 26 of those were in May or June.
- At the same 91 to 97°F, days before the summer's 5th hot day had 35% more heat ER visits.
- With HeatSignal's Heat Watch added, 131 of the 158 worst days had a warning, compared with 97. That is 83% (95% CI 75 to 91%) against 61% (51 to 74%).
- A warning was in place from the first bad day in 46 of 62 heat episodes, compared with 30.
- The cost is about 8 more alert days a summer.

Every number here and in the app is recomputed from the raw data by `analysis/verify_facts.py`. The results are in [FACTS.md](FACTS.md), along with the source for each outside fact.

## How it works

Each morning, HeatSignal takes the forecast maximum heat index for the next three days. It also uses the number of hot days so far this summer and the latest heat ER count the city has. A Poisson regression turns these into expected heat ER visits, with an 80% range.

There are three levels:

| Level | When | What happens |
|---|---|---|
| No alert | Expected visits below 9.35 a day | Routine summer operations |
| Heat Watch (new) | 9.35 or more expected visits, about 20 days a summer | Calls to older adults living alone, heat-safety texts, a heads-up to hospitals and longer cooling-center hours in the 81 neighborhoods with Heat Vulnerability Index 4 or 5 |
| Heat Advisory (unchanged) | National Weather Service rule | The city's existing heat emergency plan |

We tested it by predicting each summer with a model trained only on the other nine summers.

## What's in this repository

| Path | What it is |
|---|---|
| `index.html` | The app. Everything it needs is inside this one file. |
| `submission/` | One-page proposal (Word and PDF), slide deck (PDF) and fact check (Word) |
| `FACTS.md` | Every number we cite, recomputed, with sources |
| `analysis/` | Python code: load the data, fit and test the model, check the facts, build the app |
| `app/template.html` | Source for the app, before the data is added |
| `data/raw/` | Public data from the NYC Health Department |
| `data/` | Model outputs: test results, predictions, model settings |
| `proposal/build_proposal.py` | Fills the BioHack proposal template |

## Rerun the analysis

You need Python 3.10 or newer.

```bash
pip install -r requirements.txt
python3 analysis/model.py          # fits and tests the model (about 2 minutes)
python3 analysis/build_assets.py   # bundles data and map for the app
python3 analysis/build_page.py     # rebuilds index.html
python3 analysis/verify_facts.py   # should print 50/50 and rewrite FACTS.md
```

## Accessibility

- Works with a keyboard. Press Tab once for a "Skip to the planner" link.
- Every neighborhood on the map can be chosen from a dropdown list.
- The chart has a written summary for screen readers.
- Text and labels meet WCAG AA color contrast in light and dark mode.
- Follows your system's light or dark setting and turns off animation if you've asked for reduced motion.
- Works on phones.
- The PDFs have real text, not pictures of text.

## Limits

- The ER counts are suspected heat illness. They miss people who never reach an ER and heat deaths at home, so harm is undercounted.
- Weather comes from one station (LaGuardia Airport). Street-level heat varies.
- Daily counts are only public for the whole city. Neighborhood targeting uses the Heat Vulnerability Index, not neighborhood ER forecasts.
- A plain lower heat-index cutoff catches almost as many bad days (129 vs. 131). Most of the gain comes from warning at the temperatures where people get sick. The model adds patient estimates, an early-season adjustment and better precision.
- It underestimates the worst early heat waves. On June 25, 2025, it expected 31 heat ER visits and there were 141.
- This is a hackathon prototype, not an official warning system.

## Data and sources

- NYC Department of Health and Mental Hygiene, Environment & Health Data Portal: [nychealth/EHDP-data](https://github.com/nychealth/EHDP-data) (daily heat-related ER visits and heat index at LaGuardia; Heat Vulnerability Index; older adults living alone). Shared by the Health Department under the Apache License 2.0.
- NYC Health Department, [2026 Heat-Related Mortality Report](https://a816-dohbesp.nyc.gov/IndicatorPublic/data-features/heat-report/)
- National Weather Service New York, [heat advisory criteria](https://www.weather.gov/okx/extremeheat)
- Metzger KB, Ito K, Matte TD. Summer heat and mortality in New York City: how hot is too hot? *Environ Health Perspect* 2010. [doi:10.1289/ehp.0900906](https://doi.org/10.1289/ehp.0900906)
- Anderson GB, Bell ML. Heat waves in the United States: mortality risk during heat waves and effect modification by heat wave characteristics in 43 U.S. communities. *Environ Health Perspect* 2011. [doi:10.1289/ehp.1002313](https://doi.org/10.1289/ehp.1002313)
- Mathes RW, Ito K, Lane K, Matte TD. Real-time surveillance of heat-related morbidity. *PLoS One* 2017. [doi:10.1371/journal.pone.0184364](https://doi.org/10.1371/journal.pone.0184364)
- NOAA and CDC, [NWS HeatRisk](https://www.noaa.gov/news-release/noaa-expands-availability-of-new-heat-forecast-tool-ahead-of-summer)
- National Weather Service [API](https://www.weather.gov/documentation/services-web-api) for the live forecast

Tools: Python (pandas, NumPy, scikit-learn), HTML and JavaScript. We used Claude (Anthropic) as a coding and writing assistant.
