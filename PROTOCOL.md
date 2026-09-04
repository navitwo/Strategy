# PROTOCOL v1.0 — NQ Liquidity Sweep + CISD + IFVG Campaign (Batch 1)

Frozen: 2026-08-23. Governs Batch 1 (baseline + Experiments 1–10). Changes require a protocol version bump.

## Identity
- Project: `NQ CISD IFVG 2026` (new dedicated QC project; prior projects untouched).
- Experiment naming: `SCIFVG-v<maj>-<min>-<slug>-<hash8>` where hash8 = md5(canonical param JSON)[:8].
- Duplicate rejection: refuse creation if a remote/local backtest with same name/hash exists.

## Instrument
- Execution + signals: MNQ (micro Nasdaq-100), continuous canonical for data (OPEN_INTEREST mapping, RAW normalization, front contract), orders ALWAYS on mapped contract. NQ variant available as `instrument=NQ` stress test only.
- Tick 0.25. Point value read from symbol properties (MNQ $2, NQ $20 asserted).

## Frozen V1.0 (CONTROL) definitions
1. **Sessions (futures day)**: 18:00 ET → 17:00 ET next day (DST-aware, America/New_York via zoneinfo). PDH/PDL = completed prior session high/low only.
2. **Entry window**: 09:30–12:00 ET. Entire setup chain (sweep attempt onward) must occur inside the window. Pendings cancel at window end. Positions run to stop/target (no EOD flatten — known limitation).
3. **4H bias**: 4H bars derived from completed 5m bars, ET-wall-clock buckets [00,04,…,20,24); bucket publishes only on next-bucket arrival with first/last bar coverage check (partial buckets discarded). Swings: pivot L=3,R=3 on 4H closes; confirmed only at publish of bar i+3. Bias flips on 4H CLOSE beyond most recent confirmed swing high (bull) / low (bear); bull evaluated first; persists until opposite BOS. Neutral = no trades.
4. **Sweep (long)**: 5m bar LOW ≤ PDL − sweep_min_ticks×0.25. Depth cap: same bar LOW ≥ PDL − sweep_max_ticks×0.25 (else attempt consumed). Reclaim: a completed bar in [B0 .. B0+2] (N=3) CLOSES > PDL (B0 itself allowed). One attempt per level per session. Confirm at reclaim close.
5. **CISD (long)**: E = earliest bar with minimum LOW in [B0..reclaim bar]. R = nearest preceding bearish 5m candle (close<open) at or before E within session. Trigger: a completed bar AFTER reclaim-confirm, within cisd_max_bars=12, CLOSES > R.open. Confirm at that close.
6. **FVG store**: bearish 3-candle gaps (Low[i−2] > High[i], size ≥ fvg_min_ticks×0.25), known at close of bar i, kept fvg_max_age_bars=60; marked dead if any later close < zone bottom.
7. **IFVG (long)**: eligible at CISD confirm = created at index ≤ E, not dead, age ok, and CISD-bar close < zone_top (still below). Inversion = a completed bar within inv_max_bars=12 after CISD CLOSES > zone midpoint. First inverted gap wins; zone = original full gap.
8. **Retest/entry (long)**: BUY LIMIT at zone_top (proximal) immediately after inversion close; valid retest_max_bars=24; cancel if bar CLOSES < zone_bottom (structure invalid), bias flips, window/session ends. Fill via resting limit (no hindsight).
9. **Stop**: sweep extreme E.low − stop_buffer_ticks×0.25 (buffer 4 ticks). **Target**: entry + target_r×(entry−stop), target_r=2.0, tick-rounded.
10. **Short**: exact mirror on PDH.
11. **Risk**: $100 fixed. qty = floor(risk / (stop_points × point_value)), cap max_contracts=10; qty 0 ⇒ skip (counted). Never tighten stop to fit.
12. **Execution**: commissions $0.50/side/contract (custom fee model); slippage 1 tick/fill (slippage model); exits = protective STOP MARKET + profit LIMIT submitted only after entry-fill event; sibling canceled on other's fill; same-bar ambiguity resolved conservatively and counted (`oco_races`); unexpected protection loss ⇒ fail-closed flatten.

## Anti-lookahead guarantees
Completed 5m bars only; pivots confirmed with right-side bars; PDH/PDL from completed prior session; FVG known at 3rd close; every gate stamped with knowable timestamp; no same-bar entry on inversion bar.

## Data segmentation (frozen)
- Development: 2023-01-03 → 2025-04-30 (multiple regimes: 2023 recovery, 2024 bull, Q1-2025 vol).
- Validation: 2025-05-01 → 2026-01-01 (checked periodically, NOT tuned).
- Final holdout: 2026-01-01 → present — UNTOUCHED in Batch 1. May-2026→present current-regime benchmark lives inside holdout; evaluated only post-freeze.
- Batch 1 runs `run_segment=dev` exclusively. OOS stays locked.

## Budgets & stopping
- Max 10 VALID completed experiments after BASELINE (technical failures don't count).
- One parameter family per experiment; causal hypothesis recorded before each run.
- Concurrency 1; poll cap 60 min/run; abort >3 consecutive infra failures.
- Sample-quality gate: <30 dev trades ⇒ INSUFFICIENT SAMPLE verdict; concentration warnings precede PF/PnL in ranking.
- Mandatory stop after Experiment 10 → Batch 1 report → await authorization.

## Funnel instrumentation (mandatory output)
sessions; per side: attempts, depth_rejects, no_reclaim, sweep_ok, cisd_ok/timeout, inv_ok/timeout, submits, fills, size_skips, cancels(expiry/invalid/bias); global: rollovers, oco_races, forced flattens. Emitted via RuntimeStatistics + final FUNNEL log line.

## Decision-rule feasibility proofs (permanent rule, 2026-08-28)
Every decision rule ships with a feasibility proof showing each outcome label
is reachable given the observed dispersion, before the rule is frozen. This is
the positive counterpart of the negative-test rule (a gate that has never been
seen failing proves nothing): a classifier that can never emit a label is as
untrustworthy as a gate that can never trip. Five structurally-unreachable
outcomes have been caught in this project (funnel prefix filter, zero-trade
smoke gate, tautological Identity 1, E19B's unbounded-ratio estimator, and the
RTC2 stacked-ambiguity equivalence label); two of the last three were caught by
this proof rather than by review. The proof is a permanent committed test that
constructs each label from data already in hand and asserts it is reachable. A
label reachable only under a synthetic perturbation of an observed quantity
must state that condition explicitly (e.g. DIFFERS_AND_TRADABLE requires a
sweep surface whose pessimistic best clears the 0.2R friction threshold, which
the observed 0.0648R pessimistic best does not).

Input-anchoring clause (2026-09-04, sixth instance): **every input to a
feasibility proof must be empirically anchored to committed data, or declared
as an assumption with a reported sensitivity range.** A proof is only as good
as its dispersion estimate. The sixth structurally-unreachable-outcome case
was not a label a rule could never emit but a feasibility proof that could
never fail: the C2 grid passed at minimum_passing_n=200 (the grid floor)
because it assumed per-observation contrast sd = 0.45R, while the dispersion
computable from the committed E19B-R FT ledgers at the primary cell is
1.4481R (independence floor) to 1.6015R (anti-correlated trimodal central) —
3.2x too small. At the anchored dispersion the same grid reports whether NULL
is reachable at all; the rule for future proofs is that no hand-picked scale
enters unflagged, and the proof must ship a negative control demonstrating it
CAN fail at an adversarial input.
