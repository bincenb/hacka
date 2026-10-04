"""Bundle model outputs, ER history and neighborhood map into one JSON for the prototype."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"


def topo_to_paths(topo, size=600):
    t = topo["transform"]
    sx, sy = t["scale"]; tx, ty = t["translate"]
    arcs = []
    for arc in topo["arcs"]:
        x = y = 0; pts = []
        for dx, dy in arc:
            x += dx; y += dy
            pts.append((x * sx + tx, y * sy + ty))
        arcs.append(pts)

    def ring(idx):
        out = []
        for i in idx:
            a = arcs[i] if i >= 0 else arcs[~i][::-1]
            out.extend(a if not out else a[1:])
        return out

    geoms = list(topo["objects"].values())[0]["geometries"]
    polys = []
    for g in geoms:
        if g["type"] == "Polygon":
            rings = [ring(r) for r in g["arcs"]]
        elif g["type"] == "MultiPolygon":
            rings = [ring(r) for p in g["arcs"] for r in p]
        else:
            continue
        polys.append((g["properties"], rings))

    allpts = np.array([p for _, rs in polys for r in rs for p in r])
    k = np.cos(np.radians(40.7))
    xs = allpts[:, 0] * k; ys = allpts[:, 1]
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    s = size / max(x1 - x0, y1 - y0)
    W, H = (x1 - x0) * s, (y1 - y0) * s

    out = []
    for props, rings in polys:
        d = []
        for r in rings:
            pts, last = [], None
            for lon, lat in r:
                p = (round((lon * k - x0) * s, 1), round((y1 - lat) * s, 1))
                if p != last:
                    pts.append(p); last = p
            if len(pts) >= 3:
                d.append("M" + "L".join(f"{a:g},{b:g}" for a, b in pts) + "Z")
        out.append({"geocode": int(props["GEOCODE"]), "name": props["GEONAME"], "d": "".join(d)})
    return out, round(W, 1), round(H, 1)


def main():
    model = json.loads((ROOT / "data" / "model.json").read_text())
    results = json.loads((ROOT / "data" / "results.json").read_text())

    cv = pd.read_csv(ROOT / "data" / "cv_predictions.csv", parse_dates=["date"])
    history = {}
    for y, s in cv.groupby("year"):
        history[int(y)] = {
            "start": s.date.min().strftime("%Y-%m-%d"),
            "visits": s.visits.astype(int).tolist(),
            "hi": s.hi.astype(int).tolist(),
            "pred": s.pred.round(1).tolist(),
            "nws": s.nws.astype(int).tolist(),
            "watch": s.watch.astype(int).tolist(),
            "dates": s.date.dt.strftime("%m-%d").tolist(),
        }

    hvi = pd.read_csv(RAW / "hvi-nta-2020.csv").merge(
        pd.read_csv(RAW / "older_adults_alone_nta2020.csv"), on="GEOCODE", how="left")
    hoods = {int(r.GEOCODE): {
        "name": r.GEONAME, "hvi": int(r.HVI_RANK), "cd": r.CDTACode,
        "ac": round(float(r.PCT_HOUSEHOLDS_AC), 1), "surf": round(float(r.SURFACE_TEMP), 1),
        "income": int(r.MEDIAN_INCOME), "green": round(float(r.GREENSPACE), 1),
        "alone": None if pd.isna(r.pct_older_adults_alone) else round(float(r.pct_older_adults_alone), 1),
    } for r in hvi.itertuples()}

    paths, W, H = topo_to_paths(json.loads((RAW / "NTA2020.topo.json").read_text()))
    assets = {"model": model, "results": results, "history": history,
              "hoods": hoods, "map": {"w": W, "h": H, "paths": paths}}
    out = ROOT / "data" / "assets.json"
    out.write_text(json.dumps(assets, separators=(",", ":")))
    print(out, round(out.stat().st_size / 1024), "KB")


if __name__ == "__main__":
    main()
