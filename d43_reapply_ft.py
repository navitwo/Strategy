"""Rollback-safe restore of the committed FT source bundle after OneDrive.

The committed Git blobs are the source of truth. All replacements are staged
with original-byte backups and a mid-bundle failure rolls prior files back.
After this local restore,
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


def _stage_bytes(root, name, data, purpose):
    fd, path = tempfile.mkstemp(
        prefix=f".{name}-{purpose}-", suffix=".py", dir=root)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    return path


def _read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


def restore_source_set(blobs, root=ROOT, replace=os.replace):
    staged = {}
    backups = {}
    existed = {}
    replaced = []
    rollback_failed = False
    try:
        for name, committed in blobs.items():
            target = os.path.join(root, name)
            staged[name] = _stage_bytes(root, name, committed, "reapply")
            existed[name] = os.path.exists(target)
            backups[name] = (_stage_bytes(
                root, name, _read_bytes(target), "rollback")
                if existed[name] else None)
        try:
            for name, temp_path in staged.items():
                replace(temp_path, os.path.join(root, name))
                staged[name] = None
                replaced.append(name)
        except Exception as original:
            rollback_errors = []
            for name in reversed(replaced):
                target = os.path.join(root, name)
                try:
                    if existed[name]:
                        os.replace(backups[name], target)
                        backups[name] = None
                    elif os.path.exists(target):
                        os.unlink(target)
                except Exception as exc:
                    rollback_errors.append(f"{name}: {exc}")
            if rollback_errors:
                rollback_failed = True
                raise RuntimeError(
                    "source restore and rollback both failed; backups retained: "
                    + "; ".join(rollback_errors)) from original
            raise
    finally:
        for temp_path in staged.values():
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)
        if not rollback_failed:
            for backup_path in backups.values():
                if backup_path and os.path.exists(backup_path):
                    os.unlink(backup_path)
    for name, committed in blobs.items():
        restored = _read_bytes(os.path.join(root, name))
        assert restored == committed, \
            f"post-reapply {name}: {sha(restored)} != {sha(committed)}"


def main():
    blobs = committed_source_set()
    restore_source_set(blobs)
    for name, committed in blobs.items():
        print("atomic reapply verified sha256:", name, sha(committed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())