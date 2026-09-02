from AlgorithmImports import *

from datetime import timedelta
import hashlib
import json
from event_predicates import (resolve_event_predicates,
    validate_discovery_predicates, evaluate_event_predicates,
    pack_discovery_payload)
from event_generators import (SweepReclaimGeneratorV1,
    build_event_generator, pack_campaign2_context, pack_campaign2_ft)
from scifvg_config import (FT_CELLS, CONFIG_KEYS, CONFIG_DEFAULTS, FUNNEL_KEYS,
                           canonical_identity_config)
import random_time_control as rtc
import side_capture as sidecap

# This module is the hosted no-order engine: events_only, discovery_only,
# random_time_control, and side_capture. The archived strategy-execution code
# (atomic minute-bar simulator, OCO handling, order submission, EOD/rollover
# flatten, and reconciliation identities) was removed here and remains only in
# git history and the e19b-provisional / e19b-r-final tags.

INSTRUMENT_SPECS = {
    "NQ":  (Futures.Indices.NASDAQ_100_E_MINI,       0.25, 20.0),
    "MNQ": (Futures.Indices.MICRO_NASDAQ_100_E_MINI, 0.25,  2.0),
    "ES":  (Futures.Indices.SP_500_E_MINI,            0.25, 50.0),
    "YM":  (Futures.Indices.DOW_30_E_MINI,           1.00,  5.0),
    "RTY": (Futures.Indices.RUSSELL_2000_E_MINI,     0.10, 50.0),
    "GC":  (Futures.Metals.GOLD,                     0.10, 100.0),
}

NO_ORDER_VARIANTS = ("events_only", "discovery_only", "side_capture")


