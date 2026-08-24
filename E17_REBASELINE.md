# BATCH 3 (cont.) — E17 RE-BASELINE on corrected engine v2.1

Precondition met: SMOKE GATE PASS (bid 84d254fe…) — TZCHECK 09:35 first-RTH,
171 full-span 4H buckets, rec_ok=1, fills==trades, consolidate() slot
discipline proven. Only after that did any multi-year run submit.

## E17 runs (NQ, max_contracts=1, 2010-01 → 2024-12, dev only)
| run | fills | trades | wins | avg R | PF(R) | Σ R | rec_ok |
|---|---|---|---|---|---|---|---|
| signal | 51 | 46 | 8 | −0.399 | 0.55 | −18.4 | **0** (resid $1,180) |
| null p=0.02 | 1132 | 1121 | 391 | −0.266 | 0.67 | −297.9 | **0** ($14.5k) |
| null p=0.06 | 1346 | 1328 | 447 | −0.325 | 0.60 | −431.6 | **0** ($16.3k) |
| signal + gap stop | 51 | 51 | 19 | −0.050 | 0.94 | −2.57 | **0** ($1.37k) |

## Observations (provisional until reconcile passes)
1. Sample problem structurally improved: 46–51 signal trades over 15y
   (vs n=2-11 before), and nulls now reach n=1000+. The consolidate() fix
   restored true 5m/4H clocks — h4_published=22392 ≈ 6/day × 3929 sessions ✓.
2. Signal vs null: gap-stop signal (−0.05R, n=51) sits above every null
   calibration (−0.27R to −0.33R, n=1121+). Directionally interesting but
   NOT yet evidence — the reconciliation gate fails on all four runs.
3. Blocking item: rec residuals scale with trade count (~$25/trade),
   consistent with an unmodeled per-trade cost term in expected-vs-observed
   accounting (commissions are booked by LEAN inside equity; my obs_usd
   snapshot at entry/exit already includes them asymmetrically). Next fix:
   compare like-for-like (either both gross or both net of fees).
4. untracked_fills=0 and flatten_fills=0 across all runs: the registration
   fix works; no leak path observed.

## Gate status
- smoke_gate.py is now a mandatory precondition (would have caught the
  consolidate signature, the timezone shift, and the fragmentation bug).
- rec_ok==1 remains required before ANY number above is quotable as edge
  measurement. Until then they are engine-behavior diagnostics only.

## Next steps
1. Fee-consistent reconcile accounting (gross↔gross), rerun smoke, expect PASS.
2. Re-run E17 quartet; compute gate contribution = sig_avgR − null_avgR with
   bootstrap CIs from exported ledgers (n≥1000 on nulls).
3. Fill-realism stress (2–3 ticks/side) on whatever survives.
4. Validation segment stays LOCKED until a frozen candidate clears
   ≥200 dev trades with CI excluding zero AND survives stress.
