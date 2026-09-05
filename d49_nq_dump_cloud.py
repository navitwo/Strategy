"""d49: run the guard-(c) cloud extension — NQ/GC 30m bar dumps on
QuantConnect LEAN cloud (the compute authority's own data path) — and
materialize each run as a reconciliation fixture.

The algorithm (c2_nq_dump_main.py) is a pure data dump: one future
subscription (OPEN_INTEREST/RAW, mirrored verbatim from scifvg_main),
LEAN-native 30m consolidation, zero orders, zero signals. Windows are
DEV-segment only (DEV_END=2024-12-31). Cloud minutes on the existing
subscription; zero Databento spend.

Runs (frozen, 2026-09-04; roll/holiday facts MEASURED from the dumps
themselves, not assumed — an assumed 2024-11-25 NQ roll turned out
false, which is why run 'nq-holiday' carries no roll and 'nq-roll'
exists):
  nq-holiday  NQ 2024-11-15..2024-12-05  ordinary sessions plus the
              Thanksgiving 2024-11-28 (38 bars) / Black Friday 11-29
              (39 bars) early closes; zero mapping events.
  nq-roll     NQ 2024-12-16..2024-12-30  the directive's roll+holiday
              window: ROLL NQZ4->H5 (local stream switches 2024-12-18
              19:00 ET; LEAN's event measured 2024-12-19 00:00 ET —
              same trade session, documented vendor divergence) AND
              Christmas (Eve early-close 39 bars, Dec 25 fully absent,
              26-27 full). End 12-30 keeps session 2025-01-01 (the
              first validation session) out of the fixture entirely.
  gc-roll     GC 2020-01-15..2020-01-31  ROLL GCG0->GCJ0 (local
              2020-01-23 19:00 ET) plus MLK 2020-01-20 early close.
              LEAN shows ZERO GC mapping events through 01-31.
  gc-roll-b   GC 2020-02-01..2020-02-14  follow-on: LEAN's GC events
              measured 2020-02-06/07; paths converge BIT-EXACT from
              2020-02-10. The local Lean bundle has no GC files near
              the roll date, so the cloud dump is the ONLY guard-(c)
              coverage of a GC roll.

Bar TRANSPORT is the chart series "dump-bars" (o/h/l/c), NOT
RuntimeStatistics values: a first attempt proved RT strings are silently
capped at 200 chars (94 of 676 rows survived, mid-number). Chart reads
poll until every series delivers the declared n_bars5 points and reject
partial results (C1's ft_rows_from_chart pattern — retrieved == declared
or fail).

Fixture (data/databento/dump_<tag>.json, git-ignored dir, sha recorded
in DATABENTO_BUDGET.md): {runtimeStatistics, bars: [{et, o,h,l,c}]}.

Project discipline: a DEDICATED dump project — cloud backtests always
compile/run main.py, and campaign project 35506697's main.py is the
ARCHIVED frozen engine (its fail-closed variant guard rejected an early
misdirected submission: RuntimeError 'archived trading variant', zero
compute, zero file changes). Archived projects stay byte-frozen.

Duplicate-safe: refuses to re-create a backtest with the frozen name
(reads the existing result instead).
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qc_api  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_NAME = "C2 Guard-c NQ Bar Dump"
MAIN_FILE = "main.py"

RUNS = {
    "nq-holiday": {"root": "NQ", "start": "2024-11-15", "end": "2024-12-05"},
    # end 2024-12-30, NOT 12-31: bars ending 18:30+ ET on Dec 31 belong to
    # trade session 2025-01-01 (validation) -- the dump must not publish
    # even the shape of a locked session. Dec 30's evening bars are the
    # overnight of session 2024-12-31 (DEV, inside the population).
    "nq-roll": {"root": "NQ", "start": "2024-12-16", "end": "2024-12-30"},
    "gc-roll": {"root": "GC", "start": "2020-01-15", "end": "2020-01-31"},
    # FINDING (2026-09-04, first reconciliation): LEAN published GC with
    # ZERO mapping events through 2020-01-31 while the local Databento
    # open-interest stream switched GCG0->GCJ0 at 2020-01-23 19:00 ET.
    # This follow-on window locates the cloud's ACTUAL roll date so the
    # disagreement is quantified on both sides, not just one.
    "gc-roll-b": {"root": "GC", "start": "2020-02-01", "end": "2020-02-14"},
}

EPOCH = datetime(1970, 1, 1)


def fixture_path(tag):
    return os.path.join(HERE, "data", "databento", f"dump_{tag}.json")


def read_chart_bars(pid, bt_id, declared):
    """Poll chart 'dump-bars' until every series has `declared` points;
    fail closed on partial results (never reconcile a truncated dump).
    Bar identity: the "t" series carries the exact naive-ET-as-UTC epoch
    (float64-exact integer seconds); x only orders points."""
    keys = ("o", "h", "l", "c", "t")
    vals = {}
    for attempt in range(60):
        payload = qc_api.chart_read(pid, bt_id, "dump-bars",
                                    count=declared, start=0, end=2147483647)
        status = str(payload.get("status") or "").lower()
        if payload.get("success") is False and status != "loading":
            raise SystemExit(f"chart read failed: {payload.get('errors')}")
        series = payload.get("chart", {}).get("series", {})
        vals = {k: series.get(k, {}).get("values", []) for k in keys}
        if all(len(v) == declared for v in vals.values()):
            break
        time.sleep(3)
    else:
        raise SystemExit(f"chart incomplete after 60 polls: "
                         f"{ {k: len(v) for k, v in vals.items()} } != "
                         f"declared {declared}")

    def yv(k, i):
        p = vals[k][i]
        return float(p["y"] if isinstance(p, dict) else p[1])

    def xv(k, i):
        p = vals[k][i]
        return float(p["x"] if isinstance(p, dict) else p[0])

    bars = []
    for i in range(declared):
        et = EPOCH + timedelta(seconds=yv("t", i))
        bars.append({"et": et.isoformat(),
                     "o": round(yv("o", i), 2),
                     "h": round(yv("h", i), 2),
                     "l": round(yv("l", i), 2),
                     "c": round(yv("c", i), 2)})
    # timestamps exact integers, strictly ordered, x aligned with t
    ts = [yv("t", i) for i in range(declared)]
    assert all(t == int(t) for t in ts), "epoch series not integral"
    assert ts == sorted(ts) and len(set(ts)) == len(ts), "t disorder"
    for i in range(declared):
        for k in ("h", "l", "c", "t"):
            assert abs(xv(k, i) - xv("o", i)) < 1e-6, \
                ("series x misaligned", i, k)
    return bars


def run(tag, cfg, pid, compile_id):
    name = f"c2-{tag}"
    out = fixture_path(tag)
    existing = qc_api.backtest_list(pid)
    match = [b for b in existing if b["name"] == name]
    if match:
        bt_id = match[0]["backtest_id"]
        bt = qc_api.poll_backtest(pid, bt_id)
        rt_prev = bt.get("runtimeStatistics") or {}
        if "b5_days" not in rt_prev:
            # stale first-generation run (RT-value transport, truncated
            # at 200 chars). Deleting/resubmitting our OWN dump-project
            # backtest costs no billed spend -- the no-resubmit rule
            # governs Databento batch jobs.
            print(f"{tag}: deleting stale pre-chart-transport backtest "
                  f"{bt_id} and resubmitting")
            qc_api.backtest_delete(pid, bt_id)
            match = []
        else:
            print(f"{tag}: backtest exists ({bt_id}) — reading, never "
                  "resubmitting")
    if not match:
        created = qc_api.backtest_create(
            pid, name,
            parameters={"dump_root": cfg["root"],
                        "dump_start": cfg["start"],
                        "dump_end": cfg["end"]},
            compile_id=compile_id)
        bt_id = created["backtest_id"]
        print(f"{tag}: backtest {bt_id} submitted")
        bt = qc_api.poll_backtest(pid, bt_id)
    st = str(bt.get("status", "")).replace(".", "").strip().lower()
    print(f"{tag}: status {bt.get('status')}")
    if st != "completed" or bt.get("completed") is not True:
        print(json.dumps({k: bt.get(k) for k in
                          ("error", "stacktrace", "status")},
                         indent=2)[:3000])
        raise SystemExit(4)
    rt = bt.get("runtimeStatistics") or {}
    declared = int(rt["n_bars5"])
    bars = read_chart_bars(pid, bt_id, declared)
    # monotonic, unique end times; declared-count equality already proven
    ets = [b["et"] for b in bars]
    assert ets == sorted(ets) and len(set(ets)) == len(ets), "et disorder"
    fixture = {"runtimeStatistics": rt, "bars": bars,
               "pid": pid, "backtest_id": bt_id,
               "retrieved_at": datetime.now(timezone.utc)
                                 .isoformat(timespec="seconds")}
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(fixture, fh)
    print(f"{tag}: saved {out} — n_bars5={declared} (chart-reconciled) "
          f"rolls={rt.get('b5_roll_count')} tzfirst={rt.get('tzcheck_first')}")
    print(f"{tag}: rolls {rt.get('b5_rolls')}")
    print(f"{tag}: days {rt.get('b5_days')}")


def main():
    tags = sys.argv[1:] or list(RUNS)
    assert qc_api.authenticate()["ok"], "QC auth failed"

    projects = qc_api.list_projects()
    cand = [p for p in projects if p["name"] == PROJECT_NAME]
    if not cand:
        org = projects[0]["organization_id"]   # same org as all campaigns
        qc_api.create_project(PROJECT_NAME, org)
        # create-success shape is not trustworthy for ids (same lesson as
        # backtests/create): reconcile via list, NEVER re-create
        cand = [p for p in qc_api.list_projects() if p["name"] == PROJECT_NAME]
    if len(cand) != 1:
        raise SystemExit(f"expected exactly 1 {PROJECT_NAME!r} project, "
                         f"found {len(cand)} — not proceeding blind")
    pid = cand[0]["project_id"]
    print("dump project", pid)

    content = open(os.path.join(HERE, "c2_nq_dump_main.py"),
                   encoding="utf-8").read()
    qc_api.sync_file(pid, MAIN_FILE, content)
    compile_id = qc_api.compile_create(pid)["compile_id"]
    comp = qc_api.poll_compile(pid, compile_id)
    print("compile:", json.dumps(comp)[:800])
    if not comp.get("ok"):
        raise SystemExit(3)

    for tag in tags:
        run(tag, RUNS[tag], pid, compile_id)


if __name__ == "__main__":
    main()
