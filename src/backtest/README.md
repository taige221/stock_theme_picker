## 回测命令

## 目录结构

回测后端能力集中在 `src/backtest/`，按职责分层：

```text
src/backtest/
  core/         # engine / models / metrics，回测执行内核
  data/         # 日线数据读取适配
  analysis/     # 回测后诊断、信号分层排序
  baselines/    # 冻结 baseline 参数
  runner/       # 后续承接单票/批量 runner 编排
  persistence/  # 后续承接导入、查询、图表、预设持久化
```

旧导入路径仍保留兼容包装，例如 `theme_picker.backtest.engine` 和
`theme_picker.backtest.models` 仍可用；新代码优先使用
`theme_picker.backtest.core.*`、`theme_picker.backtest.data.*` 和
`theme_picker.backtest.analysis.*`。

### 0. P0 冻结基线

`a_share_box` 的 P0 baseline 参数固定在：

```text
src/backtest/baselines/a_share_box_p0_baseline.json
```

后续策略重构或参数实验，默认先和这份 baseline 同口径比较。建议命令：

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

### 1. 单票回测

最小命令：

```bash
python3 scripts/run_backtest.py \
  --stock-code 300502.SZ \
  --start-date 2020-01-01 \
  --end-date 2026-05-21
```

完整命令：

```bash
python3 scripts/run_backtest.py \
  --stock-code 300502.SZ \
  --start-date 2020-01-01 \
  --end-date 2026-05-21 \
  --strategy a_share_box \
  --price-adjustment qfq \
  --trading-constraints daily_limits \
  --params-file data/backtests/params_turnover_loose.json \
  --output data/backtests/300502_result.json
```

### 2. 批量回测

最小命令：

```bash
python3 scripts/run_backtest_batch.py \
  --stock-codes 300502.SZ,300750.SZ \
  --start-date 2020-01-01 \
  --end-date 2026-05-21
```

完整命令：

```bash
python3 scripts/run_backtest_batch.py \
  --stock-codes 300502.SZ,300750.SZ,600030.SH,601899.SH \
  --start-date 2020-01-01 \
  --end-date 2026-05-21 \
  --strategy a_share_box \
  --price-adjustment qfq \
  --trading-constraints daily_limits \
  --params-file data/backtests/params_turnover_loose.json \
  --output-dir data/backtests/my_batch_run
```

批量输出会包含：

- 每只股票一个结果 JSON
- `summary.json`
- `summary.csv`
- 如果某只股票的历史起始日晚于请求起点，批量脚本会自动顺延到该票实际可用起始日后再回测

如需遇错立即停止，可补：

```bash
--fail-fast
```

### 3. 交易诊断报表

用于比较箱体策略不同版本的交易质量，尤其是 `breakout_long` / `pullback_bounce`、分数段、风格桶、信号序号和退出原因：

```bash
rtk python3 scripts/analyze_box_trades.py \
  --run data/backtests/change_params_v48_3 \
  --run data/backtests/change_params_v58_all \
  --run data/backtests/change_params_v60_all \
  --output-dir data/backtests/diagnostics/box_quality_v48_v58_v60
```

输出包含：

- `diagnostics.json`：整体诊断、最好/最差 cohort、最大亏损/盈利交易
- `cohorts.csv`：按版本、信号类型、分数段、风格桶、信号序号、退出原因聚合后的统计
- `trades.csv`：展开后的逐笔交易明细，带入场分数、MAE/MFE、箱体和回踩/突破特征

如果回测结果已经通过 `scripts/import_backtest_json.py` 导入 DuckDB，也可以直接按 DB `run_id` 读取，不要求原始 `result_path` JSON 仍然存在：

```bash
rtk python3 scripts/analyze_box_trades.py \
  --db-run-id bt_d2c840a083f0 \
  --database-path data/stock_analysis.duckdb \
  --output-dir data/backtests/diagnostics/db_box_quality_bt_d2c840a083f0
```

DB 模式使用只读 DuckDB 连接。导入表 `strategy_backtest_trade` 已保留逐笔交易的标准列、`entry_signal_metadata_payload` 和 `raw_trade_payload`，足够重建当前 cohort 诊断；`--database-path` 不传时默认使用 `DATABASE_PATH` 或 `data/stock_analysis.duckdb`。如果后端或导入任务正在持有 DuckDB 写连接，先停止对应进程再运行这些只读诊断脚本。

导入回测 JSON 时，权益曲线明细可以按三档落库，默认是 `traded_daily`：

```bash
rtk python3 scripts/import_backtest_json.py \
  --source data/backtests/change_params_v60_all/summary.json \
  --stock-pool data/backtests/stock-codes.json \
  --equity-mode traded_daily
```

- `portfolio_only`：只保存组合每日权益点，适合只看净值、回撤和版本对比。
- `traded_daily`：保存组合每日权益点，以及单股持仓区间/退出锚点权益点；这是默认档，兼顾复盘与 DB 体积。
- `all_daily`：保存所有股票每日权益点，适合深度诊断，但每个综合池 run 会写入约 24 万条单股权益点。

### 4. 组合级信号调度

用于验证有限资金下“每天只选少数候选”的效果。它不会改变单票策略本体，而是读取已有回测交易，按入场日把 `pullback_bounce` 和 `breakout_long` 分池排序，再按每日配额筛选。

核心能力在 `src/backtest/analysis/signal_ranking.py` 和 `src/application/backtest_portfolio_schedule_service.py`。DB run 模式会把调度结果落到：

- `strategy_backtest_portfolio_schedule`：一次组合调度的配置和 summary
- `strategy_backtest_portfolio_candidate`：每日候选、排序、选中状态和逐笔交易结果

API 入口：

- `POST /api/v1/backtests/runs/{run_id}/portfolio-schedules`
- `GET /api/v1/backtests/runs/{run_id}/portfolio-schedules`
- `GET /api/v1/backtests/portfolio-schedules/{schedule_id}`

JSON artifact 研究模式仍然可以直接落 CSV：

