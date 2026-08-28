"""Run, retrieve, and compare the frozen same-date random-time FT control."""
import hashlib
import json
import math
import os
import random
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from d44_e19b_ft import (CELLS, OUTCOME, assert_stop_monotonic,
                         build_screen_payload, summarize_ft_rows)
from qc_api import backtest_create, backtest_list, chart_read, poll_backtest
from random_time_control import (CONTROL_SPECS, CONTROL_SPEC_SHA256,
    RISK_SPEC_SHA256, SEED, SPEC_VERSION, build_control_plans,
    unpack_random_payload)
from scifvg_config import CONFIG_DEFAULTS, canonical_identity_config

PID = 35506697
INSTRUMENTS = ("NQ", "ES", "YM", "RTY")
EXPECTED_ROWS = {key: len(value) for key, value in CONTROL_SPECS.items()}
FRICTION_R = 0.2
RATE_TOLERANCE = 0.05
BOOTSTRAP_REPS = 2000
BOOTSTRAP_SEED = "RTC2-cluster-bootstrap-v1"
ZERO_RUNTIME_KEYS = (
    "d_cycles_opened", "d_n_fillevents",
    "f_L_submits", "f_S_submits", "f_L_fills", "f_S_fills",
    "f_flatten_fills", "f_forced_flattens", "eod_flattens")


def launch_parameters(instrument):
    return {
        "start_date": "2010-01-01", "end_date": "2024-12-31",
        "run_segment": "dev", "instrument": instrument,
        "variant": "random_time_control", "random_control_seed": SEED,
        "window_start_et": "09:30", "window_end_et": "12:00",
    }


def expected_identity(instrument):
    cfg = dict(CONFIG_DEFAULTS)
    cfg.update(launch_parameters(instrument))
    cfg["event_predicates"] = ""
    cfg["random_control_spec_sha256"] = CONTROL_SPEC_SHA256
    canonical = json.dumps(canonical_identity_config(cfg), sort_keys=True,
                           separators=(",", ":"))
    return hashlib.md5(canonical.encode()).hexdigest()[:8]


def _decode_ft32(ft32):
    return [(int(ft32) >> (2 * i)) & 3 for i in range(16)]


def expected_chart_x_values(source_date, window_index):
    assert 0 <= int(window_index) < 30
    base = datetime.fromisoformat(str(source_date)) + timedelta(
        minutes=9 * 60 + 30 + 5 * int(window_index))
    naive_epoch = int(base.replace(tzinfo=timezone.utc).timestamp())
    et_epoch = int(base.replace(tzinfo=ZoneInfo("America/New_York")).timestamp())
    return tuple(sorted({naive_epoch, et_epoch}))


def validate_selected_chart_x(chart_x, source_date, window_index):
    assert int(chart_x) in expected_chart_x_values(source_date, window_index), (
        f"off-grid/wrong-date control chart x: {chart_x}")


def random_rows_from_chart(instrument, backtest_id, expected_count):
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
    assert len(points) == expected_count, (
        f"random chart incomplete: expected={expected_count}, got={len(points)}")
    plans = build_control_plans(instrument, CONTROL_SPECS[instrument], SEED)
    rows = []
    for row_index, point in enumerate(points):
        x = point.get("x") if isinstance(point, dict) else point[0]
        y = point.get("y") if isinstance(point, dict) else point[1]
        raw = float(y); packed = int(raw)
        assert raw == packed and 0 <= packed < 2 ** 52
        meta = unpack_random_payload(packed)
        source_index = meta["source_index"]
        assert source_index < len(plans)
        plan = plans[source_index]
        codes = _decode_ft32(meta["ft32"])
        rows.append({
            "instrument": instrument, "ft_row": row_index,
            "chart_x": int(x), "packed_exact": packed,
            "packed_uint32": meta["ft32"], "codes": codes,
            "cells": {key: OUTCOME[codes[i]]
                      for i, (key, _, _) in enumerate(CELLS)},
            "source_index": source_index,
            "source_chart_x": plan["source_chart_x"],
            "source_date": plan["date"], "risk_dist": plan["risk_dist"],
            "side": meta["side"], "path_bars": meta["path_bars"],
            "window_index": meta["window_index"],
        })
    return rows


