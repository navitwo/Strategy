# E18S — ATOMIC ENGINE PARALLEL VARIANT RERUN (v2.5)

> ## ⚠️ RETRACTION & CORRECTION (2026-08-23, review round 6 — E19B directive)
>
> The claims below are **RETRACTED**. "Every run rec_ok=1 under strict identities"
> and "first positive-expectancy configuration ever recorded" were both false:
>
> 1. **Identity 1 could never fail.** The atomic simulator booked
>    `exit_px = stop_px/tp_px` with ZERO slippage and ZERO fees while Identity 1
>    compared only trade_builder aggregates; the ledger expectation
>    `Σ(r × risk_dist × pv × qty)` was never checked. The same file reports
>    `r_sum +20.261` against `rec_i1_profit_raw −985.0` and
>    `rec_tpv_delta −1879.4` — a contradiction that should have gone red by
>    roughly $9k against the stated $25 tolerance, and did not.
> 2. **Identity 2 was vacuous.** It compared a PER-TRADE modeled fee to a TOTAL
>    actual fee inside an always-true band.
> 3. **Identity 3 could not fail on EOD exits**: `_eod_resolve` incremented
>    `atomic_exits`, so avgW/avgL of 1.53/−0.96 (instead of the exact ±1/±2R
>    barrier exits produce by construction) raised no alarm.
> 4. Additional defects found in review: `bar.end_time.astimezone()` shifted every
>    ledger `exit_time` by 4–5 hours (UTC-vs-ET); `_resolve_cycle_minute` was
>    starvable (a missed minute event left the stop unresolved — shadowMOC's
>    avgL = −1.287 is the evidence).
>
> All four identity defects, the tz regression, and the starvation bug are fixed in
> v2.6 with negative tests proving each gate can go red
> (`test_identity_gates_can_go_red`, `test_exit_time_algo_clock_and_drain`).
> Barrier exits now carry slippage and fees; rows publish r_gross / net r /
> friction_r; exit-kind counters, median(risk_dist), and friction_R_total are
> published per run.
>
> **The ablFVG-mkt "+0.099R, PF 1.18" result is VOID as evidence of edge** until
> re-measured under the corrected engine. E18S is retained solely as an
> execution-engine diagnostic and as documentation of this failure mode.

---

# ORIGINAL (RETRACTED) REPORT — preserved unedited below

All four variants on identical immutable population, NQ 1-contract,
2010-01→2024-12 dev. **Every run rec_ok=1 under strict identities:
cycles == atomic_exits == ledger rows, anomalies=0, untracked=0,
late≤1, I1 cash residual 0.0.**

| variant | n | WR% | avg R | PF(R) |
|---|---|---|---|---|
| candidate (sweep stop) | 54 | 27.8 | −0.237 | 0.66 |
| ablCISD (trigger bypassed) | 60 | 26.7 | −0.273 | 0.61 |
| shadowMOC (marketable entry) | 70 | 37.1 | −0.562 | 0.31 |
| ablFVG-mkt (no FVG gate) | **205** | **42.4** | **+0.099** | **1.18** |

## Findings (RETRACTED)
1. **Execution engine fully reconciled**: one clean exit per cycle across
   389 total cycles; zero races/anomalies by construction (atomic simulator).
2. **ablFVG-mkt is the first positive-expectancy configuration ever recorded**
   (+0.099R, PF 1.18, n=205). CAVEAT: it changes two factors vs candidate
   (removes FVG gate AND enters at marketable limit). Attribution between
   "FVG gate harmful" and "marketable entry beneficial" requires ablFVG with
   resting entry — not yet run.
3. shadowMOC (marketable entry WITH FVG gate) is worse than candidate
   (−0.562): entering immediately when the FVG gate passes selects badly.
   Combined with ablFVG-mkt positive: value lives in *entering earlier on
   non-FVG-confirmed signals*, i.e., the FVG gate itself is the liability.

## Next per directive
Block-bootstrap forward-return/MFE/MAE event study on the HTF-bias +
sweep/reclaim universe to test whether directional information exists at
all before any rescue experiments are considered.