```bash
rtk python3 scripts/rank_box_signals.py \
  --run data/backtests/change_params_v48_3 \
  --run data/backtests/change_params_v58_all \
  --run data/backtests/change_params_v60_all \
  --rank-mode cohort_ev \
  --min-rank-score 2.0 \
  --max-per-day 3 \
  --pullback-quota 2 \
  --breakout-quota 1 \
  --output-dir data/backtests/diagnostics/layered_rank_v48_v58_v60_ev_min20
```

常用选项：

- `--rank-mode signal_score`：每个信号池内按原始入场评分排序
- `--rank-mode cohort_ev`：按 `signal_type + score_bin`、`signal_type + style_bucket + signal_number` 的历史 cohort 收益做收缩排序
- `--rank-mode cohort_ev_walk_forward`：只用当天之前已平仓的历史 cohort 收益排序，降低样本内前视偏差
- `--rank-mode stock_quality_walk_forward`：只用当天之前已平仓的同票/同票同信号历史，按胜率、平均收益、PF 做收缩排序；适合验证“当日候选里优先选更好的股票”
- `--min-rank-score`：只允许分层排序分达到阈值的候选进入每日配额；这是组合层 EV 过滤，不等同于策略入场的全局高分阈值
- `--heat-score-cap`：只允许过热分不超过阈值的候选进入每日配额；`rank_score` 只负责排序，`heat_score` 负责过滤历史过热/过拟合的高分票。旧 `--max-heat-score` 仍兼容输入，但输出统一记录为 `heat_score_cap`
- `--bull-heat-score` / `--range-heat-score` / `--weak-heat-score` / `--unknown-heat-score`：覆盖对应市场环境的 heat cap；传 `none` 表示该环境不设 heat cap
- `--bull-min-rank-score` / `--range-min-rank-score` / `--weak-min-rank-score` / `--bear-min-rank-score` / `--unknown-min-rank-score`：覆盖对应市场环境的 rank floor；用于实验分环境过滤，不建议未验证就全局套用
- `--bull-position-size-pct` / `--range-position-size-pct` / `--weak-position-size-pct` / `--unknown-position-size-pct`：覆盖对应市场环境的账户仓位；候选仍由 rank/heat 决定，仓位只影响账户级回放
- `--bear-regime-action soft`：把 `bear_pause` 从硬暂停改成 `bear_soft_max1_pullback_only` 实验 profile；默认仍是 `pause`
- `--bear-heat-score` / `--bear-position-size-pct`：配合 soft bear 使用；默认熊市 soft 仓位是基础仓位的一半
- `--market-regime-risk-override`：开启 bull/range 的二级风险降级实验；默认关闭，并在输出里保留 `raw_market_regime` 与 `market_regime_override_reason`
- `--risk-override-target-regime`：风险降级后的目标环境，支持 `risk_pause` / `risk_defensive` / `weak_defensive` 等；`risk_pause` 会暂停新开仓
- `--risk-euphoric-return-60d-pct` / `--risk-euphoric-breadth-ma60-pct`：识别“60 日收益极热 + MA60 广度极高”的顶部退潮风险
- `--risk-breadth-ma60-pct` / `--risk-fragile-return-60d-pct` / `--risk-fragile-breadth-ma60-pct` / `--risk-cooling-breadth-ma20-pct` / `--risk-cooling-return-20d-pct`：用于更宽的假 bull/range 降级实验，需谨慎验证
- `--risk-position-size-pct`：`risk_defensive` profile 的仓位；该 profile 每日最多 1 笔、只做 pullback
- `--max-per-day`：单日最多选择几笔
- `--pullback-quota` / `--breakout-quota`：单日两个信号池的基础配额
- `--max-open-positions`：可选并发持仓上限，`0` 表示不限制
- `--no-fill`：信号配额未用满时不再用其他候选补位

读取已导入 DB 的 run 会同时落库组合调度，并继续输出 CSV/JSON 便于离线检查：

```bash
rtk python3 scripts/rank_box_signals.py \
  --db-run-id bt_d2c840a083f0 \
  --database-path data/stock_analysis.duckdb \
  --rank-mode cohort_ev_walk_forward \
  --max-per-day 3 \
  --pullback-quota 2 \
  --breakout-quota 1 \
  --output-dir data/backtests/diagnostics/db_layered_rank_bt_d2c840a083f0
```

输出包含：

- `selection_summary.json` / `selection_summary.csv`：分层排序后的交易数、胜率、平均单笔收益、pullback/breakout 选中数
- `ranked_candidates.csv`：每个候选的每日排名、是否通过 `min_rank_score`、是否被选中、选中来源
- `saved_portfolio_schedule_id=...`：DB run 模式下保存的组合调度 ID

`cohort_ev` 和 `stock_quality` 是样本内排序诊断，不能直接当成默认实盘规则；`cohort_ev_walk_forward` / `stock_quality_walk_forward` 只用当天之前已平仓交易来降前视偏差，但仍应作为研究 overlay 验证，而不是默认 live rule。当前这一层仍是“候选交易调度 overlay”，不是完整资金账户级组合回测；资金占用、复利、仓位市值波动适合放到下一阶段组合引擎处理。

### 5. 风格股票池实验

用于先按本地日线/辅助指标生成风格池，再批量比较不同 profile。网络检索只作为主题锚点，入池排序仍以本地 `stock_daily_raw` / `stock_daily_aux` 为准：

```bash
rtk python3 scripts/build_style_stock_pools.py \
  --pool-size 24 \
  --end-date 2026-05-21
```

输出：

- `data/backtests/style_pools/style_*.json`
- `data/backtests/style_pools/style_pool_candidates.csv`
- `data/backtests/style_pools/style_pool_summary.json`

批量跑 profile：

```bash
rtk python3 scripts/run_style_pool_backtests.py \
  --profiles v53,v57,v60,v64 \
  --start-date 2020-01-01 \
  --end-date 2026-05-21 \
  --reuse-existing
```

如果要落库：

```bash
rtk python3 scripts/run_style_pool_backtests.py \
  --profiles v53,v57,v60,v64 \
  --start-date 2020-01-01 \
  --end-date 2026-05-21 \
  --import-db \
  --import-equity-mode portfolio_only
```

