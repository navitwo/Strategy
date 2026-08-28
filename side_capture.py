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
    """1 if the reclaim bar's EndTime is outside the ordinary 09:30-12:00
    RTH window (holiday / shifted-schedule session), else 0."""
    m = et.hour * 60 + et.minute
    return 0 if (9 * 60 + 30 <= m < 12 * 60) else 1


def side_capture_runtime(algo):
    return {
        "side_capture_spec_version": SIDE_CAPTURE_SPEC_VERSION,
        "side_capture_instrument": str(algo.cfg["instrument"]),
        "side_capture_exp_hash": algo.exp_hash,
        "side_capture_n_ft_rows": int(getattr(algo, "_n_ft_rows", 0)),
    }