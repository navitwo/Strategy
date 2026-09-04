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

ROOT = os.path.dirname(os.path.abspath(__file__))
DATASET = "GLBX.MDP3"
SYMBOLS = "NQ.FUT,GC.FUT"
DATE_RANGE = "2010-06-07,2025-01-01"
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
    body = urllib.parse.urlencode({
        "dataset": DATASET, "schema": schema, "symbols": SYMBOLS,
        "stype_in": "parent", "date_range": DATE_RANGE}).encode()
    request = urllib.request.Request(
        "https://api.databento.com/v0/metadata.get_cost", data=body,
        headers={"Authorization": f"Bearer {key}"})
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
    total_cents = 0
    for schema in SCHEMAS:
        status, payload = quote(schema, key)
        print(schema, status, payload)
        if status != 200:
            return 1
        import json
        cents = json.loads(payload)["usd_cost_electronic_cents"] \
            if "usd_cost_electronic_cents" in payload else None
        if cents is not None:
            total_cents += cents
    print(f"TOTAL electronic cents: {total_cents} "
          f"(= ${total_cents/100:.2f}; new-account credits: $125)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