def validate_random_runtime(instrument, runtime, rows):
    expected = EXPECTED_ROWS[instrument]
    exact = {
        "event_predicates": "", "random_control_spec_version": SPEC_VERSION,
        "random_control_seed": SEED,
        "random_control_risk_sha256": RISK_SPEC_SHA256,
        "random_control_spec_sha256": CONTROL_SPEC_SHA256,
        "random_control_instrument": instrument,
        "random_control_start_date": "2010-01-01",
        "random_control_end_date": "2024-12-31",
        "random_control_run_segment": "dev",
        "random_control_window": "09:30-12:00",
        "random_control_exp_hash": expected_identity(instrument),
    }
    for key, value in exact.items():
        assert str(runtime.get(key, "")) == str(value), (
            f"{instrument}: runtime identity mismatch {key}")
    for key in ("random_control_target", "random_control_started",
                "random_control_resolved", "d_ev_results", "n_ft_rows"):
        assert int(runtime.get(key, -1)) == expected, f"{instrument}: bad {key}"
    assert int(runtime.get("random_control_eligible", -1)) == 30 * expected
    for key in ("random_control_invalid",
                "random_control_order_purpose_count") + ZERO_RUNTIME_KEYS:
        assert int(runtime.get(key, -1)) == 0, f"{instrument}: nonzero {key}"
    assert len(rows) == expected and rows
    plans = build_control_plans(instrument, CONTROL_SPECS[instrument], SEED)
    assert sorted(row["source_index"] for row in rows) == list(range(expected))
    assert len({row["chart_x"] for row in rows}) == expected
    for row in rows:
        plan = plans[row["source_index"]]
        assert row["source_chart_x"] == plan["source_chart_x"]
        assert row["risk_dist"] == plan["risk_dist"]
        assert row["side"] == plan["side"]
        assert row["window_index"] == plan["window_index"]
        assert row["path_bars"] == 24
        validate_selected_chart_x(
            row["chart_x"], plan["date"], plan["window_index"])
    assert_stop_monotonic(summarize_ft_rows(rows))


def assert_unique_chart_rows(rows):
    keys = [(row["instrument"], row["chart_x"]) for row in rows]
    assert len(keys) == len(set(keys)), "duplicate (instrument, chart_x) identity"


def _load_sweep_rows():
    rows = []
    for instrument in INSTRUMENTS:
        path = os.path.join("e19br_ft_ledger", f"{instrument}_ft.jsonl")
        with open(path, encoding="utf-8") as handle:
            market = [json.loads(line) for line in handle if line.strip()]
        assert len(market) == EXPECTED_ROWS[instrument]
        for source_index, row in enumerate(market):
            assert row.get("instrument") == instrument, (
                f"sweep ledger instrument mismatch: {instrument}")
            assert int(row["ft_row"]) == source_index, (
                f"sweep ledger order mismatch: {instrument}")
            spec = CONTROL_SPECS[instrument][source_index]
            assert int(row["chart_x"]) == int(spec[0]), (
                f"sweep chart_x != control spec identity: {instrument}")
            codes = row["codes"]
            assert len(codes) == 16 and all(code in (0, 1, 2, 3)
                                            for code in codes)
            assert int(row["packed_uint32"]) == sum(
                int(code) << (2 * i) for i, code in enumerate(codes)) \
                <= 0xFFFFFFFF, f"sweep packed uint32 mismatch: {instrument}"
            assert row["cells"] == {key: OUTCOME[codes[i]]
                for i, (key, _, _) in enumerate(CELLS)}, (
                f"sweep cells mismatch: {instrument}")
            row = dict(row)
            row["instrument"] = instrument
            row["source_index"] = source_index
            rows.append(row)
    return rows


def verify_committed_sweep_artifact(sweep_payload):
    rows = _load_sweep_rows()
    results = [json.loads(line) for line in
               open("e19br_ft_results.jsonl", encoding="utf-8")
               if line.strip()]
    assert build_screen_payload(results, rows) == sweep_payload, (
        "committed e19br_ft_screen.json does not regenerate exactly")
    for instrument in INSTRUMENTS:
        market_rows = [row for row in rows if row["instrument"] == instrument]
        assert_stop_monotonic(summarize_ft_rows(market_rows))
    assert_stop_monotonic(summarize_ft_rows(rows))
    return rows


def _cell_values(codes, cell_index, target, stop):
    code = int(codes[cell_index])
    decided = int(code != 0)
    ambiguous = int(code == 3)
    pess = None if not decided else (target / stop if code == 1 else -1.0)
    opt = None if not decided else (target / stop if code in (1, 3) else -1.0)
    return decided, ambiguous, pess, opt


