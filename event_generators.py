"""Pure event-detection seam for no-order event studies.

Every generator emits exactly `(timestamp, side, reference_level, risk_dist,
context)`. Detection is generator-owned; return processing remains downstream.
"""
from datetime import datetime, timedelta
import json
import os


class EventGenerator:
    name = "abstract"

    @staticmethod
    def validate_event(event):
        if not isinstance(event, tuple) or len(event) != 5:
            raise TypeError("event must be a 5-tuple")
        timestamp, side, reference, risk, context = event
        if not isinstance(timestamp, datetime):
            raise TypeError("event timestamp must be datetime")
        if int(side) not in (-1, 1):
            raise ValueError("event side must be -1 or +1")
        if float(risk) <= 0:
            raise ValueError("event risk_dist must be positive")
        float(reference)
        if not isinstance(context, dict):
            raise TypeError("event context must be dict")
        return True


class SweepReclaimGeneratorV1(EventGenerator):
    """Compatibility adapter for the frozen sweep/reclaim detector.

    The stateful sweep/reclaim chronology remains frozen in scifvg_main; this
    object owns the post-detection event contract and its artifact gate.
    """
    name = "generator_v1"
    FROZEN_COUNTS = {"NQ": 388, "ES": 186, "YM": 376, "RTY": 171}

    def from_reclaim(self, timestamp, side, reference_level, entry_px,
                     stop_px, context):
        event = (timestamp, int(side), float(reference_level),
                 abs(float(entry_px) - float(stop_px)), dict(context))
        self.validate_event(event)
        return event

    def verify_frozen_e19br(self, ledger_dir):
        counts = {}
        seen = set()
        for instrument, expected in self.FROZEN_COUNTS.items():
            path = os.path.join(ledger_dir, f"{instrument}_ft.jsonl")
            rows = [json.loads(line) for line in open(path, encoding="utf-8")
                    if line.strip()]
            if len(rows) != expected:
                raise AssertionError(f"{instrument} rows {len(rows)} != {expected}")
            for index, row in enumerate(rows):
                if row["instrument"] != instrument or int(row["ft_row"]) != index:
                    raise AssertionError("frozen row identity/order mismatch")
                codes = [int(code) for code in row["codes"]]
                if len(codes) != 16 or any(code not in (0, 1, 2, 3)
                                           for code in codes):
                    raise AssertionError("invalid frozen FT codes")
                packed = sum(code << (2 * i) for i, code in enumerate(codes))
                if packed != int(row["packed_uint32"]):
                    raise AssertionError("packed_uint32 differs from frozen codes")
                key = (instrument, int(row["chart_x"]))
                if key in seen:
                    raise AssertionError("duplicate frozen chart_x identity")
                seen.add(key)
            counts[instrument] = len(rows)
        return {"rows": len(seen), "markets": counts, "byte_exact": True}


