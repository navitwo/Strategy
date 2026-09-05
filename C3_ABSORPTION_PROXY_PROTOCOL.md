# C3-ABSORPTION-PROXY-v1 — bounded cost gate + proxy test protocol

Status: FROZEN BEFORE ANY QUOTE NUMBERS WERE OBTAINED (2026-09-05).
Character: exploratory only. Zero promotion power. No Campaign 3
pre-registration is drafted by this pass, in either outcome branch.
θ = 0.2R remains the fixed economic reference; it is not widened here.

## 0. The single falsifiable claim under test

> Order-Flow Absorption & Reload Reversal: **at a predefined level,
> abnormally low aggressor price efficiency — large aggressive volume
> producing little price displacement — predicts REVERSAL of the move
> into that level.**

Everything above the line (bid reload after execution, queue position,
MBO depth mechanics) is NOT tested here and is NOT claim-faithful to an
OHLCV or trades-only stack. If the line itself fails, the strategy has
no empirical basis and dies regardless of the machinery built on it.

## 1. Prior posture this test must overcome (declared before results)

1. **Friction.** The strategy's own worked example uses a 2-point NQ
   stop; round-trip cost ≈ 1.0 point, composed of $8.10 commission
   (= 0.405 pts at $0.05/0.25-pt tick... declared per directive, see
   §1a) + ~0.25 half-spread on entry + ~0.375 stop slippage in fast
   markets. Friction ≈ **0.50R on a 2-point stop, ≈ 0.25R on a 4-point
   stop** — 2–3× the ~0.2R floor that killed Campaigns 1 and 2.
   Break-even needs ≈50% win rate at a 2R target.
   - §1a (PROTOCOL anchoring rule): the $8.10 commission and slippage
     components are **declared assumptions from the strategy brief, not
     anchored to committed data**. Sensitivity range reported: any
     total round-trip in [0.8, 1.2] points keeps friction ≥ 0.40R on a
     2-point stop; no value in the range brings it under 0.2R.
2. **The house data leans against it.** The strategy's levels are
     literally Campaign 2's event (prior-day / overnight high-low).
     Corrected NQ Primary A over 3,033 events = **−0.1846R**
     (continuation, not reversal). The absorption filter must select a
     subset that reverses hard enough to overcome that drift **and**
     double the usual cost floor.
3. **Nothing in the current stack applies.** Every guard, generator and
     resolver runs on OHLCV bars. "The bid reloads after being
     executed" requires MBP-10/MBO depth that QuantConnect does not
     provide for futures and that is pre-declared likely to exceed the
     ~$86.64 remaining Databento credits.

## 2. Gate A — cost quotes (free; metadata.get_cost only)

Five quote families, all GLBX.MDP3, continuous, before any purchase:

| # | request | range |
|---|---|---|
| 1 | NQ.n.0 `trades` | full 2010-06-07 → 2026-09-04 (end exclusive) |
| 2 | NQ.n.0 `mbp-10` | full 2010-06-07 → 2026-09-04 (end exclusive) |
| 3 | ES.n.0 `trades` | full 2010-06-07 → 2026-09-04 (end exclusive) |
| 4 | ES.n.0 `mbp-10` | full 2010-06-07 → 2026-09-04 (end exclusive) |
| 5a | NQ.n.0 `trades` | conditional windows (below) |
| 5b | NQ.n.0 `mbp-10` | conditional windows (below) |

**Conditional window set (declared now):** the 3,033 committed NQ
events in `c2_local_study.json`, each window = `event_et ± 60 minutes`
converted America/New_York → UTC, overlapping windows merged
(precomputed: 2,611 merged windows, 5,606.5 total hours, file
`nq_event_windows.json`). Because `metadata.get_cost` accepts only a
single continuous range (verified live 2026-09-05: `time_range`
rejected, `start` required), the conditional quote is computed as the
**sum of per-merged-window `metadata.get_cost` calls** — free, exact
under Databento's per-record billing, and additive across jobs.
Windows with HTTP error: abort the sum and report the failure; do not
estimate by sampling.

**Stated ceiling for any purchase (frozen now): MAX_USD = $40.00** for
the conditional trades pull. Rationale: inferred balance $86.64 is
reserved for a possible ES/YM/RTY index-complex pull (user decision
2026-09-04); a proxy test must not eat more than <50% of that
reservation. This ceiling is not adjustable after the quote is seen.

**Purchase branch (Gate B):** conditional `trades` total ≤ $40.00
**and** portal balance re-verified by the operator at
databento.com/portal/billing (DATABENTO_BUDGET.md rule 1; the agent
cannot perform this step — the purchase is additionally gated on
DATABENTO_PORTAL_REVERIFIED=1 + CONFIRM=1 in code, per d48 precedent)
→ purchase ONLY the conditional trades pull. Otherwise: **no purchase
of any kind** — go to branch DEAD-UNTESTED (§6).

## 3. Metric definitions (per event, trades data; fixed now)

For each of the 3,033 NQ events with `side` = +1 at an overnight/
prior-day **high** touch the reversal arm is SHORT and **−1** at a
**low** touch (same convention as committed `reversal_R`):

- **Span:** the 60 minutes ENDING at the touch bar's timestamp (the
  "approach to the level"), in exchange time, from `trades` records of
  the continuous front resolved for that date.