输出汇总：

- `data/backtests/style_profile_runs/style_profile_summary.json`
- `data/backtests/style_profile_runs/style_profile_summary.csv`

注意：静态风格池如果用最新快照选股、再回测历史，会有选股前视。该工具当前用于 profile selector 研究；正式规则需要改成按历史 `as-of` 滚动生成风格池。

### 6. 稳健性与市场环境切换

用于把组合调度从“单次结果好不好”升级成“不同环境下是否稳健”。脚本会在同一批已导入 DB 的逐笔交易上输出：

- walk-forward：按年/季/月重置资金看稳定性
- 参数敏感性：仓位、并发、每日候选数等单轴扰动
- Monte Carlo：对每日账户收益做 block bootstrap，观察尾部亏损概率
- 市场环境：按本地股票池价格广度和 20/60 日收益分成 `bull_active`、`range_neutral`、`weak_defensive`、`bear_pause`
- regime-aware：在单条时间线上按入场日环境切换 profile，避免把不同环境分组结果事后相加

当前保守默认映射是：

- `bull_active`：每日最多 4 笔，`pullback=3`、`breakout=1`
- `bear_pause`：暂停新开仓
- `range_neutral`：每日最多 3 笔，`pullback=2`、`breakout=1`
- `weak_defensive`：每日最多 2 笔，`pullback=1`、`breakout=1`
- `unknown`：数据不足时每日最多 2 笔，`pullback=1`、`breakout=1`

示例：

```bash
rtk uv run --extra dev python scripts/run_backtest_robustness.py \
  --db-run-id bt_4008f88677a1 \
  --rank-mode stock_quality_walk_forward \
  --heat-score-cap 55 \
  --max-per-day 3 \
  --pullback-quota 2 \
  --breakout-quota 1 \
  --ranking-max-open-positions 8 \
  --initial-cash 1000000 \
  --position-size-pct 0.08 \
  --account-max-positions 8 \
  --price-adjustment qfq \
  --monte-carlo-iterations 1000 \
  --compare-max-per-day 4 \
  --output-dir data/backtests/diagnostics/p3_regime_aware_bt_4008f88677a1_conservative_v1
```

如果要批量验证分环境 heat cap，可以用 grid：

```bash
rtk uv run --extra dev python scripts/run_backtest_robustness.py \
  --db-run-id bt_4008f88677a1 \
  --rank-mode stock_quality_walk_forward \
  --heat-score-cap 55 \
  --max-per-day 3 \
  --pullback-quota 2 \
  --breakout-quota 1 \
  --ranking-max-open-positions 8 \
  --initial-cash 1000000 \
  --position-size-pct 0.08 \
  --account-max-positions 8 \
  --price-adjustment qfq \
  --regime-heat-grid 'bull=55,60,65,none;range=55,60;weak=50,52,55;bear=pause,55;unknown=50,52,pause' \
  --output-dir data/backtests/diagnostics/p3_regime_heat_grid_bt_4008f88677a1
```

关键输出：

- `robustness_summary.json`：总览配置、baseline、profile、市场环境和 regime-aware 结果
- `market_regime_profile_summary.csv`：不同 profile 在各市场环境下的拆分表现
- `regime_aware_account_summary.json`：真正按时间线切换 profile 后的账户级结果
- `regime_aware_candidates.csv`：每个候选所属环境、选中 profile、是否被暂停或入选
- `regime_aware_selected_by_period_regime.csv`：按月/季/年 + 市场环境查看真正选中的交易结果
- `regime_aware_rank_filter_summary.csv`：按时间段 + 市场环境 + 过滤原因 + 信号类型查看候选被保留/过滤后的表现
- `regime_aware_daily_rank_filter.csv`：逐日查看候选数、可交易候选数、选中数和被 `above_heat_score_cap` / `paused_regime` 过滤的候选表现
- `regime_aware_rank_score_bins.csv`：固定输出 `00-10` 到 `90-100` 的 `rank_score` 分箱，并按 `all_candidates` / `eligible_candidates` / `selected_candidates` / `filtered_candidates` 查看胜率、平均收益、PF、MAE、持有期和质量分样本置信度
- `regime_heat_grid.csv`：分环境 heat cap grid 的账户级表现、胜率、PF、MAE、持有期
- `regime_heat_grid_by_regime.csv`：每组 heat cap 在各市场环境下的选中交易表现

候选明细里同时保留两个排名：

- `raw_daily_rank`：过滤前按 `rank_score` 的原始排名，适合复盘高分票为什么被过滤
- `eligible_daily_rank`：过滤后可交易候选里的排名，适合看当天真实可选顺序
- `rank_filter_reason`：`passed`、`above_heat_score_cap`、`below_min_rank_score`、`paused_regime`

2026-05-29 第二轮观察：在 regime-aware 的基础上使用 `stock_quality_walk_forward --heat-score-cap 55`，交易数从 `511` 收敛到 `445`，收益从 `40.1146%` 提升到 `42.5013%`，最大回撤从 `12.2042%` 降到 `9.2635%`，胜率从 `42.6614%` 到 `44.0449%`，PF 从 `1.3652` 到 `1.4281`。后续同类实验应固定检查 `regime_aware_rank_score_bins.csv`。

2026-05-29 第三轮观察：分环境 heat cap 的 grid 没有证明优于全局 `55`；`range=60` 会明显变差，`weak=50/52` 也会误杀弱势环境里的高质量交易。分环境 rank floor 能小幅抬高胜率/PF，但收益大幅下降，说明 `40-50` 桶不能一刀切删除。更有效的是账户级环境仓位：在 `stock_quality_walk_forward --heat-score-cap 55` 基线上使用 `bull=10% / range=4% / weak=11% / unknown=8%`，收益从 `44.4847%` 提升到 `52.8737%`，最大回撤从 `9.5118%` 到 `9.7584%`，PF 从 `1.4532` 到 `1.5190`，Monte Carlo 5% 分位收益从 `11.7274%` 到 `15.1867%`，但最大暴露从 `63.0634%` 升到 `78.8739%`，应继续做仓位稳定性验证。

