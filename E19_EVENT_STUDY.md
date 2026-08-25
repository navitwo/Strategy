# E19 — EVENT STUDY: HTF-BIAS + SWEEP/RECLAIM FORWARD RETURNS (v2.5.6)

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
