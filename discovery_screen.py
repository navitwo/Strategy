"""Offline decoder and family summaries for pluggable discovery exports."""

import time

from d44_e19b_ft import (CELLS, OUTCOME, decode_ft_value, summarize_ft_rows,
                         validate_ft_ledger, PID)
from event_predicates import (resolve_event_predicates,
                              validate_discovery_predicates,
                              unpack_discovery_payload)
from qc_api import chart_read


def decode_discovery_points(instrument, points, predicate_names):
    predicate_names = resolve_event_predicates(
        ",".join(str(name) for name in predicate_names))
    validate_discovery_predicates("discovery_only", predicate_names)
    rows = []
    for row_index, point in enumerate(points):
        x = point.get("x") if isinstance(point, dict) else point[0]
        y = point.get("y") if isinstance(point, dict) else point[1]
        ft32, mask = unpack_discovery_payload(y)
        if not mask & 1 or mask >= (1 << len(predicate_names)):
            raise ValueError(
                f"predicate mask {mask:b} conflicts with run manifest")
        codes = decode_ft_value(ft32)
        rows.append({
            "instrument": instrument,
            "ft_row": row_index,
            "chart_x": x,
            "packed_ft_uint32": ft32,
            "event_predicate_mask": mask,
            "matched_event_predicates": [
                name for i, name in enumerate(predicate_names)
                if mask & (1 << i)],
            "codes": codes,
            "cells": {key: OUTCOME[codes[i]]
                      for i, (key, _, _) in enumerate(CELLS)},
        })
    return rows


def discovery_rows_from_chart(instrument, backtest_id, expected_count,
                              predicate_names, read_chart=None, sleep=None):
    assert int(expected_count) > 0, \
        f"non-positive expected discovery rows: {expected_count}"
    read_chart = read_chart or chart_read
    sleep = sleep or time.sleep
    points = []
    for attempt in range(30):
        payload = read_chart(PID, backtest_id, "E19B-FT",
                             count=int(expected_count), start=0,
                             end=2147483647)
        status = str(payload.get("status") or "").lower()
        if payload.get("success") is False and status != "loading":
            raise RuntimeError(f"chart read failed: {payload.get('errors')}")
        points = payload.get("chart", {}).get("series", {}).get(
            "a", {}).get("values", [])
        if len(points) == int(expected_count):
            break
        if attempt < 29:
            sleep(2)
    assert len(points) == int(expected_count), \
        f"discovery chart incomplete: expected={expected_count}, got={len(points)}"
    return decode_discovery_points(instrument, points, predicate_names)


def summarize_discovery_rows(rows, predicate_names):
    output = {}
    for name in predicate_names:
        family_rows = [row for row in rows
                       if name in row["matched_event_predicates"]]
        output[name] = {
            "n_ft_rows": len(family_rows),
            "status": "NONEMPTY" if family_rows else "EMPTY",
            "cells": summarize_ft_rows(family_rows) if family_rows else {},
        }
    return output


def validate_discovery_ledger(runtime, rows, predicate_names):
    names = resolve_event_predicates(
        ",".join(str(name) for name in predicate_names))
    validate_discovery_predicates("discovery_only", names)
    validate_ft_ledger(runtime, rows)
    assert runtime.get("event_predicates") == ",".join(names), \
        "runtime predicate manifest does not match decoder manifest"
    keys = [(row.get("instrument"), row.get("chart_x")) for row in rows]
    assert all(inst is not None and x is not None for inst, x in keys), \
        "discovery row lacks instrument/chart_x identity"
    assert len(set(keys)) == len(keys), "duplicate discovery chart identity"
    assert all(names[0] in row.get("matched_event_predicates", [])
               for row in rows), "discovery row missing base-population bit"