def _surface_vectors(pairs, selected=None):
    if selected is None:
        selected = range(len(pairs))
    lower, upper, decision, ambiguity = [], [], [], []
    for cell_index, (_, target, stop) in enumerate(CELLS):
        ep, eo, rp, ro = [], [], [], []
        ed = rd = ea = ra = n = 0
        for pair_index in selected:
            sweep, control, _ = pairs[pair_index]
            sd, sa, sp, so = _cell_values(
                sweep["codes"], cell_index, target, stop)
            cd, ca, cp, co = _cell_values(
                control["codes"], cell_index, target, stop)
            n += 1; ed += sd; rd += cd; ea += sa; ra += ca
            if sp is not None: ep.append(sp)
            if so is not None: eo.append(so)
            if cp is not None: rp.append(cp)
            if co is not None: ro.append(co)
        assert ep and eo and rp and ro and n
        lower.append(sum(ep) / len(ep) - sum(ro) / len(ro))
        upper.append(sum(eo) / len(eo) - sum(rp) / len(rp))
        decision.append(ed / n - rd / n)
        ambiguity.append(ea / n - ra / n)
    return lower, upper, decision, ambiguity


def _quantile(values, probability):
    values = sorted(values)
    index = max(0, min(len(values) - 1,
                       math.ceil(probability * len(values)) - 1))
    return values[index]


def _cluster_bands(pairs, observed, reps=BOOTSTRAP_REPS):
    if all(sweep["codes"] == control["codes"] for sweep, control, _ in pairs):
        return 0.0, 0.0, len({date for _, _, date in pairs})
    clusters = defaultdict(list)
    for index, (_, _, date) in enumerate(pairs):
        clusters[date].append(index)
    dates = sorted(clusters)
    rng = random.Random(BOOTSTRAP_SEED)
    pay_deviation, rate_deviation = [], []
    ol, ou, od, oa = observed
    for _ in range(int(reps)):
        sample = []
        for date in rng.choices(dates, k=len(dates)):
            sample.extend(clusters[date])
        bl, bu, bd, ba = _surface_vectors(pairs, sample)
        pay_deviation.append(max(
            max(abs(x - y) for x, y in zip(bl, ol)),
            max(abs(x - y) for x, y in zip(bu, ou))))
        rate_deviation.append(max(
            max(abs(x - y) for x, y in zip(bd, od)),
            max(abs(x - y) for x, y in zip(ba, oa))))
    return (_quantile(pay_deviation, 0.975),
            _quantile(rate_deviation, 0.975), len(dates))


def classify_surface(lower, upper, decision, ambiguity, pay_half, rate_half):
    equivalent = all(
        lo - pay_half > -FRICTION_R and hi + pay_half < FRICTION_R
        for lo, hi in zip(lower, upper)) and all(
        abs(value) + rate_half < RATE_TOLERANCE
        for value in decision + ambiguity)
    material = [CELLS[i][0] for i in range(16)
                if lower[i] - pay_half > FRICTION_R
                or upper[i] + pay_half < -FRICTION_R]
    if material:
        return "EVENT_SELECTION_SURFACE_DIFFERS_MATERIALLY", material
    if equivalent:
        return "SURFACES_EQUIVALENT_WITHIN_PREREGISTERED_TOLERANCES", []
    return "INCONCLUSIVE_SURFACE_DIFFERENCE", []


