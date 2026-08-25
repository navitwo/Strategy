# PRE-REGISTRATION — E19B Reclaimed-Sweep Event Study

Frozen: 2026-08-23, BEFORE any E19B data pull. Changes require a version bump and a
committed rationale. Governs the event study only; it does NOT unlock validation,
holdout, or optimization.

## 1. Population (immutable)

One candidate population: **bias-aligned sweeps that penetrate PDH/PDL within depth
limits AND close back through the level inside the reclaim window** (reclaim-
confirmed). Candidates are published once, with permanent `cand_id`s, by the
`events_only` variant (v2.6). Raw attempts are NOT candidates — E19's attempt-time
capture is retracted as a level-penetration diagnostic.

CISD, FVG, and IFVG are **pre-registered labels** attached to this single immutable
population (for later conditioning/exploratory work) — never separate portfolio runs.

Arms: `primary` (bias-aligned) and, paired to the same candidate event,
`counter` (counter-bias twin) as built-in control.

## 2. Measurement

- Forward returns in **R units**: `(P_{t+h} − P_reclaim) / risk_dist × side`,
  where `risk_dist` is the event's own sweep-extreme-to-entry distance
  (stop_buffer included). R units scale with volatility, so the economic
  threshold reads directly as "is drift > 0.2R?"
- Per-candidate MFE/MAE recorded (exploratory only — see §6).
- Primary horizon frozen at **H\* = 120 minutes** after reclaim confirmation.
- Export: full EVENT ledger (cand_id, arm, side, date, h_min, ret_r, entry/stop px,
  risk_dist, mfe_r, mae_r) — no aggregation-only output.

## 3. Power honesty (reported BEFORE any p-value)

For every cell we report **n, σ, SE, 95% CI, and minimum detectable effect
(MDE at 80% power, α=0.05)** ahead of any significance claim.

Context from E19 funnel: 952 raw attempts → 159 depth rejects → **449 reclaimed**
candidates on NQ dev 2010–2024. At NQ's ~50–70 bps 120-minute dispersion, a naive
bps-scale CI on n=449 spans roughly ±5.5 bps against the ~3.3 bps of drift needed
to clear 0.2R friction on a 20-point stop — i.e., NQ alone is likely underpowered
for the friction-adjusted threshold. Mitigation is design-based, not p-hacking:
replication across **ES, YM, RTY** (~1,800 pooled events; development-window data
only — validation and holdout are not touched), plus the paired counter-bias arm.

## 4. Three pre-registered outcomes (not two) — AMENDED v2 (2026-08-25)

Let Δ = pooled mean side-aligned forward R-drift at H\*. The outcome rule is
anchored on the FIXED economic threshold θ = 0.2R (friction bar), not on MDE:
MDE is a property of the design and using it as the decision boundary makes
"null" easier the noisier the data. MDE is computed and reported as a
PRE-RUN POWER DIAGNOSTIC ONLY.

1. **POSITIVE** — bootstrap 95% CI lower bound for Δ exceeds 0.2R:
   eligible to trigger the capped rescue study (§5).
2. **NULL** — the 95% CI upper bound for Δ falls below 0.2R:
   the word "archived" is earned; strategy family stays archived.
3. **INCONCLUSIVE** — the CI straddles 0.2R (neither 1 nor 2):
   no archive claim, no rescue claim; the study reports itself as
   uninformative at current power.

The rule is applied OFFLINE, without amendment, after seeing the numbers.
Only outcome 2 earns the word "archived." Only outcome 1 opens §5.

## 5. Multiplicity control (in writing, before data)

- **Single primary hypothesis**: mean side-aligned forward R-drift at H\* on
  the population POOLED ACROSS MARKETS over rows where bias_aligned == True
  ONLY — never pooled across arms (the counter arm is a within-candidate
  contrast reported separately, never merged into Δ). It is the SOLE trigger
  for the capped
  **6–8-run rescue study** (any rescue simulator must carry slippage + fees;
  the frictionless assumption is precisely what produced E18S's false positive).
- Everything else — other horizons, side splits, era/time-of-day/rollover
  breakdowns, CISD/FVG/IFVG label conditionings, MFE/MAE — is **explicitly
  EXPLORATORY** and cannot trigger anything.
- If any secondary is ever promoted to confirmatory, promotion requires
  **Holm–Bonferroni correction over the fully enumerated family** (list appended
  here at promotion time, before those data are examined).

"Stable positive" is defined numerically: significant after Holm correction
**AND** sign-stable in **≥12/15 leave-one-year-out folds** **AND** positive in
**≥3/4 markets** **AND** Δ > **0.2R** (above friction, not merely above zero).

## 6. MFE/MAE clause

MFE/MAE inform the NEXT hypothesis only. They may not rescue a null mean:
with optional stopping, zero drift rules out every stop/target configuration.

## 7. Inference method

Session-block (trading-day) **block bootstrap**, B = 10,000 day-level resamples,
primary and counter arms resampled jointly (preserves pairing). Two-sided 95%
percentile CI on Δ. No p-values are published from the cloud run; inference
happens offline on the exported EVENT ledger, under this document's rules.

## 8. Boundaries

Dev segment only (2010–01→2024-12 or the campaign dev window). Validation and
holdout remain LOCKED. No optimization begins regardless of outcome; POSITIVE
merely makes the capped, friction-carrying rescue study *available*.