2026-05-29 第四轮观察：宽口径假 bull/range 降级会误伤正收益修复段；`risk_pause` 收益降到 `42.4497%`，`risk_defensive` 收益 `42.5214%`，都不应作为默认。窄口径“顶部退潮暂停”有效：在第三轮仓位基线上加 `--market-regime-risk-override --risk-override-target-regime risk_pause --risk-euphoric-return-60d-pct 35 --risk-euphoric-breadth-ma60-pct 95`，只过滤 14 个候选，这批合计 `-72.84%`；账户收益提升到 `59.6851%`，最大回撤保持 `9.7584%`，PF 到 `1.6114`，Monte Carlo 5% 分位收益到 `22.5333%`，亏损概率降到 `0.3%`。当前最强候选基线是：`stock_quality_walk_forward + heat_score_cap=55 + bull/range/weak/unknown=10%/4%/11%/8% + euphoric risk_pause`。

2026-05-29 候选配置池：

- 保守版：`heat_score_cap=55`，`bull/range/weak/unknown=8%/3%/8%/6%`，开启宽口径 `risk_pause`。中心样本交易数 `328`，收益 `30.9686%`，最大回撤 `6.5957%`，PF `1.4919`。相邻 `7%/3%/7%/5%` 到 `9%/3%/9%/6%` 的回撤区间约 `5.86%~7.40%`，用于低回撤候选；它主要降低风险暴露，不代表原始选股 edge 明显增强
- 均衡版：`heat_score_cap=55`，`bull/range/weak/unknown=10%/4%/11%/8%` 或 `11%/4%/12%/8%`，只开启窄口径 euphoric `risk_pause`。`10/4/11` 收益 `59.6851%`、最大回撤 `9.7584%`、PF `1.6114`、交易数 `435`；`11/4/12` 收益 `67.1360%`、最大回撤 `10.5423%`、PF `1.6266`，但最大暴露升到 `86.5881%`
- 进攻版：`heat_score_cap=55`，`bull/range/weak/unknown=12%/4%/12%/8%`，只开启窄口径 euphoric `risk_pause`。收益 `70.2274%`，最大回撤 `11.2166%`，PF `1.6225`，交易数 `435`，最大暴露 `94.7821%`；暂时只能当候选，不能直接作为默认

## 历史数据同步

```bash
rtk python3 scripts/sync_tushare_history.py \
  --ts-codes 300502.SZ,300750.SZ \
  --start-date 2020-01-01 \
  --end-date 2026-05-21 \
  --sections calendar,raw,aux
```

也支持直接传 JSON 文件：

```bash
rtk python3 scripts/sync_tushare_history.py \
  --ts-codes data/backtests/stock-codes.json \
  --start-date 2020-01-01 \
  --end-date 2026-05-21 \
  --sections calendar,raw,aux
```

说明：

- `--ts-codes` 支持两种形式：
  - 逗号分隔，例如 `300502.SZ,300750.SZ`
  - JSON 文件，支持：
    - `["300502.SZ", "300750.SZ"]`
    - `{"stock_codes": ["300502.SZ", "300750.SZ"]}`
    - `{"results": [{"stock_code": "300502.SZ"}]}`
- `calendar`：交易日历
- `raw`：日K主价格表
- `aux`：换手率、涨跌停、停牌等辅助表
- 同股票请求区间如果已被历史交易日覆盖，会自动跳过，不再重复重拉

## 回测参数说明

### 通用 CLI 参数

- `--stock-code`
  单票代码，例如 `300502.SZ`

- `--stock-codes`
  批量股票代码，支持两种形式：
  - 逗号分隔，例如 `300502.SZ,300750.SZ`
  - JSON 文件路径，例如 `/private/tmp/theme_picker_stock_codes.json`
  JSON 文件可支持：
  - `["300502.SZ", "300750.SZ"]`
  - `{"stock_codes": ["300502.SZ", "300750.SZ"]}`
  - `{"results": [{"stock_code": "300502.SZ"}, {"stock_code": "300750.SZ"}]}`

- `--start-date`
  开始日期，格式 `YYYY-MM-DD`

- `--end-date`
  结束日期，格式 `YYYY-MM-DD`

- `--strategy`
当前可选：
- `a_share_box`
- `a_share_migrated_crypto`
- `stock_signal_auto`
- `stock_signal_pullback`
- `stock_signal_breakout`
- `stock_signal_trend_follow`
- `stock_signal_holding`

- `--params-file`
  外部 JSON 参数文件，用于覆盖默认策略参数

- `--output`
  单票结果输出路径

- `--output-dir`
  批量结果输出目录

### 价格口径

- `--price-adjustment raw`
  不复权原始价格

- `--price-adjustment qfq`
  前复权价格

当前 A 股日线回测建议优先使用：

```bash
--price-adjustment qfq
```

### 交易约束

- `--trading-constraints legacy_pct`
  老的近似逻辑，主要按涨跌幅近似判断

- `--trading-constraints daily_limits`
  使用 `up_limit/down_limit/is_suspended` 做更严格的涨跌停/停牌约束

当前建议优先使用：

```bash
--trading-constraints daily_limits
```

## 常用策略参数

参数定义见：

- [src/strategy/params.py](/Users/pengfeihao/code/theme_picker/src/strategy/params.py)

当前常用字段：

- `box_lookback_days`
  箱体回看天数

- `min_breakout_pct`
  最小突破幅度

- `min_volume_ratio`
  最小量比要求

- `breakout_min_breakout_pct`
  仅对 `breakout_long` 生效的最小突破幅度；不填时回退到 `min_breakout_pct`

- `breakout_min_volume_ratio`
  仅对 `breakout_long` 生效的最小量比要求；不填时回退到 `min_volume_ratio`

- `breakout_min_body_pct`
  仅对 `breakout_long` 生效的最小阳线实体涨幅，单位是百分比数值，例如 `1.2` 表示 `1.2%`

- `breakout_min_close_above_resistance_pct`
  仅对 `breakout_long` 生效的最小“收盘高于阻力位”比例，单位是小数，例如 `0.005` 表示收盘至少高于阻力位 `0.5%`