def build_comparison_payload(results, random_rows, sweep_payload,
                             bootstrap_reps=BOOTSTRAP_REPS):
    verify_committed_sweep_artifact(sweep_payload)
    assert_unique_chart_rows(random_rows)
    random_by_key = {(row["instrument"], row["source_index"]): row
                     for row in random_rows}
    sweep_rows = _load_sweep_rows()
    assert len(random_by_key) == len(sweep_rows) == 1121
    pairs = []
    for sweep in sweep_rows:
        key = (sweep["instrument"], sweep["source_index"])
        control = random_by_key[key]
        spec = CONTROL_SPECS[key[0]][key[1]]
        pairs.append((sweep, control, spec[1]))
    for instrument in INSTRUMENTS:
        market_rows = [row for row in random_rows
                       if row["instrument"] == instrument]
        assert len(market_rows) == EXPECTED_ROWS[instrument]
        assert_stop_monotonic(summarize_ft_rows(market_rows))
    random_screen = summarize_ft_rows(random_rows)
    assert_stop_monotonic(random_screen)
    observed = _surface_vectors(pairs)
    pay_half, rate_half, cluster_count = _cluster_bands(
        pairs, observed, bootstrap_reps)
    lower, upper, decision, ambiguity = observed
    classification, material_cells = classify_surface(
        lower, upper, decision, ambiguity, pay_half, rate_half)
    cells = {}
    max_abs_delta = 0.0
    for i, (key, _, _) in enumerate(CELLS):
        sweep, control = sweep_payload["cells"][key], random_screen[key]
        dp = (sweep["mean_R_per_unit_risked_pessimistic"]
              - control["mean_R_per_unit_risked_pessimistic"])
        do = (sweep["mean_R_per_unit_risked_optimistic"]
              - control["mean_R_per_unit_risked_optimistic"])
        max_abs_delta = max(max_abs_delta, abs(dp), abs(do))
        cells[key] = {
            "sweep": sweep, "random": control,
            "delta_mean_R_sweep_minus_random_pessimistic": dp,
            "delta_mean_R_sweep_minus_random_optimistic": do,
            "ambiguity_full_difference_interval_R": [lower[i], upper[i]],
            "simultaneous_interval_lower_endpoint_R":
                [lower[i] - pay_half, lower[i] + pay_half],
            "simultaneous_interval_upper_endpoint_R":
                [upper[i] - pay_half, upper[i] + pay_half],
            "decision_rate_difference": decision[i],
            "ambiguity_rate_difference": ambiguity[i],
            "simultaneous_decision_rate_interval":
                [decision[i] - rate_half, decision[i] + rate_half],
            "simultaneous_ambiguity_rate_interval":
                [ambiguity[i] - rate_half, ambiguity[i] + rate_half],
        }
    payload = build_screen_payload(results, random_rows)
    payload["status"] = "VALID_RANDOM_TIME_CONTROL_RTC2"
    payload["control_design"] = {
        "estimand": ("same-market/date random-time plus randomized-direction "
                     "composite control; not a causal timing-only control"),
        "event_predicates": [], "seed": SEED,
        "control_spec_sha256": CONTROL_SPEC_SHA256,
        "risk_spec_sha256": RISK_SPEC_SHA256,
        "sampling": ("one exact-uniform completed-bar EndTime draw on each "
                     "E19B-R source market/date, 09:30<=ET<12:00"),
        "side": "deterministic independent 50/50 draw in expectation",
        "reference": "completed five-minute bar close",
        "horizon_minutes": 120, "required_path_bars": 24,
    }
    payload["surface_comparison"] = {
        "reference_artifact": "e19br_ft_screen.json",
        "friction_tolerance_R": FRICTION_R,
        "rate_tolerance": RATE_TOLERANCE,
        "bootstrap_method": ("paired market/date cluster bootstrap; separate "
                             "97.5% max-deviation bands per metric family "
                             "(payoff endpoints, rate endpoints); joint "
                             "coverage across families is not claimed"),
        "bootstrap_seed": BOOTSTRAP_SEED, "bootstrap_reps": bootstrap_reps,
        "date_cluster_count": cluster_count,
        "simultaneous_payoff_half_width_R": pay_half,
        "simultaneous_rate_half_width": rate_half,
        "max_abs_matched_policy_delta_R": max_abs_delta,
        "material_difference_cells": material_cells,
        "classification": classification,
        "decision_rule": (
            "material requires a simultaneous ambiguity-robust difference "
            "bound outside +/-0.2R; equivalence requires every full ambiguity "
            "difference band inside +/-0.2R and every decision/ambiguity-rate "
            "band inside +/-0.05; otherwise inconclusive"),
        "formula_scope": sweep_payload["martingale_benchmark"]["formula_scope"],
        "cells": cells,
    }
    return payload


def write_jsonl_atomic(path, rows):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    os.replace(tmp, path)


def launch_status_is_allowed(status):
    allowed = {"compile_id.txt", "compile_manifest.json"}
    lines = [line for line in status.splitlines() if line.strip()]
    return all(len(line) >= 4 and line[3:] in allowed
               and (line[3:] == "compile_manifest.json"
                    or "?" not in line[:2]) for line in lines)


