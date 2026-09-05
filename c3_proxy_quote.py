"""Gate A: free metadata.get_cost quotes for the C3 absorption-proxy pass.

Implements C3_ABSORPTION_PROXY_PROTOCOL.md section 2 exactly:
  1-4  full-range trades / mbp-10 quotes for NQ.n.0 and ES.n.0
  5a-b conditional-window quotes: sum of per-merged-window get_cost calls
     over the 2,611 merged +/-60-minute windows (nq_event_windows.json)

metadata.get_cost is a metadata endpoint: zero data purchased, nothing
downloaded. The API key is read via d47's guarded loader (env or
git-ignored file, validated by git check-ignore) and NEVER printed.

Usage:
  python c3_proxy_quote.py full        # items 1-4
  python c3_proxy_quote.py conditional # items 5a-5b (threaded; resumable)
"""
import json
import os
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import base64
from concurrent.futures import ThreadPoolExecutor

import d47_databento_quote as d47  # reuse guarded key loader + quote()

ROOT = os.path.dirname(os.path.abspath(__file__))
DATASET = "GLBX.MDP3"
FULL_START, FULL_END = "2010-06-07", "2026-09-04"  # end exclusive
OUT_FULL = os.path.join(ROOT, "c3_proxy_quotes_full.json")
OUT_COND = os.path.join(ROOT, "c3_proxy_quotes_conditional.json")
COND_PROGRESS = OUT_COND + ".progress"


def get_cost_raw(key, schema, symbol, start, end):
    """One get_cost call; returns (ok, usd_or_err) — never leaks the key."""
    params = {"dataset": DATASET, "schema": schema, "symbols": symbol,
              "stype_in": "continuous", "start": start, "end": end}
    url = f"{d47.BASE}/metadata.get_cost?" + urllib.parse.urlencode(params)
    basic = base64.b64encode(f"{key}:".encode()).decode()
    req = urllib.request.Request(url, headers={"Authorization": f"Basic {basic}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode().replace(key, "[redacted]")
            return True, float(body.strip())
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: " + e.read().decode(errors="replace").replace(key, "[redacted]")[:200]
    except Exception as e:  # noqa: BLE001 — record, abort-sum decides
        return False, f"{type(e).__name__}: {e}"


def do_full():
    key = d47._key()
    out = {}
    for symbol in ("NQ.n.0", "ES.n.0"):
        for schema in ("trades", "mbp-10"):
            ok, val = get_cost_raw(key, schema, symbol, FULL_START, FULL_END)
            print(f"{symbol} {schema} full-range: "
                  + (f"${val:.4f}" if ok else f"FAIL {val}"), flush=True)
            out[f"{symbol}|{schema}"] = {"ok": ok, "usd": val if ok else None,
                                         "error": None if ok else val}
    json.dump(out, open(OUT_FULL, "w"), indent=1)
    print("saved", OUT_FULL)
    return 0


def do_conditional(workers=8):
    key = d47._key()
    windows = json.load(open(os.path.join(ROOT, "nq_event_windows.json")))
    done = set()
    sums = {"trades": 0.0, "mbp-10": 0.0}
    if os.path.exists(COND_PROGRESS):
        done = {tuple(w) for w in json.load(open(COND_PROGRESS))["done"]}
        sums = json.load(open(COND_PROGRESS))["sums"]
    print(f"windows: {len(windows)}, already done: {len(done)}", flush=True)
    lock = threading.Lock()
    fails = []
    counter = [0]

    def work(w):
        with lock:
            if tuple(w) in done:
                return
        for schema in ("trades", "mbp-10"):
            ok, val = get_cost_raw(key, schema, "NQ.n.0", w[0], w[1])
            with lock:
                if ok:
                    sums[schema] += val
                else:
                    fails.append((schema, w[0], val))
        with lock:
            done.add(tuple(w))
            counter[0] += 1
            if counter[0] % 100 == 0:
                print(f"  {counter[0]} windows...", flush=True)
                json.dump({"done": sorted(done), "sums": sums},
                          open(COND_PROGRESS, "w"))

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(work, windows))
    json.dump({"done": sorted(done), "sums": sums}, open(COND_PROGRESS, "w"))
    result = {"n_windows": len(windows), "n_done": len(done),
              "trades_usd": round(sums["trades"], 4),
              "mbp10_usd": round(sums["mbp-10"], 4),
              "failures": fails[:20], "n_failures": len(fails)}
    json.dump(result, open(OUT_COND, "w"), indent=1)
    print(json.dumps(result, indent=1))
    return 1 if fails else 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"
    raise SystemExit(do_full() if mode == "full" else do_conditional())
