"""C3-absorption proxy analysis — ONLY run if Gate B purchased the
conditional NQ trades pull (C3_ABSORPTION_PROXY_PROTOCOL.md section 3-5).

Inputs:
  c3_trades/ (directory of CSVs from the batch job, schema 'trades')
  c2_local_study.json  — committed NQ event ledger (fwd_R, contrasts)
  nq_event_windows.json — merged +/-60min windows for span->file mapping

Method (frozen in the protocol BEFORE any purchase or quote was seen):
  span = 60 min ending at event_et
  V+ / V- = aggressive (action==T) trade size by side
  delta = V+ - V-;  displacement dP = last - first trade price
  A = (V+ + V-) / max(|dP|, 0.01)  contracts per point
  split: candidates = upper quartile of A WITHIN each level_kind
  outcomes: committed fwd_R(30/60/120/240) + contrast_R, session-date
  clustered bootstrap (10k draws, seed 20260905), decision per protocol S5.

Zero new outcome computation: all outcome fields are read from the
committed ledger; only INPUT-side quantities are computed from trades.
"""
import csv
import glob
import json
import os
import statistics
import sys

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
TRADES_DIR = os.path.join(ROOT, "c3_trades")
LEDGER = os.path.join(ROOT, "c2_local_study.json")
EVENTS = ("NQ",)
SEED, DRAWS = 20260905, 10_000
HORIZONS = ("30", "60", "120", "240")


def load_trades():
    """Map ISO-minute -> (list of (ts_ns_or_iso, price, action, side, size)
    per raw symbol). Trade CSVs are per-day; we index per event window
    lazily by (raw_symbol, date) to keep memory sane."""
    frames = {}
    for path in sorted(glob.glob(os.path.join(TRADES_DIR, "*.csv"))):
        base = os.path.basename(path)
        # typical batch csv naming: <name>-<raw_symbol>-<date>.csv (varies);
        # read header once
        with open(path, newline="") as fh:
            rd = csv.DictReader(fh)
            rows = list(rd)
        if not rows:
            continue
        key = rows[0]["ts_event"][:10]
        frames.setdefault(base, rows)
    return frames


def ts_parse(v):
    # DBN CSV ts_event may be ISO or nanoseconds; normalize to epoch ns int
    s = v.strip()
    if s.isdigit():
        return int(s)
    from datetime import datetime, timezone
    return int(datetime.fromisoformat(s.replace("Z", "+00:00"))
               .timestamp() * 1e9)