def validate_compile_manifest(compile_id):
    with open("compile_manifest.json", encoding="utf-8") as handle:
        manifest = json.load(handle)
    assert manifest["compile_id"] == compile_id
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    assert manifest["git_head"] == head
    from d10_sync_compile import SOURCES
    expected = {}
    for remote, (local, _, _, _) in SOURCES.items():
        expected[remote] = hashlib.sha256(open(local, "rb").read()).hexdigest()
    assert manifest["source_sha256"] == expected
    return manifest


def assert_preregistered_head():
    status = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT).decode()
    assert launch_status_is_allowed(status), (
        f"unexpected worktree changes before launch: {status}")
    for name in ("RANDOM_TIME_CONTROL_PREREGISTRATION.md",
                 "random_time_control.py", "d45_random_time_control.py"):
        local = open(os.path.join(ROOT, name), "rb").read()
        committed = subprocess.check_output(
            ["git", "show", f"HEAD:{name}"], cwd=ROOT)
        assert local == committed, f"uncommitted preregistration input: {name}"
    divergence = subprocess.check_output(
        ["git", "rev-list", "--left-right", "--count", "origin/main...main"],
        cwd=ROOT).decode().strip()
    assert divergence == "0\t0", f"local/remote divergence: {divergence}"


def main():
    assert_preregistered_head()
    compile_id = open("compile_id.txt", encoding="utf-8").read().strip()
    validate_compile_manifest(compile_id)
    tags = {f"RTC2-FT32-{instrument}" for instrument in INSTRUMENTS}
    existing = {row["name"] for row in backtest_list(PID)}
    duplicates = sorted(tags & existing)
    assert not duplicates, f"duplicate remote experiments: {duplicates}"
    os.makedirs("random_time_ft_ledger", exist_ok=True)
    results, all_rows = [], []
    with open("random_time_ft_results.jsonl", "w", encoding="utf-8",
              newline="\n") as out:
        for instrument in INSTRUMENTS:
            params = launch_parameters(instrument)
            tag = f"RTC2-FT32-{instrument}"
            fresh = {row["name"] for row in backtest_list(PID)}
            assert tag not in fresh, f"duplicate appeared before create: {tag}"
            created = backtest_create(PID, tag, params, compile_id=compile_id)
            bid = created["backtest_id"]
            print(instrument, "submitted", bid, flush=True)
            bt = poll_backtest(PID, bid, max_wait=7200, poll_s=20)
            runtime = (bt or {}).get("runtimeStatistics") or {}
            status = str((bt or {}).get("status", ""))
            assert status.lower().replace(".", "") == "completed"
            error = str((bt or {}).get("error") or "")
            assert error in ("", "None"), f"{instrument}: {error}"
            rows = random_rows_from_chart(
                instrument, bid, int(runtime["n_ft_rows"]))
            validate_random_runtime(instrument, runtime, rows)
            write_jsonl_atomic(os.path.join(
                "random_time_ft_ledger", f"{instrument}_ft.jsonl"), rows)
            record = {"inst": instrument, "bid": bid, "status": status,
                      "error": error[:300], "n_ft_rows_retrieved": len(rows),
                      "rt": {key: str(value) for key, value in runtime.items()}}
            out.write(json.dumps(record, sort_keys=True) + "\n"); out.flush()
            results.append(record); all_rows.extend(rows)
            print(instrument, status, "| ft:", len(rows), flush=True)
    assert_unique_chart_rows(all_rows)
    sweep = json.load(open("e19br_ft_screen.json", encoding="utf-8"))
    payload = build_comparison_payload(results, all_rows, sweep)
    with open("random_time_ft_screen.json", "w", encoding="utf-8",
              newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True); handle.write("\n")
    reloaded_rows, reloaded_results = [], []
    for instrument in INSTRUMENTS:
        with open(os.path.join("random_time_ft_ledger",
                              f"{instrument}_ft.jsonl"), encoding="utf-8") as h:
            reloaded_rows.extend(json.loads(line) for line in h if line.strip())
    with open("random_time_ft_results.jsonl", encoding="utf-8") as handle:
        reloaded_results = [json.loads(line) for line in handle if line.strip()]
    assert payload == build_comparison_payload(
        reloaded_results, reloaded_rows, sweep)
    print("ALL RANDOM-TIME MARKETS DONE", len(all_rows),
          payload["surface_comparison"]["classification"], flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
