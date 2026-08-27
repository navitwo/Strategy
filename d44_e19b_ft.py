"""Run and retrieve the repaired 32-bit E19B-R first-touch export."""
import sys, os, json, time, math

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from qc_api import (backtest_create, backtest_list, chart_read,
                    poll_backtest)

PID = 35506697
REV = "FT32E"
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


def ft_rows_from_chart(inst, backtest_id, expected_count):
    points = []
    for attempt in range(30):
        payload = chart_read(PID, backtest_id, "E19B-FT",
                             count=expected_count, start=0, end=2147483647)
        status = str(payload.get("status") or "").lower()
        if payload.get("success") is False and status != "loading":
            raise RuntimeError(f"chart read failed: {payload.get('errors')}")
        series = payload.get("chart", {}).get("series", {}).get("a", {})
        points = series.get("values", [])
        if len(points) == expected_count:
            break
        if attempt < 29:
            time.sleep(2)
    assert len(points) == expected_count, \
        f"FT chart incomplete: expected={expected_count}, got={len(points)}"
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
    assert "d_ev_results" in runtime, "missing d_ev_results RuntimeStatistic"
    n_events = int(runtime["d_ev_results"])
    assert n_events > 0, f"non-positive d_ev_results: {n_events}"
    assert "n_ft_rows" in runtime, "missing n_ft_rows RuntimeStatistic"
    declared = int(runtime["n_ft_rows"])
    assert declared > 0, f"non-positive n_ft_rows: {declared}"
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
        target_n = counts["target-first"]
        stop_n = counts["stop-first"]
        ambiguous_n = counts["ambiguous"]
        p_target = target_n / n_decided if n_decided else None
        p_target_opt = ((target_n + ambiguous_n) / n_decided
                        if n_decided else None)
        mean_per_risk = ((target_n * (target / stop)
                          - stop_n - ambiguous_n) / n_decided
                         if n_decided else None)
        mean_per_risk_opt = (((target_n + ambiguous_n) * (target / stop)
                              - stop_n) / n_decided
                             if n_decided else None)
        martingale_p = stop / (target + stop)
        z = ((p_target - martingale_p)
             / math.sqrt(martingale_p * (1 - martingale_p) / n_decided)
             if n_decided else None)
        z_opt = ((p_target_opt - martingale_p)
                 / math.sqrt(martingale_p * (1 - martingale_p) / n_decided)
                 if n_decided else None)
        screen[key] = {
            "target_risk_dist": target, "stop_risk_dist": stop,
            "n_ft_rows": len(rows), "n_decided": n_decided,
            **counts,
            "p_target_given_decided": p_target,
            "mean_R_per_unit_risked": mean_per_risk,
            "p_target_given_decided_pessimistic": p_target,
            "p_target_given_decided_optimistic": p_target_opt,
            "mean_R_per_unit_risked_pessimistic": mean_per_risk,
            "mean_R_per_unit_risked_optimistic": mean_per_risk_opt,
            "martingale_target_probability": martingale_p,
            "binomial_z_pessimistic_vs_martingale": z,
            "binomial_z_optimistic_vs_martingale": z_opt,
            "binomial_z_ambiguity_interval": [z, z_opt],
            "idealized_eventual_exit_target_probability": martingale_p,
            "iid_binomial_z_pessimistic_vs_idealized_eventual_exit": z,
        }
    return screen


def holm_rejections(z_cells, alpha=0.05):
    ranked = sorted((math.erfc(abs(z) / math.sqrt(2)), key)
                    for key, z in z_cells.items())
    rejected = []
    for i, (p_value, key) in enumerate(ranked):
        if p_value > alpha / (len(ranked) - i):
            break
        rejected.append(key)
    return rejected


