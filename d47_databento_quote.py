"""Free exact Databento cost quote for the Campaign-2 NQ+GC pull.

Zero bytes of market data are downloaded and nothing is purchased: this
calls metadata.get_cost only. The API key is read from an environment
variable or an ignored *.env file, validated by git check-ignore, and
NEVER printed, hashed, or logged.
"""
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

import base64
import json

ROOT = os.path.dirname(os.path.abspath(__file__))
BASE = "https://hist.databento.com/v0"
DATASET = "GLBX.MDP3"
SYMBOLS = "NQ.FUT,GC.FUT"
START = "2010-06-07"
END = "2025-01-01"          # exclusive: dev interval through 2024-12-31
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


def quote(schema, key):
    # official auth: HTTP Basic with the API key as username, empty password
    basic = base64.b64encode(f"{key}:".encode()).decode()
    body = urllib.parse.urlencode({
        "dataset": DATASET, "schema": schema, "symbols": SYMBOLS,
        "stype_in": "parent", "start": START, "end": END}).encode()
    request = urllib.request.Request(
        f"{BASE}/metadata.get_cost", data=body,
        headers={"Authorization": f"Basic {basic}"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read().decode(errors="replace")
            # scrub on both paths so the key-never-printed guarantee is
            # uniform, not just defensive on error bodies
            return response.status, body.replace(key, "[redacted]")
    except urllib.error.HTTPError as error:
        # response bodies from Databento are non-secret error details, but
        # scrub defensively just in case a header ever echoes into them.
        detail = error.read().decode(errors="replace").replace(key, "[redacted]")
        return error.code, detail


def main():
    key = _key()
    total_usd = 0.0
    for schema in SCHEMAS:
        status, payload = quote(schema, key)
        if status != 200:
            print(schema, status, payload)
            return 1
        # metadata.get_cost returns a plain USD float (docs: -> float)
        usd = float(payload.strip())
        print(f"{schema}: {usd:.4f} USD")
        total_usd += usd
    print(f"TOTAL: ${total_usd:.4f} USD (new-account credits: $125.00)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
