# Local NQ + GC Minute-Data Costing (2026-09-01)

Scope: one-time local development coverage for NQ and GC, 2010-06-07 through 2024-12-31, sufficient to build raw/open-interest-mapped continuous futures and consolidate to 30 minutes. Validation (2025) and holdout (2026+) are intentionally excluded.

## Recommendation

**Quote and use Databento `GLBX.MDP3` first.** Request `ohlcv-1m` plus point-in-time `definition` records for `NQ.FUT` and `GC.FUT`, filter outright contracts, and preserve `source_contract` on every bar. Databento is usage-based, has no historical license requirement, exposes an exact free `metadata.get_cost` quote, and gives new accounts $125 in historical credits. Do not buy QuantConnect bulk minute data for this two-ticker study.

## Databento

Official facts:

- GLBX.MDP3 starts 2010-06-06 UTC and includes CME/CBOT/NYMEX/COMEX futures, `OHLCV-1m`, definitions, and continuous symbology.
- Historical pricing is usage-based on uncompressed DBN bytes; the public catalog advertises **from $0.50/GB**.
- New users receive **$125** historical-data credits, expiring after six months.
- Exact price is available without downloading data by configuring the request / calling `metadata.get_cost`; the public static page does not disclose the schema-specific final quote.
- Standard is $199/month but is unnecessary for a one-time L0 historical pull.

Sizing sanity check (not a quote): two continuous products over 16 years at 23h × 252 sessions/year × one 56-byte record/minute is ~0.62 GB; retaining roughly six simultaneous outrights is ~3.74 GB. At the advertised floor this is ~$0.31–$1.87. The actual bill may be higher because schema-specific rates, listings, and actual record counts control it. **Budget ceiling: do not download if the exact Databento quote exceeds the $125 credit without a new approval.**

Exact-quote request:

- dataset: `GLBX.MDP3`
- symbols: `NQ.FUT`, `GC.FUT`
- input symbology: `parent`
- schemas: `ohlcv-1m` and `definition`
- dates: 2010-06-07 through 2025-01-01 exclusive

Sources:

- https://databento.com/pricing
- https://databento.com/catalog/cme/GLBX.MDP3
- https://databento.com/catalog/cme/GLBX.MDP3/futures/NQ
- https://databento.com/catalog/cme/GLBX.MDP3/futures/GC
- https://databento.com/docs/faqs/usage-pricing-and-data-credits

## QuantConnect local download

Official per-ticker rates on the Quant Researcher tier:

- US Futures Security Master: **$600** initial.
- US Future Universe: **$1 per ticker per trading-day file**.
- US Futures minute data: **$0.50 per ticker per trading day per data format** (trade, quote, and open interest are separate).
- Bulk minute package: **$31,800 initial** including prerequisites; updates $2,760/year.

The frozen interval contains 3,802 weekdays, an explicit upper bound before exchange holidays:

| Package | Trade-only bars | Trade + quote + OI |
|---|---:|---:|
| Security Master | $600 | $600 |
| Universe, 2 × 3,802 × $1 | $7,604 | $7,604 |
| Minute files | $3,802 | $11,406 |
| **Upper-bound initial total** | **$12,006** | **$19,610** |

Actual per-ticker cost is somewhat lower because holidays remove files, but it remains orders of magnitude above the Databento usage-based path. Trade-only minute bars plus Universe/definitions are enough for this no-order OHLC event study; quote data is not required.

Source: https://www.quantconnect.com/docs/v2/lean-cli/datasets/quantconnect/futures

## Exact-quote gate (executed 2026-09-04)

`POST https://api.databento.com/v0/metadata.get_cost` (dataset GLBX.MDP3,
symbols NQ.FUT,GC.FUT, stype_in=parent, ohlcv-1m and definition,
date_range 2010-06-07,2025-01-01) returned `{"detail":"Not authenticated"}`:
the endpoint is reachable but **requires a Databento API key**, and none
exists in this environment (no env var, no `~/.databento`, no ignored env
file). The user must create a free key at databento.com and provide it via
the standard environment boundary (`DATABENTO_API_KEY` in an ignored file);
then `d47_databento_quote.py` prints the exact cost with zero data
downloaded and zero bytes purchased.

## Decision

1. Obtain the free Databento exact quote before any download.
2. Proceed only if it is within existing credits (≤$125); otherwise stop for explicit cost approval.
3. Ingest local immutable raw files, hash them, filter outright contracts from definitions, map by open interest without price adjustment, preserve full source-contract provenance, and run the event study locally.
4. Keep QuantConnect as an independent hosted replication authority, not the primary iteration loop.
