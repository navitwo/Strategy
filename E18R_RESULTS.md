# E18R — POST-CORRECTNESS DEV RERUN (engine v2.3, all rec_ok=1)

Preconditions met before submission: local suite 13/13 (incl. OCO
single-exit invariant, deterministic replay, protocol conformance),
smoke gate PASS (FY-23, rec_ok=1 cash identity), OCO void-leg fix verified
live (7 fills → 7 trades), entry-fallthrough self-exit bug found & fixed.

## CRITICAL BUG FOUND DURING E18R (now fixed, commit 5e7726d)
Entry fills fell through into the exit handler: every entry instantly
"exited" itself at 0.0R and wiped position context. First E18R attempt
produced 51 phantom rows with r_sum=0. Root cause: missing return/kind-gate.
Local red→green repro added. This is exactly the class of defect the new
gate suite exists to catch — and it did, before any number was quoted.

## Panel (NQ, 1 contract, 2010-01→2024-12 dev, all rec_ok=1)
| variant | n | WR% | avgR | PF(R) |
|---|---|---|---|---|
| candidate (sweep stop) | 46 | 17.4 | −0.399 | 0.55 |
| ablCISD (trigger bypassed) | 53 | 20.8 | −0.445 | 0.48 |
| shadowMOC (marketable entry) | 62 | 37.1 | −0.381 | 0.33 |
| ablFVG-mkt (no FVG gate) | 132 | 29.5 | −0.207 | 0.73 |

## Readings (diagnostic-grade; not edge claims)
- CISD ablation: removing the trigger wait shifts n 46→53 and WR 17.4→20.8%
  but expectancy worsens (−0.399→−0.445). The CISD wait adds mild negative
  selectivity on entries — consistent with E18's adverse-selection finding,
  now measured against a matched ablation rather than a random null.
- FVG-mkt ablation: dropping the FVG gate nearly triples sample (132 vs 46)
  with better expectancy (−0.207 vs −0.399). The FVG+retest chain as
  specified is net-negative relative to its own components.
- Market-entry shadow: WR jumps to 37.1% (vs 17.4% resting-limit candidate)
  confirming adverse selection directionally, but PF(R) collapses to 0.33:
  immediate entries pay for wins with many full -1R losses.
- Every variant remains below breakeven (WR<33.3% at 2R). No configuration
  of these gates shows positive expectancy on 2010–2024 dev.

## Status
- Optimization remains PAUSED pending directive review of this panel.
- Validation/holdout LOCKED (untouched).
- Ledger exports (e18r_results.jsonl, per-run rt dicts) preserved for audit;
  block-bootstrap CI computation deferred until user selects which variants
  merit formal CI treatment given all are sub-breakeven.

## Honest bottom line
The engine is now correct and fully reconciled. The strategy as specified
does not show positive dev expectancy in any tested variant. The most
defensible next research question is whether ANY entry mechanism applied to
this signal family clears friction on NQ intraday — currently answered no.