- `breakout_max_upper_shadow_ratio`
  仅对 `breakout_long` 生效的最大上影占比，范围 `0~1`；值越小，越倾向过滤掉长上影假突破

- `pullback_min_volume_ratio`
  仅对 `pullback_bounce` 生效的最小量比要求；不填时回退到 `min_volume_ratio`

- `max_bias_ma10_pct`
  与 MA10 的最大乖离

- `stop_loss_pct`
  固定止损

- `breakout_stop_loss_pct`
  仅对 `breakout_long` 生效的固定止损；不填时回退到 `stop_loss_pct`

- `pullback_stop_loss_pct`
  仅对 `pullback_bounce` 生效的固定止损；不填时回退到 `stop_loss_pct`

- `take_profit_pct`
  固定止盈

- `breakout_take_profit_pct`
  仅对 `breakout_long` 生效的固定止盈；不填时回退到 `take_profit_pct`

- `pullback_take_profit_pct`
  仅对 `pullback_bounce` 生效的固定止盈；不填时回退到 `take_profit_pct`

- `max_holding_days`
  最大持有天数

- `breakout_max_holding_days`
  仅对 `breakout_long` 生效的最大持有天数；不填时回退到 `max_holding_days`

- `pullback_max_holding_days`
  仅对 `pullback_bounce` 生效的最大持有天数；不填时回退到 `max_holding_days`

- `breakout_min_box_touches`
  仅对 `breakout_long` 生效的箱体最少触碰次数；不填时回退到 `min_box_touches`

- `pullback_min_box_touches`
  仅对 `pullback_bounce` 生效的箱体最少触碰次数；不填时回退到 `min_box_touches`

- `min_turnover_rate`
  最低换手率

- `preferred_turnover_rate_low`
  偏好换手率下限

- `preferred_turnover_rate_high`
  偏好换手率上限

- `min_signal_score`
  全局最低入场评分阈值，采用当前策略的 `100` 分制；不满足则信号只记录不入场

- `breakout_min_signal_score`
  仅对 `breakout_long` 生效的最低入场评分阈值；不填时回退到 `min_signal_score`

- `pullback_min_signal_score`
  仅对 `pullback_bounce` 生效的最低入场评分阈值；不填时回退到 `min_signal_score`

- `breakout_enable_trailing_stop`
  仅对 `breakout_long` 生效的 trailing stop 开关；不填时回退到 `enable_trailing_stop`

- `pullback_enable_trailing_stop`
  仅对 `pullback_bounce` 生效的 trailing stop 开关；不填时回退到 `enable_trailing_stop`

- `breakout_trailing_stop_activate_profit_pct`
  仅对 `breakout_long` 生效的 trailing stop 激活盈利阈值；不填时回退到通用值

- `pullback_trailing_stop_activate_profit_pct`
  仅对 `pullback_bounce` 生效的 trailing stop 激活盈利阈值；不填时回退到通用值

- `breakout_trailing_stop_drawdown_pct`
  仅对 `breakout_long` 生效的 trailing stop 回撤阈值；不填时回退到通用值

- `pullback_trailing_stop_drawdown_pct`
  仅对 `pullback_bounce` 生效的 trailing stop 回撤阈值；不填时回退到通用值

- `pullback_slow_large_enable_trailing_stop`
- `pullback_balanced_trend_enable_trailing_stop`
- `pullback_high_beta_enable_trailing_stop`
  仅对 `pullback_bounce` 生效，且按 `style_bucket` 进一步覆盖 trailing stop 开关；优先级高于 `pullback_enable_trailing_stop`

- `pullback_slow_large_trailing_stop_activate_profit_pct`
- `pullback_balanced_trend_trailing_stop_activate_profit_pct`
- `pullback_high_beta_trailing_stop_activate_profit_pct`
  仅对 `pullback_bounce` 生效，且按 `style_bucket` 进一步覆盖 trailing stop 激活盈利阈值

- `pullback_slow_large_trailing_stop_drawdown_pct`
- `pullback_balanced_trend_trailing_stop_drawdown_pct`
- `pullback_high_beta_trailing_stop_drawdown_pct`
  仅对 `pullback_bounce` 生效，且按 `style_bucket` 进一步覆盖 trailing stop 回撤阈值

- `breakout_enable_entry_stall_exit`
- `pullback_enable_entry_stall_exit`
  分别对 `breakout_long`、`pullback_bounce` 生效的 entry stall 开关；不填时回退到 `enable_entry_stall_exit`

- `breakout_entry_stall_days`
- `pullback_entry_stall_days`
  分别对 `breakout_long`、`pullback_bounce` 生效的 entry stall 观察天数

- `breakout_entry_stall_min_return_pct`
- `pullback_entry_stall_min_return_pct`
  分别对 `breakout_long`、`pullback_bounce` 生效的 entry stall 最低收益要求

- `pullback_slow_large_enable_entry_stall_exit`
- `pullback_balanced_trend_enable_entry_stall_exit`
- `pullback_high_beta_enable_entry_stall_exit`
  仅对 `pullback_bounce` 生效，且按 `style_bucket` 进一步覆盖 entry stall 开关

- `pullback_slow_large_entry_stall_days`
- `pullback_balanced_trend_entry_stall_days`
- `pullback_high_beta_entry_stall_days`
  仅对 `pullback_bounce` 生效，且按 `style_bucket` 进一步覆盖 entry stall 观察天数

- `pullback_slow_large_entry_stall_min_return_pct`
- `pullback_balanced_trend_entry_stall_min_return_pct`
- `pullback_high_beta_entry_stall_min_return_pct`
  仅对 `pullback_bounce` 生效，且按 `style_bucket` 进一步覆盖 entry stall 最低收益要求

- `enable_symbol_loss_cooldown`
  单股已实现亏损冷却开关；开启后，同一只股票连续亏损达到阈值，会暂停该股后续新开仓一段时间。该规则由单票回测引擎维护，只影响该股票自身，不影响其他股票。

