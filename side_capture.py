"""Side-capture export: capture the numeric trade side (long/short), the
explicit reclaim timestamp, and a session-type flag for each E19B-R aligned
H=120 event, in the same no-order pass that produced the frozen FT32 ledger.

The committed E19B-R FT32 ledger retains only the 16-cell first-touch vector
(chart_x, codes, packed_uint32) and the arm as an 'a'/'o' series split. It does
NOT retain the numeric +/-1 side (long/short), nor an explicit session-type
flag. This module is a THIRD hosted source (beside random_time_control.py and
scifvg_main.py) that packs those two extra fields into the high bits of the
exact float64 payload, leaving the low 32-bit FT32 vector byte-identical to the
frozen ledger so a fail-closed population gate can verify the engine is
deterministic across the change.

Bit layout (all exactly representable in float64, total < 2^52):
    bits [ 0..31] = FT32E 16-cell vector (unchanged)
    bit  [32]     = side: 0 = short (-1), 1 = long (+1)
    bit  [33]     = session_type: 0 = ordinary RTH session, 1 = holiday
                    / shifted-schedule session (reclaim outside 09:30-12:00)
"""

SIDE_CAPTURE_SPEC_VERSION = "SIDE-CAPTURE-v1"

# Frozen US-market-holiday session dates whose GTB Globex schedule shifts the
# ordinary 09:30-12:00 window gate. Mirrors EXCLUDED_HOLIDAY_DATES in
# d45_random_time_control.py. These reclaims are a documented conformance
# defect in the frozen E19B-R study (see EXPERIMENT_LOG.md "RTC2 conformance
# finding"), and are excluded from BOTH sides of the RTC2 paired comparison.
HOLIDAY_SESSION_DATES = ("2011-02-21", "2018-02-19", "2022-06-20")


def is_side_capture(config):
    return str(config.get("variant")) == "side_capture"


def configure_side_capture(config):
    if not is_side_capture(config):
        return False
    config["event_predicates"] = "sweep_reclaim_v1"
    return True


def pack_side_payload(ft32, side, session_type):
    ft = int(ft32)
    assert 0 <= ft <= 0xFFFFFFFF, f"FT payload outside uint32: {ft}"
    side_bit = 0 if int(side) < 0 else 1
    sess_bit = 1 if int(session_type) == 1 else 0
    payload = ft | (side_bit << 32) | (sess_bit << 33)
    assert 0 <= payload < 2 ** 52
    return payload


def unpack_side_payload(payload):
    payload = int(payload)
    assert 0 <= payload < 2 ** 52, f"side payload outside 52 bits: {payload}"
    ft32 = payload & 0xFFFFFFFF
    side_bit = (payload >> 32) & 1
    sess_bit = (payload >> 33) & 1
    return {"ft32": ft32, "side": 1 if side_bit else -1,
            "session_type": sess_bit}


def session_type_for_reclaim_et(et):
    """1 if the reclaim bar falls on a US-market-holiday session whose Globex
    schedule shifts the ordinary 09:30-12:00 window gate, else 0.

    The holiday determination is the FROZEN conformance-finding date set, not
    a clock-window heuristic: the four affected events reclaim inside the
    ordinary window on the shifted schedule, so a pure hour/minute test cannot
    distinguish them. Reclaim on one of HOLIDAY_SESSION_DATES => 1 (holiday /
    shifted-schedule session), otherwise 0 (ordinary RTH session)."""
    iso = et.date().isoformat() if hasattr(et, "date") else str(et)[:10]
    return 1 if iso in HOLIDAY_SESSION_DATES else 0


def side_capture_runtime(algo):
    return {
        "side_capture_spec_version": SIDE_CAPTURE_SPEC_VERSION,
        "side_capture_instrument": str(algo.cfg["instrument"]),
        "side_capture_exp_hash": algo.exp_hash,
        "side_capture_n_ft_rows": int(getattr(algo, "_n_ft_rows", 0)),
    }