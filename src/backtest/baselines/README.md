# Backtest Baselines

This directory stores versioned baseline parameter files that should stay stable while strategy experiments move forward.

## `a_share_box_p0_baseline.json`

P0 frozen baseline for the A-share box strategy.

- Strategy: `a_share_box`
- Source profile: `data/backtests/params_turnover_loose_v64.json`
- Execution assumptions: next-bar open execution, `qfq`, `daily_limits`
- Purpose: compare future refactors and strategy experiments against a stable, named parameter profile

Recommended batch command:

```bash
rtk uv run --extra dev python scripts/run_backtest_batch.py \
  --stock-codes data/backtests/nextbar_v64_all_stock_codes.json \
  --start-date 2020-01-01 \
  --end-date 2026-05-21 \
  --strategy a_share_box \
  --price-adjustment qfq \
  --trading-constraints daily_limits \
  --params-file src/backtest/baselines/a_share_box_p0_baseline.json \
  --output-dir data/backtests/p0_a_share_box_baseline
```