class SweepCisdIfvgAlgorithm(QCAlgorithm):

    def initialize(self):
        raw = {}
        for p in CONFIG_KEYS:
            v = self.get_parameter(p)
            if v is not None and str(v).strip() != "":
                raw[p] = v

        defaults = CONFIG_DEFAULTS
        cfg = {}
        for k, dv in defaults.items():
            rv = raw.get(k)
            if rv is None:
                cfg[k] = dv
            elif isinstance(dv, str):
                cfg[k] = str(rv)
            elif isinstance(dv, float):
                cfg[k] = float(rv)
            else:
                cfg[k] = int(float(rv))

        generator_name = str(cfg.get("event_generator", "generator_v1"))
        if generator_name == "overnight_level_touch_v1":
            self.event_predicate_names = ()
        elif rtc.configure_random_control(cfg):
            self.event_predicate_names = ()
        elif sidecap.configure_side_capture(cfg):
            self.event_predicate_names = resolve_event_predicates(
                cfg["event_predicates"])
            cfg["event_predicates"] = ",".join(self.event_predicate_names)
            validate_discovery_predicates(cfg["variant"],
                                          self.event_predicate_names)
        else:
            self.event_predicate_names = resolve_event_predicates(
                cfg["event_predicates"])
            cfg["event_predicates"] = ",".join(self.event_predicate_names)
            validate_discovery_predicates(cfg["variant"],
                                          self.event_predicate_names)
        if not rtc.is_random_control(cfg) \
                and str(cfg["variant"]) not in NO_ORDER_VARIANTS:
            raise RuntimeError(
                f"archived trading variant {cfg['variant']!r}: this engine "
                "supports only no-order variants "
                "(events_only, discovery_only, side_capture, "
                "random_time_control)")
        canon = json.dumps(canonical_identity_config(cfg), sort_keys=True,
                           separators=(",", ":"))
        self.exp_hash = hashlib.md5(canon.encode()).hexdigest()[:8]
        self._ev_candidates = []
        self._ev_results = []
        self._tr_series = []
        self._atr5 = None
        self.charts = {}
        self.cfg = cfg

        overall_start = datetime.strptime(str(cfg["start_date"]), "%Y-%m-%d").date()
        overall_end = datetime.strptime(str(cfg["end_date"]), "%Y-%m-%d").date()
        oos_start = datetime.strptime("2025-05-01", "%Y-%m-%d").date()
        seg = str(cfg["run_segment"])
        if seg == "dev":
            start, end = overall_start, min(overall_end, oos_start - timedelta(days=1))
        elif seg == "oos":
            start, end = max(overall_start, oos_start), overall_end
        else:
            start, end = overall_start, overall_end
        self.camp_start, self.camp_end = start, end

        warmup_days = 40
        ws = start - timedelta(days=warmup_days)
        self.set_start_date(ws.year, ws.month, ws.day)
        self.set_end_date(end.year, end.month, end.day)
        self.set_cash(50000)
        self.set_time_zone(TimeZones.NEW_YORK)

        inst = str(cfg["instrument"]).upper()
        if inst not in INSTRUMENT_SPECS:
            raise RuntimeError(f"bad instrument {inst!r}")
        root, tick_sz, _pv = INSTRUMENT_SPECS[inst]
        ab = {"NQ": 0.7, "ES": 0.5, "YM": 2.2, "RTY": 0.6}.get(inst, 0.7)
        for k, m_ in (("depth_min_bps", 1), ("depth_max_bps", 24),
                      ("stop_buffer_bps", 1)):
            cfg[k] = cfg.get(k) or round(ab * m_, 3)
        self.fut = self.add_future(
            root, Resolution.MINUTE, extended_market_hours=True,
            data_mapping_mode=DataMappingMode.OPEN_INTEREST,
            data_normalization_mode=DataNormalizationMode.RAW,
            contract_depth_offset=0)
        self.fut.set_filter(timedelta(0), timedelta(days=182))

        self.tick = tick_sz
        self.event_generator = build_event_generator(
            generator_name, self.tick, int(cfg.get("event_atr_period", 14)))
        event_minutes = int(cfg.get("event_bar_minutes", 5))
        expected_minutes = 30 if generator_name == "overnight_level_touch_v1" else 5
        if event_minutes != expected_minutes:
            raise RuntimeError(f"{generator_name} requires {expected_minutes}m bars")
        handler = (self._on_30m_consolidated if event_minutes == 30
                   else self._on_5m_consolidated)
        self.consolidate(self.fut.symbol, timedelta(minutes=event_minutes), handler)

        wh, wm = str(cfg["window_start_et"]).split(":")
        eh, em = str(cfg["window_end_et"]).split(":")
        self.w_start = int(wh) * 60 + int(wm)
        self.w_end = int(eh) * 60 + int(em)
        if rtc.is_random_control(cfg):
            rtc.initialize_random_control(
                self, inst, seed=cfg["random_control_seed"])

        self.fun = {k: 0 for k in FUNNEL_KEYS}
        self.cur_session = None
        self.pdh = None
        self.pdl = None
        self.cur_high = None
        self.cur_low = None
        self.session_tried = set()

        self.bars5 = []
        self.h4_pub = []
        self.h4_bucket = None
        self.h4_min_span_min = 210
        self.h4_max_offset0 = 5
        self.h4_gap_pending = False
        self.swing_hi = []
        self.swing_lo = []
        self.bias = 0

        self.setup = None

        self.d_bars5_total = 0
        self.tzcheck_ok = 0


    def _et_minutes(self, et):
        return et.hour * 60 + et.minute

    def _in_window(self, et):
        m = self._et_minutes(et)
        if self.w_start <= self.w_end:
            return self.w_start <= m < self.w_end
        return m >= self.w_start or m < self.w_end

    def _session_key(self, et):
        d = et.date()
        if et.hour >= 18:
            return d
        if et.hour >= 17:
            return None
        return d - timedelta(days=1)

    def _rt(self, px, up=True):
        t = self.tick
        if up:
            return round(math.ceil(px / t - 1e-9) * t, 4)
        return round(math.floor(px / t + 1e-9) * t, 4)

    def _inc(self, k, n=1):
        self.fun[k] = self.fun.get(k, 0) + n

    def _sk(self, side):
        return "L" if side > 0 else "S"

    def _advance_session(self, et):
        skey = self._session_key(et)
        if skey is None or skey == self.cur_session:
            return

        if self.bias == 0:
            self._inc("no_bias")
        self.cur_session = skey
        self.pdh = self.cur_high
        self.pdl = self.cur_low
        self.cur_high = None
        self.cur_low = None
        self.session_tried = set()
        self._inc("sessions")
        if self.pdh is None or self.pdl is None:
            self._inc("no_prior_levels")

    def _publish_h4(self, new_id):
        bk = self.h4_bucket
        if bk is None or bk["id"] == new_id:
            return
        self.h4_bucket = None
        bars = bk["bars"]
        t0 = bk.get("t0")
        tN = bk.get("tN")
        span = (tN - t0).total_seconds() / 60.0 if (t0 and tN) else 0.0
        if span < self.h4_min_span_min or bk["offset0"] > self.h4_max_offset0:
            self.h4_gap_pending = True
            return
        o = bars[0]["open"]
        c = bars[-1]["close"]
        h = max(x["high"] for x in bars)
        l = min(x["low"] for x in bars)
        idx = len(self.h4_pub)
        self.h4_pub.append({"idx": idx, "open": o, "high": h, "low": l, "close": c})

        if self.h4_gap_pending:
            self.h4_gap_pending = False
        else:
            L = int(self.cfg.get("pivot_lookback", 3))
            Rn = int(self.cfg.get("pivot_right", 3))
            ci = idx - (Rn + 1)
            if ci >= L:
                b = self.h4_pub[ci]
                left = self.h4_pub[ci - L:ci]
                right = self.h4_pub[ci + 1:ci + 1 + Rn]
                if len(left) == L and len(right) == Rn:
                    if all(x["high"] < b["high"] for x in left) and \
                       all(x["high"] < b["high"] for x in right):
                        self.swing_hi.append((ci, b["high"]))
                    if all(x["low"] > b["low"] for x in left) and \
                       all(x["low"] > b["low"] for x in right):
                        self.swing_lo.append((ci, b["low"]))

        bull_break = bool(self.swing_hi) and self.swing_hi[-1][0] < idx \
            and c > self.swing_hi[-1][1]
        bear_break = bool(self.swing_lo) and self.swing_lo[-1][0] < idx \
            and c < self.swing_lo[-1][1]
        if self.bias != 1 and bull_break:
            self.bias = 1
        elif self.bias != -1 and bear_break:
            self.bias = -1

    def _accumulate_h4(self, b5):
        st = b5["et"] - timedelta(minutes=5)
        bid = (st.year, st.month, st.day, st.hour // 4)
        if self.h4_bucket is None or self.h4_bucket["id"] != bid:
            self._publish_h4(bid)
            self.h4_bucket = {
                "id": bid, "bars": [],
                "offset0": (st.hour % 4) * 60 + st.minute,
                "t0": st,
                "tN": b5["et"],
            }
        self.h4_bucket["bars"].append(b5)
        self.h4_bucket["tN"] = b5["et"]

    def _new_setup_allowed(self):
        return (self.setup is None
                and self.pdh is not None and self.pdl is not None)

    def _depth_thresholds(self, ref_px):
        c = self.cfg
        px = max(float(ref_px), 1e-9)
        bmin = float(c.get("depth_min_bps", 0.0) or 0.0)
        bmax = float(c.get("depth_max_bps", 0.0) or 0.0)
        dmin = px * bmin / 1e4 if bmin > 0 else (
            float(c.get("sweep_min_ticks", 4)) * self.tick)
        dmax = px * bmax / 1e4 if bmax > 0 else (
            float(c.get("sweep_max_ticks", 96)) * self.tick)
        return dmin, dmax

    def _stop_buffer(self, ref_px):
        bb = float(self.cfg.get("stop_buffer_bps", 0.0) or 0.0)
        if bb > 0:
            return max(float(ref_px), 1e-9) * bb / 1e4
        return float(self.cfg.get("stop_buffer_ticks", 4)) * self.tick

    def _try_arm_attempt(self, b, idx, et, skey):
        events_only = str(self.cfg.get("variant")) in (
            "events_only", "discovery_only", "side_capture")
        max_att = self.cfg.get("max_attempts_per_day", 1)
        for side, level in ((1, self.pdl), (-1, self.pdh)):
            if not events_only and self.bias != side:
                continue
            used = sum(1 for s, sd in self.session_tried
                       if s == skey and sd == side)
            if used >= max_att:
                continue
            pen = (level - b["low"]) if side > 0 else (b["high"] - level)
            dmin, dmax = self._depth_thresholds(level)
            if pen < dmin:
                continue
            self.session_tried.add((skey, side))
            self._inc("attempts_used")
            self._inc(f"{self._sk(side)}_attempts")
            if pen > dmax:
                self._inc(f"{self._sk(side)}_depth_rejects")
                continue
            self.setup = {
                "side": side, "stage": "SWEPT", "arm_sk": skey, "b0": idx,
                "reclaim_deadline": idx + self.cfg["reclaim_bars"] - 1,
                "level": level, "extreme_idx": idx,
                "extreme": b["low"] if side > 0 else b["high"],
                "bias_aligned": (self.bias == side)}
            return

    def _advance_setup(self, b, idx, et, skey):
        try:
            _now_ts = int(et.timestamp())
        except Exception:
            _now_ts = 0
        s = self.setup
        side = s["side"]
        K = self._sk(side)
        lvl = s["level"]

        # SWEPT stage only: the CISD/INV/PENDING -> entry stages are archived
        # trading code and no longer exist in this no-order engine.
        beyond = (b["low"] < s["extreme"]) if side > 0 else (b["high"] > s["extreme"])
        if beyond:
            s["extreme"] = b["low"] if side > 0 else b["high"]
            s["extreme_idx"] = idx
            exc = (s["level"] - s["extreme"]) if side > 0 \
                else (s["extreme"] - s["level"])
            _, dmax = self._depth_thresholds(s["level"])
            if exc > dmax:
                self._inc(f"{K}_depth_rejects")
                self._inc("excursion_depth_kills")
                self.setup = None
                return
        closed_back = (b["close"] > lvl) if side > 0 else (b["close"] < lvl)
        if closed_back:
            self._inc(f"{K}_sweep_ok")
            buf = self._stop_buffer(b["close"])
            stop = (s["extreme"] - buf) if side > 0 \
                else (s["extreme"] + buf)
            dist = abs(b["close"] - stop)
            floor = max(float(self.cfg.get("min_stop_ticks", 0))
                        * self.tick,
                        float(self.cfg.get("floor_atr_frac", 0))
                        * (self._atr5 or 0))
            if dist < floor:
                self._inc(f"{self._sk(side)}_floor_rejects")
                self.setup = None
                return
            labels = self._shadow_labels(s, b)
            context = {"side": side,
                "bias_aligned": bool(s.get("bias_aligned",
                                           self.bias == side)),
                "risk_dist": float(dist),
                "sweep_depth": abs(float(s["extreme"] - s["level"])),
                "reclaim_bars": idx - s["extreme_idx"] + 1,
                **labels}
            predicate_mask = evaluate_event_predicates(
                self.event_predicate_names, context)
            if not predicate_mask:
                self.setup = None
                return
            generator = getattr(self, "event_generator", None)
            if not isinstance(generator, SweepReclaimGeneratorV1):
                raise RuntimeError("frozen sweep path requires generator_v1")
            generated = generator.from_reclaim(
                et, side, lvl, b["close"], stop, context)
            self._accept_generated_event(generated, {
                "entry_px": float(b["close"]), "stop_px": float(stop),
                "session_type": sidecap.session_type_for_reclaim_et(et),
                "event_predicate_mask": predicate_mask,
                "event_predicate_names": list(self.event_predicate_names),
                **labels})
            self.setup = None
            return
        if idx >= s["reclaim_deadline"]:
            self._inc(f"{K}_no_reclaim")
            self.setup = None
        return

    def _elapsed_min(self, ev, agg):
        try:
            return (agg["ts"] - ev["ts0"]) / 60.0
        except Exception:
            return (self._abs_now - ev["idx0"]) * 5.0

    def _shadow_labels(self, s, b):

        side = s["side"]
        bars = self.bars5
        n = len(bars)
        ref_open = None
        lo_j = max(0, n - 2 - int(self.cfg["cisd_max_bars"]))
        for j in range(n - 2, lo_j - 1, -1):
            bb = bars[j]
            if (bb["close"] < bb["open"]) if side > 0 \
                    else (bb["close"] > bb["open"]):
                ref_open = bb
                break
        fvg = None
        for j in range(max(0, n - 2 - int(
                self.cfg.get("fvg_max_age_bars", 60))), n - 2):
            c0, c2 = bars[j], bars[j + 2]
            if side > 0 and c0["low"] > c2["high"]:
                fvg = {"lo": c2["high"], "hi": c0["low"]}
                break
            if side < 0 and c0["high"] < c2["low"]:
                fvg = {"lo": c0["high"], "hi": c2["low"]}
                break
        ifvg = bool(fvg) and (
            (b["close"] < fvg["lo"]) if side < 0 else (b["close"] > fvg["hi"]))
        return {"shadow_cisd": ref_open is not None,
                "shadow_fvg": fvg is not None,
                "shadow_ifvg": ifvg}

    def _accept_generated_event(self, event, extra=None):
        timestamp, side, reference, risk_dist, context = event
        context = dict(context)
        if extra:
            context.update(extra)
        self._ev_seq = getattr(self, "_ev_seq", 0) + 1
        event_id = f"{self.exp_hash}-{self._ev_seq:06d}"
        directions = [(int(side), None)]
        if context.get("resolve_both_directions"):
            directions = [(int(side), "reversal"), (-int(side), "continuation")]
        for resolved_side, arm in directions:
            px = float(context.get("entry_px", reference))
            stop = float(context.get(
                "stop_px", px - resolved_side * float(risk_dist)))
            aligned = bool(context.get("bias_aligned", True)) if arm is None \
                else arm == "reversal"
            candidate = {
                "event_id": event_id, "generator": context.get(
                    "generator", "generator_v1"),
                "bias_aligned": aligned, "side": resolved_side,
                "arm": arm, "date": str(timestamp.date()),
                "ts0": int(timestamp.timestamp()),
                "event_et": str(timestamp),
                "session_type": int(context.get("session_type", 0)),
                "reference_level": float(reference),
                "px": px, "stop_px": stop, "risk_dist": float(risk_dist),
                "idx0": self._abs_now,
                "remaining": set(self.cfg.get("event_horizons", [120])),
                "mfe_r": 0.0, "mae_r": 0.0, "ft": {},
                "event_predicate_mask": int(context.get(
                    "event_predicate_mask", 1)),
                "event_predicate_names": list(context.get(
                    "event_predicate_names", ["sweep_reclaim_v1"])),
            }
            for key in ("shadow_cisd", "shadow_fvg", "shadow_ifvg",
                        "level_kind", "session_date",
                        "overnight_range_points", "overnight_range_atr",
                        "touch_time_et", "touch_minute_et",
                        "roll_generation"):
                if key in context:
                    candidate[key] = context[key]
            self._ev_candidates.append(candidate)

    def _advance_events(self, agg):
        if not self._ev_candidates:
            return
        still = []
        for ev in self._ev_candidates:
            rd = max(float(ev["risk_dist"]), 1e-9)
            fav = ((agg["high"] - ev["px"]) if ev["side"] > 0
                   else (ev["px"] - agg["low"]))
            adv = ((agg["low"] - ev["px"]) if ev["side"] > 0
                   else (ev["px"] - agg["high"]))
            ev["mfe_r"] = max(ev["mfe_r"], float(fav) / rd)
            ev["mae_r"] = min(ev["mae_r"], float(adv) / rd)
            ftg = ev["ft"]
            for k, t, s_lev in FT_CELLS:
                if k in ftg:
                    continue
                m_, n_ = ev["mfe_r"], ev["mae_r"]
                hit_t, hit_s = m_ >= t, n_ <= -s_lev
                if hit_t or hit_s:
                    ftg[k] = (99 if hit_t and hit_s
                              else t if hit_t else -s_lev)
            for h in list(ev["remaining"]):
                if self._elapsed_min(ev, agg) >= h:
                    ret_r = ((agg["close"] - ev["px"]) / rd) * ev["side"]
                    self._ev_results.append({
                        "event_id": ev["event_id"],
                        "last_reclaim_et": str(agg.get("et")),
                        "bias_aligned": ev["bias_aligned"],
                        "arm": ev.get("arm") or (
                            "counter" if not ev["bias_aligned"] else "primary"),
                        "side": ev["side"], "date": ev["date"],
                        "session_type": ev.get("session_type", 0),
                        "h_min": h, "ret_r": round(ret_r, 6),
                        "entry_px": round(ev["px"], 2),
                        "stop_px": round(ev["stop_px"], 2),
                        "risk_dist": round(ev["risk_dist"], 4),
                        "shadow_mask": int(bool(ev.get("shadow_cisd")))
                        | int(bool(ev.get("shadow_fvg"))) << 1
                        | int(bool(ev.get("shadow_ifvg"))) << 2,
                        "ft": dict(ev.get("ft", {})),
                        "mfe_r": round(ev["mfe_r"], 4),
                        "mae_r": round(ev["mae_r"], 4),
                        "event_predicate_mask": ev.get(
                            "event_predicate_mask", 1),
                        "event_predicate_names": ev.get(
                            "event_predicate_names", ["sweep_reclaim_v1"]),
                        **{k: ev.get(k) for k in (
                           "shadow_cisd", "shadow_fvg", "shadow_ifvg",
                           "generator", "reference_level", "event_et",
                           "level_kind", "session_date",
                           "overnight_range_points", "overnight_range_atr",
                           "touch_time_et", "touch_minute_et",
                           "roll_generation") if k in ev}})
                    ev["remaining"].discard(h)
            if ev["remaining"]:
                still.append(ev)
        self._ev_candidates = still

    def _rebase(self, trim):
        if self.setup:
            for f in ("b0", "reclaim_deadline", "extreme_idx"):
                v = self.setup.get(f)
                if isinstance(v, int):
                    self.setup[f] = v - trim

    def _on_5m_consolidated(self, consolidated):
        et = consolidated.end_time
        _etv = et
        try:
            _ts = int(_etv.timestamp())
        except Exception:
            _ts = 0
        agg = {
            "open": float(consolidated.open),
            "ts": _ts,
            "high": float(consolidated.high),
            "low": float(consolidated.low),
            "close": float(consolidated.close),
            "idx": -1,
            "et": et,
        }
        self.bars5.append(agg)
        self.d_bars5_total += 1
        self._abs_bar = getattr(self, "_abs_bar", -1) + 1
        self._abs_now = self._abs_bar
        _pc = self.bars5[-1]["close"] if self.bars5 else agg["close"]
        _tr = max(agg["high"] - agg["low"], abs(agg["high"] - _pc),
                  abs(_pc - agg["low"]))
        self._tr_series.append(_tr)
        if len(self._tr_series) > 14:
            self._tr_series.pop(0)
        if len(self._tr_series) == 14:
            self._atr5 = sum(self._tr_series) / 14.0
        agg["abs"] = self._abs_bar
        if len(self.bars5) > 600:
            trim = len(self.bars5) - 600
            del self.bars5[:trim]
            self._rebase(trim)
        agg["idx"] = len(self.bars5) - 1

        if not getattr(self, "_tzcheck_done", False):
            hm = et.hour * 60 + et.minute
            if hm == 9 * 60 + 35:
                self._tzcheck_done = True
                self.tzcheck_ok = 1
                self.Debug(f"TZCHECK first-RTH-bar et={et.isoformat()} "
                           f"ok=True")

        skey = self._session_key(et)
        if skey is not None:
            self._advance_session(et)

        if self.cur_high is None or agg["high"] > self.cur_high:
            self.cur_high = agg["high"]
        if self.cur_low is None or agg["low"] < self.cur_low:
            self.cur_low = agg["low"]

        self._accumulate_h4(agg)

        variant = str(self.cfg.get("variant", "candidate"))
        if variant != "random_time_control":
            self._advance_events(agg)
        warm = et.date() >= self.camp_start
        if variant == "random_time_control":
            rtc.advance_random_control(self, agg, warm, self._in_window(et))
        elif warm and skey is not None and self._in_window(et) \
                and self._new_setup_allowed() and self.bias in (1, -1):
            self._try_arm_attempt(agg, agg["idx"], et, skey)

        if self.setup is not None and self.setup["stage"] == "SWEPT":
            if self._in_window(et) and self.setup["arm_sk"] == skey:
                self._advance_setup(agg, agg["idx"], et, skey)
            else:
                K = self._sk(self.setup["side"])
                self._inc(f"{K}_cancel_window")
                self.setup = None

    def _on_30m_consolidated(self, consolidated):
        et = consolidated.end_time
        self._abs_event_bar = getattr(self, "_abs_event_bar", -1) + 1
        self._abs_now = self._abs_event_bar
        agg = {"open": float(consolidated.open),
               "high": float(consolidated.high),
               "low": float(consolidated.low),
               "close": float(consolidated.close),
               "et": et, "ts": int(et.timestamp()),
               "idx": self._abs_event_bar, "abs": self._abs_event_bar}
        # Advance prior events first: the touch bar cannot leak pre-touch range
        # into post-event MFE/MAE or first-touch outcomes.
        self._advance_events(agg)
        events = self.event_generator.on_bar(agg)
        if et.date() >= self.camp_start:
            for event in events:
                self._accept_generated_event(event)

    def on_symbol_changed_events(self, changes):
        generator = getattr(self, "event_generator", None)
        if generator is None or not hasattr(generator, "on_rollover"):
            return
        for change in changes.values():
            generator.on_rollover(self.time, str(change.old_symbol),
                                  str(change.new_symbol))
            self._inc("rollovers")

    def _export_charts(self):
        local,fx={},{}
        fc, fs = Chart("E19B-FT"), Series("a", SeriesType.SCATTER)
        fc.add_series(fs)
        c2 = str(self.cfg.get("event_generator")) == "overnight_level_touch_v1"
        cc, cs, cx = Chart("C2-context"), Series("a", SeriesType.SCATTER), {}
        cc.add_series(cs)
        self._n_ft_rows=0
        variant = str(self.cfg.get("variant"))
        rc = variant == "random_time_control"
        for e in getattr(self, "_ev_results", []):
            cname = f"E19B-h{e['h_min']}"
            sname = "a" if e.get("bias_aligned") or rc else "o"
            try:
                ts_dt = datetime.fromisoformat(e["random_selected_et"] if
                    rc else e["last_reclaim_et"])
            except Exception:
                continue
            mask = (int(bool(e.get("shadow_cisd")))
                    | int(bool(e.get("shadow_fvg"))) << 1
                    | int(bool(e.get("shadow_ifvg"))) << 2)
            if e["h_min"] == 120 and (sname == "a" or
                    variant == "discovery_only" or c2):
                p = 0
                for i2, (k2, _, _) in enumerate(FT_CELLS):
                    v = e.get("ft", {}).get(k2)
                    c = 0 if v is None else 3 if v == 99 else 1 if v > 0 else 2
                    p |= c << (2 * i2)
                if rc:
                    p = rtc.pack_event_payload(p, e)
                elif variant == "discovery_only":
                    p = pack_discovery_payload(
                        p, e.get("event_predicate_mask", 1))
                elif variant == "side_capture":
                    p = sidecap.pack_side_payload(
                        p, e.get("side"), e.get("session_type", 0))
                elif c2:
                    p = pack_campaign2_ft(
                        p, e["arm"], e["level_kind"])
                x = fx.get(ts_dt, 0); fx[ts_dt] = x + 1
                fs.add_point(ts_dt + timedelta(seconds=x), float(p))
                self._n_ft_rows += 1
                if c2 and e["arm"] == "reversal":
                    event_dt = datetime.fromisoformat(e["event_et"])
                    cp = pack_campaign2_context(e, self.tick)
                    x2 = cx.get(event_dt, 0); cx[event_dt] = x2 + 1
                    cs.add_point(event_dt + timedelta(seconds=x2), float(cp))
            if e["h_min"]==120:continue
            if cname not in local:
                ch = Chart(cname)
                pres = ("", "rd-", "mfe-", "mae-", "mask-")
                for pre in pres:
                    ch.add_series(Series(pre + "a",
                                         SeriesType.SCATTER))
                    ch.add_series(Series(pre + "o",
                                         SeriesType.SCATTER))
                local[cname] = ch
            vals = {"": e["ret_r"], "rd-": e["risk_dist"],
                    "mfe-": e["mfe_r"], "mae-": e["mae_r"],
                    "mask-": float(mask)}
            for pre, v in vals.items():
                sr = local[cname].series[pre + sname]
                sr.add_point(ts_dt, float(v))
        for ch in local.values():self.add_chart(ch)
        self.add_chart(fc)
        if c2:
            self.add_chart(cc)

    def on_end_of_algorithm(self):
        held = 0
        if rtc.is_random_control(self.cfg):
            rtc.finalize_random_control(self)
        self._export_charts()
        try:
            RT = self.RuntimeStatistics
            RT["funnel_sessions"] = str(self.fun["sessions"])
            RT["exp_hash"] = self.exp_hash
            for k in sorted(self.fun.keys()):
                RT[f"f_{k}"] = str(self.fun[k])
            RT["d_bars5_total"] = str(self.d_bars5_total)
            try:
                _s = int(self.fun["sessions"])
                RT["bars_per_session"] = \
                    repr(round(self.d_bars5_total / _s, 1)) if _s else "0"
            except Exception:
                self.RuntimeStatistics["bars_per_session"] = "0"
            self.RuntimeStatistics["tzcheck_ok"] = str(self.tzcheck_ok)
            self.RuntimeStatistics["event_predicates"] = ",".join(
                self.event_predicate_names)
            if rtc.is_random_control(self.cfg):
                for key, value in rtc.random_control_runtime(self).items():
                    RT[key] = str(value)
            if sidecap.is_side_capture(self.cfg):
                for key, value in sidecap.side_capture_runtime(self).items():
                    RT[key] = str(value)
            # no-order invariant: execution/reconciliation counters are
            # structurally zero for this engine.
            for k2 in ("d_cycles_opened", "d_atomic_exits", "d_n_fillevents",
                       "eod_flattens", "rollovers", "f_flatten_fills",
                       "f_untracked_fills", "f_late_fill_events",
                       "f_orphan_entry_fills", "f_oco_void_legs",
                       "f_anomalous_exit_events", "f_forced_flattens",
                       "f_L_submits", "f_S_submits", "f_L_fills", "f_S_fills"):
                RT[k2] = str(self.fun.get(k2, 0))
            for k5, v5 in (("d_ev_results", len(self._ev_results)),
                           ("n_event_rows", len(self._ev_results)),
                           ("n_ft_rows", self._n_ft_rows),
                           ("d_open_at_end", held),
                           ("d_pos_side_end", 0),
                           ("d_rows_total", 0)):
                self.RuntimeStatistics[k5] = str(v5)
            import statistics as _st
            by_key = {}
            for e in getattr(self, "_ev_results", []):
                by_key.setdefault((e["arm"], e["h_min"]), []).append(e["ret_r"])
            for (arm, h) in sorted(by_key):
                xs = by_key[(arm, h)]
                n = len(xs)
                mean = _st.mean(xs)
                sd = _st.stdev(xs) if n > 1 else 0.0
                se = sd / (n ** 0.5) if n else 0.0
                hw = 1.96 * se
                mde = (2.80 * se) if n > 1 else None
                p_ = f"evb_{arm}_h{h}"
                self.RuntimeStatistics[f"{p_}_n"] = str(n)
                self.RuntimeStatistics[f"{p_}_meanR"] = repr(round(mean, 4))
                self.RuntimeStatistics[f"{p_}_sdR"] = repr(round(sd, 4))
                self.RuntimeStatistics[f"{p_}_seR"] = repr(round(se, 4))
                self.RuntimeStatistics[f"{p_}_ci95R"] = \
                    f"[{round(mean - hw, 4)},{round(mean + hw, 4)}]"
                self.RuntimeStatistics[f"{p_}_mde80R"] = \
                    repr(round(mde, 4)) if mde is not None else "na"
        except Exception:
            pass