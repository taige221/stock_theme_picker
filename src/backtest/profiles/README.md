# A-share Box Strategy Profiles

These profiles split the current `params_turnover_loose_v64.json` baseline into testable strategy personalities.

## Profiles

- `balanced_v1`: balanced breakout + pullback profile with turnover cap, breakeven, lower trailing activation, and pullback stall exit.
- `pullback_dominant_v1`: pullback-first profile with stricter early-failure handling and rebound-risk score penalty.
- `breakout_selective_v1`: lower-frequency breakout profile with stricter breakout quality gates.

The companion `a_share_box_profiles_manifest.json` records the recommended portfolio scheduling settings for P2.5 comparisons.

## P2.5 Run Notes

Artifacts from the 2026-05-28 style-pool run:

- Profile summary: `data/backtests/style_profile_runs_p25/style_profile_summary.csv`
- Balanced schedule: `data/backtests/diagnostics/p25_style_profiles_balanced_signal_score_3_p2_b1_cap8/selection_summary.csv`
- Pullback-only schedule: `data/backtests/diagnostics/p25_style_profiles_pullback_only_no_fill/selection_summary.csv`
- Breakout-only schedule: `data/backtests/diagnostics/p25_style_profiles_breakout_only_min80_no_fill/selection_summary.csv`

Current read:

- `balanced_v1` is the most stable default candidate across style pools: average aggregate return 2.49%, median 2.90%, 2 losing pools.
- `pullback_dominant_v1` is stronger in AI semiconductor and high-beta growth pools, but weak in slow large value and pullback-repair pools.
- Strict pullback-only scheduling improved average selected trade return from 0.28% to 0.40%, but only lifted average win rate from 37.31% to 37.94%.
- `breakout_selective_v1` is diagnostic only for now. Strict breakout-only scheduling selected 24 trades with average selected return -2.34% and no positive style pool, so high-score breakouts should not be promoted to P3.
- For single-shape comparisons, keep `fill_unused_slots` false; otherwise a zero quota can still be backfilled by other signal types.

Main-pool follow-up:

- `bt_4008f88677a1` (`v64`/mainline) remains the P3 baseline: aggregate return 2.85%, win rate 39.79%, PF 1.2554, 749 trades.
- `balanced_v1` main-pool run `bt_3733d9bf6f89` dropped to 0.52% aggregate return and 37.12% win rate.
- `pullback_dominant_v1` main-pool run `bt_4ecfd55ea824` dropped to 0.33% aggregate return and 35.26% win rate.
- P2.5 should start P3 from `v64` + `signal_score_3_p2_b1_cap8`; the new profiles are research lenses, not default replacements.

## Style-Pool Command

```bash
rtk uv run --extra dev python scripts/run_style_pool_backtests.py \
  --profiles balanced_v1,pullback_dominant_v1,breakout_selective_v1 \
  --start-date 2021-01-01 \
  --end-date 2026-05-28 \
  --price-adjustment qfq \
  --trading-constraints daily_limits \
  --import-db \
  --import-equity-mode portfolio_only \
  --output-root data/backtests/style_profile_runs_p25
```

## Main-Pool Command Example

```bash
rtk uv run --extra dev python scripts/run_backtest_batch.py \
  --stock-codes data/backtests/stock-codes.json \
  --start-date 2021-01-01 \
  --end-date 2026-05-28 \
  --strategy a_share_box \
  --price-adjustment qfq \
  --trading-constraints daily_limits \
  --params-file src/backtest/profiles/a_share_box_balanced_v1.json \
  --output-dir data/backtests/profile_runs/balanced_v1_main \
  --import-db \
  --import-stock-pool data/backtests/stock-codes.json \
  --import-equity-mode portfolio_only
```
