# CAMPAIGN CLOSEOUT — SCIFVG (Sweep → CISD → IFVG), 2026-08-25

**Outcome label (precise): administratively closed campaign with an
INCONCLUSIVE raw primary and a NULL winsorized sensitivity — not a
pre-registered primary NULL.**

No further backtests, optimization, rescue variants, or parameter work are
authorized under this campaign. Validation (2025-05→2026-01) and the
May-2026 holdout were never touched and remain locked for whatever follows.
This document is the terminal record; it supersedes no frozen artifact and
amends nothing retroactively.

---

## Layer 1 — Frozen primary (tag `e19b-provisional`)

Unfloored event study, commit `7de3be0`, published 2026-08-25 and never
amended:

- Population: bias-aligned reclaim candidates pooled across NQ/ES/YM/RTY,
  2010-01→2024-12 dev segment only.
- H\* = 120m, raw mean of forward R: **−0.0091R, day-clustered 95% CI
  [−0.2414, +0.2263] → INCONCLUSIVE** (n = 1,381 events; the true iid CI
  is [−0.2236, +0.2054] — narrower, same verdict).
- θ = 0.2R; three-outcome rule as pre-registered.

## Layer 2 — Floored primary (tag `e19b-r-final`)

Population-conformance correction (declared in `PREREGISTRATION_E19B_R.md`
BEFORE the rerun): tradability floor on `risk_dist` = max(≥ min ticks per
instrument, ≥ 0.10 × ATR14(5m)). Commit `e207dcc` fixed the read-list
defect found mid-course (below). Result on compile `3605cbb7`, 12,004 rows,
0 floor violations:

| h | n | mean R | iid 95% CI | verdict |
|---|---|---|---|---|
| 30m | 1121 | +0.006 | [−0.135, +0.154] | NULL |
| 60m | 1121 | −0.001 | [−0.202, +0.210] | INCONCLUSIVE |
| 120m | 1121 | −0.079 | [−0.352, +0.219] | **INCONCLUSIVE** |
| 240m | 1121 | −0.116 | [−0.479, +0.259] | INCONCLUSIVE |

Note: this is not the same population as Layer 1 (composition shift, see
Defect & Findings). Both primaries stand as published; neither authorizes
rescue or optimization.

## Layer 3 — Robustness (declared POST-HOC; not part of any preregistration)

Computed after results, on the floored ledger, session-clustered (see
Defect). Winsorized ±5R / trimmed (|ret|>5R excluded) / median, aligned
population, clustered 95% CIs, 10k resamples:

| h | winsorized mean [CI] | trimmed mean [CI] | median |
|---|---|---|---|
| 30m | −0.010 [−0.141, +0.118] NULL | +0.041 [−0.072, +0.154] NULL | +0.074 |
| 60m | −0.026 [−0.187, +0.126] NULL | +0.025 [−0.114, +0.161] NULL | +0.058 |
| 120m | −0.115 [−0.295, +0.067] NULL | −0.056 [−0.209, +0.092] NULL | −0.047 |
| 240m | −0.140 [−0.347, +0.062] NULL | +0.026 [−0.144, +0.190] NULL | 0.000 |

- Winsorized/trimmed: **NULL at every horizon.**
- Per-market aligned winsorized CIs contain zero at every horizon except
  one cell (ES 240m, marginally below 0); no estimator POSITIVE anywhere;
  no market-horizon cell exceeds +0.2R at its upper bound.

## Layer 4 — Mechanism (exploratory only)

MFE/MAE structure of the aligned H\* population (n = 1,121):
68.9% reach MAE ≤ −1R while 45.8% reach MFE ≥ +2R. The 2R-target/1R-stop
geometry is mechanically unfavourable on this population regardless of
drift sign. This is a property statement about barriers vs excursions, not
evidence of directional edge, and it cannot rescue any verdict.

---

## Defect disclosure (exactly one)

**The published CIs in `E19B_R_ANALYSIS.md` and `E19B_R_RESULT.md` are
iid, not session-clustered.** Evidence is internal to those documents:
they print sessions = n = 1121 at all four horizons, whereas the committed
ledger contains **895 distinct session-dates** for that population, and
the printed SEs equal σ/√1121 exactly (0.0741, 0.1058, 0.1432, 0.1883).

