"""Free Databento cost quotes + billing balance. Zero data downloaded.

Calls metadata.get_cost (and optionally billing.balance) only — nothing is
purchased or pulled. The API key is read from an environment variable or an
ignored *.env file, validated by git check-ignore, and NEVER printed,
hashed, or logged. Auth per official docs: HTTP Basic, key as username.

Usage:
  python d47_databento_quote.py                          # frozen C2 parent quote
  python d47_databento_quote.py --stype-in continuous \
      --symbols NQ.n.0,GC.n.0 --end 2026-09-05 --balance
"""
import argparse
import base64
import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
BASE = "https://hist.databento.com/v0"
DATASET = "GLBX.MDP3"
SCHEMAS = ("ohlcv-1m", "definition")


def _key():
    value = os.environ.get("DATABENTO_API_KEY", "").strip()
    if value:
        return value
    env_path = os.path.join(ROOT, "databento_credentials.env")
    if os.path.exists(env_path):
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", "databento_credentials.env"],
            cwd=ROOT)
        if ignored.returncode != 0:
            # explicit raise, not assert: python -O must not skip this guard
            raise SystemExit(
                "credentials file is NOT git-ignored; refusing to read it")
        for line in open(env_path, encoding="utf-8"):
            name, _, got = line.strip().partition("=")
            if name == "DATABENTO_API_KEY" and got.strip():
                return got.strip()
    raise SystemExit(
        "DATABENTO_API_KEY not found. Set the env var or create an ignored "
        "databento_credentials.env (pattern *.env is already git-ignored).")


def _get(path, key, params=None):
    """GET (or POST when params) against BASE; returns (status, scrubbed body)."""
    data = urllib.parse.urlencode(params).encode() if params else None
    basic = base64.b64encode(f"{key}:".encode()).decode()
    request = urllib.request.Request(
        f"{BASE}/{path}", data=data,
        headers={"Authorization": f"Basic {basic}"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read().decode(errors="replace")
            # scrub on both paths so the key-never-printed guarantee is
            # uniform, not just defensive on error bodies
            return response.status, body.replace(key, "[redacted]")
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace").replace(key, "[redacted]")
        return error.code, detail


def quote(schema, key, stype_in, symbols, start, end):
    """metadata.get_cost for one schema; returns (status, USD float or text)."""
    status, body = _get("metadata.get_cost", key, {
        "dataset": DATASET, "schema": schema, "symbols": symbols,
        "stype_in": stype_in, "start": start, "end": end})
    if status != 200:
        return status, body
    # metadata.get_cost returns a plain USD float (docs: -> float)
    return status, float(body.strip())


def balance(key):
    """Best-effort billing balance from the API (same number the billing page
    shows). Returns (status, parsed-dict-or-text)."""
    status, body = _get("billing.balance", key)
    if status != 200:
        return status, body
    try:
        return status, json.loads(body)
    except ValueError:
        return status, body


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stype-in", default="parent",
                        help="parent | instrument_id | continuous (default parent)")
    parser.add_argument("--symbols", default="NQ.FUT,GC.FUT",
                        help="comma-separated symbols in stype_in")
    parser.add_argument("--start", default="2010-06-07")
    parser.add_argument("--end", default="2025-01-01",
                        help="EXCLUSIVE date")
    parser.add_argument("--balance", action="store_true",
                        help="also fetch billing.balance (real credit state)")
    args = parser.parse_args()

    key = _key()
    total_usd = 0.0
    for schema in SCHEMAS:
        status, value = quote(schema, key, args.stype_in, args.symbols,
                              args.start, args.end)
        if status != 200:
            print(schema, status, value)
            return 1
        print(f"{schema} ({args.stype_in}: {args.symbols} {args.start}→"
              f"{args.end} excl.): {value:.4f} USD")
        total_usd += value
    print(f"TOTAL: ${total_usd:.4f} USD")
    if args.balance:
        status, value = balance(key)
        print(f"billing.balance: HTTP {status} {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
