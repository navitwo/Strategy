"""Run and retrieve the repaired 32-bit E19B-R first-touch export."""
import sys, os, json

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from qc_api import (backtest_create, backtest_list, chart_read,
                    poll_backtest)

PID = 35506697
REV = "FT32C"
TARGETS = (0.5, 1.0, 1.5, 2.0)
STOPS = (0.5, 1.0, 1.5, 2.0)
CELLS = [(f"T{target:g}S{stop:g}", target, stop)
         for target in TARGETS for stop in STOPS]
OUTCOME = {0: "undecided", 1: "target-first", 2: "stop-first",
           3: "ambiguous"}


def decode_ft_value(value):
    raw = float(value)
    packed = int(raw)
    assert raw == packed, f"non-integral FT payload: {value!r}"
    assert 0 <= packed <= 0xFFFFFFFF, f"FT payload outside uint32: {packed}"
    return [(packed >> (2 * i)) & 3 for i in range(16)]


def ft_rows_from_chart(inst, backtest_id):
    payload = chart_read(PID, backtest_id, "E19B-FT")
    series = payload.get("chart", {}).get("series", {}).get("ft-a", {})
    points = series.get("values", [])
    rows = []
    for row_index, point in enumerate(points):
        x = point.get("x") if isinstance(point, dict) else point[0]
        y = point.get("y") if isinstance(point, dict) else point[1]
        codes = decode_ft_value(y)
        rows.append({
            "instrument": inst, "ft_row": row_index, "chart_x": x,
            "packed_uint32": int(float(y)), "codes": codes,
            "cells": {key: OUTCOME[codes[i]]
                      for i, (key, _, _) in enumerate(CELLS)},
        })
    return rows


def validate_ft_ledger(runtime, rows):
    n_events = int(runtime.get("d_ev_results", 0) or 0)
    assert "n_ft_rows" in runtime, "missing n_ft_rows RuntimeStatistic"
    declared = int(runtime["n_ft_rows"])
    if n_events > 0:
        assert rows, f"d_ev_results={n_events} but FT ledger is empty"
    assert declared == len(rows), \
        f"FT row mismatch: runtime={declared}, retrieved={len(rows)}"


def summarize_ft_rows(rows):
    screen = {}
    for i, (key, target, stop) in enumerate(CELLS):
        counts = {name: 0 for name in OUTCOME.values()}
        for row in rows:
            counts[OUTCOME[int(row["codes"][i])]] += 1
        n_decided = (counts["target-first"] + counts["stop-first"]
                     + counts["ambiguous"])
        p_target = (counts["target-first"] / n_decided
                    if n_decided else None)
        mean_per_risk = ((counts["target-first"] * (target / stop)
                          - counts["stop-first"] - counts["ambiguous"])
                         / n_decided
                         if n_decided else None)
        screen[key] = {
            "target_risk_dist": target, "stop_risk_dist": stop,
            "n_ft_rows": len(rows), "n_decided": n_decided,
            **counts,
            "p_target_given_decided": p_target,
            "mean_R_per_unit_risked": mean_per_risk,
        }
    return screen


def assert_stop_monotonic(screen, tol=1e-12):
    for target in TARGETS:
        ps = [screen[f"T{target:g}S{stop:g}"]["p_target_given_decided"]
              for stop in STOPS]
        decided = [p for p in ps if p is not None]
        assert all(b + tol >= a for a, b in zip(decided, decided[1:])), \
            f"target {target:g}: p_target decreases with wider stop: {ps}"


def write_jsonl_atomic(path, rows):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    os.replace(tmp, path)


def main():
    compile_id = open("compile_id.txt").read().strip()
    tags = {f"E19BR-{REV}-{inst}" for inst in ("NQ", "ES", "YM", "RTY")}
    existing = {row["name"] for row in backtest_list(PID)}
    duplicates = sorted(tags & existing)
    assert not duplicates, f"duplicate remote experiments: {duplicates}"
    os.makedirs("e19br_ft_ledger", exist_ok=True)
    results, all_rows = [], []
    with open("e19br_ft_results.jsonl", "w", encoding="utf-8",
              newline="\n") as out:
      for inst in ("NQ", "ES", "YM", "RTY"):
            min_ticks = {"NQ": 8, "ES": 8, "YM": 6, "RTY": 12}[inst]
            params = {"start_date": "2010-01-01", "end_date": "2024-12-31",
                      "run_segment": "dev", "instrument": inst,
                      "risk_usd": "10000", "max_contracts": "1",
                      "variant": "events_only",
                      "min_stop_ticks": str(min_ticks),
                      "floor_atr_frac": "0.10"}
            tag = f"E19BR-{REV}-{inst}"
            r = backtest_create(PID, tag, params, compile_id=compile_id)
            print(inst, "submitted", r["backtest_id"], flush=True)
            res = poll_backtest(PID, r["backtest_id"],
                                max_wait=7200, poll_s=20)
            bt = res if isinstance(res, dict) else {}
            rt = bt.get("runtimeStatistics") or {}
            assert str(bt.get("status", "")).lower().replace(".", "") \
                == "completed", f"{inst} did not complete: {bt.get('status')}"
            error = str(bt.get("error") or "")
            assert error in ("", "None"), f"{inst} runtime error: {error}"
            rows = ft_rows_from_chart(inst, r["backtest_id"])
            validate_ft_ledger(rt, rows)
            write_jsonl_atomic(
                os.path.join("e19br_ft_ledger", f"{inst}_ft.jsonl"), rows)
            rec = {"inst": inst, "bid": r["backtest_id"],
                   "status": str(bt.get("status")),
                   "error": str(bt.get("error", ""))[:300],
                   "n_ft_rows_retrieved": len(rows),
                   "rt": {k: str(v) for k, v in rt.items()}}
            out.write(json.dumps(rec) + "\n")
            out.flush()
            results.append(rec)
            all_rows.extend(rows)
            atts = (int(rt.get("f_L_attempts", 0) or 0)
                    + int(rt.get("f_S_attempts", 0) or 0))
            print(inst, bt.get("status"), "| att:", atts,
                  "| ev:", rt.get("d_ev_results"),
                  "| ft:", len(rows), flush=True)
    screen = summarize_ft_rows(all_rows)
    assert_stop_monotonic(screen)
    with open("e19br_ft_screen.json", "w", encoding="utf-8",
              newline="\n") as handle:
        json.dump({"status": "VALID_REPLACEMENT", "encoding":
                   "uint32: 2 bits/cell; 0 undecided, 1 target, 2 stop, 3 ambiguous",
                   "ambiguity_policy": "pessimistic stop-first in p and mean_R",
                   "runs": [{"instrument": r["inst"], "backtest_id": r["bid"],
                             "n_ft_rows": r["n_ft_rows_retrieved"]}
                            for r in results],
                   "cells": screen}, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print("ALL MARKETS DONE", flush=True)


if __name__ == "__main__":
    main()