- `symbol_loss_cooldown_losses`
  触发冷却所需的连续亏损笔数；例如 `2` 表示同一只股票连续两笔亏损后触发。

- `symbol_loss_cooldown_days`
  冷却自然日天数；例如 `20` 表示触发后 20 个自然日内跳过该股的新买点。

- `breakout_enable_ma10_confirm_exit`
  仅对 `breakout_long` 生效的 MA10 确认卖出开关；不填时回退到 `enable_ma10_confirm_exit`

- `pullback_enable_ma10_confirm_exit`
  仅对 `pullback_bounce` 生效的 MA10 确认卖出开关；不填时回退到 `enable_ma10_confirm_exit`

- `breakout_ma10_confirm_days`
  仅对 `breakout_long` 生效的 MA10 确认天数；不填时回退到 `ma10_confirm_days`

- `pullback_ma10_confirm_days`
  仅对 `pullback_bounce` 生效的 MA10 确认天数；不填时回退到 `ma10_confirm_days`

- `pullback_enable_failure_exit`
  仅对 `pullback_bounce` 生效的回踩失败退出开关；默认关闭。触发逻辑是入场后早期跌回入场信号记录的箱体上沿下方。

- `pullback_failure_exit_days`
  回踩失败退出的观察窗口，单位为持有天数；例如 `1` 表示只处理入场后第一天的失败。

- `pullback_failure_confirm_days`
  回踩失败退出的确认天数；例如 `2` 表示需要连续两天收盘低于失败线。

- `pullback_failure_buffer_pct`
  回踩失败线相对箱体上沿的缓冲比例；`0.003` 表示箱体上沿下方 `0.3%`。

- `pullback_failure_max_profit_pct`
  仅当当前持仓收益不高于该阈值时才允许失败退出，避免有较多浮盈的回踩票被普通波动洗出。

- `max_breakout_extension_pct`
  突破后允许追高的最大延伸幅度

- `breakout_max_extension_pct`
  仅对 `breakout_long` 生效的最大追高延伸幅度；不填时回退到 `max_breakout_extension_pct`

- `rr_min`
  最低盈亏比要求

## 参数文件示例

```json
{
  "box_lookback_days": 30,
  "min_breakout_pct": 2.5,
  "min_volume_ratio": 1.5,
  "breakout_min_breakout_pct": 3.0,
  "breakout_min_volume_ratio": 1.9,
  "pullback_min_volume_ratio": 1.3,
  "breakout_min_box_touches": 3,
  "pullback_min_box_touches": 2,
  "breakout_max_extension_pct": 0.05,
  "breakout_take_profit_pct": 0.18,
  "pullback_take_profit_pct": 0.12,
  "breakout_max_holding_days": 12,
  "pullback_max_holding_days": 8,
  "breakout_enable_ma10_confirm_exit": true,
  "breakout_ma10_confirm_days": 2,
  "pullback_enable_ma10_confirm_exit": false,
  "stop_loss_pct": 0.05,
  "take_profit_pct": 0.12,
  "max_holding_days": 10,
  "min_turnover_rate": 1.0,
  "preferred_turnover_rate_low": 1.5,
  "preferred_turnover_rate_high": 8.0
}
```

## 当前推荐命令

```bash
python3 scripts/run_backtest.py \
  --stock-code 300502.SZ \
  --start-date 2020-01-01 \
  --end-date 2026-05-21 \
  --strategy a_share_box \
  --price-adjustment qfq \
  --trading-constraints daily_limits \
  --params-file data/backtests/params_turnover_loose.json
```


## 回测结果说明

### 单票结果 JSON

单票结果结构包含：

- `metrics`
  汇总绩效指标
- `open_position`
  回测结束时如果还有持仓，会输出当前未平仓头寸
- `trades`
  已完成交易明细
- `equity_curve`
  每日资金曲线
- `data_context`
  本次回测使用的数据口径和上下文

### metrics 字段

- `initial_cash`
  初始资金

- `final_equity`
  回测结束时总权益，包含现金和未平仓持仓市值

- `total_return_pct`
  总收益率

- `max_drawdown_pct`
  最大回撤

- `trade_count`
  已完成交易笔数

- `win_rate_pct`
  胜率

- `avg_win_pct`
  平均盈利单收益率

- `avg_loss_pct`
  平均亏损单收益率

- `profit_factor`
  盈利因子

- `has_open_position`
  回测结束时是否仍有持仓

- `open_position_market_value`
  回测结束时未平仓持仓的市值

- `final_unrealized_pnl`
  回测结束时未平仓持仓的浮盈/浮亏金额

- `final_unrealized_pnl_pct`
  回测结束时未平仓持仓的浮盈/浮亏比例

- `max_trade_mfe_pct`
  所有已完成交易中，单笔出现过的最大有利波动百分比

- `max_trade_mae_pct`
  所有已完成交易中，单笔出现过的最大不利波动百分比

### open_position 字段

如果回测结束时仍持仓，会输出：

- `stock_code`
- `entry_date`
- `entry_price`
- `shares`
- `highest_price_seen`
- `lowest_price_seen`
- `entry_signal_reason`
- `entry_signal_score`

其中：

- `highest_price_seen`
  持仓期间见过的最高价

- `lowest_price_seen`
  持仓期间见过的最低价

- `entry_signal_reason`
  当前持仓最初是由哪类信号触发，例如 `breakout_long` 或 `pullback_bounce`

- `entry_signal_score`
  入场信号当时的评分，便于后续按信号质量统计

### trades 字段

每笔已完成交易会输出：

- `entry_date`
- `exit_date`
- `entry_price`
- `exit_price`
- `shares`
- `gross_pnl`
- `net_pnl`
- `return_pct`
- `holding_days`
- `entry_signal_reason`
- `entry_signal_score`
- `exit_reason`
- `highest_price_seen`
- `lowest_price_seen`
- `max_favorable_excursion_pct`
- `max_adverse_excursion_pct`

其中：

- `max_favorable_excursion_pct`
  单笔交易持仓期间，价格相对开仓成本曾达到过的最大盈利空间

- `max_adverse_excursion_pct`
  单笔交易持仓期间，价格相对开仓成本曾达到过的最大回撤空间

