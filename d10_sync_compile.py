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
SOURCES = {
    "main.py": ("scifvg_main.py",
                ("FT_CELLS", 'Chart("E19B-FT")', 'Series("a",',
                 '"n_ft_rows"', "resolve_event_predicates",
                 "validate_discovery_predicates"),
                ('Series("fta-a"', 'Series("ftb-a"'), 64000),
    "event_predicates.py": ("event_predicates.py",
                            ("EVENT_PREDICATES", "pack_discovery_payload"),
                            (), 64000),
    "scifvg_config.py": ("scifvg_config.py",
                         ("CONFIG_DEFAULTS", "FT_CELLS", "FUNNEL_KEYS",
                          "canonical_identity_config"),
                         (), 64000),
}


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_exact_text(path):
    with open(path, encoding="utf-8", newline="") as handle:
        return handle.read()


def _validate_source(path, current, required, forbidden, max_chars):
    ast.parse(current)
    assert len(current) <= max_chars, \
        f"QC source limit {path}: {len(current)}"
    for marker in required:
        assert marker in current, f"missing source marker: {marker}"
    for marker in forbidden:
        assert marker not in current, f"obsolete source marker: {marker}"


def stable_sources(sources=SOURCES, read_text=None, attempts=12, sleep_s=0.5):
    if read_text is None:
        def read_text(local_name):
            return read_exact_text(os.path.join(ROOT, local_name))
    previous = None
    for _ in range(attempts):
        current = {remote_name: read_text(spec[0])
                   for remote_name, spec in sources.items()}
        if current == previous:
            for remote_name, text in current.items():
                local_name, required, forbidden, max_chars = sources[remote_name]
                _validate_source(local_name, text, required, forbidden,
                                 max_chars)
            return current
        previous = current
        time.sleep(sleep_s)
    raise RuntimeError(
        "OneDrive source set never reached two identical bundle reads")


def main():
    snaps = stable_sources()
    for remote_name, snap in snaps.items():
        local_name = SOURCES[remote_name][0]
        snapshot = os.path.join(os.environ.get("LOCALAPPDATA", ROOT), "Temp",
                                local_name + ".upload")
        os.makedirs(os.path.dirname(snapshot), exist_ok=True)
        with open(snapshot, "w", encoding="utf-8", newline="") as handle:
            handle.write(snap)
        reread = read_exact_text(snapshot)
        assert digest(reread) == digest(snap), \
            f"snapshot mismatch: {local_name}"
        print("sync:", remote_name, sync_file(PID, remote_name, reread))
    remote_files = read_files(PID)
    for remote_name, snap in snaps.items():
        remote = remote_files.get(remote_name) or ""
        assert remote == snap, f"remote/local byte mismatch {remote_name}: " \
            f"{digest(remote)} != {digest(snap)}"
        print("remote==local sha256:", remote_name, digest(snap)[:16])

    c = compile_create(PID)
    cr = poll_compile(PID, c["compile_id"], max_wait=300)
    print("compile ok:", cr.get("ok"), cr.get("state"))
    if not cr.get("ok"):
        print(cr.get("logs", "")[:2500])
        return 1
    with open(os.path.join(ROOT, "compile_id.txt"), "w",
              encoding="utf-8", newline="\n") as handle:
        handle.write(c["compile_id"] + "\n")
    print("compile id saved:", c["compile_id"][:20], "...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
