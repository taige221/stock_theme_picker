# Strategy Package Layout

Strategies are grouped by strategy family so new implementations can be added without growing one flat module namespace.

```text
src/strategy/
  base.py             # shared Strategy / StrategySignal contract
  params.py           # shared parameter schema
  __init__.py         # registry and metadata facade

  a_share_box/        # A-share box breakout / pullback strategy family
    strategy.py

  stock_signal/       # adapters around single-stock signal views
    strategy.py

  benchmarks/         # simple or legacy comparison strategies
    a_share_migrated_crypto.py
```

New strategy families should get their own package and register their strategy class in `src/strategy/__init__.py`.