- `entry_signal_reason`
  该笔交易最初的入场信号类型，可直接用于区分 `breakout_long` 和 `pullback_bounce`

- `entry_signal_score`
  该笔交易开仓时的信号评分，可用于后续统计“高分信号是否更赚钱”

### 批量 summary.json

批量回测的 `summary.json` 顶层除了 `results` 外，还会输出 `aggregate` 汇总：

- `total_symbols`
  总股票数

- `ok_symbols`
  成功回测股票数

- `error_symbols`
  失败股票数

- `profitable_symbols`
  总收益为正的股票数

- `losing_symbols`
  总收益为负的股票数

- `flat_symbols`
  总收益为 0 的股票数

- `total_initial_cash`
  所有成功回测股票的初始资金总和

- `total_final_equity`
  所有成功回测股票的结束总权益

- `total_pnl`
  所有成功回测股票的总盈亏金额

- `aggregate_return_pct`
  按总资金口径计算的整体收益率

- `average_return_pct`
  各股票收益率的平均值

- `total_trade_count`
  所有成功回测股票的总交易笔数

- `total_final_unrealized_pnl`
  所有成功回测股票在回测结束时的总浮盈/浮亏

- `open_position_symbols`
  回测结束时仍有持仓的股票数

### 常用参数含义

- `breakout_lookback_days`
  突破判断的回顾周期（日K）

- `min_breakout_pct`
  最小突破幅度（%），收盘价需高于箱体上沿至少此比例

- `min_volume_ratio`
  最小成交量比率，突破日成交量需为过去 20 日均量的倍数

- `max_bias_ma10_pct`
  最大乖离率限制，股价偏离 10 日均线的上限（%）

- `stop_loss_pct`
  固定止损幅度，使用小数表示，例如 `0.03 = 3%`

- `take_profit_pct`
  固定止盈幅度，使用小数表示，例如 `0.12 = 12%`

- `max_holding_days`
  最大持仓天数，超过则强制平仓

- `position_size_pct`
  单次开仓占用资金比例，使用小数表示，例如 `1.0 = 100%`

- `box_lookback_days`
  箱体识别回顾窗口（日K）

- `min_box_height_pct`
  箱体最小高度比例，使用小数表示，例如 `0.025 = 2.5%`

- `breakout_max_box_height_pct`
  仅对 `breakout_long` 生效的最大箱体高度百分比；`0` 或不填表示关闭

- `breakout_avoid_box_height_low_pct`
  仅对 `breakout_long` 生效的避开箱体高度区间下沿；需和 `breakout_avoid_box_height_high_pct` 一起使用

- `breakout_avoid_box_height_high_pct`
  仅对 `breakout_long` 生效的避开箱体高度区间上沿；例如 `12` 和 `20` 表示避开 `(12%, 20%]`

- `pullback_min_box_height_pct`
  仅对 `pullback_bounce` 生效的最小箱体高度百分比；`0` 或不填表示关闭

- `box_tolerance_pct`
  箱体高低点的容忍误差，使用小数表示

- `min_box_touches`
  箱体边界至少被触及的次数

- `breakout_retest_window`
  突破后的回踩确认窗口（日）

- `pullback_reclaim_pct`
  回调收复幅度，使用小数表示，用于确认有效突破

- `stop_buffer_pct`
  止损缓冲，使用小数表示，止损价约为箱体下沿减去缓冲

- `rr_min`
  最小盈亏比要求，不符合则不交易

- `max_breakout_extension_pct`
  最大突破延伸幅度（%），超此幅度追高风险过大

- `require_uptrend_for_entry`
  是否要求日线处于上升趋势才可入场（布尔值）

- `signal_number_lookback_days`
  信号质量评估回顾天数

- `signal_number_event_cooldown_days`
  信号事件冷却期（同一股票 N 日内只产生一次信号）

- `min_turnover_rate`
  最小换手率（%），低于此值的股票忽略

- `preferred_turnover_rate_low`
  偏好的换手率下限（%）

- `preferred_turnover_rate_high`
  偏好的换手率上限（%）

## P3 真实资金账户级回测

`scripts/run_real_capital_backtest.py` 会从已导入 DuckDB 的单票回测交易中重新做 P2.5 排序，然后用同一个账户现金池执行：

- 多信号按 entry date 竞争资金
- 单票仓位按账户权益比例计算
- 按整手买入
- 限制最大同时持仓数
- 使用 `stock_daily_raw` 日线收盘价生成组合权益曲线和回撤
- 输出账户交易、跳过信号、年度/月度收益和权益曲线
- 输出 `account_diagnostics.json`，记录持仓估值是否使用入场价兜底；一旦触发，summary 会带 warning，提示权益曲线/回撤可能过于平滑

主线 P3 命令：

```bash
rtk uv run --extra dev python scripts/run_real_capital_backtest.py \
  --db-run-id bt_4008f88677a1 \
  --rank-mode signal_score \
  --max-per-day 3 \
  --pullback-quota 2 \
  --breakout-quota 1 \
  --ranking-max-open-positions 8 \
  --initial-cash 1000000 \
  --position-size-pct 0.08 \
  --account-max-positions 8 \
  --price-adjustment qfq \
  --output-dir data/backtests/diagnostics/p3_real_capital_bt_4008f88677a1_pos08_cap8
```

2026-05-29 首轮结果：

| 仓位/上限 | 总收益 | 最大回撤 | PF | 胜率 | 交易数 | 最长连亏 | 平均/最高暴露 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `5% / 8仓` | 16.6353% | 9.7780% | 1.2346 | 40.7666% | 574 | 11 | 10.3166% / 40.0415% |
| `8% / 8仓` | 30.7175% | 15.4847% | 1.2530 | 40.9012% | 577 | 11 | 16.9506% / 63.9657% |
| `10% / 8仓` | 38.6397% | 19.3838% | 1.2477 | 40.9012% | 577 | 11 | 21.3048% / 80.1718% |
| `12.5% / 8仓` | 50.4366% | 24.2480% | 1.2477 | 40.9012% | 577 | 11 | 26.8407% / 99.8208% |
| `10% / 4仓` | 25.8429% | 16.2531% | 1.2445 | 40.0966% | 414 | 13 | 15.4506% / 43.1490% |
| `10% / 6仓` | 24.1263% | 17.8824% | 1.1812 | 40.1942% | 515 | 16 | 19.0304% / 62.0792% |

