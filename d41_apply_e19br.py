"""Apply the E19B-R engine edits (v2.8) atomically and verify each landed.

Edits:
  1. init: _tr_series/_atr5 state
  2. handler: ATR(14) update per completed 5m bar
  3. emission: tradability floor gate (min_stop_ticks AND floor_atr_frac)
  4. cfg defaults: min_stop_ticks/floor_atr_frac + funnel keys
  5. resolver row: stop_px/risk_dist/shadow_mask/censored
  6. charts: rd-/mfe-/mae-/mask- companion series; n_event_rows RT

Each edit asserts its anchor; file must parse at the end.
"""
import ast
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
p = os.path.join(ROOT, "scifvg_main.py")
src = open(p, encoding="utf-8").read()
applied = []


def rep(name, old, new, count=1):
    global src
    if new in src:
        applied.append(f"{name}: already present")
        return
    assert old in src, f"anchor missing for {name}"
    src = src.replace(old, new, count)
    applied.append(f"{name}: applied")


# 1) state init
rep("state-init",
'''        self._ev_candidates = []
        self._ev_results = []
        self.charts = {}''',
'''        self._ev_candidates = []
        self._ev_results = []
        self._tr_series = []
        self._atr5 = None
        self.charts = {}''')

# 2) ATR update
rep("atr-update",
'''        self._abs_bar = getattr(self, "_abs_bar", -1) + 1
        self._abs_now = self._abs_bar''',
'''        self._abs_bar = getattr(self, "_abs_bar", -1) + 1
        self._abs_now = self._abs_bar
        _pc = self.bars5[-1]["close"] if self.bars5 else agg["close"]
        _tr = max(agg["high"] - agg["low"], abs(agg["high"] - _pc),
                  abs(_pc - agg["low"]))
        self._tr_series.append(_tr)
        if len(self._tr_series) > 14:
            self._tr_series.pop(0)
        if len(self._tr_series) == 14:
            self._atr5 = sum(self._tr_series) / 14.0''')

# 3) floor gate
rep("floor-gate",
'''                if str(self.cfg.get("variant")) == "events_only":
                    buf = self._stop_buffer(b["close"])
                    stop = (s["extreme"] - buf) if side > 0 \\
                        else (s["extreme"] + buf)
                    dist = abs(b["close"] - stop)
                    self._ev_seq = getattr(self, "_ev_seq", 0) + 1''',
'''                if str(self.cfg.get("variant")) == "events_only":
                    stop = ((s["extreme"]
                             - self._stop_buffer(b["close"])) if side > 0
                            else (s["extreme"]
                                  + self._stop_buffer(b["close"])))
                    dist = abs(b["close"] - stop)
                    floor = max(float(self.cfg.get("min_stop_ticks", 0))
                                * self.tick,
                                float(self.cfg.get("floor_atr_frac", 0))
                                * (self._atr5 or 0))
                    if dist < floor:
                        self._inc(f"{self._sk(side)}_floor_rejects")
                        self.setup = None
                        return
                    self._ev_seq = getattr(self, "_ev_seq", 0) + 1''')

# 4) cfg defaults + funnel keys
rep("cfg-defaults",
'''            "stop_buffer_bps": 0.0,''',
'''            "stop_buffer_bps": 0.0,
            "min_stop_ticks": 0.0, "floor_atr_frac": 0.0,''')
rep("funnel-keys",
'"excursion_depth_kills",',
'"excursion_depth_kills", "L_floor_rejects", "S_floor_rejects",')

# 5) extended resolver row
rep("row-fields",
'''                        "h_min": h, "ret_r": round(ret_r, 6),
                        "entry_px": round(ev["px"], 2),
                        "mfe_r": round(ev["mfe_r"], 4),''',
'''                        "h_min": h, "ret_r": round(ret_r, 6),
                        "entry_px": round(ev["px"], 2),
                        "stop_px": round(ev["stop_px"], 2),
                        "risk_dist": round(ev["risk_dist"], 4),
                        "shadow_mask": (int(bool(
                            ev.get("shadow_cisd")))
                            | int(bool(ev.get("shadow_fvg"))) << 1
                            | int(bool(ev.get("shadow_ifvg"))) << 2),
                        "censored": False,
                        "mfe_r": round(ev["mfe_r"], 4),''')

# 6a) chart companion series creation
rep("chart-series",
'''            if cname not in local:
                ch = Chart(cname)
                sa = Series("a", SeriesType.SCATTER)
                so = Series("o", SeriesType.SCATTER)
                ch.add_series(sa)
                ch.add_series(so)
                local[cname] = ch
            sr = local[cname].series[sname]
            sr.add_point(ts_dt, float(e['ret_r']))''',
'''            mask = (int(bool(e.get("shadow_cisd")))
                    | int(bool(e.get("shadow_fvg"))) << 1
                    | int(bool(e.get("shadow_ifvg"))) << 2)
            if cname not in local:
                ch = Chart(cname)
                for sfx in ("a", "o"):
                    for pre in ("", "rd-", "mfe-", "mae-", "mask-"):
                        ch.add_series(Series(pre + sfx,
                                             SeriesType.SCATTER))
                local[cname] = ch
            vals = {"": e["ret_r"], "rd-": e["risk_dist"],
                    "mfe-": e["mfe_r"], "mae-": e["mae_r"],
                    "mask-": float(mask)}
            for pre, v in vals.items():
                sr = local[cname].series[pre + sname]
                sr.add_point(ts_dt, float(v))''')

# 6b) n_event_rows RuntimeStatistic
if '"n_event_rows"' not in src:
    a2 = 'self.RuntimeStatistics["os_events"] = ' \
         'str(len(self._ev_results))'
    assert a2 in src, "os_events anchor missing"
    src = src.replace(a2, a2 + '''
            self.RuntimeStatistics["n_event_rows"] = \\
                str(len(self._ev_results))''', 1)
    applied.append("n_event_rows: applied")

open(p, "w", encoding="utf-8", newline="\n").write(src)
ast.parse(src)
for line in applied:
    print(line)
print("size:", len(src), "(limit 64000)")
assert len(src) <= 63990 or len(src) <= 64000, "over QC limit"
print("OK")
