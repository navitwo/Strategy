"""Run, retrieve, and fail-closed-gate the side-capture export.

The side-capture export re-derives the frozen E19B-R aligned H=120 population
(the same 1,121 events) with two extra fields packed into the high float64
bits: numeric +/-1 side (long/short) and a session-type flag (ordinary RTH vs
holiday / shifted-schedule). Because it is a re-derivation of a FROZEN artifact,
the low-32-bit FT32 vector, the chart_x identities, and the codes must
reproduce the committed e19br_ft_ledger byte-for-byte. Any differing event
means the engine is not deterministic across the side-capture change, and the
correct response is to STOP (fail closed), never to reconcile.
"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from d44_e19b_ft import CELLS, OUTCOME, decode_ft_value
from qc_api import backtest_create, backtest_list, chart_read, poll_backtest
from side_capture import SIDE_CAPTURE_SPEC_VERSION, unpack_side_payload

PID = 35506697
INSTRUMENTS = ("NQ", "ES", "YM", "RTY")
MIN_TICKS = {"NQ": 8, "ES": 8, "YM": 6, "RTY": 12}
# Frozen E19B-R population identities per market (aligned H=120 events).
FROZEN_POPULATION = {"NQ": 388, "ES": 186, "YM": 376, "RTY": 171}
FROZEN_TOTAL = 1121


def launch_parameters(instrument):
    return {
        "start_date": "2010-01-01", "end_date": "2024-12-31",
        "run_segment": "dev", "instrument": instrument,
        "risk_usd": "10000", "max_contracts": "1",
        "variant": "side_capture",
        "min_stop_ticks": str(MIN_TICKS[instrument]),
        "floor_atr_frac": "0.10",
    }


def side_rows_from_chart(instrument, backtest_id, expected_count):
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
        f"side-capture chart incomplete: expected={expected_count}, "
        f"got={len(points)}")
    rows = []
    for row_index, point in enumerate(points):
        x = point.get("x") if isinstance(point, dict) else point[0]
        y = point.get("y") if isinstance(point, dict) else point[1]
        raw = float(y); packed = int(raw)
        assert raw == packed and 0 <= packed < 2 ** 52
        meta = unpack_side_payload(packed)
        ft32 = meta["ft32"]
        codes = decode_ft_value(ft32)
        rows.append({
            "instrument": instrument, "ft_row": row_index,
            "chart_x": int(x), "packed_exact": packed,
            "packed_uint32": ft32, "codes": codes,
            "cells": {key: OUTCOME[codes[i]]
                      for i, (key, _, _) in enumerate(CELLS)},
            "side": meta["side"], "session_type": meta["session_type"],
        })
    return rows


def load_frozen_ledger(instrument):
    path = os.path.join("e19br_ft_ledger", f"{instrument}_ft.jsonl")
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def gate_side_capture_population(rows):
    """Fail-closed byte-exact reproduction of the frozen 1,121 population.

    The side-capture run must reproduce the committed FT32E ledger exactly:
    same per-market counts, same chart_x identities, same codes, same
    packed_uint32. Any discrepancy raises AssertionError (STOP, not reconcile).
    """
    by_inst = {}
    for row in rows:
        by_inst.setdefault(row["instrument"], []).append(row)
    total = 0
    seen_keys = set()
    for instrument in INSTRUMENTS:
        market = by_inst.get(instrument, [])
        frozen = load_frozen_ledger(instrument)
        assert len(frozen) == FROZEN_POPULATION[instrument], (
            f"frozen ledger count mismatch for {instrument}")
        assert len(market) == len(frozen), (
            f"{instrument}: side-capture reproduced {len(market)} rows, "
            f"frozen has {len(frozen)} -- STOP (engine not deterministic)")
        total += len(market)
        frozen_by_x = {int(row["chart_x"]): row for row in frozen}
        assert len(frozen_by_x) == len(frozen), (
            f"{instrument}: frozen ledger chart_x duplicates")
        for row in market:
            chart_x = int(row["chart_x"])
            key = (instrument, chart_x)
            assert key not in seen_keys, f"duplicate identity {key}"
            seen_keys.add(key)
            assert chart_x in frozen_by_x, (
                f"{instrument}: side-capture chart_x {chart_x} absent from "
                "frozen ledger -- STOP (differing event identity)")
            frozen_row = frozen_by_x[chart_x]
            assert int(row["packed_uint32"]) == int(frozen_row["packed_uint32"]), (
                f"{instrument}@{chart_x}: packed_uint32 differs -- STOP")
            assert list(row["codes"]) == list(frozen_row["codes"]), (
                f"{instrument}@{chart_x}: codes differ -- STOP")
    assert total == FROZEN_TOTAL, (
        f"side-capture reproduced {total} rows, frozen total is "
        f"{FROZEN_TOTAL} -- STOP")
    return total


def main():
    from d45_random_time_control import (assert_preregistered_head,
                                         validate_compile_manifest)
    assert_preregistered_head()
    compile_id = open("compile_id.txt", encoding="utf-8").read().strip()
    validate_compile_manifest(compile_id)
    tags = {f"SIDECAP-FT32-{instrument}" for instrument in INSTRUMENTS}
    existing = {row["name"] for row in backtest_list(PID)}
    duplicates = sorted(tags & existing)
    assert not duplicates, f"duplicate remote experiments: {duplicates}"
    os.makedirs("side_capture_ledger", exist_ok=True)
    results, all_rows = [], []
    with open("side_capture_results.jsonl", "w", encoding="utf-8",
              newline="\n") as out:
        for instrument in INSTRUMENTS:
            params = launch_parameters(instrument)
            tag = f"SIDECAP-FT32-{instrument}"
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
            assert int(runtime.get("n_ft_rows", -1)) == FROZEN_POPULATION[instrument]
            assert runtime.get("side_capture_spec_version") == SIDE_CAPTURE_SPEC_VERSION
            rows = side_rows_from_chart(
                instrument, bid, int(runtime["n_ft_rows"]))
            with open(os.path.join(
                    "side_capture_ledger", f"{instrument}_side.jsonl"),
                    "w", encoding="utf-8", newline="\n") as ledger:
                for row in rows:
                    ledger.write(json.dumps(row, sort_keys=True) + "\n")
            record = {"inst": instrument, "bid": bid, "status": status,
                      "error": error[:300],
                      "n_ft_rows_retrieved": len(rows),
                      "rt": {key: str(value) for key, value in runtime.items()}}
            out.write(json.dumps(record, sort_keys=True) + "\n"); out.flush()
            results.append(record); all_rows.extend(rows)
            print(instrument, status, "| ft:", len(rows), flush=True)
    # Fail-closed byte-exact population gate: STOP on any divergence.
    total = gate_side_capture_population(all_rows)
    reloaded_rows = []
    for instrument in INSTRUMENTS:
        path = os.path.join("side_capture_ledger",
                            f"{instrument}_side.jsonl")
        with open(path, encoding="utf-8") as handle:
            reloaded_rows.extend(json.loads(line) for line in handle if line.strip())
    assert gate_side_capture_population(reloaded_rows) == total
    print("ALL SIDE-CAPTURE MARKETS DONE; byte-exact population reproduced:",
          total, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())