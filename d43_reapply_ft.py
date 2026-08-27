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
TARGETS = {
    "scifvg_main.py": ((b"FT_CELLS", b'Chart("E19B-FT")',
                        b'Series("a",', b'"n_ft_rows"',
                        b"resolve_event_predicates",
                        b"validate_discovery_predicates"),
                       (b'Series("fta-a"', b'Series("ftb-a"'), 64000),
    "event_predicates.py": ((b"EVENT_PREDICATES",
                             b"pack_discovery_payload"), (), 64000),
    "scifvg_config.py": ((b"CONFIG_DEFAULTS", b"FT_CELLS",
                          b"FUNNEL_KEYS", b"canonical_identity_config"),
                         (), 64000),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _validate_committed(name, committed, required, forbidden, max_chars):
    text = committed.decode("utf-8")
    ast.parse(text)
    assert len(text) <= max_chars
    for marker in required:
        assert marker in committed, f"committed {name} lacks {marker!r}"
    for marker in forbidden:
        assert marker not in committed, f"committed {name} retains {marker!r}"


def committed_source_set(targets=TARGETS, loader=None):
    if loader is None:
        def loader(name):
            return subprocess.check_output(
                ["git", "show", f"HEAD:{name}"], cwd=ROOT)
    blobs = {name: loader(name) for name in targets}
    for name, committed in blobs.items():
        _validate_committed(name, committed, *targets[name])
    return blobs


def main():
    blobs = committed_source_set()
    staged = {}
    try:
        for name, committed in blobs.items():
            fd, temp_path = tempfile.mkstemp(
                prefix=f".{name}-reapply-", suffix=".py", dir=ROOT)
            staged[name] = temp_path
            with os.fdopen(fd, "wb") as handle:
                handle.write(committed)
                handle.flush()
                os.fsync(handle.fileno())
        for name, temp_path in staged.items():
            os.replace(temp_path, os.path.join(ROOT, name))
            staged[name] = None
    finally:
        for temp_path in staged.values():
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)
    for name, committed in blobs.items():
        restored = open(os.path.join(ROOT, name), "rb").read()
        assert restored == committed, \
            f"post-reapply {name}: {sha(restored)} != {sha(committed)}"
        print("atomic reapply verified sha256:", name, sha(restored))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())