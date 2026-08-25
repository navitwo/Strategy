# E19 — EVENT STUDY: HTF-BIAS + SWEEP/RECLAIM FORWARD RETURNS (v2.5.6)

> ## ⚠️ RECLASSIFICATION (2026-08-23, review round 6 — E19B directive)
>
> This study measured **raw bias-aligned level penetrations**, not sweep/reclaim
> events. Verified in code: the `events_only` branch inside `_try_arm_attempt`
> returned immediately after the min-penetration check — BEFORE the
> `sweep_max_ticks` depth reject and BEFORE reclaim confirmation. Confirmed by
> its own funnel: `f_attempts_used=952` with `f_L_sweep_ok=0`,
> `f_depth_rejects=0`, `f_no_reclaim=0` (a genuine sweep/reclaim study must show
> non-zero values in all three). E19 is therefore relabeled a **raw
> level-penetration diagnostic**.
>
> Additional statistical deficiencies, per the directive: it published no σ,
> no t-statistic on the means (only binomial win-rate z), no confidence
> intervals, no block bootstrap, and no MFE/MAE; its stated per-event vol of
> "~10–20 bps" contradicts NQ's actual ~50–70 bps dispersion at 120 minutes.
> The true reclaimed population is **449** (952 → 159 depth rejects → 449
> sweep_ok), not 952.
>
> **Consequence:** the "no directional information → ARCHIVED" verdict is
> WITHDRAWN as an archive justification. Under PREREGISTRATION_E19B.md's three
> outcome classes (positive / null / inconclusive), a study with this
> mislabeled population and no power reporting can earn at most
> **INCONCLUSIVE**. The strategy family's archive status is suspended pending
> E19B, which reruns the idea correctly: post-reclaim candidate capture,
> R-unit forward returns, paired counter-bias control, cross-market
> replication (ES/YM/RTY dev data only), and n/σ/SE/CI/MDE reported before
> any p-values.

---

# ORIGINAL (RECLASSIFIED) REPORT — preserved unedited below

Question (review round 5): does the HTF-bias + sweep/reclaim signal family
contain ANY forward directional information on NQ intraday, independent of
entry mechanism, gates, or costs?

## Method
- events_only variant: arms exactly the same bias-aligned sweep attempts as
  the candidate (952 events over 2010-01→2024-12; 497 long / 455 short),
  but submits nothing.
- Each event resolves signed forward return (side-aligned) at 30/60/120/240
  minutes from the arming bar close, on completed 5m bars.
- Engine-internal resolution on a monotonic absolute bar counter (immune to
  ring-buffer trim); full population captured (952/952, pending=0).

## Results
| horizon | n | mean (bps) | WR | binomial z | p (two-sided) |
|---|---|---|---|---|---|
| 30m | 952 | +0.41 | 50.74% | 0.46 | 0.65 |
| 60m | 952 | −0.47 | 51.47% | 0.91 | 0.36 |
| 120m | 952 | −0.60 | 51.58% | 0.98 | 0.33 |
| 240m | 952 | −0.59 | 51.16% | 0.72 | 0.47 |

## Verdict
**No detectable directional information.** All means are sub-basis-point
against per-event vol of ~10–20 bps (|t| < 1); win-rate deviations from
coin-flip are z < 1 everywhere. The sweep/reclaim event, conditioned on
4H-bias alignment, is statistically indistinguishable from a coin flip at
every tested horizon.

## Consequence per the pre-registered decision rule
The rescue-study precondition ("event study identifies positive directional
information") is **NOT met**. Per the directive:
→ The strategy family (HTF bias → sweep/reclaim → CISD → IFVG → retest) is
  **ARCHIVED without touching validation or holdout data**.
→ No capped rescue study (8–12 experiments) is conducted, because there is
  no directional signal for it to rescue.

## Notes
- This verdict concerns the SIGNAL's information content, not execution:
  E18S already proved the engine reconciles to the cent with one clean exit
  per cycle.
- The ablFVG-mkt positive reading in E18S (+0.099R, n=205) is consistent
  with this null: its confidence interval spans zero widely, and the event
  study now shows the underlying event carries no edge that a gate could
  either add or destroy.
