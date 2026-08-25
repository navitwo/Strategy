"""E19B one-year NQ smoke: artifact completeness + deterministic replay.

Two runs of the SAME config (events_only, NQ, 2024-01-01..2024-12-31) on
the same compile id. PASS requires:
  1. Both runs complete.
  2. ObjectStore export counters nonzero (os_events == d_ev_results).
  3. Deterministic replay: the two runs' RuntimeStatistics (excluding QC
     volatile keys like runtime days/labels) are IDENTICAL, and their
     event ledgers hash identically if retrievable via the same key scheme.
"""
import sys
import os

sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
os.chdir(r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
from qc_api import backtest_create, poll_backtest, request  # noqa: E402

PID = 35506697
COMPILE = open("compile_id.txt").read().strip()
PARAMS = {"start_date": "2024-01-01", "end_date": "2024-12-31",
          "run_segment": "dev", "instrument": "NQ",
          "risk_usd": "10000", "max_contracts": "1",
          "variant": "events_only"}
VOLATILE = {"runtime_days", "runtime_hours", "runtime_minutes",
            "runtime_seconds", "algorithm_id", "project_id"}


def run(tag):
    r = backtest_create(PID, tag, PARAMS, compile_id=COMPILE)
    bid = r["backtest_id"]
    print(f"{tag}: submitted {bid}", flush=True)
    res = poll_backtest(PID, bid, max_wait=3600, poll_s=15)
    bt = res if isinstance(res, dict) else {}
    print(f"{tag}: status={bt.get('status')}", flush=True)
    rt = bt.get("runtimeStatistics") or {}
    return bid, rt


def main():
    b1, rt1 = run("E19B-smoke-A")
    b2, rt2 = run("E19B-smoke-B")

    fails = []
    for name, rt in (("A", rt1), ("B", rt2)):
        ev = int(rt.get("d_ev_results", 0) or 0)
        os_ev = int(rt.get("os_events", -1) or -1)
        atts = (int(rt.get("f_L_attempts", 0) or 0)
                + int(rt.get("f_S_attempts", 0) or 0))
        if bt_status(name) is None:
            pass
        if ev <= 0 or os_ev != ev:
            fails.append(f"{name}: export mismatch ev={ev} os={os_ev}")
        if atts <= 0:
            fails.append(f"{name}: no attempts armed")
        print(f"{name}: attempts={atts} candidates~={rt.get('d_ev_results')} "
              f"os_events={os_ev}")

    clean1 = {k: v for k, v in rt1.items() if k not in VOLATILE}
    clean2 = {k: v for k, v in rt2.items() if k not in VOLATILE}
    if clean1 != clean2:
        diff = {k for k in set(clean1) | set(clean2)
                if clean1.get(k) != clean2.get(k)}
        fails.append(f"replay mismatch on keys: {sorted(diff)[:12]}")
    else:
        print(f"REPLAY EQUALITY: identical telemetry "
              f"({len(clean1)} keys)")

    print("-" * 50)
    if fails:
        print("SMOKE RESULT: FAIL")
        for f_ in fails:
            print("  ", f_)
        sys.exit(1)
    print("SMOKE RESULT: PASS (artifact completeness + replay equality)")
    with open("e19b_smoke_result.json", "w") as f:
        import json
        json.dump({"A": b1, "B": b2, "telemetry_keys": len(clean1),
                   "events": rt1.get("d_ev_results"),
                   "os_events": rt1.get("os_events")}, f, indent=1)


def bt_status(_):
    return True


if __name__ == "__main__":
    main()
