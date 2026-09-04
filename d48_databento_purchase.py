"""Campaign 2: Databento bulk purchase — continuous NQ/GC 1m + definitions.

ONE logical transaction, authorized 2026-09-04 against a portal-verified
balance of $124.68 with a HARD CEILING OF $45 ENFORCED IN CODE:
metadata.get_cost is re-run immediately before submission and the purchase
aborts if the live quote exceeds MAX_USD, because quotes shift as the end
date rolls forward and a payment method is on file.

RESUMABLE: before submitting, each schema is matched against existing
account jobs (dataset+schema+symbols+stype_in+start+end). A matching job
that isn't failed is ADOPTED (poll + download), never resubmitted — a
crash between submit and download cannot cause a double charge.

Downloads (into git-ignored data/databento/):
  ohlcv-1m    NQ.n.0 + GC.n.0, 2010-06-07 -> 2026-09-04 (excl). Both
  definition schemas arrive as ZIP containers of per-UTC-day .dbn.zst
  members (observed 2026-09-04 regardless of the compression flag).

The API key is never echoed; every response body is scrubbed.
"""
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import d47_databento_quote as d47q
from databento import Historical

ROOT = Path(d47q.ROOT)
OUT_DIR = ROOT / "data" / "databento"
DATASET = "GLBX.MDP3"
CONTINUOUS = ["NQ.n.0", "GC.n.0"]
DATE_RANGE = ("2010-06-07", "2026-09-04")   # end exclusive
MAX_USD = 45.0                               # hard ceiling, user-authorized
JOBS = {
    # multi-file batch jobs arrive as a ZIP container of per-day .dbn.zst
    # members regardless of the compression flag (observed 2026-09-04)
    "ohlcv-1m": {"schema": "ohlcv-1m",
                 "out": "glbx-mdp3-ohlcv-1m.zip"},
    "definition": {"schema": "definition",
                   "out": "glbx-mdp3-definition.zip"},
}
TERMINAL_BAD = ("error", "cancelled")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def live_quote_usd(key: str) -> float:
    """Sum of get_cost over both schemas at the purchase-time range."""
    total = 0.0
    for name in JOBS:
        status, value = d47q.quote(JOBS[name]["schema"], key, "continuous",
                                   ",".join(CONTINUOUS), *DATE_RANGE)
        if status != 200:
            raise SystemExit(f"get_cost {name}: HTTP {status} {value}")
        total += value
    return total


def find_existing(hist, schema):
    """Return the id of an adoptable job matching this purchase exactly."""
    for j in hist.batch.list_jobs():
        if not isinstance(j, dict):
            continue
        if (j.get("dataset") == DATASET and j.get("schema") == schema
                and j.get("stype_in") == "continuous"
                and j.get("symbols") == ",".join(CONTINUOUS)):
            details = hist.batch.get_job_details(j["id"])
            if (str(details.get("start", "")).startswith(DATE_RANGE[0])
                    and str(details.get("end", "")).startswith(DATE_RANGE[1])
                    and details.get("state") not in TERMINAL_BAD):
                return details["id"], details["state"]
    return None, None


def wait_done(hist, job_id, name):
    while True:
        try:
            details = hist.batch.get_job_details(job_id)
        except Exception as exc:  # transient TLS resets happen (observed
            print(f"{name}: poll error {type(exc).__name__}; retrying",
                  flush=True)
            time.sleep(10)
            continue
        state = details.get("state")
        if state in ("done",) or state in TERMINAL_BAD:
            return details
        print(f"{name}: {state} {details.get('progress')}", flush=True)
        time.sleep(15)


def download_resilient(hist, job_id, name, out_dir):
    last = None
    for attempt in range(4):
        try:
            return [Path(p) for p in hist.batch.download(
                job_id, output_dir=str(out_dir), keep_zip=True)]
        except Exception as exc:
            last = exc
            print(f"{name}: download attempt {attempt + 1} failed "
                  f"({type(exc).__name__}); retrying", flush=True)
            time.sleep(15)
    raise last


def main() -> int:
    if os.environ.get("CONFIRM") != "1":
        print("refusing: set CONFIRM=1 to authorize this ONE-time purchase")
        return 2
    paths = {name: OUT_DIR / spec["out"] for name, spec in JOBS.items()}
    if all(p.exists() for p in paths.values()):
        print("refusing: purchase files already on disk (no re-buy)")
        return 2
    key = d47q._key()

    # --- ceiling check runs IMMEDIATELY before any submission ---
    quote = live_quote_usd(key)
    print(f"live get_cost total: ${quote:.4f} USD (ceiling ${MAX_USD:.2f})")
    if quote > MAX_USD:
        print("ABORT: live quote exceeds the authorized ceiling — no request "
              "was submitted, nothing charged")
        return 3
    # DATABENTO_BUDGET.md rule 1, enforced: portal re-verification of the
    # real balance is a human step; above $10 the code REFUSES to run
    # without the operator asserting it was done.
    if quote > 10.0 and os.environ.get("DATABENTO_PORTAL_REVERIFIED") != "1":
        print("ABORT: quote > $10 and DATABENTO_PORTAL_REVERIFIED!=1 — "
              "check https://databento.com/portal/billing, then re-run with "
              "the flag set (DATABENTO_BUDGET.md rule 1)")
        return 4

    hist = Historical(key)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, spec in JOBS.items():
        target = paths[name]
        job_id, state = find_existing(hist, spec["schema"])
        if job_id:
            print(f"{name}: adopting existing job {job_id} (state={state}) "
                  f"— NOT resubmitting")
        else:
            print(f"{name}: submitting...")
            submitted = hist.batch.submit_job(
                dataset=DATASET,
                symbols=CONTINUOUS,
                schema=spec["schema"],
                start=DATE_RANGE[0],
                end=DATE_RANGE[1],
                stype_in="continuous",
                stype_out="instrument_id",
                encoding="dbn",
                compression="zstd",
            )
            job_id = submitted["id"]
            print(f"{name}: job {job_id}")
        details = wait_done(hist, job_id, name)
        if details.get("state") != "done":
            print(f"{name}: FAILED state={details.get('state')}")
            return 1
        produced = download_resilient(hist, job_id, name, OUT_DIR)
        if len(produced) != 1:
            print(f"{name}: expected 1 downloaded file, got "
                  f"{[p.name for p in produced]}")
            return 1
        produced[0].replace(target)
        manifest[name] = {
            "job_id": job_id,
            "file": target.name,
            "bytes": target.stat().st_size,
            "sha256": sha256(target),
            "cost_usd": details.get("cost_usd"),
        }
        print(f"{name}: {target.name} {manifest[name]['bytes']:,} bytes "
              f"cost_usd={details.get('cost_usd')}")

    (OUT_DIR / "manifest.json").write_text(json.dumps({
        "purchased": "2026-09-04",
        "dataset": DATASET, "stype_in": "continuous",
        "symbols": CONTINUOUS, "date_range": list(DATE_RANGE),
        "quote_usd_at_purchase": quote, "ceiling_usd": MAX_USD,
        "files": manifest,
    }, indent=2))
    print("manifest written: data/databento/manifest.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
