# E19B ANALYSIS — pre-registered rule applied offline

Population: bias_aligned == True, pooled across markets.
Rule: POSITIVE if CI_lo > 0.2R; NULL if CI_hi < 0.2R; else INCONCLUSIVE.

| horizon | n | mean R | CI lo | CI hi | verdict |
|---|---|---|---|---|---|
| 30m | 1381 | 0.0706 | -0.0410 | 0.1849 | **NULL** |
    - per-market means: ES +0.101, NQ +0.161, RTY -0.021, YM +0.006
| 60m | 1381 | 0.0378 | -0.1238 | 0.2032 | **INCONCLUSIVE** |
    - per-market means: ES -0.039, NQ +0.163, RTY -0.120, YM +0.064
| 120m | 1381 | -0.0091 | -0.2198 | 0.2171 | **INCONCLUSIVE** |
    - per-market means: ES -0.204, NQ +0.233, RTY -0.288, YM +0.063
| 240m | 1381 | -0.0329 | -0.3012 | 0.2493 | **INCONCLUSIVE** |
    - per-market means: ES -0.207, NQ +0.105, RTY -0.277, YM +0.117

PRIMARY (H*=120m): **INCONCLUSIVE**

All horizons: 30m=NULL, 60m=INCONCLUSIVE, 120m=INCONCLUSIVE, 240m=INCONCLUSIVE


## Pre-run power diagnostic (MDE, reported after the fact as design property)

Day-level SD of aligned forward R (120m): computed across ~3.7k market-days.
With n=1381 events over ~3.5 years and day-clustered resampling, the design's
MDE at 80% power / alpha=0.05 is approximately 0.20-0.25R - i.e., this study
was powered to just barely detect the friction bar itself. The INCONCLUSIVE
verdict at H* is consistent with a true effect near zero OR a small positive
below the design's resolving power; the rule forbids interpreting it as
either.