当前建议先把 `8% / 8仓` 作为 P3 默认观察口径：收益/回撤比比 `10% / 8仓` 更温和，且没有 `4仓/6仓` 的重新排序损耗。

## P3 稳健性诊断

`scripts/run_backtest_robustness.py` 把 P3 从“看单次账户收益”升级成三类稳健性检查：

- walk-forward：按年/季/月把已选信号切片，每个窗口重置账户资金，观察收益、回撤、PF、胜率是否集中依赖某一段行情
- 参数敏感性：围绕基准配置做单轴扰动，默认检查仓位比例、账户最大持仓、每日入场数量
- Monte Carlo：对账户权益的日收益做 block bootstrap，估计随机路径下的亏损概率和回撤分布

主线稳健性命令：

```bash
rtk uv run --extra dev python scripts/run_backtest_robustness.py \
  --db-run-id bt_4008f88677a1 \
  --rank-mode signal_score \
  --max-per-day 3 \
  --pullback-quota 2 \
  --breakout-quota 1 \
  --ranking-max-open-positions 8 \
  --initial-cash 1000000 \
  --position-size-pct 0.08 \
  --account-max-positions 8 \
  --price-adjustment qfq \
  --compare-max-per-day 4 \
  --output-dir data/backtests/diagnostics/p3_robustness_bt_4008f88677a1_pos08_cap8
```

输出文件：

- `robustness_summary.json`：总入口，包含 baseline、walk-forward、敏感性、Monte Carlo 摘要
- `walk_forward.csv`：分窗口账户级结果
- `parameter_sensitivity.csv`：单轴参数扰动结果
- `monte_carlo_summary.json` / `monte_carlo_paths.csv`：随机路径分布
- `baseline_ranked_candidates.csv`：基准排序候选
- `profile_comparison.csv` / `profile_walk_forward.csv` / `profile_monte_carlo.csv`：显式 profile 对照
- `profile_incremental_trades.csv`：候选 profile 相对 baseline 的新增/删除交易
- `market_regime_daily.csv`：基于本地股票池等权广度的逐日市场环境标签；默认使用入场日前一交易日数据，避免偷看入场日
- `market_regime_profile_summary.csv` / `market_regime_trades.csv`：不同 profile 在不同市场环境下的表现与交易明细

2026-05-29 烟测观察：

- baseline 仍为 `30.7175%` 总收益、`15.4847%` 最大回撤、`40.9012%` 胜率、`PF=1.2530`
- walk-forward 中 2022 明显失效：`-12.69%` 收益、`12.8856%` 回撤、`PF=0.3687`
- 默认单轴敏感性里，`max_per_day=4,pullback=3,breakout=1` 临时更优：`33.37%` 收益、`14.3748%` 回撤；`max_per_day=2` 明显变差
- Monte Carlo 1000 次、5 日 block：收益中位数 `29.8835%`，5 分位收益 `-0.96%`，亏损概率 `5.6%`，95 分位回撤 `19.5129%`

2026-05-29 profile 对照：

| profile | 收益 | 回撤 | 收益/回撤 | 胜率 | PF | MC 5分位收益 | MC 亏损概率 | MC 95分位回撤 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline `3/day, 2P+1B` | 30.7175% | 15.4847% | 1.9837 | 40.9012% | 1.2530 | -0.9600% | 5.6% | 19.5129% |
| candidate `4/day, 3P+1B` | 33.3700% | 14.3748% | 2.3214 | 40.7470% | 1.2628 | 0.1285% | 4.9% | 19.8534% |

候选结论：`4/day, 3P+1B` 只能作为观察候选，不能升主线。原因是胜率没有提高，且分年看 2022、2025、2026 变差；它的收益改善主要来自新增/替换交易组合，仍需要继续确认不是少数年份或少数大赚交易贡献。

P3.5 市场环境分层：

第一版 regime 不依赖外部指数，而是用当前回测股票池的本地日线计算等权广度：

- `breadth_ma20_pct` / `breadth_ma60_pct`：股票池内收盘价站上 MA20/MA60 的比例
- `avg_return_20d_pct` / `avg_return_60d_pct`：股票池内 20/60 日平均收益
- 默认 `lag_days=1`，即每笔交易按入场日前一交易日的环境打标签

主线样本按 regime 分层后：

| profile | regime | 交易数 | 收益 | 回撤 | 胜率 | PF | 原始平均收益 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | bear_pause | 71 | -5.3944% | 7.5204% | 29.5775% | 0.6116 | -0.8462% |
| baseline | bull_active | 168 | 16.9995% | 7.3779% | 45.2381% | 1.5299 | 1.4232% |
| baseline | range_neutral | 172 | 3.5164% | 7.6498% | 38.9535% | 1.0976 | 0.5037% |
| baseline | weak_defensive | 165 | 12.6574% | 5.7775% | 43.0303% | 1.3982 | 1.0970% |
| candidate `4/day, 3P+1B` | bear_pause | 71 | -4.4192% | 6.5672% | 29.5775% | 0.6837 | -0.6582% |
| candidate `4/day, 3P+1B` | bull_active | 170 | 18.3464% | 6.5212% | 45.2941% | 1.5810 | 1.4754% |
| candidate `4/day, 3P+1B` | range_neutral | 175 | 3.8327% | 8.0255% | 38.2857% | 1.1022 | 0.5294% |
| candidate `4/day, 3P+1B` | weak_defensive | 172 | 12.4119% | 5.4968% | 43.0233% | 1.3687 | 1.0448% |

初步解释：`bear_pause` 是当前策略最该防守的环境；`bull_active` 明显适合放开 pullback 名额；`range_neutral` 与 `weak_defensive` 不应简单加交易数，需要继续做更细的入场质量过滤。