- **Aggressive volume V± :** sum of trade `size` with `action == T`,
  by aggressor `side` (B = buy-aggressor, A = sell-aggressor).
- **Signed aggressive volume (delta):** D = V+ − V−.
- **Displacement Δp:** close-of-span price − open-of-span price
  (last trade vs first trade in span), in POINTS, signed.
- **Raw efficiency:** E_raw = |Δp| / max(V+ + V−, 1) — points moved
  per contract traded.
- **Directional efficiency:** E_dir = Δp / D, defined when D ≠ 0
  (displacement per net aggressive contract); reported, not the split.
- **Absorption score (FROZEN PRIMARY SPLIT):**
  **A = (V+ + V−) / max(|Δp|, 0.01)** — aggressive contracts per point
  of displacement. High A = lots of aggression bought little price
  movement = the claim's "abnormally low aggressor price efficiency".
  **Absorption-candidate = upper quartile of A within each
  level-kind** (high-touch and low-touch populations split separately
  at their own 75th percentile of A), so candidates are ~25% of events
  by construction. The threshold is computed from INPUTS ONLY, never
  from any outcome variable. (The floor of 0.01 pts is one NQ tick —
  a zero-displacement span scores maximum absorption, as the claim
  requires.)
- Sensitivity (declared now, reported alongside, not selectable ex
  post): median split of A within level-kind (~50% candidates), and
  separately a volume-conditioned version: above-median total
  aggressive volume AND below-median E_raw.

## 4. Outcome comparison (uses ONLY already-committed ledger values)

- **Direction convention (verified against the generator, c2_local_study.py
  :126):** committed `fwd_R = (close − level)/atr × side` where `side`
  is the REVERSAL arm's side (+1 at an overnight LOW, −1 at an
  overnight HIGH). So a reversal-favourable outcome — price backing off
  the level — is a POSITIVE `fwd_R`. The claim's prediction is
  therefore: **candidates' mean `fwd_R` HIGHER than non-candidates'**,
  at both high cells and low cells, under absorption→reversal.
- Per candidate/non-candidate subset, report committed `fwd_R`(30/60/
  120/240m) and committed barrier contrast (`contrast_R`, pessimistic
  primary = continuation minus reversal in R; reversal-favourable =
  candidates' contrast_R LOWER than non-candidates'), state per-cell
  for high vs low touches.
- Clustering: **session-date clusters**, 10,000 draws, seed 20260905,
  percentile CI — the declared convention of the archive
  (`C2_RESIDUE_STOPWIDEN_PROTOCOL.md` §4). Assert `sessions < n`.
- The 30-minute-bar granularity of the committed outcomes bounds the
  test: any absorption edge that only exists at seconds scale is
  invisible here BY CONSTRUCTION — declared, not discovered.

## 5. Frozen decision rule (THE ONLY BRANCHING AUTHORITY)

Compute primary statistic T_high = candidates' mean `fwd_R`(120m)
minus non-candidates' mean `fwd_R`(120m) at **overnight-high cells**,
and T_low the same at **overnight-low cells**, session-date clustered.
Under the §4 convention (positive `fwd_R` = reversal), the
absorption→reversal claim predicts BOTH T_high > 0 and T_low > 0.

- **SUPPORTED (justifies Campaign 3 prereg + scoped MBP-10 quote):**
  BOTH of: (i) 95% CI of T_high lies entirely above +0.10R, AND
  (ii) 95% CI of T_low lies entirely above +0.10R.
- **DEAD:** either CI contains 0 (no separation) OR either separation
  runs in the CONTINUATION direction (CI entirely negative).
- **INCONCLUSIVE:** everything else. Counts as a FAIL of the gate:
  no MBP-10 purchase, no prereg; recorded as "not shown under a
  30-minute-resolution proxy."

No promotion in any branch. θ = 0.2R reference: even a SUPPORTED
result is reported against the §1 friction (≥0.40R declared range on
the strategy's own 2-point stop), and the write-up must state that
seconds-scale backtests are least reliable exactly where queue
position and fast-market slippage dominate, so any eventual
implementation must widen the stop or lengthen the hold to bring
friction under control.

## 6. No-data branch: DEAD-UNTESTED

If Gate A finds the conditional trades pull above the $40.00 ceiling
(or portal re-verification fails, or the purchase is refused): no data
is bought. The absorption hypothesis is then recorded as **UNTESTED-
AT-AFFORDABLE-COST — CLOSED** in the C2/C3 record: the proxy cannot be
run at all on the OHLCV-only stack, the full-depth version costs more
than the account reservation allows, and per the user's decision
discipline an unfalsifiable-because-unaffordable claim is filed dead
by default, with the five quote numbers as the evidence for that
filing. No MBP-10 scope, no Campaign 3 prereg for this strategy.

## 7. Prohibitions restated (binding)

No purchases beyond the conditional trades pull (and not even that
without Gate B). No backtests. No optimization. No parameter
selection (split thresholds are fixed in §3, outcomes-blind). No
Campaign 3 pre-registration drafted in this pass. Validation and
holdout data stay locked and unread. `DEV_END = 2024-12-31` guard is
irrelevant to quotes but honored for any computation.
