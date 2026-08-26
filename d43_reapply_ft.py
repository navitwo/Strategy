"""Re-apply v2.9 first-touch grid export atomically (OneDrive keeps
reverting multi-step edits). Verifies all markers before exiting; writes
once; asserts parse + size + markers on the re-READ file."""
import ast
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
p = os.path.join(ROOT, "scifvg_main.py")
src = open(p, encoding="utf-8").read()


def must_absent(tok):
    assert tok not in src, f"already present: {tok}"


# 1) module constant after INSTRUMENT_SPECS opening line
must_absent("FT_CELLS = ")
a1 = 'INSTRUMENT_SPECS = {'
assert a1 in src
cells = ('FT_CELLS = [(f"T{t:g}S{s:g}", t, s)\n'
         '            for t in (0.5, 1, 1.5, 2)\n'
         '            for s in (0.5, 1, 1.5, 2)]\n\n')
src = src.replace(a1, cells + a1, 1)

# 2) candidate init: add "ft": {}
a2 = '"mfe_r": 0.0, "mae_r": 0.0,'
assert a2 in src
src = src.replace(a2, '"mfe_r": 0.0, "mae_r": 0.0, "ft": {},', 1)

# 3) grid loop in _advance_events after mae update
a3 = 'ev["mae_r"] = min(ev["mae_r"], float(adv) / rd)'
assert a3 in src
g = '''            ftg = ev["ft"]
            for k, t, s_lev in FT_CELLS:
                if k in ftg:
                    continue
                m_, n_ = ev["mfe_r"], ev["mae_r"]
                hit_t, hit_s = m_ >= t, n_ <= -s_lev
                if hit_t or hit_s:
                    ftg[k] = (99 if hit_t and hit_s
                              else t if hit_t else -s_lev)'''
src = src.replace(a3, a3 + "\n" + g, 1)

# 4) row export: ft dict
a4 = '"censored": False,'
assert a4 in src
src = src.replace(a4, a4 + '\n                        "ft": dict('
                         'ev.get("ft", {})),', 1)

# 5) chart creation: fta/ftb series for aligned side
a5 = '''                for sfx in ("a", "o"):
                    for pre in ("", "rd-", "mfe-", "mae-", "mask-"):
                        ch.add_series(Series(pre + sfx,
                                             SeriesType.SCATTER))'''
assert a5 in src
b5 = '''                for sfx in ("a", "o"):
                    pres = ["", "rd-", "mfe-",
                            "mae-", "mask-", "fta-", "ftb-"]
                    for pre in pres:
                        ch.add_series(Series(pre + sfx,
                                             SeriesType.SCATTER))'''
src.replace(a5, b5, 1)

# 6) packing block in vals section
a6 = '''            for pre, v in vals.items():
                sr = local[cname].series[pre + sname]
                sr.add_point(ts_dt, float(v))'''
assert a6 in src
b6 = '''            if (sname == "a" and e["h_min"] == 120
                    and e.get("ft")):
                tb = sb = 0
                for i2, v2 in enumerate(e["ft"].values()):
                    tb |= (1 << i2) if v2 >= 0 else 0
                    sb |= (1 << i2) if v2 <= 0 else 0
                vals["fta-"], vals["ftb-"] = float(tb), float(sb)
''' + a6
src = src.replace(a6, b6, 1)


# 7) trim: compact Debug JSON in on_end_of_algorithm
a7 = '''        self.Debug(json.dumps({
            "exp_hash": self.exp_hash, "cfg": self.cfg,
            "trades": len(rs), "wins": wins, "losses": losses,
            "win_rate": round(wins / len(rs), 4) if rs else 0.0,
            "avg_r": round(avg_r, 4), "pf_local_r": round(pf, 4),
            "max_consec_losses": self._max_consec_losses(rs),
            "open_at_end": held,
        }, sort_keys=True))'''
if a7 in src:
    b7 = '''        self.Debug(json.dumps({"exp_hash": self.exp_hash,
            "trades": len(rs), "wins": wins, "losses": losses,
            "avg_r": round(avg_r, 4), "open_at_end": held,
        }, sort_keys=True))'''
    src = src.replace(a7, b7, 1)

# 8) trim: RT alias for the funnel publish block (EoA only, anchored on
#    the funnel_sessions line)
if 'RT["funnel_sessions"]' not in src:
    a8 = ('            self.RuntimeStatistics'
          '["funnel_sessions"]')
    k = src.find(a8)
    assert k != -1
    j8 = src.find("except Exception:", k)
    blk = src[k:j8].replace(
        "self.RuntimeStatistics", "RT")
    src = (src[:k] + "            RT = self."
           "RuntimeStatistics\n" + blk + src[j8:])



if '"n_event_rows"' not in src:
    a9 = 'RT["d_ev_results"]'
    k9 = src.find(a9)
    if k9 != -1:
        e9 = src.find("\n", k9)
        src = (src[:e9+1]
               + '            RT["n_event_rows"] = '
                 'str(len(self._ev_results))\n' + src[e9+1:])


open(p, "w", encoding="utf-8", newline="\n").write(src)
ast.parse(src)

# verify persistence by READING BACK from disk
chk = open(p, encoding="utf-8").read()
for m in ("FT_CELLS", '"ft": {},', "for k, t, s_lev in FT_CELLS:",
          '"ft": dict(ev.get(', '"fta-"'):
    assert m in chk, f"marker lost after write: {m}"
print("all markers persisted; size:", len(chk))
assert len(chk) <= 64000, "OVER QC LIMIT"
print("OK <= 64k")