Scope limits of this defect, stated accurately:
- It does **not** change any verdict. The correctly clustered CIs are
  reproducible offline from the committed ledgers
  (`e19br_ledgers/{NQ,ES,YM,RTY}_events.jsonl`):
  - raw H\*: mean −0.0787, clustered CI ≈ **[−0.374, +0.230] →
    INCONCLUSIVE** (this document's rerun: [−0.366, +0.227]; Monte Carlo
    variation across seeds spans both),
  - winsorized H\*: mean −0.1145, clustered CI ≈ **[−0.298, +0.070] →
    NULL** (rerun: [−0.295, +0.067]).
- Reclaim timestamps are NOT missing: `reclaim_ts = ts − h_min×60`
  recovers the reclaim time exactly, and the session-date assignment of an
  event is identical at all four horizons (verified: 895 distinct dates by
  every construction). The only genuine data gaps are the absent permanent
  `event_id` field and the iid-vs-clustered statistical error itself.

The earlier E19B analysis (`E19B_ANALYSIS.md`) already used day-level
clustered resampling and is unaffected by this defect.

---

## Findings the successor campaign must not lose

1. **Estimator design.** The raw mean of an unbounded ratio was structurally
   incapable of returning NULL: with ~1% of observations carrying |R| ≥ 10
   and σ set by that tail, √n could never outrun it. It missed NULL by 0.02
   (floored) and 0.03 (unfloored, winsorized-vs-raw gap) in two independent
   studies. Future primaries must be bounded ex ante (fixed trimming rule or
   volatility normalizer independent of the trade's own stop).
2. **MFE/MAE mechanism.** 68.9% of aligned H\* events touch ≤ −1R against
   45.8% reaching ≥ +2R — sample-independent evidence that the bracket
   geometry, not signal direction, dominates realized outcomes here.
3. **Bias-gate control.** Aligned −0.079 vs bias-rejected +0.121 (z = −1.16)
   at H\*; directionally identical in the unfloored study. The HTF-bias
   filter selects the worse half in both studies (n.s., but consistent with
   every prior ablation).
4. **60m horizon reporting.** Pre-registered and computed, but omitted from
   the closeout-facing prose summaries (commit messages, memory) of E19B-R;
   it IS present in both result tables. Its verdicts: raw INCONCLUSIVE
   ([−0.202, +0.210]), winsorized NULL ([−0.187, +0.126]).
5. **Floor composition shift.** The floor removed ES −40% (−42% all-arm),
   RTY −34%, NQ −10% (−13% all-arm), YM ~0% of candidates (verified on both
   the aligned and all-arm bases from the committed ledgers), so Layers 1
   and 2 are non-identical populations and their INCONCLUSIVES are not
   independent confirmations.
   Additionally, there is no observed row where the ATR clause was the
   operative constraint: min risk_dist equals the tick floor per market,
   which proves the tick floor binds for at least one event per market but
   not that the ATR clause never bound for any event; across the ledger it
   sat below the tick floor in every market (only 12 RTY rows within 1% of
   the floor, none elsewhere) — declarative rather than operative as far as
   the data can show.

---

## Disposition

- Campaign closed administratively. Tags preserved: `e18-diagnostic`,
  `e19-archive-verdict`, `e19b-preflight-v2.7`, `e19b-provisional`,
  `e19b-r-final`. All result documents, ledgers, drivers, and the engine
  remain in-tree.
- Any future work proceeds as **Campaign 2 in this repository** (branch,
  not fork): the durable asset is the v2.8 engine, identity gates, null
  infrastructure, chart-series ledger channel, smoke gate, and regression
  suite. Forking loses or drifts them.
- Campaign 2 entry conditions, binding before any hypothesis is chosen:
  1. Screen candidate bracket geometries OFFLINE against the existing
     3,001-candidate H\* MFE/MAE ledger at zero cloud cost; selection by
     assertion is prohibited.
  2. Fresh pre-registration: no-order event study first; primary definition
     and statistical rule frozen before results; bounded primary estimator
     (fixed trimming rule or ex-ante volatility normalizer, never the
     trade's own stop); θ and the three-outcome rule declared up front;
     genuine session-date clustering with a suite test asserting
     sessions < n.
  3. Parameter optimization prohibited unless that event study first
     demonstrates a robust, economically meaningful edge.
