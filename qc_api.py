"""Secret-safe QuantConnect Cloud API v2 client.

Rules:
- Credentials loaded ONLY from quantconnect_credentials.env in project root (or QC_* env vars).
- Never print/return tokens, hashes, Authorization payloads, or raw auth response bodies.
- Regenerate timestamp/hash per request. Retry only transient errors.
- All public helpers return sanitized data only.
"""
import base64
import hashlib
import json
import os
import time
from pathlib import Path

import requests

API = "https://www.quantconnect.com/api/v2"
ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / "quantconnect_credentials.env"
_TRANSIENT = {429, 500, 502, 503, 504}
MAX_RETRIES = 3

_cache = {}


def _load_creds():
    if "uid" in _cache:
        return _cache["uid"], _cache["tok"]
    uid = os.environ.get("QC_USER_ID")
    tok = os.environ.get("QC_API_TOKEN")
    if not uid or not tok:
        if ENV_FILE.exists():
            for line in ENV_FILE.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k == "QC_USER_ID" and not uid:
                    uid = v
                elif k == "QC_API_TOKEN" and not tok:
                    tok = v
        if not uid or not tok:
            raise RuntimeError("QuantConnect credentials not found")
    _cache["uid"], _cache["tok"] = uid, tok
    return uid, tok


def _auth_headers():
    uid, tok = _load_creds()
    ts = str(int(time.time()))
    h = hashlib.sha256(f"{tok}:{ts}".encode()).hexdigest()
    b64 = base64.b64encode(f"{uid}:{h}".encode()).decode()
    return {"Authorization": f"Basic {b64}", "Timestamp": ts}


def request(endpoint, payload=None, max_retries=MAX_RETRIES):
    """POST to QC API. Returns parsed JSON. Raises on permanent failure."""
    url = f"{API}/{endpoint}"
    last = None
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.post(url, json=payload or {}, headers=_auth_headers(), timeout=60)
            if r.status_code == 200:
                return r.json()
            if r.status_code in _TRANSIENT and attempt < max_retries:
                time.sleep(min(2 ** attempt, 30))
                continue
            raise RuntimeError(f"QC API {endpoint}: HTTP {r.status_code}: {r.text[:200]}")
        except (requests.ConnectionError, requests.Timeout) as e:
            last = e
            if attempt < max_retries:
                time.sleep(min(2 ** attempt, 30))
                continue
            raise RuntimeError(f"QC API {endpoint}: transport error after retries: {e}")
    raise RuntimeError(f"QC API {endpoint}: failed after retries: {last}")


# ---------- high-level helpers (all sanitized) ----------

def authenticate():
    """Returns dict with sanitized booleans only."""
    try:
        d = request("projects/read", {})
        ok = isinstance(d, dict) and str(d.get("success", "")).lower() == "true"
        n = len(d.get("projects", [])) if ok else 0
        return {"ok": ok, "projects_visible": n}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def list_projects():
    d = request("projects/read", {})
    if str(d.get("success", "")).lower() != "true":
        raise RuntimeError(f"projects/read failed: {str(d)[:150]}")
    out = []
    for p in d.get("projects", []):
        out.append({
            "project_id": p.get("projectId"),
            "name": p.get("name"),
            "organization_id": p.get("organizationId"),
            "created": p.get("created", {}).get("time") if isinstance(p.get("created"), dict) else p.get("created"),
            "language": (p.get("parameters") or {}).get("language") or p.get("language"),
        })
    return out


def create_project(name, organization_id, language="Py"):
    d = request("projects/create", {"name": name, "organizationId": organization_id, "language": language})
    if str(d.get("success", "")).lower() != "true":
        raise RuntimeError(f"projects/create failed: {str(d)[:200]}")
    p = d.get("project", {})
    return {"project_id": p.get("projectId"), "name": p.get("name")}


def read_files(project_id):
    d = request("files/read", {"projectId": project_id})
    if str(d.get("success", "")).lower() != "true":
        raise RuntimeError(f"files/read failed: {str(d)[:150]}")
    out = {}
    for f in d.get("files", []):
        out[f.get("name")] = f.get("content")
    return out


def create_file(project_id, name, content):
    d = request("files/create", {"projectId": project_id, "name": name, "content": content})
    if str(d.get("success", "")).lower() != "true":
        raise RuntimeError(f"files/create {name} failed: {str(d)[:200]}")