class OvernightLevelTouchV1(EventGenerator):
    """First bare touch of completed full-session overnight high and low.

    Inputs are completed 30-minute ET-wall-clock bars. Overnight endpoints are
    18:30 previous day through 09:30 trade date (31 contiguous bars). RTH touch
    endpoints are 10:00 through 12:30. ATR(14) is ex-ante: the touch bar is not
    included in the event's risk distance or range/ATR context.
    """
    name = "overnight_level_touch_v1"

    def __init__(self, tick_size, atr_period=14):
        self.tick_size = float(tick_size)
        self.atr_period = int(atr_period)
        if self.tick_size <= 0 or self.atr_period < 2:
            raise ValueError("invalid tick/ATR specification")
        self._prev_close = None
        self._trs = []
        self._current_trade_date = None
        self._overnight = []
        self._overnight_valid = False
        self._levels = None
        self._touched = set()
        self._roll_generation = 0

    @staticmethod
    def _trade_date(et):
        return et.date() + timedelta(days=1) if et.hour >= 18 else et.date()

    @staticmethod
    def _minutes(et):
        return et.hour * 60 + et.minute

    def on_rollover(self, timestamp, old_contract, new_contract):
        if old_contract == new_contract:
            raise ValueError("rollover requires distinct contracts")
        self._roll_generation += 1
        self._prev_close = None
        self._trs = []
        self._overnight = []
        self._overnight_valid = False
        self._levels = None
        self._touched = set()

    def _atr(self):
        if len(self._trs) < self.atr_period:
            return None
        return sum(self._trs[-self.atr_period:]) / self.atr_period

    def _update_tr(self, row):
        high, low, close = (float(row[k]) for k in ("high", "low", "close"))
        tr = high - low if self._prev_close is None else max(
            high - low, abs(high - self._prev_close), abs(low - self._prev_close))
        self._trs.append(tr)
        if len(self._trs) > self.atr_period:
            self._trs.pop(0)
        self._prev_close = close

    def on_bar(self, row):
        et = row["et"]
        if not isinstance(et, datetime):
            raise TypeError("bar et must be datetime")
        td = self._trade_date(et)
        if td != self._current_trade_date:
            self._current_trade_date = td
            self._overnight = []
            self._overnight_valid = True
            self._levels = None
            self._touched = set()

        minute = self._minutes(et)
        is_overnight = minute > 18 * 60 or minute <= 9 * 60 + 30
        if is_overnight:
            expected = (datetime.combine(td - timedelta(days=1),
                                         datetime.min.time())
                        .replace(hour=18, minute=30)
                        + timedelta(minutes=30 * len(self._overnight)))
            if et != expected:
                self._overnight_valid = False
            self._overnight.append(row)
            self._update_tr(row)
            if minute == 9 * 60 + 30:
                if self._overnight_valid and len(self._overnight) == 31:
                    self._levels = (max(float(x["high"]) for x in self._overnight),
                                    min(float(x["low"]) for x in self._overnight))
                else:
                    self._levels = None
            return []

        atr = self._atr()
        events = []
        if (self._levels is not None and atr and atr > 0
                and 10 * 60 <= minute <= 12 * 60 + 30):
            on_high, on_low = self._levels
            width = on_high - on_low
            candidates = (("overnight_high", -1, on_high,
                           float(row["high"]) >= on_high),
                          ("overnight_low", 1, on_low,
                           float(row["low"]) <= on_low))
            for kind, side, level, touched in candidates:
                if not touched or kind in self._touched:
                    continue
                self._touched.add(kind)
                context = {
                    "generator": self.name,
                    "level_kind": kind,
                    "session_date": td.isoformat(),
                    "overnight_range_points": round(width, 10),
                    "overnight_range_atr": round(width / atr, 10),
                    "touch_time_et": et.strftime("%H:%M"),
                    "touch_minute_et": minute,
                    "resolve_both_directions": True,
                    "roll_generation": self._roll_generation,
                }
                event = (et, side, float(level), float(atr), context)
                self.validate_event(event)
                events.append(event)
        self._update_tr(row)
        return events


def build_event_generator(name, tick_size, atr_period=14):
    if name == "generator_v1":
        return SweepReclaimGeneratorV1()
    if name == "overnight_level_touch_v1":
        return OvernightLevelTouchV1(tick_size, atr_period)
    raise ValueError(f"unknown event generator: {name!r}")


def pack_campaign2_ft(ft32, arm, level_kind):
    if not 0 <= int(ft32) <= 0xFFFFFFFF:
        raise ValueError("FT payload is not uint32")
    if arm not in ("reversal", "continuation"):
        raise ValueError("unknown direction arm")
    if level_kind not in ("overnight_high", "overnight_low"):
        raise ValueError("unknown overnight level")
    return (int(ft32) | (arm == "continuation") << 32
            | (level_kind == "overnight_low") << 33)


def decode_campaign2_ft(payload):
    value = int(payload)
    if value < 0 or value >= 2 ** 34:
        raise ValueError("invalid Campaign-2 FT payload")
    return {"ft32": value & 0xFFFFFFFF,
            "arm": "continuation" if value & (1 << 32) else "reversal",
            "level_kind": "overnight_low" if value & (1 << 33)
                          else "overnight_high"}


def pack_campaign2_context(context, tick_size):
    tick = float(tick_size)
    ticks = int(round(float(context["overnight_range_points"]) / tick))
    atr_milli = int(round(float(context["overnight_range_atr"]) * 1000))
    minute = int(context["touch_minute_et"])
    level = context["level_kind"]
    if not 0 <= ticks < 2 ** 20:
        raise ValueError("overnight range exceeds 20-bit tick field")
    if not 0 <= atr_milli < 2 ** 18:
        raise ValueError("range/ATR exceeds 18-bit milli field")
    if not 0 <= minute < 24 * 60:
        raise ValueError("touch minute is outside ET day")
    if level not in ("overnight_high", "overnight_low"):
        raise ValueError("unknown overnight level")
    return (ticks | atr_milli << 20 | minute << 38
            | (level == "overnight_low") << 49)


def decode_campaign2_context(payload, tick_size):
    value = int(payload)
    if value < 0 or value >= 2 ** 50:
        raise ValueError("invalid Campaign-2 context payload")
    ticks = value & ((1 << 20) - 1)
    atr_milli = (value >> 20) & ((1 << 18) - 1)
    minute = (value >> 38) & ((1 << 11) - 1)
    return {"overnight_range_points": ticks * float(tick_size),
            "overnight_range_atr": atr_milli / 1000.0,
            "touch_minute_et": minute,
            "level_kind": "overnight_low" if value & (1 << 49)
                          else "overnight_high"}