def build_screen_payload(results, rows):
    screen = summarize_ft_rows(rows)
    assert_stop_monotonic(screen)
    best_pess = max(screen, key=lambda k:
                    screen[k]["mean_R_per_unit_risked_pessimistic"])
    best_opt = max(screen, key=lambda k:
                   screen[k]["mean_R_per_unit_risked_optimistic"])
    z_cells = {key: cell["binomial_z_pessimistic_vs_martingale"]
               for key, cell in screen.items()}
    exceed = [key for key, z in z_cells.items() if abs(z) > 1.96]
    robust = [key for key, cell in screen.items()
              if (cell["binomial_z_pessimistic_vs_martingale"] > 1.96
                  or cell["binomial_z_optimistic_vs_martingale"] < -1.96)]
    t_ge_1 = {key: z for key, z in z_cells.items()
              if screen[key]["target_risk_dist"] >= 1.0}
    return {
        "status": f"VALID_REPLACEMENT_{REV}",
        "encoding": "uint32: 2 bits/cell; 0 undecided, 1 target, 2 stop, 3 ambiguous",
        "ambiguity_policy": "reported as bounds: pessimistic stop-first through maximally optimistic target-first",
        "runs": [{"instrument": r["inst"], "backtest_id": r["bid"],
                  "n_ft_rows": r["n_ft_rows_retrieved"]}
                 for r in results],
        "ambiguity_bounds": {
            "population": "decided paths only; undecided paths excluded",
            "is_complete_horizon_upper_bound": False,
            "round_trip_friction_reference_R": 0.2,
            "round_trip_friction_reference_qualifier": "approximately; observed campaign reference",
            "best_pessimistic": {
                "cell": best_pess,
                "mean_R_per_unit_risked": screen[best_pess][
                    "mean_R_per_unit_risked_pessimistic"]},
            "best_optimistic": {
                "cell": best_opt,
                "mean_R_per_unit_risked": screen[best_opt][
                    "mean_R_per_unit_risked_optimistic"]},
            "any_decided_cell_clears_friction_under_either_bound": any(
                cell["mean_R_per_unit_risked_optimistic"] >= 0.2
                for cell in screen.values())},
        "martingale_benchmark": {
            "formula": "p_target=S/(T+S)",
            "assumptions": ["driftless martingale", "no barrier overshoot",
                            "almost-sure eventual barrier decision",
                            "admissible optional-stopping conditions"],
            "formula_scope": "idealized eventual two-sided exit; not generally the conditional hit-by-120m probability when undecided paths are discarded",
            "z_definition": "descriptive iid-binomial score using pessimistic target count",
            "mean_abs_binomial_z": sum(abs(z) for z in z_cells.values())
                                   / len(z_cells),
            "n_cells_abs_z_gt_1_96": len(exceed),
            "n_cells_abs_z_le_1_96": len(z_cells) - len(exceed),
            "cells_abs_z_gt_1_96": exceed,
            "ambiguity_robust_raw_rejections": robust,
            "holm_rejections_16_cells": holm_rejections(z_cells),
            "n_T_ge_1_cells": len(t_ge_1),
            "holm_rejections_T_ge_1_cells": holm_rejections(t_ge_1),
            "proves_conditional_process_is_martingale": False,
            "scope_limit": "not cluster-robust; non-rejection is not equivalence and does not prove the conditional price process is a martingale or exclude every stopping rule empirically",
        },
        "cells": screen,
    }


def assert_stop_monotonic(screen, tol=1e-12):
    for target in TARGETS:
        ps = [screen[f"T{target:g}S{stop:g}"]["p_target_given_decided"]
              for stop in STOPS]
        assert all(p is not None for p in ps), \
            f"vacuous FT cells for target={target:g}: {ps}"
        assert all(b + tol >= a for a, b in zip(ps, ps[1:])), \
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
            assert "n_ft_rows" in rt, "missing n_ft_rows RuntimeStatistic"
            rows = ft_rows_from_chart(
                inst, r["backtest_id"], int(rt["n_ft_rows"]))
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
    payload = build_screen_payload(results, all_rows)
    with open("e19br_ft_screen.json", "w", encoding="utf-8",
              newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print("ALL MARKETS DONE", flush=True)


if __name__ == "__main__":
    main()
