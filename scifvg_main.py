from AlgorithmImports import *

from datetime import timedelta
import hashlib
import json
import math

class ScifvgFeeModel(FeeModel):
    """Flat commission per side per contract (USD)."""
    def __init__(self, per_side):
        self.per_side = float(per_side)
        super().__init__()

    def get_order_fee(self, parameters):
        fee = self.per_side * abs(parameters.order.quantity)
        return OrderFee(CashAmount(fee, "USD"))

class TickSlippage:
    """Fixed adverse slippage of N ticks per fill."""
    def __init__(self, ticks):
        self.ticks = ticks

    def get_slippage_approximation(self, asset, order):
        return float(asset.symbol_properties.minimum_price_variation) * self.ticks

INSTRUMENT_SPECS = {
    "NQ":  (Futures.Indices.NASDAQ_100_E_MINI,       0.25, 20.0),
    "MNQ": (Futures.Indices.MICRO_NASDAQ_100_E_MINI, 0.25,  2.0),
    "ES":  (Futures.Indices.SP_500_E_MINI,            0.25, 50.0),
    "YM":  (Futures.Indices.DOW_30_E_MINI,           1.00,  5.0),
    "RTY": (Futures.Indices.RUSSELL_2000_E_MINI,     0.10, 50.0),
}

FUNNEL_KEYS = [
    "sessions", "no_prior_levels", "no_bias", "attempts_used", "excursion_depth_kills", "rollover_no_mark",
    "L_attempts", "L_depth_rejects", "L_no_reclaim", "L_sweep_ok",
    "L_cisd_ok", "L_cisd_timeout", "L_inv_ok", "L_inv_timeout",
    "L_submits", "L_fills", "L_size_skips", "L_cancel_expiry",
    "L_cancel_invalid", "L_cancel_bias", "L_cancel_window", "L_cancel_other",
    "S_attempts", "S_depth_rejects", "S_no_reclaim", "S_sweep_ok",
    "S_cisd_ok", "S_cisd_timeout", "S_inv_ok", "S_inv_timeout",
    "S_submits", "S_fills", "S_size_skips", "S_cancel_expiry",
    "S_cancel_invalid", "S_cancel_bias", "S_cancel_window", "S_cancel_other",
    "rollovers", "oco_races", "forced_flattens", "end_flattens", "eod_flattens", "flatten_fills", "untracked_fills", "oco_void_legs", "anomalous_exit_events", "cycles_opened", "atomic_exits",
]