def update_file(project_id, name, content):
    d = request("files/update", {"projectId": project_id, "name": name, "content": content})
    if str(d.get("success", "")).lower() != "true":
        raise RuntimeError(f"files/update {name} failed: {str(d)[:200]}")


def sync_file(project_id, name, content):
    """Create if missing, update if different. Returns 'created'/'updated'/'unchanged'."""
    remote = read_files(project_id)
    if name not in remote:
        create_file(project_id, name, content)
        return "created"
    if (remote[name] or "").strip() != content.strip():
        update_file(project_id, name, content)
        return "updated"
    return "unchanged"


def compile_create(project_id):
    d = request("compile/create", {"projectId": project_id})
    if str(d.get("success", "")).lower() != "true":
        raise RuntimeError(f"compile/create failed: {str(d)[:200]}")
    return {"compile_id": d.get("compileId")}


def compile_read(project_id, compile_id):
    d = request("compile/read", {"projectId": project_id, "compileId": compile_id})
    return d


def poll_compile(project_id, compile_id, max_wait=300):
    t0 = time.time()
    while time.time() - t0 < max_wait:
        d = compile_read(project_id, compile_id)
        st = (d.get("state") or "").lower().replace(".", "")
        if st in ("buildsuccess", "buildsuccess."):
            return {"ok": True, "state": d.get("state")}
        if st in ("builderror", "failed", "error"):
            logs = ""
            try:
                logs = json.dumps(d.get("logs", []))[:3000]
            except Exception:
                logs = str(d)[:1000]
            return {"ok": False, "state": d.get("state"), "logs": logs}
        time.sleep(5)
    return {"ok": False, "state": "timeout", "logs": ""}


def backtest_create(project_id, name, parameters=None, compile_id=None):
    payload = {"projectId": project_id, "backtestName": name}
    if parameters:
        payload["parameters"] = parameters
    if compile_id:
        payload["compileId"] = compile_id
    body = json.dumps(payload["parameters"] or {})
    if len(body) > 2000:
        raise RuntimeError(f"parameter payload too large: {len(body)} chars")
    d = request("backtests/create", payload)
    if str(d.get("success", "")).lower() != "true":
        raise RuntimeError(f"backtests/create failed: {str(d)}")
    bid = d.get("backtestId") or d.get("backtest", {}).get("backtestId") \
        or d.get("backTestId") or d.get("id")
    if not bid:
        raise RuntimeError(f"backtests/create returned no id; keys={sorted(d.keys())}")
    return {"backtest_id": bid, "name": name,
            "parameters": payload.get("parameters"), "compile_id": compile_id}


def backtest_read(project_id, backtest_id):
    return request("backtests/read", {"projectId": project_id, "backtestId": backtest_id})


def backtest_list(project_id):
    d = request("backtests/list", {"projectId": project_id})
    if str(d.get("success", "")).lower() != "true":
        raise RuntimeError(f"backtests/list failed: {str(d)[:150]}")
    out = []
    for b in d.get("backtests", []):
        out.append({
            "backtest_id": b.get("backtestId"),
            "name": b.get("name"),
            "status": b.get("status"),
            "completed": b.get("completed"),
            "created": (b.get("created") or {}).get("time") if isinstance(b.get("created"), dict) else b.get("created"),
        })
    return out


def poll_backtest(project_id, backtest_id, max_wait=3600, poll_s=15):
    t0 = time.time()
    while time.time() - t0 < max_wait:
        d = backtest_read(project_id, backtest_id)
        bt = d.get("backtest", d)
        st = str(bt.get("status") or "").lower().replace(".", "")
        if st in ("runtime error", "runtimeerror"):
            return {"status": "RuntimeError",
                    "error": bt.get("error"), "stacktrace": bt.get("stacktrace")}
        if st in ("completed",) and bt.get("completed") is True:
            perf = bt.get("totalPerformance") or {}
            if perf:
                return bt
        if st in ("aborted", "failed", "deleted"):
            return {"status": bt.get("status")}
        time.sleep(poll_s)
    return {"status": "poll-timeout"}


def chart_read(project_id, backtest_id, chart_name):
    d = request("backtests/chart/read", {"projectId": project_id, "backtestId": backtest_id, "name": chart_name})
    return d
