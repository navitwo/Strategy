"""Atomically restore the committed FT engine after a OneDrive revert.

The committed Git blob is the source of truth.  After this local restore,
run d10_sync_compile.py; it snapshots outside OneDrive and requires exact
remote==local bytes before QuantConnect compilation.
"""
import ast
import hashlib
import os
import subprocess
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(ROOT, "scifvg_main.py")
REQUIRED = (b"FT_CELLS", b'Chart("E19B-FT")', b'Series("ft-a"',
            b'"n_ft_rows"')
FORBIDDEN = (b'Series("fta-a"', b'Series("ftb-a"')


def sha(data):
    return hashlib.sha256(data).hexdigest()


committed = subprocess.check_output(
    ["git", "show", "HEAD:scifvg_main.py"], cwd=ROOT)
ast.parse(committed.decode("utf-8"))
assert len(committed.decode("utf-8")) <= 64000
for marker in REQUIRED:
    assert marker in committed, f"committed source lacks {marker!r}"
for marker in FORBIDDEN:
    assert marker not in committed, f"committed source retains {marker!r}"

fd, temp_path = tempfile.mkstemp(prefix=".scifvg-reapply-", suffix=".py",
                                 dir=ROOT)
try:
    with os.fdopen(fd, "wb") as handle:
        handle.write(committed)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, TARGET)
finally:
    if os.path.exists(temp_path):
        os.unlink(temp_path)

restored = open(TARGET, "rb").read()
assert restored == committed, \
    f"post-reapply mismatch: {sha(restored)} != {sha(committed)}"
print("atomic reapply verified sha256:", sha(restored))