class SweepCisdIfvgAlgorithm(QCAlgorithm):

    def initialize(self):
        raw = {}
        for p in ("instrument", "start_date", "end_date", "run_segment",
                  "sweep_min_ticks", "sweep_max_ticks", "reclaim_bars",
                  "cisd_max_bars", "inv_max_bars", "retest_max_bars",
                  "fvg_min_ticks", "fvg_max_age_bars", "stop_buffer_ticks",
                  "target_r", "risk_usd", "max_contracts", "slippage_ticks",
                  "commission_per_side", "window_start_et", "window_end_et",
                  "invert_on_cisd_bar", "entry_location",
                  "pivot_lookback", "pivot_right", "max_attempts_per_day",
                  "stop_mode", "entry_mode", "random_entry_prob", "variant",
                  "event_horizons", "depth_min_bps", "depth_max_bps",
                  "stop_buffer_bps", "counter_bias_arm"):
            v = self.get_parameter(p)
            if v is not None and str(v).strip() != "":
                raw[p] = v

        defaults = {
            "instrument": "MNQ", "start_date": "2023-01-03", "end_date": "2025-04-30",
            "run_segment": "dev", "sweep_min_ticks": 4, "sweep_max_ticks": 96,
            "reclaim_bars": 3, "cisd_max_bars": 12, "inv_max_bars": 12,
            "retest_max_bars": 24, "fvg_min_ticks": 4, "fvg_max_age_bars": 60,
            "stop_buffer_ticks": 4, "target_r": 2.0, "risk_usd": 100.0,
            "max_contracts": 10, "slippage_ticks": 1, "commission_per_side": 0.50,
            "window_start_et": "09:30", "window_end_et": "12:00",
            "invert_on_cisd_bar": 0, "entry_location": "proximal",
            "pivot_lookback": 3, "pivot_right": 3,
            "max_attempts_per_day": 1, "stop_mode": "sweep",
            "entry_mode": "signal", "random_entry_prob": 0.02,
            "variant": "candidate",
            "event_horizons": [30, 60, 120, 240],
            "depth_min_bps": 0.0, "depth_max_bps": 0.0,
            "stop_buffer_bps": 0.0,
        }
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

        canon = json.dumps(cfg, sort_keys=True, separators=(",", ":"))
        self.exp_hash = hashlib.md5(canon.encode()).hexdigest()[:8]
        self._ev_candidates = []
        self._ev_results = []
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
        root, tick_sz, pv = INSTRUMENT_SPECS[inst]
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
        self.fut.set_fee_model(ScifvgFeeModel(cfg["commission_per_side"]))
        self.fut.set_slippage_model(TickSlippage(cfg["slippage_ticks"]))

        self.consolidate(self.fut.symbol, timedelta(minutes=5),
                         self._on_5m_consolidated)

        self.tick = tick_sz
        self.point_value = pv
        self.slippage_ticks = int(self.cfg.get("slippage_ticks", 1))
        self._minq = []
        self._ledger_exp_usd = 0.0
        self._fees_modeled_total = 0.0

        wh, wm = str(cfg["window_start_et"]).split(":")
        eh, em = str(cfg["window_end_et"]).split(":")
        self.w_start = int(wh) * 60 + int(wm)
        self.w_end = int(eh) * 60 + int(em)

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
        self.order_purpose = {}
        self.pos_side = 0
        self.pos_qty = 0
        self.exit_qty_acc = 0
        self.entry_avg = None
        self.stop_px = None
        self.tp_px = None
        self.risk_dist = None
        self.stop_ticket = None
        self.tp_ticket = None

        self.trade_rs = []
        self.last_mapped = None
        self.race_stop_legs = 0
        self.race_tp_legs = 0
        self.race_pnl_usd = 0.0
        self._last_equity = None
        self.trade_economics = []
        self.race_pnl_obs = 0.0
        self._equity_deltas = []
        self._eq_at_entry = None
        self._race_eq_open = None
        self._flatten_tickets = []
        self._row_written = False
        self.d_bars5_total = 0
        self.tzcheck_ok = 0
        self.qty_max_seen = 0

        self._starting_tpv = None
        self.Debug(f"SCIFVG init {cfg['instrument']} trade {start}..{end} "
                   f"warmup_from={ws.isoformat()} win={cfg['window_start_et']}-"
                   f"{cfg['window_end_et']} hash={self.exp_hash}")

    def _equity(self):
        try:
            return float(self.portfolio.total_portfolio_value)
        except Exception:
            return 0.0


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

    def _eod_resolve(self, et, cid):
        """Close open cycle at last mark; r is net (fees deducted)."""
        side = self.pos_side
        exit_px = getattr(self, "_last_min_close", None) or self.entry_avg
        r_gross_e = ((exit_px - self.entry_avg) / self.risk_dist) * side
        qty_e = max(int(self.pos_qty), 1)
        pv_qty_e = self.point_value * qty_e
        fee_rt_e = 2.0 * float(self.cfg["commission_per_side"]) * qty_e
        usd_net_e = r_gross_e * self.risk_dist * pv_qty_e - fee_rt_e
        r_contrib = usd_net_e / (self.risk_dist * pv_qty_e)
        self._ledger_exp_usd += usd_net_e
        self._fees_modeled_total += fee_rt_e
        self.trade_economics.append({
            "cycle_id": cid,
            "candidate": str(self.cfg.get("variant")),
            "side": side,
            "entry_px": round(self.entry_avg, 2),
            "entry_time": getattr(self, "_cyc_entry_ts", None),
            "exit_px": round(exit_px, 2), "exit_time": str(et),
            "exit_kind": "eod",
            "r": round(r_contrib, 4),
            "friction_r": round(-fee_rt_e / (self.risk_dist * pv_qty_e), 4),
            "risk_dist": round(self.risk_dist, 4),
            "qty": self.pos_qty,
            "mfe_r": round(getattr(self, "_cyc_mfe", 0.0) / self.risk_dist, 4),
            "mae_r": round(getattr(self, "_cyc_mae", 0.0) / self.risk_dist, 4),
            "is_race": False,
            "resolved": "eod_mark",
        })
        self.trade_rs.append(round(r_contrib, 4))
        self.fun["r_trades"] = self.fun.get("r_trades", 0) + 1
        if r_contrib > 0:
            self.fun["r_wins"] = self.fun.get("r_wins", 0) + 1
        self._inc(f"{self._sk(side)}_exits_eod")
        self._inc("atomic_exits")

    def _advance_session(self, et):
        skey = self._session_key(et)
        if skey is None or skey == self.cur_session:
            return

        if self.pos_side != 0:
            _cid = f"{self.exp_hash}-{getattr(self, '_cycle_seq', 0)}"
            if not any(t.get("cycle_id") == _cid
                       for t in self.trade_economics):
                self._eod_resolve(et, _cid)
            else:
                self._inc("anomalous_exit_events")
        try:
            held = self.portfolio[self.fut.mapped].quantity
            if held != 0:
                mark = getattr(self, "_last_min_close", None) or \
                    self.entry_avg or self.stop_px
                slip = 20 * self.tick
                px = self._rt(mark + slip, up=True) if held < 0 \
                    else self._rt(mark - slip, up=False)
                tk = self.limit_order(self.fut.mapped, -held, px,
                                      tag=f"EOD-FLATTEN-{getattr(self, '_cycle_seq', 0)}")
                self._register_flatten_order(tk, held)
                self._inc("eod_flattens")
        except Exception:
            pass
        self._cancel_ticket(self.stop_ticket)
        self._cancel_ticket(self.tp_ticket)
        self.stop_ticket = None
        self.tp_ticket = None
        if self.setup is not None and self.pos_qty == 0:
            self._cancel_pending(None)
        self.pos_side = 0
        self.pos_qty = 0
        self.exit_qty_acc = 0
        self.entry_avg = None
        self.risk_dist = None
        self._eq_at_entry = None
        if self.bias == 0:
            self._inc("no_bias")
        self.cur_session = skey
        self.pdh = self.cur_high
        self.pdl = self.cur_low
        self.cur_high = None
        self.cur_low = None
        self.session_tried = set()
        try:
            cur_mapped = self.fut.mapped
            if self.last_mapped is not None and cur_mapped is not None \
                    and str(cur_mapped) != str(self.last_mapped):
                self._inc("rollovers")
                try:
                    held = self.portfolio[cur_mapped].quantity
                    if held != 0:
                        _m = getattr(self, "_last_min_close", None)
                        if _m is None:
                            self._inc("rollover_no_mark")
                            _m = float(cur_mapped.price if hasattr(
                                cur_mapped, "price") else 0.0) or None
                        _px = self._rt(_m + 20 * self.tick if held < 0
                                       else _m - 20 * self.tick,
                                       up=(held < 0))
                        tk = self.limit_order(cur_mapped, -held, _px,
                                              tag="ROLLOVER-FLATTEN")
                        self._register_flatten_order(tk, held)
                        self._inc("flatten_fills")
                except Exception:
                    pass
                if self.setup is not None:
                    self.setup = None
                    self._inc("rollover_setup_killed")
                self.pos_side = 0
                self.pos_qty = 0
                self.exit_qty_acc = 0
                self.risk_dist = None
                self.entry_avg = None
                self._eq_at_entry = None
                self._row_written = False
        except Exception:
            pass
        try:
            self.last_mapped = self.fut.mapped
        except Exception:
            pass
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

    def _scan_fvgs(self, upto_idx, side):
        """3-candle opposing FVGs."""
        out = []
        lo = max(2, upto_idx - self.cfg["fvg_max_age_bars"])
        m = self.cfg["fvg_min_ticks"] * self.tick
        for i in range(lo, upto_idx + 1):
            if side > 0:
                top = self.bars5[i - 2]["low"]
                bot = self.bars5[i]["high"]
                if top - bot >= m:
                    out.append({"lo": bot, "hi": top, "created": i})
            else:
                bot = self.bars5[i - 2]["high"]
                top = self.bars5[i]["low"]
                if top - bot >= m:
                    out.append({"lo": bot, "hi": top, "created": i})
        return out

    def _dead(self, g, cur_idx, side):
        for j in range(g["created"] + 1, cur_idx + 1):
            if side > 0:
                if self.bars5[j]["close"] < g["lo"]:
                    return True
            else:
                if self.bars5[j]["close"] > g["hi"]:
                    return True
        return False

    def _new_setup_allowed(self):
        return (self.setup is None and self.pos_qty == 0
                and self.pdh is not None and self.pdl is not None)

    def _depth_thresholds(self, ref_px):
        """Depth thresholds; bps overrides ticks."""
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
        """Arm sweeps; both sides if events_only."""
        events_only = (str(self.cfg.get("variant")) == "events_only")
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
                "ref_open": None, "ref_idx": None,
                "cisd_deadline": None, "fvg": None, "inv_deadline": None,
                "cisd_idx": None, "retest_deadline": None,
                "entry_id": None, "bias_aligned": (self.bias == side),
                "arm_et": str(et)}
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

        if s["stage"] == "SWEPT":
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
                if str(self.cfg.get("variant")) == "events_only":
                    buf = self._stop_buffer(b["close"])
                    stop = (s["extreme"] - buf) if side > 0 \
                        else (s["extreme"] + buf)
                    dist = abs(b["close"] - stop)
                    self._ev_seq = getattr(self, "_ev_seq", 0) + 1
                    self._ev_candidates.append({
                        "event_id": f"{self.exp_hash}-{self._ev_seq:06d}",
                        "bias_aligned": bool(s.get(
                            "bias_aligned", self.bias == side)),
                        "side": side,
                        "date": str(getattr(et, "date", lambda: et)()),
                        "ts0": _now_ts,
                        "px": float(b["close"]),
                        "stop_px": float(stop), "risk_dist": float(dist),
                        "idx0": self._abs_now,
                        "remaining": set(self.cfg.get(
                            "event_horizons", [120])),
                        "mfe_r": 0.0, "mae_r": 0.0,
                        **self._shadow_labels(s, b)})
                    self.setup = None
                    return
                s["stage"] = "CISD"
                s["cisd_deadline"] = idx + self.cfg["cisd_max_bars"]
                s["ref_open"] = None
                lo = max(0, idx - 200)
                for j in range(s["extreme_idx"], lo - 1, -1):
                    bb = self.bars5[j]
                    opposing = (bb["close"] < bb["open"]) if side > 0 \
                        else (bb["close"] > bb["open"])
                    if opposing:
                        s["ref_open"] = bb["open"]
                        s["ref_idx"] = j
                        break
                if s["ref_open"] is None:
                    self._inc(f"{K}_cisd_timeout")
                    self.setup = None
                    return
                if str(self.cfg.get("variant", "candidate")) == "ablate_cisd":
                    s["stage"] = "CISD"
                    s["cisd_immediate"] = True
                return
            if idx >= s["reclaim_deadline"]:
                self._inc(f"{K}_no_reclaim")
                self.setup = None
            return

        if s["stage"] == "CISD":
            if s.pop("cisd_immediate", False):
                trigger = True
            else:
                trigger = ((b["close"] > s["ref_open"]) if side > 0
                           else (b["close"] < s["ref_open"]))
            if str(self.cfg.get("variant", "candidate")) == "ablate_fvg":
                if trigger and self._in_window(et):
                    stop_mode = str(self.cfg.get("stop_mode", "sweep"))
                    ext = s["extreme"]
                    buf = self.cfg["stop_buffer_ticks"] * self.tick
                    stop = self._rt(ext - buf, up=False) if side > 0 \
                        else self._rt(ext + buf, up=True)
                    entry = self._rt(b["close"], up=(side > 0))
                    dist = abs(entry - stop)
                    if dist > 0:
                        qty = int(float(self.cfg["risk_usd"]) /
                                  (dist * self.point_value))
                        qty = min(qty, int(self.cfg["max_contracts"]))
                        tp = self._rt(
                            entry + side * float(self.cfg["target_r"]) * dist,
                            up=(side > 0)) if side > 0 else self._rt(
                            entry - float(self.cfg["target_r"]) * dist, up=False)
                        if qty >= 1:
                            s["stage"] = "FILLED"
                            mk = self._rt(entry + side * 2 * self.tick,
                                          up=(side > 0))
                            s["entry_px"] = entry
                            s["stop_px"] = stop
                            s["tp_px"] = tp
                            s["qty"] = qty
                            sym = self.fut.mapped
                            tk = self.limit_order(sym, qty * side, mk,
                                                  tag=f"E-{K}-{idx}-{self.exp_hash}")
                            self.order_purpose[tk.order_id] = ("entry", side)
                            self._inc(f"{K}_submits")
                            return
            if trigger:
                imm = None
                elig = None
                for g in self._scan_fvgs(idx - 1, side):
                    if idx - g["created"] > self.cfg["fvg_max_age_bars"]:
                        continue
                    if self._dead(g, idx, side):
                        continue
                    if self.cfg.get("invert_on_cisd_bar", 0) == 1:
                        mid = (g["lo"] + g["hi"]) / 2.0
                        crossed = (b["close"] > mid) if side > 0 else (b["close"] < mid)
                        if crossed:
                            if imm is None or g["created"] < imm["created"]:
                                imm = g
                            continue
                    if side > 0:
                        prox = abs(b["close"] - g["hi"])
                    else:
                        prox = abs(b["close"] - g["lo"])
                    if elig is None or prox < elig.get("_prox", 1e18):
                        gg = dict(g)
                        gg["_prox"] = prox
                        elig = gg
                chosen = imm if imm is not None else elig
                if chosen is None:
                    self._inc(f"{K}_cisd_ok")
                    self._inc(f"{K}_inv_timeout")
                    self.setup = None
                    return
                self._inc(f"{K}_cisd_ok")
                s["fvg"] = chosen
                s["cisd_idx"] = idx
                if imm is not None:
                    self._inc(f"{K}_inv_ok")
                    s["stage"] = "PENDING"
                    s["retest_deadline"] = idx + self.cfg["retest_max_bars"]
                    self._submit_entry(s, idx)
                else:
                    s["stage"] = "INV"
                    s["inv_deadline"] = idx + self.cfg["inv_max_bars"]
                return
            if idx >= s["cisd_deadline"]:
                self._inc(f"{K}_cisd_timeout")
                self.setup = None
            return

        if s["stage"] == "INV":
            g = s["fvg"]
            mid = (g["lo"] + g["hi"]) / 2.0
            inverted = (b["close"] > mid) if side > 0 else (b["close"] < mid)
            if inverted:
                self._inc(f"{K}_inv_ok")
                s["stage"] = "PENDING"
                s["retest_deadline"] = idx + self.cfg["retest_max_bars"]
                self._submit_entry(s, idx)
            elif idx >= s["inv_deadline"]:
                self._inc(f"{K}_inv_timeout")
                self.setup = None
            return

    def _submit_entry(self, s, idx):
        side = s["side"]
        b_close_ref = getattr(self, "_last_bar_close", None) or (
            self.bars5[-1]["close"] if self.bars5 else 0.0)
        K = self._sk(side)
        g = s["fvg"]
        ext = s["extreme"]
        mid = (g["lo"] + g["hi"]) / 2.0
        loc = str(self.cfg.get("entry_location", "proximal"))
        use_mid = (loc == "midpoint")
        use_far = (loc == "gap_far")
        stop_mode = str(self.cfg.get("stop_mode", "sweep"))

        if side > 0:
            stop_base = g["lo"] - self.cfg["stop_buffer_ticks"] * self.tick \
                if stop_mode == "gap" else ext - self.cfg["stop_buffer_ticks"] * self.tick
            stop = self._rt(stop_base, up=False)
            if use_far:
                entry_px = g["lo"]
            elif use_mid:
                entry_px = mid
            else:
                entry_px = g["hi"]
            entry = self._rt(entry_px, up=True)
            tp = self._rt(entry + float(self.cfg["target_r"]) * (entry - stop), up=True)
        else:
            stop_base = g["hi"] + self.cfg["stop_buffer_ticks"] * self.tick \
                if stop_mode == "gap" else ext + self.cfg["stop_buffer_ticks"] * self.tick
            stop = self._rt(stop_base, up=True)
            if use_far:
                entry_px = g["hi"]
            elif use_mid:
                entry_px = mid
            else:
                entry_px = g["lo"]
            entry = self._rt(entry_px, up=False)
            tp = self._rt(entry - float(self.cfg["target_r"]) * (stop - entry), up=False)
        dist = abs(entry - stop)
        if dist <= 0:
            self._inc(f"{K}_cancel_other")
            self.setup = None
            return
        qty = int(float(self.cfg["risk_usd"]) / (dist * self.point_value))
        qty = min(qty, int(self.cfg["max_contracts"]))
        if qty < 1:
            self._inc(f"{K}_size_skips")
            self.setup = None
            return

        sym = self.fut.mapped
        if sym is None:
            self._inc(f"{K}_cancel_other")
            self.setup = None
            return
        entry_px_mkt = b_close_ref if b_close_ref else (
            self.bars5[-1]["close"] if self.bars5 else 0.0)
        if str(self.cfg.get("variant", "candidate")) == "shadow_moc":
            mk = self._rt(entry_px_mkt + side * 2 * self.tick,
                          up=(side > 0))
            try:
                tk = self.limit_order(sym, qty * side, mk,
                                      tag=f"E-{K}-{idx}-{self.exp_hash}")
            except Exception:
                self._inc(f"{K}_cancel_other")
                self.setup = None
                return
            s["entry_id"] = tk.order_id
            s["stage"] = "FILLED"
            s["entry_px"] = self._rt(b_close_ref, up=(side > 0))
            s["qty"] = qty
            s["stop_px"] = stop
            s["tp_px"] = tp
            self.order_purpose[tk.order_id] = ("entry", side)
            self._inc(f"{K}_submits")
            return
        try:
            tk = self.limit_order(sym, qty * side, entry,
                                  tag=f"E-{K}-{idx}-{self.exp_hash}")
        except Exception:
            self._inc(f"{K}_cancel_other")
            self.setup = None
            return
        s["entry_id"] = tk.order_id
        s["entry_px"] = entry
        s["qty"] = qty
        s["stop_px"] = stop
        s["tp_px"] = tp
        self.order_purpose[tk.order_id] = ("entry", side)
        self._inc(f"{K}_submits")

    def _cancel_pending(self, counter):
        s = self.setup
        if s and s.get("stage") == "FILLED":
            return
            try:
                t = self.transactions.get_order_by_id(s["entry_id"])
                if t is not None and t.status == OrderStatus.SUBMITTED \
                        and t.quantity_left != 0:
                    t.cancel()
            except Exception:
                pass
            self.order_purpose.pop(s["entry_id"], None)
        if counter:
            self._inc(counter)
        self.setup = None

    def on_data(self, data):
        for symbol, bar in data.bars.items():
            if symbol != self.fut.symbol and symbol != self.fut.mapped:
                continue
            self._last_min_close = float(bar.close)
            if self.pos_side != 0:
                self._minq.append({
                    "o": float(bar.open), "h": float(bar.high),
                    "l": float(bar.low), "c": float(bar.close)})
                self._drain_minq()
                continue
            self._minq = []

    def _on_5m_consolidated(self, consolidated):
        """One call per 5m slot; ET-native."""
        et = consolidated.end_time
        if getattr(self, "_starting_tpv", None) is None:
            try:
                self._starting_tpv = float(self.portfolio.total_portfolio_value)
            except Exception:
                self._starting_tpv = 0.0
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
            elif 9 * 60 + 30 < hm < 12 * 60:
                self.Debug(f"TZCHECK candidate bar et={et.isoformat()} "
                           f"(waiting for 09:35)")

        skey = self._session_key(et)
        if skey is not None:
            self._advance_session(et)

        if self.cur_high is None or agg["high"] > self.cur_high:
            self.cur_high = agg["high"]
        if self.cur_low is None or agg["low"] < self.cur_low:
            self.cur_low = agg["low"]

        self._accumulate_h4(agg)

        if self.setup is not None and self.setup["stage"] == "PENDING" \
                and self.pos_qty == 0:
            self._manage_pending(agg, agg["idx"], et, skey)

        self._advance_events(agg)

        warm = et.date() >= self.camp_start
        if str(self.cfg.get("entry_mode", "signal")) == "random":
            raise RuntimeError("random null retired; use paired variants")
        elif warm and skey is not None and self._in_window(et) \
                and self._new_setup_allowed() and self.bias in (1, -1):
            self._try_arm_attempt(agg, agg["idx"], et, skey)

        if self.setup is not None and self.setup["stage"] in ("SWEPT", "CISD", "INV"):
            if self._in_window(et) and self.setup["arm_sk"] == skey:
                self._advance_setup(agg, agg["idx"], et, skey)
            else:
                K = self._sk(self.setup["side"])
                self._cancel_pending(f"{K}_cancel_window")

    def _elapsed_min(self, ev, agg):
        """Minutes since reclaim confirmation (wall-clock)."""
        try:
            return (agg["ts"] - ev["ts0"]) / 60.0
        except Exception:
            return (self._abs_now - ev["idx0"]) * 5.0

    def _shadow_labels(self, s, b):
        """Shadow labels (never gate)."""
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

    def _advance_events(self, agg):
        """Resolve candidates (wall-clock)."""
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
            for h in list(ev["remaining"]):
                if self._elapsed_min(ev, agg) >= h:
                    ret_r = ((agg["close"] - ev["px"]) / rd) * ev["side"]
                    self._ev_results.append({
                        "event_id": ev["event_id"],
                        "last_reclaim_et": str(agg.get("et")),
                        "bias_aligned": ev["bias_aligned"],
                        "arm": "counter" if not ev["bias_aligned"]
                               else "primary",
                        "side": ev["side"], "date": ev["date"],
                        "h_min": h, "ret_r": round(ret_r, 6),
                        "entry_px": round(ev["px"], 2),
                        "mfe_r": round(ev["mfe_r"], 4),
                        "mae_r": round(ev["mae_r"], 4),
                        **{k: ev.get(k) for k in
                           ("shadow_cisd", "shadow_fvg", "shadow_ifvg")}})
                    ev["remaining"].discard(h)
            if ev["remaining"]:
                still.append(ev)
        self._ev_candidates = still

    def _rebase(self, trim):
        if self.setup:
            for f in ("b0", "reclaim_deadline", "extreme_idx", "cisd_deadline",
                      "inv_deadline", "cisd_idx", "retest_deadline", "ref_idx"):
                v = self.setup.get(f)
                if isinstance(v, int):
                    self.setup[f] = v - trim
            if self.setup.get("fvg"):
                self.setup["fvg"]["created"] -= trim

    def _manage_pending(self, b, idx, et, skey):
        s = self.setup
        side = s["side"]
        K = self._sk(side)
        g = s["fvg"]
        if not self._in_window(et):
            self._cancel_pending(f"{K}_cancel_window")
            return
        if self.bias != side:
            self._cancel_pending(f"{K}_cancel_bias")
            return
        invalid = (b["close"] < g["lo"]) if side > 0 else (b["close"] > g["hi"])
        if invalid:
            self._cancel_pending(f"{K}_cancel_invalid")
            return
        if idx >= s["retest_deadline"]:
            self._cancel_pending(f"{K}_cancel_expiry")
            return

    def on_order_event(self, order_event):
        if order_event.status == OrderStatus.SUBMITTED:
            return
        oid = order_event.order_id
        purpose = self.order_purpose.get(oid)
        status = order_event.status

        if status == OrderStatus.FILLED:
            fq = abs(order_event.fill_quantity)
            fp = float(order_event.fill_price)
            self._n_fill_events = getattr(self, "_n_fill_events", 0) + 1
            if purpose and purpose[0] == "flatten":
                self._inc("flatten_fills")
                self.order_purpose.pop(oid, None)
                _cid = f"{getattr(self, 'exp_hash', '')}-{getattr(self, '_cycle_seq', 0)}"
                try:
                    tg = str(getattr(order_event.order, "tag", ""))
                    tag_cycle = (f"{self.exp_hash}-{tg.rsplit('-', 1)[1]}"
                                 if tg.startswith("EOD-FLATTEN-") else None)
                except Exception:
                    tag_cycle = None
                if (tag_cycle != _cid or any(
                        t.get("cycle_id") == _cid
                        for t in self.trade_economics)):
                    self.pos_side = 0
                    self.pos_qty = 0
                    self.exit_qty_acc = 0
                    self.risk_dist = None
                    self.entry_avg = None
                    return
                if self.pos_side != 0 and self.risk_dist:
                    side = self.pos_side
                    r_contrib = ((fp - self.entry_avg) / self.risk_dist) * side
                    self.exit_qty_acc += fq
                    self.trade_economics.append({
                        "r": round(r_contrib, 4),
                        "risk_dist": self.risk_dist,
                        "qty": fq,
                        "is_race": getattr(self, "_race_leg_pending", False),
                    })
                    self._race_leg_pending = False
                    t = self.trade_economics[-1]
                    eq_now = self._equity()
                    t["obs_usd"] = round(eq_now - (self._eq_at_entry or eq_now), 2)
                    self._eq_at_entry = eq_now
                    if self.exit_qty_acc >= self.pos_qty:
                        is_race = self.trade_economics[-1].get("is_race", False)
                        if not is_race:
                            self.fun["r_trades"] = self.fun.get("r_trades", 0) + 1
                            if r_contrib > 0:
                                self.fun["r_wins"] = self.fun.get("r_wins", 0) + 1
                            self.trade_rs.append(round(r_contrib, 4))
                        self.pos_side = 0
                        self.exit_qty_acc = 0
                return
            if purpose is None:
                self._inc("late_fill_events")
                self.pos_side = 0
                self.pos_qty = 0
                self.exit_qty_acc = 0
                return
            kind = purpose[0]
            side = purpose[1]
            if kind == "entry":
                K = self._sk(side)
                self._inc(f"{K}_fills")
                self._row_written = False
                if self.pos_side != 0 and self.pos_side != side:
                    self._inc("entry_reversal_blocks")
                    self._fail_closed_flatten("entry_reversal")
                    return
                if self.pos_qty == 0:
                    self.entry_avg = fp
                else:
                    self.entry_avg = ((self.entry_avg * self.pos_qty) + fp * fq) / (self.pos_qty + fq)
                self.pos_side = side
                self.pos_qty += fq
                self.qty_max_seen = max(self.qty_max_seen, fq)
                s = self.setup
                if s is None:
                    self._inc("orphan_entry_fills")
                    self._fail_closed_flatten("entry_fill_no_state")
                    return
                self.stop_px = s["stop_px"]
                self.tp_px = s["tp_px"]
                self.risk_dist = abs(fp - s["stop_px"])
                self.exit_qty_acc = 0
                self._eq_at_entry = self._equity()
                self._row_written = False
                self._cycle_seq = getattr(self, "_cycle_seq", 0) + 1
                self._cyc_mfe = 0.0
                self._cyc_mae = 0.0
                self._cyc_entry_ts = str(getattr(self, "time", ""))
                self._inc(f"{K}_cycles_opened")
                return

            if kind in ("stop", "tp"):
                self._inc("anomalous_exit_events")
                self.order_purpose.pop(oid, None)
                return

        if status in (OrderStatus.CANCELED, OrderStatus.INVALID):
            purpose = self.order_purpose.get(oid)
            if purpose and purpose[0] == "entry":
                self.order_purpose.pop(oid, None)
                s = self.setup
                if (s is not None and s.get("entry_id") == oid
                        and self.pos_qty == 0):
                    K = self._sk(purpose[1])
                    if status == OrderStatus.INVALID:
                        self._inc(f"{K}_cancel_other")
                    self.setup = None
            elif purpose and purpose[0] in ("stop", "tp"):
                self.order_purpose.pop(oid, None)
    def _drain_minq(self):
        """Drain minute queue vs open cycle."""
        if self.pos_side == 0:
            self._minq = []
            return
        while self._minq and self.pos_side != 0:
            m = self._minq.pop(0)
            self._resolve_cycle_minute(m["o"], m["h"], m["l"], m["c"],
                                       self.time)

    def _resolve_cycle_minute(self, o, h, l, c, bar_end_et):
        """Cycle resolve."""
        side = self.pos_side
        if side == 0 or self.risk_dist is None or self.entry_avg is None:
            return
        if side > 0:
            self._cyc_mfe = max(self._cyc_mfe, h - self.entry_avg)
            self._cyc_mae = min(self._cyc_mae, l - self.entry_avg)
            hit_stop = l <= self.stop_px
            hit_tp = h >= self.tp_px
        else:
            self._cyc_mfe = max(self._cyc_mfe, self.entry_avg - l)
            self._cyc_mae = min(self._cyc_mae, self.entry_avg - h)
            hit_stop = h >= self.stop_px
            hit_tp = l <= self.tp_px

        if not (hit_stop or hit_tp):
            return

        exit_if_stop = hit_stop or (hit_stop and hit_tp)
        px = self.stop_px if exit_if_stop else self.tp_px
        kind = "stop" if exit_if_stop else "tp"
        slip = self.slippage_ticks * self.tick
        fill_px = px - slip * side
        qty = max(int(self.pos_qty), 1)
        pv_qty = self.point_value * qty
        fee_rt = 2.0 * float(self.cfg["commission_per_side"]) * qty
        r_gross = ((px - self.entry_avg) / self.risk_dist) * side
        r_fill = ((fill_px - self.entry_avg) / self.risk_dist) * side
        usd_net = r_fill * self.risk_dist * pv_qty - fee_rt
        r_contrib = usd_net / (self.risk_dist * pv_qty)
        cid = f"{self.exp_hash}-{self._cycle_seq}"
        self._ledger_exp_usd += usd_net
        self._fees_modeled_total += fee_rt
        row = {
            "cycle_id": cid,
            "candidate": str(self.cfg.get("variant", "candidate")),
            "side": side,
            "entry_px": round(self.entry_avg, 2),
            "entry_time": getattr(self, "_cyc_entry_ts", None),
            "exit_px": round(fill_px, 2),
            "barrier_px": round(px, 2),
            "exit_time": str(bar_end_et),
            "exit_kind": kind,
            "r": round(r_contrib, 4),
            "r_gross": round(r_gross, 4),
            "friction_r": round(r_contrib - r_gross, 4),
            "risk_dist": round(self.risk_dist, 4),
            "qty": self.pos_qty,
            "mfe_r": round(self._cyc_mfe / self.risk_dist, 4),
            "mae_r": round(self._cyc_mae / self.risk_dist, 4),
            "is_race": False,
            "resolved": "atomic",
        }
        self.trade_economics.append(row)
        self.trade_rs.append(round(r_contrib, 4))
        self._row_written = True
        self.fun["r_trades"] = self.fun.get("r_trades", 0) + 1
        if r_contrib > 0:
            self.fun["r_wins"] = self.fun.get("r_wins", 0) + 1
        self._inc(f"{self._sk(side)}_exits_{kind}")
        self._inc("atomic_exits")
        self.pos_side = 0
        self.pos_qty = 0
        self.exit_qty_acc = 0
        self.entry_avg = None
        self.risk_dist = None
        self.stop_ticket = None
        self.tp_ticket = None
        self.setup = None


    def _cancel_ticket(self, t):
        if t is None:
            return
        try:
            if t.status == OrderStatus.SUBMITTED and t.quantity_left != 0:
                t.cancel()
        except Exception:
            pass

    def _register_flatten_order(self, ticket, held_qty):
        """Track flatten fill."""
        if ticket is None:
            return
        self.order_purpose[ticket.order_id] = ("flatten", 1 if held_qty < 0 else -1)
        self._flatten_tickets.append(ticket.order_id)

    def _fail_closed_flatten(self, reason):
        try:
            held = self.portfolio[self.fut.mapped].quantity
            if held:
                _m = getattr(self, "_last_min_close", None)
                _ref = _m if isinstance(_m, (int, float)) and _m > 0 \
                    else self.entry_avg
                if not (_ref and _ref > 0):
                    _ref = self.stop_px
                if _ref and _ref > 0:
                    _px = self._rt(
                        _ref + 20 * self.tick if held < 0
                        else _ref - 20 * self.tick, up=(held < 0))
                    tk = self.limit_order(self.fut.mapped, -held, _px,
                                          tag=f"FC-{reason}")
                    self._register_flatten_order(tk, held)
                else:
                    self._inc("flatten_no_reference")
        except Exception:
            pass
        self._cancel_ticket(self.stop_ticket)
        self._cancel_ticket(self.tp_ticket)
        self.stop_ticket = None
        self.tp_ticket = None
        self.pos_side = 0
        self.pos_qty = 0
        self.exit_qty_acc = 0
        self.entry_avg = None
        self.risk_dist = None
        self.setup = None
        self._inc("forced_flattens")

    def _sample_equity(self):
        """Equity drift detector."""
        try:
            eq = float(self.portfolio.total_portfolio_value)
        except Exception:
            return
        if self._last_equity is not None:
            self._equity_deltas.append(eq - self._last_equity)
        self._last_equity = eq

    def _reconcile_pnl(self):
        """Hard gate identities (see conformance doc)."""
        out = {"ok": False}
        try:
            tb_trades = list(self.trade_builder.closed_trades)
        except Exception:
            tb_trades = []
        n_tb = len(tb_trades)

        fees_actual = 0.0
        i1_profit_raw = 0.0
        for t in tb_trades:
            i1_profit_raw += float(getattr(t, "profit_loss", 0.0) or 0.0)
            try:
                fees_actual += float(t.total_fees)
            except Exception:
                pass

        try:
            tpv_delta = float(self.portfolio.total_portfolio_value) \
                - float(self._starting_tpv)
        except Exception:
            tpv_delta = None
        if tpv_delta is None:
            i1_resid, tol_i1 = 0.0, 0.0
            i1_cash_resid = None
        else:
            i1_cash_resid = abs((i1_profit_raw - fees_actual) - tpv_delta)
            i1_resid, tol_i1 = i1_cash_resid, max(0.01 * abs(tpv_delta), 25.0)

        led_exp = float(getattr(self, "_ledger_exp_usd", 0.0))
        i1_ledger_resid = abs(led_exp - i1_profit_raw)
        tol_i1_ledger = 25.0

        fees_modeled_total = float(getattr(self, "_fees_modeled_total", 0.0))
        i2_resid = abs(fees_modeled_total - fees_actual)
        tol_i2 = 25.0

        fills = self.fun.get("L_fills", 0) + self.fun.get("S_fills", 0)
        orphans = self.fun.get("orphan_entry_fills", 0)
        lates = self.fun.get("late_fill_events", 0)
        flatfills = self.fun.get("flatten_fills", 0)
        late_closes = self.fun.get("late_closes", 0)
        cycles_opened = self.fun.get("L_cycles_opened", 0) + \
            self.fun.get("S_cycles_opened", 0)
        atomic_exits = self.fun.get("atomic_exits", 0)
        anomalies = self.fun.get("anomalous_exit_events", 0)
        untracked = self.fun.get("untracked_fills", 0)
        rows = self.trade_economics
        ex_stop = sum(1 for t in rows if t.get("exit_kind") == "stop")
        ex_tp = sum(1 for t in rows if t.get("exit_kind") == "tp")
        ex_eod = sum(1 for t in rows if t.get("exit_kind") == "eod")
        tr_r = float(self.cfg["target_r"])
        purity_viol = sum(1 for t in rows if t.get("exit_kind") in ("stop", "tp")
                          and abs(abs(t.get("r_gross", 0.0)) - (1.0 if
                          t["exit_kind"] == "stop" else tr_r)) > 5e-4)
        i3_ok = (fills == cycles_opened and atomic_exits == cycles_opened
                 and anomalies == 0 and untracked == 0
                 and len(self.trade_economics) == cycles_opened)
        late_closes = 0
        import statistics as _stat
        rds = [t["risk_dist"] for t in rows if t.get("risk_dist")]
        median_risk_dist = _stat.median(rds) if rds else None
        friction_R_total = sum(float(t.get("friction_r", 0.0)) for t in rows)
        ok = (i1_resid <= tol_i1 and i1_ledger_resid <= tol_i1_ledger
              and i2_resid <= tol_i2 and i3_ok and purity_viol == 0)
        out.update({
            "ok": ok, "n_tradebuilder": n_tb,
            "i1_profit_raw": round(i1_profit_raw, 2),
            "ledger_exp_usd": round(led_exp, 2),
            "i1_ledger_resid": round(i1_ledger_resid, 2),
            "i1_cash_resid": (round(i1_cash_resid, 2)
                              if i1_cash_resid is not None else None),
            "fees_actual": round(fees_actual, 2),
            "fees_modeled_total": round(fees_modeled_total, 2),
            "exits_barrier_stop": ex_stop, "exits_barrier_tp": ex_tp,
            "exits_eod": ex_eod, "barrier_purity_violations": purity_viol,
            "median_risk_dist": (round(median_risk_dist, 4)
                                 if median_risk_dist is not None else None),
            "friction_R_total": round(friction_R_total, 4),
            "i1_resid": round(i1_resid, 2), "i1_tol": round(tol_i1, 2),
            "i2_resid": round(i2_resid, 2),
            "tpv_delta": (round(tpv_delta, 2)
                          if tpv_delta is not None else None),
            "fills_vs_ledger_orphans":
                f"{fills}/{len(self.trade_economics)}+{orphans}+{late_closes}",
            "late_events": lates})
        return out

    def _export_charts(self):
        """Build charts locally; register once at end."""
        local = {}
        for e in getattr(self, "_ev_results", []):
            cname = f"E19B-h{e['h_min']}"
            sname = "a" if e.get("bias_aligned") else "o"
            try:
                ts_dt = datetime.fromisoformat(e["last_reclaim_et"])
            except Exception:
                continue
            ts = ts_dt
            if cname not in local:
                ch = Chart(cname)
                sa = Series("a", SeriesType.SCATTER)
                so = Series("o", SeriesType.SCATTER)
                ch.add_series(sa)
                ch.add_series(so)
                local[cname] = ch
            sr = local[cname].series[sname]
            sr.add_point(ts_dt, float(e['ret_r']))
        for ch in local.values():
            self.add_chart(ch)

    def _export_ledgers(self, rec):
        """EVENT/TRADE/META to Object Store."""
        try:
            t = self.exp_hash
            for key, rows in (f"E19B/{t}/events.jsonl",
                              getattr(self, "_ev_results", [])), \
                             (f"E19B/{t}/trades.jsonl",
                              self.trade_economics):
                buf = "\n".join(json.dumps(r, sort_keys=True) for r in rows)
                self.object_store.save_bytes(key, buf.encode())
            meta = {"funnel": self.fun, "reconcile": rec, "cfg": self.cfg}
            self.object_store.save_bytes(f"E19B/{t}/meta.json",
                                         json.dumps(meta,
                                                    sort_keys=True).encode())
            self.RuntimeStatistics["os_events"] = str(len(self._ev_results))
            self.RuntimeStatistics["os_trades"] = \
                str(len(self.trade_economics))
        except Exception as ex:
            self.Debug(f"OBJECT STORE EXPORT FAILED: {ex}")

    def on_end_of_algorithm(self):
        held = 0
        try:
            held = self.portfolio[self.fut.mapped].quantity
        except Exception:
            pass
        self._export_charts()
        try:
            rec = self._reconcile_pnl()
        except Exception:
            rec = {"ok": False, "error": "reconcile_unavailable"}
        rs = self.trade_rs
        wins = sum(1 for r in rs if r > 0)
        losses = sum(1 for r in rs if r <= 0)
        avg_r = sum(rs) / len(rs) if rs else 0.0
        gross_w = sum(r for r in rs if r > 0)
        gross_l = -sum(r for r in rs if r <= 0)
        pf = (gross_w / gross_l) if gross_l > 0 else (999.0 if gross_w > 0 else 0.0)
        self._export_ledgers(rec)
        self.Debug("RECONCILE " + json.dumps(rec, sort_keys=True)[:600])
        self.Debug(json.dumps({
            "exp_hash": self.exp_hash, "cfg": self.cfg,
            "trades": len(rs), "wins": wins, "losses": losses,
            "win_rate": round(wins / len(rs), 4) if rs else 0.0,
            "avg_r": round(avg_r, 4), "pf_local_r": round(pf, 4),
            "max_consec_losses": self._max_consec_losses(rs),
            "open_at_end": held,
        }, sort_keys=True))
        try:
            self.RuntimeStatistics["funnel_sessions"] = str(self.fun["sessions"])
            self.RuntimeStatistics["funnel_L_entries"] = str(self.fun["L_fills"])
            self.RuntimeStatistics["funnel_S_entries"] = str(self.fun["S_fills"])
            self.RuntimeStatistics["local_trades"] = str(len(rs))
            self.RuntimeStatistics["exp_hash"] = self.exp_hash
            for k in sorted(self.fun.keys()):
                self.RuntimeStatistics[f"f_{k}"] = str(self.fun[k])
            self.RuntimeStatistics["d_h4_published"] = str(len(self.h4_pub))
            self.RuntimeStatistics["d_swing_hi"] = str(len(self.swing_hi))
            self.RuntimeStatistics["d_swing_lo"] = str(len(self.swing_lo))
            self.RuntimeStatistics["r_trades"] = str(len(rs))
            self.RuntimeStatistics["r_wins"] = str(wins)
            self.RuntimeStatistics["r_avg"] = repr(round(avg_r, 4))
            self.RuntimeStatistics["r_pf"] = repr(round(pf, 4))
            self.RuntimeStatistics["r_sum"] = repr(round(sum(rs), 3))
            self.RuntimeStatistics["r_maxconsecL"] = str(self._max_consec_losses(rs))
            lw = [r for r in rs if r > 0]
            ll = [r for r in rs if r <= 0]
            self.RuntimeStatistics["r_avgwin"] = repr(round(sum(lw) / len(lw), 4)) if lw else "0"
            self.RuntimeStatistics["r_avgloss"] = repr(round(sum(ll) / len(ll), 4)) if ll else "0"
            self.RuntimeStatistics["rec_ok"] = "1" if rec["ok"] else "0"
            for k2 in ("i1_exp_usd", "i1_profit", "i1_resid",
                       "ledger_exp_usd", "i1_ledger_resid",
                       "i1_cash_resid", "fees_modeled_total",
                       "exits_barrier_stop", "exits_barrier_tp",
                       "exits_eod", "barrier_purity_violations",
                       "median_risk_dist", "friction_R_total"):
                self.RuntimeStatistics[f"rec_{k2}"] = repr(rec.get(k2))
            for k4 in ("eod_flattens", "rollovers"):
                self.RuntimeStatistics[k4] = str(self.fun.get(k4, 0))
            self.RuntimeStatistics["d_bars5_total"] = str(self.d_bars5_total)
            try:
                _s = int(self.fun["sessions"])
                self.RuntimeStatistics["bars_per_session"] = \
                    repr(round(self.d_bars5_total / _s, 1)) if _s else "0"
            except Exception:
                self.RuntimeStatistics["bars_per_session"] = "0"
            self.RuntimeStatistics["tzcheck_ok"] = str(self.tzcheck_ok)
            self.RuntimeStatistics["qty_max_seen"] = str(self.qty_max_seen)
            for k6 in ("flatten_fills", "untracked_fills",
                       "late_fill_events", "orphan_entry_fills",
                       "oco_void_legs"):
                self.RuntimeStatistics[f"f_{k6}"] = str(self.fun.get(k6, 0))
            _cyc = int(self.fun.get("L_cycles_opened", 0)) + \
                int(self.fun.get("S_cycles_opened", 0))
            self.RuntimeStatistics["d_cycles_opened"] = str(_cyc)
            self.RuntimeStatistics["d_atomic_exits"] = \
                str(self.fun.get("atomic_exits", 0))
            self.RuntimeStatistics["f_anomalous_exit_events"] = \
                str(self.fun.get("anomalous_exit_events", 0))
            self.RuntimeStatistics["f_late_fill_events"] = \
                str(self.fun.get("late_fill_events", 0))
            self.RuntimeStatistics["f_untracked_fills"] = \
                str(self.fun.get("untracked_fills", 0))
            for k5, v5 in (("d_rows_total", len(self.trade_economics)),
                           ("d_ev_results", len(self._ev_results)),
                           ("d_open_at_end", held),
                           ("d_race_rows", sum(1 for t in
                            self.trade_economics if t.get("is_race"))),
                           ("d_pos_side_end", self.pos_side),
                           ("d_exit_acc_end", self.exit_qty_acc),
                           ("d_n_fillevents", getattr(
                               self, "_n_fill_events", 0))):
                self.RuntimeStatistics[k5] = str(v5)
            for rk in ("n_tradebuilder", "i1_profit_raw", "i1_resid",
                       "i1_tol", "fees_actual", "fees_modeled_total",
                       "i2_resid", "tpv_delta", "fills_vs_ledger_orphans",
                       "late_events"):
                self.RuntimeStatistics[f"rec_{rk}"] = str(rec.get(rk))
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

    @staticmethod
    def _max_consec_losses(rs):
        best = cur = 0
        for r in rs:
            if r <= 0:
                cur += 1
                best = max(best, cur)
            else:
                cur = 0
        return best
