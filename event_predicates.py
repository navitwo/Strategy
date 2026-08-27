"""Pure, versioned predicates for multi-family no-order discovery screens.

Predicates classify one shared sweep/reclaim event context. They do not place
orders or change barrier resolution. Up to ten matches travel beside the FT32
vector in one exactly representable 42-bit float64 integer.
"""

MAX_PREDICATES = 10


def _all(_):
    return True


def _field(name, expected=True):
    return lambda context: name in context and bool(context[name]) is expected


EVENT_PREDICATES = {
    "sweep_reclaim_v1": _all,
    "bias_aligned_v1": _field("bias_aligned"),
    "bias_opposed_v1": _field("bias_aligned", False),
    "shadow_cisd_v1": _field("shadow_cisd"),
    "shadow_fvg_v1": _field("shadow_fvg"),
    "shadow_ifvg_v1": _field("shadow_ifvg"),
}


def resolve_event_predicates(spec):
    names = tuple(name.strip() for name in str(spec or "sweep_reclaim_v1").split(",")
                  if name.strip())
    if not names:
        raise ValueError("at least one event predicate is required")
    if len(names) > MAX_PREDICATES:
        raise ValueError(f"at most {MAX_PREDICATES} event predicates are supported")
    if len(set(names)) != len(names):
        raise ValueError(f"duplicate event predicates: {names}")
    unknown = [name for name in names if name not in EVENT_PREDICATES]
    if unknown:
        raise ValueError(f"unknown event predicates: {unknown}")
    return names


def validate_discovery_predicates(variant, names):
    variant = str(variant)
    if variant == "discovery_only" and (
            not names or names[0] != "sweep_reclaim_v1"):
        raise ValueError(
            "discovery_only requires sweep_reclaim_v1 as predicate bit 0")
    if variant == "events_only" and len(names) != 1:
        raise ValueError(
            "events_only supports one predicate because FT32 has no family mask")
    if (variant not in ("events_only", "discovery_only")
            and tuple(names) != ("sweep_reclaim_v1",)):
        raise ValueError(
            f"event predicates are inactive for trading variant {variant!r}")


def evaluate_event_predicates(names, context):
    mask = 0
    for i, name in enumerate(names):
        result = EVENT_PREDICATES[name](context)
        if type(result) is not bool:
            raise TypeError(
                f"event predicate {name!r} returned {type(result).__name__}, not bool")
        if result:
            mask |= 1 << i
    return mask


def pack_discovery_payload(ft_uint32, predicate_mask):
    ft = int(ft_uint32)
    mask = int(predicate_mask)
    if not 0 <= ft <= 0xFFFFFFFF:
        raise ValueError(f"FT payload outside uint32: {ft}")
    if not 0 <= mask < (1 << MAX_PREDICATES):
        raise ValueError(f"predicate mask outside {MAX_PREDICATES} bits: {mask}")
    return ft | (mask << 32)


def unpack_discovery_payload(value):
    raw = float(value)
    packed = int(raw)
    if raw != packed or not 0 <= packed < (1 << (32 + MAX_PREDICATES)):
        raise ValueError(f"non-exact discovery payload: {value!r}")
    return packed & 0xFFFFFFFF, packed >> 32