def window_index(rows):
    """rows -> dict by epoch-ns sorted, all fields kept."""
    out = []
    for r in rows:
        out.append((ts_parse(r["ts_event"]), float(r["price"]),
                    r.get("action", ""), r.get("side", ""), int(r["size"])))
    out.sort()
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv-dir", default=TRADES_DIR,
                    help="directory with the purchased trades CSVs")
    ap.add_argument("--continuous-map", required=True,
                    help="json: continuous NQ.n.0 -> {date: raw_symbol} "
                         "from symbology.resolve (free endpoint)")
    args = ap.parse_args()

    # load purchased trades, one index per raw symbol per day
    idx = {}
    for path in sorted(glob.glob(os.path.join(args.csv_dir, "*.csv"))):
        with open(path, newline="") as fh:
            rows = list(csv.DictReader(fh))
        if rows:
            # batch export merges symbols; group rows by (instrument_id,date)
            for r in rows:
                key = (r["instrument_id"], ts_parse(r["ts_event"]) // 10**9
                       // 86400)
                idx.setdefault(key, []).append(
                    (ts_parse(r["ts_event"]), float(r["price"]),
                     r.get("action", "T"), r.get("side", "N"),
                     int(r["size"])))
    for k in idx:
        idx[k].sort()
    print("instrument-day buckets:", len(idx))

    cmap = json.load(open(args.continuous_map))
    led = json.load(open(LEDGER))
    events = led["events"]["NQ"]

    NS = 1_000_000_000

    def seconds_from_iso(iso):
        from datetime import datetime
        s = iso.replace("+00:00", "Z")
        if s.endswith("Z"):
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        else:
            from zoneinfo import ZoneInfo
            dt = datetime.fromisoformat(s).replace(
                tzinfo=ZoneInfo("America/New_York"))
        return dt.timestamp()

    recs = []
    miss = 0
    for ev in events:
        et = ev["event_et"]
        t0 = seconds_from_iso(et)
        day = int(t0) // 86400
        raw = None
        # continuous map: {"YYYY-MM-DD": raw_symbol}
        dkey = __import__("datetime").datetime.utcfromtimestamp(t0).date().isoformat()
        raw = cmap.get(dkey) or cmap.get(dkey[:7])
        rows = idx.get((raw, day)) if raw else None
        if rows is None:
            miss += 1
            continue
        a_ts = int(t0 - 3600) * NS  # span: 60 min ENDING at touch ts
        b_ts = int(t0) * NS
        seg = [r for r in rows if a_ts <= r[0] < b_ts]
        if len(seg) < 2:
            miss += 1
            continue
        v_plus = sum(sz for _, _, act, side, sz in seg if act == "T" and side == "B")
        v_minus = sum(sz for _, _, act, side, sz in seg if act == "T" and side == "A")
        dp = seg[-1][1] - seg[0][1]
        delta = v_plus - v_minus
        a_score = (v_plus + v_minus) / max(abs(dp), 0.01)
        e_raw = abs(dp) / max(v_plus + v_minus, 1)
        recs.append({"event_et": et, "session_date": ev["session_date"],
                     "level_kind": ev["level_kind"], "A": a_score,
                     "E_raw": e_raw, "V": v_plus + v_minus, "dP": dp,
                     "delta": delta, "fwd_R": ev["fwd_R"],
                     "contrast_R": ev["contrast_R"]})
    print("scored events:", len(recs), "| unscored (missing/short):", miss)
    json.dump(recs, open(os.path.join(ROOT, "c3_proxy_scored.json"), "w"))

    rng = np.random.default_rng(SEED)

    def clustered(rows_, key):
        vals = [r[key] for r in rows_ if r[key] is not None]
        if not vals:
            return None
        groups = {}
        for r in rows_:
            if r[key] is not None:
                groups.setdefault(r["session_date"], []).append(r[key])
        keys = list(groups)
        assert len(keys) < len(vals), "sessions < n violated"
        means = []
        for _ in range(DRAWS):
            pick = rng.choice(len(keys), size=len(keys), replace=True)
            flat = [v for i in pick for v in groups[keys[i]]]
            means.append(statistics.fmean(flat))
        return (statistics.fmean(vals),
                float(np.percentile(means, 2.5)),
                float(np.percentile(means, 97.5)), len(vals), len(keys))

    report = {}
    for kind in ("overnight_high", "overnight_low"):
        sub = [r for r in recs if r["level_kind"] == kind]
        thr = float(np.percentile([r["A"] for r in sub], 75))
        cand = [r for r in sub if r["A"] >= thr]
        rest = [r for r in sub if r["A"] < thr]
        cells = {"threshold_A": thr, "n_cand": len(cand), "n_rest": len(rest)}
        # forward per-horizon and contrast
        for h in HORIZONS:
            cc = [dict(r, val=r["fwd_R"][h]) for r in cand if r["fwd_R"][h] is not None]
            rr = [dict(r, val=r["fwd_R"][h]) for r in rest if r["fwd_R"][h] is not None]
            fc, fr = clustered(cc, "val"), clustered(rr, "val")
            # T statistic: cand mean minus rest mean, clustered at session level
            cgrp, rgrp = {}, {}
            for r in cc: cgrp.setdefault(r["session_date"], []).append(r["val"])
            for r in rr: rgrp.setdefault(r["session_date"], []).append(r["val"])
            ck = list(set(cgrp) & set(rgrp))
            assert len(ck) < len(cc) + len(rr)
            diffs = []
            for _ in range(DRAWS):
                pick = rng.choice(len(ck), size=len(ck), replace=True)
                a = [v for i in pick for v in cgrp[ck[i]]]
                b = [v for i in pick for v in rgrp[ck[i]]]
                if a and b:
                    diffs.append(statistics.fmean(a) - statistics.fmean(b))
            point = statistics.fmean([r["val"] for r in cc]) - \
                    statistics.fmean([r["val"] for r in rr])
            cells[f"fwd_{h}"] = {
                "cand": fc, "rest": fr,
                "T": {"point": point,
                      "ci95": [float(np.percentile(diffs, 2.5)),
                               float(np.percentile(diffs, 97.5))],
                      "n_cand": len(cc), "n_rest": len(rr),
                      "clusters": len(ck)}}
        # contrast_R
        cells["contrast"] = {"cand": clustered(cand, "contrast_R"),
                             "rest": clustered(rest, "contrast_R")}
        report[kind] = cells

    json.dump(report, open(os.path.join(ROOT, "c3_proxy_analysis.json"), "w"),
              indent=1)

    def fmt(x):
        if not x: return "  --  "
        return f"{x[0]:+.4f} CI[{x[1]:+.4f},{x[2]:+.4f}]"
    lines = ["C3 ABSORPTION PROXY (exploratory; protocol S3/S5 frozen "
             "pre-results)", ""]
    for kind, cells in report.items():
        lines.append(f"== {kind}: split A>={cells['threshold_A']:.1f} "
                     f"cand n={cells['n_cand']} rest n={cells['n_rest']}")
        for h in HORIZONS:
            c = cells[f"fwd_{h}"]
            lines.append(f"  fwd_{h}m  cand {fmt(c['cand'])}  "
                         f"rest {fmt(c['rest'])}")
            lines.append(f"           T={c['T']['point']:+.4f} "
                         f"CI[{c['T']['ci95'][0]:+.4f},"
                         f"{c['T']['ci95'][1]:+.4f}]")
        lines.append(f"  contrast cand {fmt(cells['contrast']['cand'])} "
                     f"rest {fmt(cells['contrast']['rest'])}")
        lines.append("")

    # decision per protocol section 5
    def ci(kind, h="120"):
        t = report[kind][f"fwd_{h}"]["T"]["ci95"]
        return t
    th, tl = ci("overnight_high"), ci("overnight_low")
    supported = (th[0] > 0.10) and (tl[0] > 0.10)
    dead = (th[0] <= 0.0 <= th[1]) or (tl[0] <= 0.0 <= tl[1]) \
        or th[1] < 0 or tl[1] < 0
    verdict = "SUPPORTED" if supported else ("DEAD" if dead else "INCONCLUSIVE")
    lines.append(f"VERDICT: {verdict}  (rule: protocol section 5; "
                 "T_high CI entirely >+0.10R AND T_low CI entirely >+0.10R)")
    open(os.path.join(ROOT, "c3_proxy_analysis_report.txt"), "w").write(
        "\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
