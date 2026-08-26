"""Hash-stable, byte-verified QuantConnect source sync and compile."""
import ast
import hashlib
import os
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from qc_api import (compile_create, poll_compile, read_files, sync_file)

PID = 35506697
SOURCE = os.path.join(ROOT, "scifvg_main.py")
REQUIRED = ("FT_CELLS", 'Chart("E19B-FT")', 'Series("a",',
            '"n_ft_rows"')
FORBIDDEN = ('Series("fta-a"', 'Series("ftb-a"')


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_source():
    previous = None
    for _ in range(12):
        current = open(SOURCE, encoding="utf-8").read()
        if current == previous:
            ast.parse(current)
            assert len(current) <= 64000, f"QC source limit: {len(current)}"
            for marker in REQUIRED:
                assert marker in current, f"missing source marker: {marker}"
            for marker in FORBIDDEN:
                assert marker not in current, f"obsolete source marker: {marker}"
            return current
        previous = current
        time.sleep(0.5)
    raise RuntimeError("OneDrive source never reached two identical reads")


src = stable_source()
snapshot = os.path.join(os.environ.get("LOCALAPPDATA", ROOT),
                        "Temp", "scifvg_main.upload.py")
os.makedirs(os.path.dirname(snapshot), exist_ok=True)
with open(snapshot, "w", encoding="utf-8", newline="\n") as handle:
    handle.write(src)
snap = open(snapshot, encoding="utf-8").read()
assert digest(snap) == digest(src), "stable snapshot write mismatch"

st = sync_file(PID, "main.py", snap)
remote = read_files(PID).get("main.py") or ""
assert remote == snap, \
    f"remote/local byte mismatch: {digest(remote)} != {digest(snap)}"
print("sync:", st, "| remote==local sha256:", digest(snap)[:16])

c = compile_create(PID)
cr = poll_compile(PID, c["compile_id"], max_wait=300)
print("compile ok:", cr.get("ok"), cr.get("state"))
if not cr.get("ok"):
    print(cr.get("logs", "")[:2500])
    sys.exit(1)
with open(os.path.join(ROOT, "compile_id.txt"), "w",
          encoding="utf-8", newline="\n") as handle:
    handle.write(c["compile_id"] + "\n")
print("compile id saved:", c["compile_id"][:20], "...")
