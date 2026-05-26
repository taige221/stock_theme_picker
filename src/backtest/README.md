## 回测命令

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
