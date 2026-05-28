import type React from 'react';
import { Play, Save } from 'lucide-react';
import type {
  BacktestPreset,
  BacktestRunDetailResponse,
} from '../api/backtests';
import { Button } from './common';

export type ParamDraftValue = string | number | boolean | null;
export type ParamDraft = Record<string, ParamDraftValue>;

type ParamGroupKey =
  | 'range'
  | 'universe'
  | 'box'
  | 'entry'
  | 'volume'
  | 'momentum'
  | 'pullback'
  | 'failureExit'
  | 'risk'
  | 'costs'
  | 'other';

type ParamInputType = 'number' | 'boolean' | 'select' | 'text' | 'json';

interface ParamOption {
  label: string;
  value: string;
}

interface ParamMeta {
  label: string;
  help: string;
  unit?: string;
  group: ParamGroupKey;
  order: number;
  type?: ParamInputType;
  step?: number;
  options?: ParamOption[];
}

interface ParamField {
  path: string;
  key: string;
  normalizedKey: string;
  value: unknown;
  defaultValue: unknown;
  meta: ParamMeta;
}

interface BacktestParamEditorProps {
  detail: BacktestRunDetailResponse | null;
  preset: BacktestPreset | null;
  values: ParamDraft;
  onChange: (key: string, value: ParamDraftValue) => void;
  onExecute: () => void;
  onSave: () => void;
  executing: boolean;
  saving: boolean;
  actionMessage?: string | null;
}

const PARAM_GROUPS: Array<{ key: ParamGroupKey; title: string; desc: string }> = [
  { key: 'range', title: '回测范围', desc: '开始、结束与本次样本时间长度。' },
  { key: 'universe', title: '股票池 / 资金', desc: '股票池文件、股票代码、名称预览、资金和持仓约束。' },
  { key: 'box', title: '箱体结构', desc: '箱体周期、容忍度、触碰次数、箱体高度和抬升过滤。' },
  { key: 'entry', title: '入场 / 突破', desc: '突破幅度、实体强度、影线、趋势过滤和信号评分。' },
  { key: 'volume', title: '量价过滤', desc: '成交量、换手率、均线乖离和突破延伸限制。' },
  { key: 'momentum', title: '动能 / MACD', desc: 'MACD 动能状态、放量突破弱动能惩罚和回踩修复判断。' },
  { key: 'pullback', title: '回踩确认', desc: '回踩站回箱顶、分风格确认和回踩信号质量。' },
  { key: 'failureExit', title: '失败退出', desc: '回踩后快速跌回箱体时的保护退出。' },
  { key: 'risk', title: '持仓 / 风控', desc: '止损、止盈、持仓天数、移动止损和 MA10 确认。' },
  { key: 'costs', title: '费用 / 交易约束', desc: '复权方式、涨跌停约束、滑点、佣金和成本口径。' },
  { key: 'other', title: '其他参数', desc: '当前策略或导入文件里的补充字段。' },
];

const OPTION_PRICE_ADJUSTMENT: ParamOption[] = [
  { label: '前复权 qfq', value: 'qfq' },
  { label: '后复权 hfq', value: 'hfq' },
  { label: '不复权 none', value: 'none' },
];

const OPTION_TRADING_CONSTRAINTS: ParamOption[] = [
  { label: 'A股日内涨跌停约束', value: 'daily_limits' },
  { label: '不启用约束', value: 'none' },
];

const PARAM_META: Record<string, ParamMeta> = {
  start_date: {
    label: '回测开始日期',
    help: '回测样本的起始日期，格式 YYYY-MM-DD。',
    group: 'range',
    order: 1,
    type: 'text',
  },
  end_date: {
    label: '回测结束日期',
    help: '回测样本的结束日期，格式 YYYY-MM-DD。',
    group: 'range',
    order: 2,
    type: 'text',
  },
  pool_id: {
    label: '股票池 ID',
    help: '当前回测样本池的内部标识。',
    group: 'universe',
    order: 1,
    type: 'text',
  },
  name: {
    label: '策略/股票池名称',
    help: '用于保存预设和历史 run 展示。',
    group: 'universe',
    order: 2,
    type: 'text',
  },
  source_path: {
    label: '股票池文件',
    help: '执行回测时优先使用的股票池 JSON 路径，例如 data/backtests/stock-codes-2.json。',
    group: 'universe',
    order: 3,
    type: 'text',
  },
  stock_codes: {
    label: '股票代码过滤 / 覆盖',
    help: '可选。填写后会覆盖股票池文件，支持逗号、空格或换行分隔。',
    group: 'universe',
    order: 4,
    type: 'text',
  },
  total_symbols: {
    label: '样本股票数',
    help: '股票池中的总标的数量。',
    unit: '只',
    group: 'universe',
    order: 5,
    type: 'number',
    step: 1,
  },
  initial_cash: {
    label: '单票初始资金',
    help: '每只股票独立回测时的初始资金。',
    unit: '元',
    group: 'universe',
    order: 6,
    type: 'number',
    step: 1000,
  },
  total_initial_cash: {
    label: '组合初始资金',
    help: '组合权益曲线合并后的初始资金。',
    unit: '元',
    group: 'universe',
    order: 7,
    type: 'number',
    step: 10000,
  },
  position_pct: {
    label: '单票仓位比例',
    help: '每次开仓使用可用资金的比例。',
    unit: '小数',
    group: 'universe',
    order: 8,
    type: 'number',
    step: 0.05,
  },
  position_size_pct: {
    label: '策略仓位比例',
    help: '策略下单时使用资金的比例，1 表示满仓。',
    unit: '小数',
    group: 'universe',
    order: 9,
    type: 'number',
    step: 0.05,
  },
  max_positions: {
    label: '最大持仓数',
    help: '组合模式下允许同时持有的最大股票数。',
    unit: '只',
    group: 'universe',
    order: 10,
    type: 'number',
    step: 1,
  },
  box_lookback_days: {
    label: '箱体观察周期',
    help: '用最近多少个交易日识别箱体支撑和压力。',
    unit: '天',
    group: 'box',
    order: 10,
    type: 'number',
    step: 1,
  },
  box_tolerance_pct: {
    label: '箱体触碰容忍',
    help: '价格接近箱体边界时允许的误差，0.015 表示 1.5%。',
    unit: '小数',
    group: 'box',
    order: 11,
    type: 'number',
    step: 0.001,
  },
  min_box_touches: {
    label: '最低箱体触碰次数',
    help: '压力位/支撑位至少被验证的次数。',
    unit: '次',
    group: 'box',
    order: 12,
    type: 'number',
    step: 1,
  },
  breakout_min_box_touches: {
    label: '突破最低触碰次数',
    help: '突破信号要求箱体压力位至少被触碰的次数。',
    unit: '次',
    group: 'box',
    order: 13,
    type: 'number',
    step: 1,
  },
  pullback_min_box_touches: {
    label: '回踩最低触碰次数',
    help: '回踩信号要求箱体压力位至少被触碰的次数。',
    unit: '次',
    group: 'box',
    order: 14,
    type: 'number',
    step: 1,
  },
  pullback_slow_large_min_box_touches: {
    label: '慢速大票回踩触碰',
    help: 'slow_large 风格回踩信号的最低触碰次数。',
    unit: '次',
    group: 'box',
    order: 15,
    type: 'number',
    step: 1,
  },
  pullback_balanced_trend_min_box_touches: {
    label: '均衡趋势回踩触碰',
    help: 'balanced_trend 风格回踩信号的最低触碰次数。',
    unit: '次',
    group: 'box',
    order: 16,
    type: 'number',
    step: 1,
  },
  pullback_high_beta_min_box_touches: {
    label: '高弹性回踩触碰',
    help: 'high_beta 风格回踩信号的最低触碰次数。',
    unit: '次',
    group: 'box',
    order: 17,
    type: 'number',
    step: 1,
  },
  min_box_height_pct: {
    label: '最低箱体高度',
    help: '过滤过窄箱体，0.05 表示箱体高度至少 5%。',
    unit: '小数',
    group: 'box',
    order: 18,
    type: 'number',
    step: 0.005,
  },
  breakout_max_box_height_pct: {
    label: '突破最高箱体高度',
    help: '突破模式允许的最高箱体高度，空值表示不限制。',
    unit: '小数',
    group: 'box',
    order: 19,
    type: 'number',
    step: 0.005,
  },
  breakout_avoid_box_height_low_pct: {
    label: '避开箱体高度下沿',
    help: '突破过滤的箱体高度禁入区间下沿。',
    unit: '小数',
    group: 'box',
    order: 20,
    type: 'number',
    step: 0.005,
  },
  breakout_avoid_box_height_high_pct: {
    label: '避开箱体高度上沿',
    help: '突破过滤的箱体高度禁入区间上沿。',
    unit: '小数',
    group: 'box',
    order: 21,
    type: 'number',
    step: 0.005,
  },
  pullback_min_box_height_pct: {
    label: '回踩最低箱体高度',
    help: '回踩模式要求箱体具备的最低高度。',
    unit: '小数',
    group: 'box',
    order: 22,
    type: 'number',
    step: 0.005,
  },
  breakout_min_stack_lift_pct: {
    label: '箱体抬升最低幅度',
    help: '新箱体相对前一箱体的最低抬升比例。',
    unit: '小数',
    group: 'box',
    order: 23,
    type: 'number',
    step: 0.005,
  },
  box_stack_lift_score_weight: {
    label: '箱体抬升评分权重',
    help: '箱体抬升对入场信号评分的贡献权重。',
    unit: '权重',
    group: 'box',
    order: 24,
    type: 'number',
    step: 0.1,
  },
  box_height_score_weight: {
    label: '箱体高度评分权重',
    help: '箱体高度对入场信号评分的贡献权重。',
    unit: '权重',
    group: 'box',
    order: 25,
    type: 'number',
    step: 0.1,
  },
  breakout_lookback_days: {
    label: '突破观察周期',
    help: '用于判断突破前高的回看窗口。',
    unit: '天',
    group: 'entry',
    order: 30,
    type: 'number',
    step: 1,
  },
  min_breakout_pct: {
    label: '最低突破幅度',
    help: '收盘突破前高/箱顶的最低幅度，单位为百分比点。',
    unit: '%',
    group: 'entry',
    order: 31,
    type: 'number',
    step: 0.1,
  },
  breakout_min_breakout_pct: {
    label: '突破模式最低幅度',
    help: '只作用于突破买点的最低突破幅度。',
    unit: '%',
    group: 'entry',
    order: 32,
    type: 'number',
    step: 0.1,
  },
  breakout_min_body_pct: {
    label: '突破实体最低涨幅',
    help: '突破日 K 线实体至少需要达到的涨幅。',
    unit: '%',
    group: 'entry',
    order: 33,
    type: 'number',
    step: 0.1,
  },
  breakout_min_close_above_resistance_pct: {
    label: '收盘站上箱顶幅度',
    help: '突破日收盘价高于箱体压力位的最小比例。',
    unit: '小数',
    group: 'entry',
    order: 34,
    type: 'number',
    step: 0.001,
  },
  breakout_max_upper_shadow_ratio: {
    label: '最大上影线比例',
    help: '突破日上影线相对实体/振幅的上限，避免冲高回落。',
    unit: '比例',
    group: 'entry',
    order: 35,
    type: 'number',
    step: 0.05,
  },
  require_uptrend_for_entry: {
    label: '要求上升趋势',
    help: '开启后只有趋势判定为上升时才允许开仓。',
    group: 'entry',
    order: 36,
    type: 'boolean',
  },
  block_breakout_after_downtrend: {
    label: '下跌趋势后禁突破',
    help: '下跌趋势后的首次突破不直接买入。',
    group: 'entry',
    order: 37,
    type: 'boolean',
  },
  signal_number_lookback_days: {
    label: '信号编号回看周期',
    help: '统计同一阶段第几次突破/回踩信号的回看窗口。',
    unit: '天',
    group: 'entry',
    order: 38,
    type: 'number',
    step: 1,
  },
  signal_number_event_cooldown_days: {
    label: '信号事件冷却',
    help: '避免短期重复信号被重复编号。',
    unit: '天',
    group: 'entry',
    order: 39,
    type: 'number',
    step: 1,
  },
  min_signal_score: {
    label: '最低信号评分',
    help: '通用入场评分门槛。',
    unit: '分',
    group: 'entry',
    order: 40,
    type: 'number',
    step: 1,
  },
  breakout_min_signal_score: {
    label: '突破最低评分',
    help: '突破买点必须达到的评分门槛。',
    unit: '分',
    group: 'entry',
    order: 41,
    type: 'number',
    step: 1,
  },
  pullback_min_signal_score: {
    label: '回踩最低评分',
    help: '回踩买点必须达到的评分门槛。',
    unit: '分',
    group: 'entry',
    order: 42,
    type: 'number',
    step: 1,
  },
  score_high_box_height_threshold_pct: {
    label: '箱体过高扣分阈值',
    help: '箱体高度超过该值时降低信号评分，0 表示关闭。',
    unit: '%',
    group: 'entry',
    order: 43,
    type: 'number',
    step: 1,
  },
  score_high_box_height_penalty: {
    label: '箱体过高扣分',
    help: '命中箱体过高阈值时扣除的评分。',
    unit: '分',
    group: 'entry',
    order: 44,
    type: 'number',
    step: 1,
  },
  score_high_turnover_rate_threshold: {
    label: '高换手扣分阈值',
    help: '换手率超过该值时降低信号评分，0 表示关闭。',
    unit: '%',
    group: 'entry',
    order: 45,
    type: 'number',
    step: 0.5,
  },
  score_high_turnover_rate_penalty: {
    label: '高换手扣分',
    help: '命中高换手阈值时扣除的评分。',
    unit: '分',
    group: 'entry',
    order: 46,
    type: 'number',
    step: 1,
  },
  score_high_volume_ratio_threshold: {
    label: '高量比扣分阈值',
    help: '量比超过该值时降低信号评分，0 表示关闭。',
    unit: '倍',
    group: 'entry',
    order: 47,
    type: 'number',
    step: 0.1,
  },
  score_high_volume_ratio_penalty: {
    label: '高量比扣分',
    help: '命中高量比阈值时扣除的评分。',
    unit: '分',
    group: 'entry',
    order: 48,
    type: 'number',
    step: 1,
  },
  enable_macd_score_adjustment: {
    label: '启用 MACD 评分调整',
    help: '开启后 MACD 只影响信号排序/评分，不改变箱体入场结构。',
    group: 'momentum',
    order: 1,
    type: 'boolean',
  },
  macd_bullish_bonus: {
    label: 'MACD 多头加分',
    help: 'DIF 高于 DEA、柱体为正且三日斜率不弱时增加的评分。',
    unit: '分',
    group: 'momentum',
    order: 2,
    type: 'number',
    step: 0.5,
  },
  macd_bearish_penalty: {
    label: 'MACD 空头扣分',
    help: 'DIF 不高于 DEA 且柱体为负时扣除的评分。',
    unit: '分',
    group: 'momentum',
    order: 3,
    type: 'number',
    step: 0.5,
  },
  breakout_high_volume_macd_weak_penalty: {
    label: '爆量弱动能扣分',
    help: '突破量比大于 4 且 MACD 缩柱/弱势时额外扣分。',
    unit: '分',
    group: 'momentum',
    order: 4,
    type: 'number',
    step: 0.5,
  },
  pullback_macd_weak_penalty: {
    label: '回踩弱动能扣分',
    help: '回踩确认时 MACD 未修复或继续转弱时扣除的评分。',
    unit: '分',
    group: 'momentum',
    order: 5,
    type: 'number',
    step: 0.5,
  },
  enable_macd_divergence_decision: {
    label: '启用 MACD 背驰决策',
    help: '开启后识别突破顶背驰和回踩底背驰，并将结果接入入场评分或阻断逻辑。',
    group: 'momentum',
    order: 6,
    type: 'boolean',
  },
  macd_divergence_lookback_days: {
    label: '背驰参考窗口',
    help: '寻找前高/前低和对应 MACD 参考点的回看天数。',
    unit: '天',
    group: 'momentum',
    order: 7,
    type: 'number',
    step: 1,
  },
  macd_divergence_price_tolerance_pct: {
    label: '背驰价格容差',
    help: '允许价格接近前高/前低时也识别为背驰。',
    unit: '比例',
    group: 'momentum',
    order: 8,
    type: 'number',
    step: 0.001,
  },
  breakout_macd_bearish_divergence_min_volume_ratio: {
    label: '突破背驰最低量比',
    help: '突破顶背驰需要同时满足的最低量比；设为 0 表示不限制。',
    unit: '倍',
    group: 'momentum',
    order: 9,
    type: 'number',
    step: 0.1,
  },
  breakout_macd_bearish_divergence_penalty: {
    label: '突破顶背驰扣分',
    help: '突破时价格接近或突破前高，但 MACD 柱体和 DIF 弱于前高时扣除的评分。',
    unit: '分',
    group: 'momentum',
    order: 10,
    type: 'number',
    step: 0.5,
  },
  breakout_block_macd_bearish_divergence: {
    label: '阻断突破顶背驰',
    help: '开启后，突破买点若出现 MACD 顶背驰会直接跳过。',
    group: 'momentum',
    order: 11,
    type: 'boolean',
  },
  pullback_macd_bullish_divergence_bonus: {
    label: '回踩底背驰加分',
    help: '回踩时价格接近或略破前低，但 MACD 柱体和 DIF 修复时增加的评分。',
    unit: '分',
    group: 'momentum',
    order: 12,
    type: 'number',
    step: 0.5,
  },
  enable_pullback_rebound_risk_control: {
    label: '启用高位回踩风控',
    help: '识别下跌修复期里短期涨幅或 MA10 乖离过高的回踩信号。',
    group: 'momentum',
    order: 13,
    type: 'boolean',
  },
  pullback_rebound_recent_gain_days: {
    label: '高位回踩涨幅窗口',
    help: '统计回踩信号日前短期涨幅的交易日窗口。',
    unit: '天',
    group: 'momentum',
    order: 14,
    type: 'number',
    step: 1,
  },
  pullback_rebound_max_recent_gain_pct: {
    label: '高位回踩涨幅阈值',
    help: '修复期内短期涨幅超过该值时，视为高位反弹型回踩。',
    unit: '%',
    group: 'momentum',
    order: 15,
    type: 'number',
    step: 0.5,
  },
  pullback_rebound_max_bias_ma10_pct: {
    label: '高位回踩 MA10 乖离阈值',
    help: '修复期内 MA10 正乖离超过该值时，视为追高风险。',
    unit: '%',
    group: 'momentum',
    order: 16,
    type: 'number',
    step: 0.5,
  },
  pullback_rebound_score_penalty: {
    label: '高位回踩扣分',
    help: '命中高位回踩风险时扣除的评分。',
    unit: '分',
    group: 'momentum',
    order: 17,
    type: 'number',
    step: 0.5,
  },
  pullback_rebound_block_entry: {
    label: '阻断高位回踩',
    help: '开启后，命中高位回踩风险的 pullback 信号会被延迟/跳过。',
    group: 'momentum',
    order: 18,
    type: 'boolean',
  },
  enable_pullback_profit_power_filter: {
    label: '启用弹性豁免',
    help: '开启后，只有缺少历史盈利弹性的高位回踩才会被阻断，强弹性个股会被放行或轻扣分。',
    group: 'momentum',
    order: 19,
    type: 'boolean',
  },
  pullback_profit_power_lookback_days: {
    label: '弹性统计窗口',
    help: '统计个股历史振幅和滚动涨幅的交易日窗口。',
    unit: '天',
    group: 'momentum',
    order: 20,
    type: 'number',
    step: 1,
  },
  pullback_profit_power_min_range_pct: {
    label: '强弹性振幅阈值',
    help: '信号日前窗口内最高价相对最低价的涨幅达到该值时，视为具备强盈利弹性。',
    unit: '%',
    group: 'momentum',
    order: 21,
    type: 'number',
    step: 1,
  },
  pullback_profit_power_rolling_gain_days: {
    label: '滚动涨幅窗口',
    help: '统计历史滚动涨幅所用的交易日跨度。',
    unit: '天',
    group: 'momentum',
    order: 22,
    type: 'number',
    step: 1,
  },
  pullback_profit_power_min_rolling_gain_pct: {
    label: '强弹性滚动涨幅阈值',
    help: '历史滚动涨幅达到该值时，也视为具备强盈利弹性；填 0 等于关闭这一项。',
    unit: '%',
    group: 'momentum',
    order: 23,
    type: 'number',
    step: 1,
  },
  pullback_rebound_profit_power_penalty_multiplier: {
    label: '弹性豁免扣分倍率',
    help: '强弹性个股命中高位回踩风险时，按该倍率保留原扣分；0 表示不扣分。',
    unit: '倍',
    group: 'momentum',
    order: 26,
    type: 'number',
    step: 0.1,
  },
  pullback_profit_power_max_recent_gain_pct: {
    label: '弹性豁免涨幅上限',
    help: '强弹性个股若短期涨幅超过该值，仍然不豁免高位回踩阻断；填 0 等于关闭上限。',
    unit: '%',
    group: 'momentum',
    order: 24,
    type: 'number',
    step: 0.5,
  },
  pullback_profit_power_max_ma10_bias_pct: {
    label: '弹性豁免 MA10 乖离上限',
    help: '强弹性个股若 MA10 正乖离超过该值，仍然不豁免高位回踩阻断；填 0 等于关闭上限。',
    unit: '%',
    group: 'momentum',
    order: 25,
    type: 'number',
    step: 0.5,
  },
  enable_breakout_trend_hold_extension: {
    label: '启用突破趋势延长',
    help: '突破持仓在 MACD 强势且收盘站上 MA10 时，跳过固定止盈和最大持仓天数。',
    group: 'risk',
    order: 119,
    type: 'boolean',
  },
  breakout_trend_hold_extension_max_days: {
    label: '突破延长最长持仓',
    help: '突破趋势延长最多允许持有的自然天数。',
    unit: '天',
    group: 'risk',
    order: 120,
    type: 'number',
    step: 1,
  },
  min_volume_ratio: {
    label: '最低量比',
    help: '入场当天成交量相对均量的最低倍数。',
    unit: '倍',
    group: 'volume',
    order: 50,
    type: 'number',
    step: 0.1,
  },
  breakout_min_volume_ratio: {
    label: '突破最低量比',
    help: '突破买点要求的最低放量倍数。',
    unit: '倍',
    group: 'volume',
    order: 51,
    type: 'number',
    step: 0.1,
  },
  pullback_min_volume_ratio: {
    label: '回踩最低量比',
    help: '回踩确认时要求的最低量比。',
    unit: '倍',
    group: 'volume',
    order: 52,
    type: 'number',
    step: 0.1,
  },
  min_turnover_rate: {
    label: '最低换手率',
    help: '过滤流动性不足的股票。',
    unit: '%',
    group: 'volume',
    order: 53,
    type: 'number',
    step: 0.1,
  },
  preferred_turnover_rate_low: {
    label: '偏好换手下沿',
    help: '评分偏好的换手率区间下沿。',
    unit: '%',
    group: 'volume',
    order: 54,
    type: 'number',
    step: 0.1,
  },
  preferred_turnover_rate_high: {
    label: '偏好换手上沿',
    help: '评分偏好的换手率区间上沿。',
    unit: '%',
    group: 'volume',
    order: 55,
    type: 'number',
    step: 0.1,
  },
  max_turnover_rate: {
    label: '最高换手率',
    help: '换手率超过该值时直接跳过入场，0 表示不限制。',
    unit: '%',
    group: 'volume',
    order: 56,
    type: 'number',
    step: 0.5,
  },
  max_bias_ma10_pct: {
    label: '最大 MA10 乖离',
    help: '入场价相对 MA10 的最大乖离限制，0 表示不限制。',
    unit: '小数',
    group: 'volume',
    order: 57,
    type: 'number',
    step: 0.005,
  },
  breakout_max_bias_ma10_pct: {
    label: '突破最大 MA10 乖离',
    help: '突破买点相对 MA10 的最大乖离限制。',
    unit: '小数',
    group: 'volume',
    order: 58,
    type: 'number',
    step: 0.005,
  },
  pullback_max_bias_ma10_pct: {
    label: '回踩最大 MA10 乖离',
    help: '回踩买点相对 MA10 的最大乖离限制。',
    unit: '小数',
    group: 'volume',
    order: 59,
    type: 'number',
    step: 0.005,
  },
  max_breakout_extension_pct: {
    label: '最大突破延伸',
    help: '避免突破当天离箱顶过远后追高。',
    unit: '小数',
    group: 'volume',
    order: 59,
    type: 'number',
    step: 0.005,
  },
  breakout_max_extension_pct: {
    label: '突破模式最大延伸',
    help: '只作用于突破模式的追高过滤上限。',
    unit: '小数',
    group: 'volume',
    order: 60,
    type: 'number',
    step: 0.005,
  },
  breakout_retest_window: {
    label: '突破后回踩窗口',
    help: '突破后多少天内允许识别回踩确认。',
    unit: '天',
    group: 'pullback',
    order: 70,
    type: 'number',
    step: 1,
  },
  pullback_reclaim_pct: {
    label: '回踩站回箱顶幅度',
    help: '回踩后收盘重新站上箱顶的确认幅度。',
    unit: '小数',
    group: 'pullback',
    order: 71,
    type: 'number',
    step: 0.001,
  },
  pullback_max_break_below_resistance_pct: {
    label: '回踩跌破箱顶上限',
    help: '回踩最低价相对箱体上沿的最大跌破幅度，0 表示不限制。',
    unit: '小数',
    group: 'pullback',
    order: 72,
    type: 'number',
    step: 0.005,
  },
  pullback_slow_large_reclaim_pct: {
    label: '慢速大票站回幅度',
    help: 'slow_large 风格回踩站回箱顶的确认幅度。',
    unit: '小数',
    group: 'pullback',
    order: 73,
    type: 'number',
    step: 0.001,
  },
  pullback_balanced_trend_reclaim_pct: {
    label: '均衡趋势站回幅度',
    help: 'balanced_trend 风格回踩站回箱顶的确认幅度。',
    unit: '小数',
    group: 'pullback',
    order: 74,
    type: 'number',
    step: 0.001,
  },
  pullback_high_beta_reclaim_pct: {
    label: '高弹性站回幅度',
    help: 'high_beta 风格回踩站回箱顶的确认幅度。',
    unit: '小数',
    group: 'pullback',
    order: 75,
    type: 'number',
    step: 0.001,
  },
  pullback_enable_failure_exit: {
    label: '启用回踩失败退出',
    help: '回踩买入后快速跌回箱体则触发保护退出。',
    group: 'failureExit',
    order: 80,
    type: 'boolean',
  },
  pullback_failure_exit_days: {
    label: '失败退出观察期',
    help: '回踩买入后前多少天内检查失败信号。',
    unit: '天',
    group: 'failureExit',
    order: 81,
    type: 'number',
    step: 1,
  },
  pullback_failure_confirm_days: {
    label: '失败确认天数',
    help: '连续多少天收盘跌破失败线才确认退出。',
    unit: '天',
    group: 'failureExit',
    order: 82,
    type: 'number',
    step: 1,
  },
  pullback_failure_buffer_pct: {
    label: '失败线缓冲',
    help: '箱顶下方的容忍缓冲，0.003 表示 0.3%。',
    unit: '小数',
    group: 'failureExit',
    order: 83,
    type: 'number',
    step: 0.001,
  },
  pullback_failure_max_profit_pct: {
    label: '失败退出最高盈利',
    help: '已有盈利超过该值时不再按回踩失败退出。',
    unit: '小数',
    group: 'failureExit',
    order: 84,
    type: 'number',
    step: 0.005,
  },
  stop_loss_pct: {
    label: '通用止损',
    help: '默认止损比例，0.04 表示 -4%。',
    unit: '小数',
    group: 'risk',
    order: 90,
    type: 'number',
    step: 0.005,
  },
  breakout_stop_loss_pct: {
    label: '突破止损',
    help: '突破买点专用止损比例，空值则使用通用止损。',
    unit: '小数',
    group: 'risk',
    order: 91,
    type: 'number',
    step: 0.005,
  },
  pullback_stop_loss_pct: {
    label: '回踩止损',
    help: '回踩买点专用止损比例，空值则使用通用止损。',
    unit: '小数',
    group: 'risk',
    order: 92,
    type: 'number',
    step: 0.005,
  },
  take_profit_pct: {
    label: '通用止盈',
    help: '默认止盈比例，0.16 表示 +16%。',
    unit: '小数',
    group: 'risk',
    order: 93,
    type: 'number',
    step: 0.005,
  },
  breakout_take_profit_pct: {
    label: '突破止盈',
    help: '突破买点专用止盈比例。',
    unit: '小数',
    group: 'risk',
    order: 94,
    type: 'number',
    step: 0.005,
  },
  pullback_take_profit_pct: {
    label: '回踩止盈',
    help: '回踩买点专用止盈比例。',
    unit: '小数',
    group: 'risk',
    order: 95,
    type: 'number',
    step: 0.005,
  },
  max_holding_days: {
    label: '通用最长持仓',
    help: '超过该天数后按时间止盈/止损退出。',
    unit: '天',
    group: 'risk',
    order: 96,
    type: 'number',
    step: 1,
  },
  breakout_max_holding_days: {
    label: '突破最长持仓',
    help: '突破买点专用最长持仓天数。',
    unit: '天',
    group: 'risk',
    order: 97,
    type: 'number',
    step: 1,
  },
  pullback_max_holding_days: {
    label: '回踩最长持仓',
    help: '回踩买点专用最长持仓天数。',
    unit: '天',
    group: 'risk',
    order: 98,
    type: 'number',
    step: 1,
  },
  stop_buffer_pct: {
    label: '止损缓冲',
    help: '箱体支撑下方的额外止损缓冲。',
    unit: '小数',
    group: 'risk',
    order: 99,
    type: 'number',
    step: 0.001,
  },
  rr_min: {
    label: '最低盈亏比',
    help: '候选交易至少需要满足的风险收益比。',
    unit: '倍',
    group: 'risk',
    order: 100,
    type: 'number',
    step: 0.1,
  },
  enable_entry_stall_exit: {
    label: '启用入场停滞退出',
    help: '买入后短期没有浮盈时提前退出。',
    group: 'risk',
    order: 101,
    type: 'boolean',
  },
  breakout_enable_entry_stall_exit: {
    label: '突破停滞退出',
    help: '突破买点是否启用入场停滞退出。',
    group: 'risk',
    order: 102,
    type: 'boolean',
  },
  pullback_enable_entry_stall_exit: {
    label: '回踩停滞退出',
    help: '回踩买点是否启用入场停滞退出。',
    group: 'risk',
    order: 103,
    type: 'boolean',
  },
  entry_stall_days: {
    label: '停滞观察天数',
    help: '买入后多少天内检查是否走弱。',
    unit: '天',
    group: 'risk',
    order: 104,
    type: 'number',
    step: 1,
  },
  breakout_entry_stall_days: {
    label: '突破停滞天数',
    help: '突破买点专用停滞观察天数。',
    unit: '天',
    group: 'risk',
    order: 105,
    type: 'number',
    step: 1,
  },
  pullback_entry_stall_days: {
    label: '回踩停滞天数',
    help: '回踩买点专用停滞观察天数。',
    unit: '天',
    group: 'risk',
    order: 106,
    type: 'number',
    step: 1,
  },
  entry_stall_min_return_pct: {
    label: '停滞最低收益',
    help: '观察期内未达到该收益则视为停滞。',
    unit: '小数',
    group: 'risk',
    order: 107,
    type: 'number',
    step: 0.005,
  },
  breakout_entry_stall_min_return_pct: {
    label: '突破停滞最低收益',
    help: '突破买点停滞退出的最低收益要求。',
    unit: '小数',
    group: 'risk',
    order: 108,
    type: 'number',
    step: 0.005,
  },
  pullback_entry_stall_min_return_pct: {
    label: '回踩停滞最低收益',
    help: '回踩买点停滞退出的最低收益要求。',
    unit: '小数',
    group: 'risk',
    order: 109,
    type: 'number',
    step: 0.005,
  },
  enable_symbol_loss_cooldown: {
    label: '启用单股亏损冷却',
    help: '同一只股票连续亏损达到阈值后，暂停该股一段时间的新买点。',
    group: 'risk',
    order: 110,
    type: 'boolean',
  },
  symbol_loss_cooldown_losses: {
    label: '冷却触发亏损次数',
    help: '同一只股票连续亏损多少笔后触发冷却。',
    unit: '笔',
    group: 'risk',
    order: 111,
    type: 'number',
    step: 1,
  },
  symbol_loss_cooldown_days: {
    label: '单股冷却天数',
    help: '触发后该股票暂停新开仓的自然日天数。',
    unit: '天',
    group: 'risk',
    order: 112,
    type: 'number',
    step: 1,
  },
  enable_breakeven_stop: {
    label: '启用保本止损',
    help: '浮盈达到阈值后，若回落到成本附近则提前离场。',
    group: 'risk',
    order: 113,
    type: 'boolean',
  },
  breakout_enable_breakeven_stop: {
    label: '突破保本止损',
    help: '突破买点是否启用保本止损；留空则使用通用设置。',
    group: 'risk',
    order: 114,
    type: 'boolean',
  },
  pullback_enable_breakeven_stop: {
    label: '回踩保本止损',
    help: '回踩买点是否启用保本止损；留空则使用通用设置。',
    group: 'risk',
    order: 115,
    type: 'boolean',
  },
  breakeven_activate_profit_pct: {
    label: '保本止损启动盈利',
    help: '浮盈达到该值后启动保本保护。',
    unit: '小数',
    group: 'risk',
    order: 116,
    type: 'number',
    step: 0.005,
  },
  breakeven_exit_threshold_pct: {
    label: '保本止损退出线',
    help: '启动后回落到成本价上方该比例以内时卖出。',
    unit: '小数',
    group: 'risk',
    order: 117,
    type: 'number',
    step: 0.005,
  },
  enable_trailing_stop: {
    label: '启用移动止损',
    help: '浮盈达到阈值后按回撤比例跟踪止损。',
    group: 'risk',
    order: 120,
    type: 'boolean',
  },
  breakout_enable_trailing_stop: {
    label: '突破移动止损',
    help: '突破买点是否启用移动止损。',
    group: 'risk',
    order: 121,
    type: 'boolean',
  },
  pullback_enable_trailing_stop: {
    label: '回踩移动止损',
    help: '回踩买点是否启用移动止损。',
    group: 'risk',
    order: 122,
    type: 'boolean',
  },
  trailing_stop_activate_profit_pct: {
    label: '移动止损启动盈利',
    help: '浮盈达到该值后启动移动止损。',
    unit: '小数',
    group: 'risk',
    order: 123,
    type: 'number',
    step: 0.005,
  },
  breakout_trailing_stop_activate_profit_pct: {
    label: '突破移动止损启动',
    help: '突破买点移动止损的启动盈利。',
    unit: '小数',
    group: 'risk',
    order: 124,
    type: 'number',
    step: 0.005,
  },
  pullback_trailing_stop_activate_profit_pct: {
    label: '回踩移动止损启动',
    help: '回踩买点移动止损的启动盈利。',
    unit: '小数',
    group: 'risk',
    order: 125,
    type: 'number',
    step: 0.005,
  },
  trailing_stop_drawdown_pct: {
    label: '移动止损回撤',
    help: '启动后从最高价回撤多少触发卖出。',
    unit: '小数',
    group: 'risk',
    order: 126,
    type: 'number',
    step: 0.005,
  },
  breakout_trailing_stop_drawdown_pct: {
    label: '突破移动止损回撤',
    help: '突破买点移动止损允许的回撤比例。',
    unit: '小数',
    group: 'risk',
    order: 127,
    type: 'number',
    step: 0.005,
  },
  pullback_trailing_stop_drawdown_pct: {
    label: '回踩移动止损回撤',
    help: '回踩买点移动止损允许的回撤比例。',
    unit: '小数',
    group: 'risk',
    order: 128,
    type: 'number',
    step: 0.005,
  },
  enable_ma10_confirm_exit: {
    label: '启用 MA10 确认退出',
    help: '跌破 MA10 后等待确认天数再退出。',
    group: 'risk',
    order: 140,
    type: 'boolean',
  },
  breakout_enable_ma10_confirm_exit: {
    label: '突破 MA10 退出',
    help: '突破买点是否启用 MA10 确认退出。',
    group: 'risk',
    order: 141,
    type: 'boolean',
  },
  pullback_enable_ma10_confirm_exit: {
    label: '回踩 MA10 退出',
    help: '回踩买点是否启用 MA10 确认退出。',
    group: 'risk',
    order: 142,
    type: 'boolean',
  },
  ma10_confirm_days: {
    label: 'MA10 确认天数',
    help: '连续多少天弱于 MA10 才确认退出。',
    unit: '天',
    group: 'risk',
    order: 143,
    type: 'number',
    step: 1,
  },
  breakout_ma10_confirm_days: {
    label: '突破 MA10 确认天数',
    help: '突破买点专用 MA10 退出确认天数。',
    unit: '天',
    group: 'risk',
    order: 144,
    type: 'number',
    step: 1,
  },
  pullback_ma10_confirm_days: {
    label: '回踩 MA10 确认天数',
    help: '回踩买点专用 MA10 退出确认天数。',
    unit: '天',
    group: 'risk',
    order: 145,
    type: 'number',
    step: 1,
  },
  price_adjustment: {
    label: '复权方式',
    help: '回测使用的价格复权口径。',
    group: 'costs',
    order: 200,
    type: 'select',
    options: OPTION_PRICE_ADJUSTMENT,
  },
  trading_constraints: {
    label: '交易约束',
    help: '是否按 A 股涨跌停、停牌等约束执行。',
    group: 'costs',
    order: 201,
    type: 'select',
    options: OPTION_TRADING_CONSTRAINTS,
  },
  commission_rate: {
    label: '佣金费率',
    help: '单边佣金费率，0.00025 表示 0.025%。',
    unit: '小数',
    group: 'costs',
    order: 202,
    type: 'number',
    step: 0.00005,
  },
  stamp_tax_rate: {
    label: '印花税率',
    help: '卖出时计提的印花税率。',
    unit: '小数',
    group: 'costs',
    order: 203,
    type: 'number',
    step: 0.0001,
  },
  slippage_rate: {
    label: '滑点比例',
    help: '成交价相对信号价的滑点估计。',
    unit: '小数',
    group: 'costs',
    order: 204,
    type: 'number',
    step: 0.0005,
  },
};

const TOKEN_LABELS: Record<string, string> = {
  avg: '平均',
  above: '站上',
  activate: '启动',
  after: '之后',
  avoid: '避开',
  balanced: '均衡',
  beta: '弹性',
  bias: '乖离',
  block: '阻断',
  body: '实体',
  box: '箱体',
  bearish: '空头',
  breakout: '突破',
  bullish: '多头',
  buffer: '缓冲',
  capital: '资金',
  close: '收盘',
  confirm: '确认',
  constraints: '约束',
  cooldown: '冷却',
  days: '天数',
  decision: '决策',
  divergence: '背驰',
  downtrend: '下跌趋势',
  drawdown: '回撤',
  enable: '启用',
  entry: '入场',
  equity: '权益',
  event: '事件',
  exit: '退出',
  extension: '延伸',
  failure: '失败',
  final: '最终',
  for: '',
  high: '高',
  height: '高度',
  holding: '持仓',
  large: '大票',
  lift: '抬升',
  lookback: '回看',
  loss: '亏损',
  low: '低',
  ma10: 'MA10',
  macd: 'MACD',
  max: '最大',
  min: '最低',
  number: '编号',
  pct: '比例',
  pnl: '盈亏',
  pool: '股票池',
  position: '仓位',
  preferred: '偏好',
  price: '价格',
  profit: '盈利',
  pullback: '回踩',
  rate: '费率',
  ratio: '比例',
  reclaim: '站回',
  require: '要求',
  resistance: '压力',
  retest: '回测确认',
  return: '收益',
  rr: '盈亏比',
  score: '评分',
  shadow: '影线',
  signal: '信号',
  size: '规模',
  slow: '慢速',
  source: '来源',
  stack: '叠箱',
  stall: '停滞',
  stop: '止损',
  strategy: '策略',
  symbols: '标的数',
  take: '止盈',
  tolerance: '容忍',
  total: '总计',
  touches: '触碰',
  trailing: '移动',
  trend: '趋势',
  turnover: '换手',
  uptrend: '上升趋势',
  upper: '上影线',
  volume: '成交量',
  weak: '弱动能',
  weight: '权重',
  window: '窗口',
};

const HIDDEN_COMPUTED_FIELDS = new Set([
  'aggregate_return_pct',
  'annualized_return_pct',
  'average_holding_days',
  'benchmark_return_pct',
  'calmar',
  'final_equity',
  'max_drawdown_pct',
  'profit_factor',
  'sharpe',
  'sortino',
  'total_final_equity',
  'total_pnl',
  'total_return_pct',
  'total_trade_count',
  'win_rate_pct',
]);

const HIDDEN_CONTEXT_PATHS = new Set([
  'stockPool.poolId',
  'stockPool.pool_id',
  'stockPool.name',
  'stockPool.totalSymbols',
  'stockPool.total_symbols',
  'stockPool.description',
  'stockPool.summary',
  'stockPool.membersPreview',
  'stockPool.members_preview',
]);

const MIGRATED_TREND_PARAM_KEYS = new Set([
  'breakout_lookback_days',
  'min_breakout_pct',
  'min_volume_ratio',
  'max_bias_ma10_pct',
  'stop_loss_pct',
  'take_profit_pct',
  'max_holding_days',
  'position_size_pct',
]);

const GENERIC_NON_BOX_PARAM_KEYS = new Set([
  ...MIGRATED_TREND_PARAM_KEYS,
  'min_turnover_rate',
  'require_uptrend_for_entry',
  'enable_ma10_confirm_exit',
  'ma10_confirm_days',
]);

const STOCK_SIGNAL_PARAM_KEYS = new Set([
  'breakout_lookback_days',
  'stop_loss_pct',
  'take_profit_pct',
  'max_holding_days',
  'position_size_pct',
]);

function strategyParamKeys(strategy?: string | null, category?: string | null): Set<string> | null {
  const normalizedStrategy = String(strategy ?? '').trim().toLowerCase();
  const normalizedCategory = String(category ?? '').trim().toLowerCase();
  if (normalizedStrategy === 'a_share_box' || normalizedCategory === 'box') return null;
  if (normalizedStrategy === 'a_share_migrated_crypto' || normalizedCategory === 'trend_breakout') {
    return MIGRATED_TREND_PARAM_KEYS;
  }
  if (normalizedStrategy.startsWith('stock_signal_') || normalizedCategory === 'single_stock_signal') {
    return STOCK_SIGNAL_PARAM_KEYS;
  }
  if (/(trend|pullback|breakout|holding)/.test(normalizedStrategy) && !normalizedStrategy.includes('box')) {
    return GENERIC_NON_BOX_PARAM_KEYS;
  }
  return null;
}

function strategyProfileLabel(strategy?: string | null, category?: string | null): string {
  const normalizedStrategy = String(strategy ?? '').trim().toLowerCase();
  const normalizedCategory = String(category ?? '').trim().toLowerCase();
  if (normalizedStrategy === 'a_share_box' || normalizedCategory === 'box') return '箱体突破/回踩参数';
  if (normalizedStrategy === 'a_share_migrated_crypto' || normalizedCategory === 'trend_breakout') return '趋势突破参数';
  if (normalizedStrategy.startsWith('stock_signal_') || normalizedCategory === 'single_stock_signal') return '单股信号参数';
  if (/(trend|pullback|breakout|holding)/.test(normalizedStrategy) && !normalizedStrategy.includes('box')) return '非箱体策略参数';
  return '完整参数';
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function toSnakeKey(key: string): string {
  return key
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .replace(/[-\s]+/g, '_')
    .toLowerCase();
}

function cloneRecord(value: unknown): Record<string, unknown> {
  return isRecord(value) ? JSON.parse(JSON.stringify(value)) as Record<string, unknown> : {};
}

function stringValue(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

function valueByAnyKey(payload: unknown, keys: string[]): unknown {
  if (!isRecord(payload)) return undefined;
  for (const key of keys) {
    if (payload[key] !== undefined && payload[key] !== null && payload[key] !== '') return payload[key];
  }
  return undefined;
}

function valueAtPath(payload: unknown, path: string): unknown {
  return path.split('.').reduce<unknown>((current, segment) => {
    if (!isRecord(current)) return undefined;
    return current[segment];
  }, payload);
}

function buildBasePayload(
  detail: BacktestRunDetailResponse | null,
  preset: BacktestPreset | null,
): Record<string, unknown> {
  const strategyCard = detail?.strategyCard;
  const presetParams = cloneRecord(preset?.params);
  const defaultParams = cloneRecord(preset?.defaultParams);
  const runParams = cloneRecord(strategyCard?.params);
  const importedVersion = preset?.importedVersions?.[0];
  return {
    range: {
      startDate: detail?.run.startDate ?? importedVersion?.startDate ?? '2024-01-01',
      endDate: detail?.run.endDate ?? importedVersion?.endDate ?? '2024-12-31',
    },
    stockPool: cloneRecord(strategyCard?.stockPool ?? preset?.stockPool),
    stockCodes: '',
    capital: cloneRecord(strategyCard?.capital ?? preset?.capital),
    constraints: cloneRecord(strategyCard?.constraints ?? preset?.constraints),
    config: cloneRecord(strategyCard?.config ?? preset?.config),
    params: {
      ...defaultParams,
      ...presetParams,
      ...runParams,
    },
  };
}

function deriveGroup(path: string, normalizedKey: string): ParamGroupKey {
  if (path.startsWith('range.')) return 'range';
  if (path.startsWith('stockPool.') || path.startsWith('capital.')) return 'universe';
  if (path.startsWith('constraints.') || path.startsWith('config.')) return 'costs';
  if (normalizedKey.includes('failure')) return 'failureExit';
  if (normalizedKey.includes('pullback') || normalizedKey.includes('retest') || normalizedKey.includes('reclaim')) return 'pullback';
  if (normalizedKey.includes('volume') || normalizedKey.includes('turnover') || normalizedKey.includes('bias') || normalizedKey.includes('extension')) return 'volume';
  if (normalizedKey.includes('box') || normalizedKey.includes('touches') || normalizedKey.includes('stack')) return 'box';
  if (
    normalizedKey.includes('stop')
    || normalizedKey.includes('profit')
    || normalizedKey.includes('holding')
    || normalizedKey.includes('trailing')
    || normalizedKey.includes('ma10')
    || normalizedKey.includes('stall')
    || normalizedKey === 'rr_min'
  ) return 'risk';
  if (normalizedKey.includes('breakout') || normalizedKey.includes('signal') || normalizedKey.includes('trend')) return 'entry';
  return 'other';
}

function inferInputType(value: unknown, meta?: ParamMeta): ParamInputType {
  if (meta?.type) return meta.type;
  if (typeof value === 'boolean') return 'boolean';
  if (typeof value === 'number' || value === null) return 'number';
  if (Array.isArray(value) || isRecord(value)) return 'json';
  return 'text';
}

function fallbackLabel(normalizedKey: string): string {
  return normalizedKey
    .split('_')
    .filter(Boolean)
    .map((token) => TOKEN_LABELS[token] ?? token)
    .join('');
}

function shouldIncludeField(path: string, key: string): boolean {
  const normalizedKey = toSnakeKey(key);
  if (HIDDEN_CONTEXT_PATHS.has(path)) return false;
  if (HIDDEN_COMPUTED_FIELDS.has(normalizedKey)) return false;
  if (path.startsWith('capital.') && normalizedKey.includes('pnl')) return false;
  if (path.startsWith('capital.') && normalizedKey.includes('equity') && normalizedKey !== 'initial_cash') return false;
  return true;
}

function visibleForStrategy(field: ParamField, strategy?: string | null, category?: string | null): boolean {
  if (!field.path.startsWith('params.')) return true;
  const visibleKeys = strategyParamKeys(strategy, category);
  if (!visibleKeys) return true;
  return visibleKeys.has(field.normalizedKey);
}

function metaForField(path: string, key: string, value: unknown): ParamMeta {
  const normalizedKey = toSnakeKey(key);
  const exact = PARAM_META[normalizedKey];
  if (exact) return exact;
  const group = deriveGroup(path, normalizedKey);
  return {
    label: fallbackLabel(normalizedKey) || '未命名参数',
    help: '导入数据中的扩展参数，后续可补充更精确的中文说明。',
    unit: typeof value === 'number' ? '数值' : undefined,
    group,
    order: 900,
    type: inferInputType(value),
  };
}

function collectFields(
  payload: Record<string, unknown>,
  defaults: Record<string, unknown>,
  pathPrefix = '',
): ParamField[] {
  const fields: ParamField[] = [];
  Object.entries(payload).forEach(([key, value]) => {
    const path = pathPrefix ? `${pathPrefix}.${key}` : key;
    if (!shouldIncludeField(path, key)) return;
    if (isRecord(value)) {
      fields.push(...collectFields(value, defaults, path));
      return;
    }
    const meta = metaForField(path, key, value);
    fields.push({
      path,
      key,
      normalizedKey: toSnakeKey(key),
      value,
      defaultValue: valueAtPath(defaults, path),
      meta: {
        ...meta,
        type: inferInputType(value, meta),
      },
    });
  });
  return fields;
}

function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '--';
  if (typeof value === 'boolean') return value ? '是' : '否';
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(6)));
  if (typeof value === 'string') return value;
  return JSON.stringify(value);
}

function fieldValue(field: ParamField, values: ParamDraft): ParamDraftValue {
  return Object.prototype.hasOwnProperty.call(values, field.path)
    ? values[field.path]
    : (field.value as ParamDraftValue);
}

function groupedFields(fields: ParamField[]): Record<ParamGroupKey, ParamField[]> {
  return fields.reduce<Record<ParamGroupKey, ParamField[]>>((acc, field) => {
    acc[field.meta.group].push(field);
    return acc;
  }, {
    range: [],
    universe: [],
    box: [],
    entry: [],
    volume: [],
    momentum: [],
    pullback: [],
    failureExit: [],
    risk: [],
    costs: [],
    other: [],
  });
}

function dateValueFromPath(payload: Record<string, unknown>, values: ParamDraft, path: string): string | null {
  const value = Object.prototype.hasOwnProperty.call(values, path) ? values[path] : valueAtPath(payload, path);
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed ? trimmed.slice(0, 10) : null;
}

function durationDays(startDate: string | null, endDate: string | null): number | null {
  if (!startDate || !endDate) return null;
  const start = new Date(`${startDate}T00:00:00`);
  const end = new Date(`${endDate}T00:00:00`);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return null;
  const diff = Math.round((end.getTime() - start.getTime()) / 86_400_000) + 1;
  return diff > 0 ? diff : null;
}

function rangeSummary(
  payload: Record<string, unknown>,
  values: ParamDraft,
  detail: BacktestRunDetailResponse | null,
): Array<{ label: string; value: string }> {
  const startDate = dateValueFromPath(payload, values, 'range.startDate') ?? dateValueFromPath(payload, values, 'range.start_date');
  const endDate = dateValueFromPath(payload, values, 'range.endDate') ?? dateValueFromPath(payload, values, 'range.end_date');
  const naturalDays = durationDays(startDate, endDate);
  const sampleDays = detail?.run.sampleDays;
  const durationText = [
    naturalDays != null ? `${naturalDays} 自然日` : null,
    typeof sampleDays === 'number' && Number.isFinite(sampleDays) ? `${sampleDays} 交易日` : null,
  ].filter(Boolean).join(' / ');
  return [
    { label: '开始日期', value: startDate ?? '未设置' },
    { label: '结束日期', value: endDate ?? '未设置' },
    { label: '时间长度', value: durationText || '填写开始和结束日期后自动计算' },
  ];
}

function stockPoolSummary(payload: Record<string, unknown>): Array<{ label: string; value: string }> {
  const stockPool = payload.stockPool;
  const path = stringValue(valueByAnyKey(stockPool, ['sourcePath', 'source_path']));
  const name = stringValue(valueByAnyKey(stockPool, ['name']));
  const poolId = stringValue(valueByAnyKey(stockPool, ['poolId', 'pool_id']));
  const totalSymbols = valueByAnyKey(stockPool, ['totalSymbols', 'total_symbols']);
  const namedSymbols = valueByAnyKey(stockPool, ['namedSymbols', 'named_symbols']);
  const description = stringValue(valueByAnyKey(stockPool, ['description', 'summary']));
  const preview = valueByAnyKey(stockPool, ['membersPreview', 'members_preview']);
  const previewItems = Array.isArray(preview)
    ? preview
      .filter(isRecord)
      .slice(0, 8)
      .map((item) => {
        const code = stringValue(valueByAnyKey(item, ['stockCode', 'stock_code']));
        const stockName = stringValue(valueByAnyKey(item, ['stockName', 'stock_name']));
        return code ? { code, stockName } : null;
      })
      .filter((item): item is { code: string; stockName: string | null } => Boolean(item))
    : [];
  const codePreviewText = previewItems.map((item) => item.code).join(' / ');
  const namePreviewText = previewItems
    .map((item) => item.stockName ? `${item.stockName} ${item.code}` : null)
    .filter(Boolean)
    .join(' / ');
  return [
    { label: '股票池名称', value: name ?? '未命名股票池' },
    { label: '股票池文件', value: path ?? '未绑定，执行时会尝试使用当前 run 的股票池成员' },
    {
      label: '股票代码预览',
      value: codePreviewText || '暂无代码预览；可在下方股票代码过滤中手动输入',
    },
    { label: '股票名称预览', value: namePreviewText || 'DB 暂无名称；后续导入带名称的股票池文件后会自动显示' },
    {
      label: '股票池元数据',
      value: description ?? `${totalSymbols ? `${totalSymbols} 只` : '数量未知'}${namedSymbols ? ` · 已有名称 ${namedSymbols} 个` : ''}${poolId ? ` · ${poolId}` : ''}`,
    },
  ];
}

const ParamControl: React.FC<{
  field: ParamField;
  value: ParamDraftValue;
  onChange: (value: ParamDraftValue) => void;
}> = ({ field, value, onChange }) => {
  const inputId = `backtest-param-${field.path.replace(/[^a-zA-Z0-9_-]/g, '-')}`;
  const type = field.meta.type ?? inferInputType(field.value, field.meta);
  if (type === 'boolean') {
    return (
      <label className="backtest-param-switch" htmlFor={inputId}>
        <input
          id={inputId}
          type="checkbox"
          checked={Boolean(value)}
          onChange={(event) => onChange(event.target.checked)}
        />
        <span className="track" />
        <span className="state">{value === true ? '开启' : '关闭'}</span>
      </label>
    );
  }
  if (type === 'select' && field.meta.options?.length) {
    return (
      <select
        id={inputId}
        className="backtest-param-input"
        value={value == null ? '' : String(value)}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">未设置</option>
        {field.meta.options.map((option) => (
          <option key={option.value} value={option.value}>{option.label}</option>
        ))}
      </select>
    );
  }
  if (type === 'json') {
    return (
      <textarea
        id={inputId}
        className="backtest-param-input backtest-param-textarea"
        value={value == null ? '' : typeof value === 'string' ? value : JSON.stringify(value, null, 2)}
        onChange={(event) => onChange(event.target.value)}
      />
    );
  }
  return (
    <input
      id={inputId}
      className="backtest-param-input"
      type={type === 'number' ? 'number' : 'text'}
      step={field.meta.step}
      value={value == null ? '' : String(value)}
      onChange={(event) => {
        if (type === 'number') {
          onChange(event.target.value === '' ? null : Number(event.target.value));
          return;
        }
        onChange(event.target.value);
      }}
    />
  );
};

export const BacktestParamEditor: React.FC<BacktestParamEditorProps> = ({
  detail,
  preset,
  values,
  onChange,
  onExecute,
  onSave,
  executing,
  saving,
  actionMessage,
}) => {
  const payload = buildBasePayload(detail, preset);
  const defaults = {
    stockPool: {},
    capital: {},
    constraints: cloneRecord(preset?.constraints),
    config: cloneRecord(preset?.config),
    params: cloneRecord(preset?.defaultParams ?? preset?.params),
  };
  const activeStrategy = preset?.strategy ?? detail?.run.strategy;
  const activeCategory = preset?.category;
  const profileLabel = strategyProfileLabel(activeStrategy, activeCategory);
  const fields = collectFields(payload, defaults)
    .filter((field) => visibleForStrategy(field, activeStrategy, activeCategory))
    .sort((left, right) => left.meta.order - right.meta.order || left.meta.label.localeCompare(right.meta.label, 'zh-CN'));
  const groups = groupedFields(fields);
  const poolSummary = stockPoolSummary(payload);
  const rangeItems = rangeSummary(payload, values, detail);
  const dirtyCount = Object.keys(values).length;

  return (
    <div className="backtest-param-workbench">
      <div className="backtest-param-actionbar">
        <div>
          <p className="backtest-param-action-title">参数工作台</p>
          <p className="backtest-param-action-desc">
            {profileLabel} · 已展开 {fields.length} 个参数，当前修改 {dirtyCount} 项。保存会写入策略预设，执行会提交回测任务并刷新 run 列表。
          </p>
        </div>
        <div className="backtest-param-actions">
          <Button type="button" variant="secondary" onClick={onSave} isLoading={saving} disabled={executing || fields.length === 0}>
            <Save className="h-4 w-4" />
            保存策略
          </Button>
          <Button type="button" variant="primary" onClick={onExecute} isLoading={executing} disabled={saving || fields.length === 0}>
            <Play className="h-4 w-4" />
            执行回测
          </Button>
        </div>
      </div>

      {actionMessage ? <div className="backtest-param-action-message">{actionMessage}</div> : null}

      <div className="backtest-param-grid">
        {PARAM_GROUPS.map((group) => {
          const groupFields = groups[group.key];
          return (
            <details key={group.key} className="backtest-param-section">
              <summary className="backtest-param-section-head">
                <div>
                  <h4 className="backtest-param-section-title">{group.title}</h4>
                  <p className="backtest-param-section-desc">{group.desc}</p>
                </div>
                <span className="backtest-param-section-meta">
                  <span className="backtest-param-section-count">{groupFields.length}</span>
                  <span className="backtest-param-section-chevron" aria-hidden="true" />
                </span>
              </summary>
              <div className="backtest-param-section-body">
                {group.key === 'range' ? (
                  <div className="backtest-range-summary">
                    {rangeItems.map((item) => (
                      <div key={item.label} className="backtest-range-summary-item">
                        <span className="label">{item.label}</span>
                        <span className="value">{item.value}</span>
                      </div>
                    ))}
                  </div>
                ) : null}
                {group.key === 'universe' ? (
                  <div className="backtest-stock-pool-summary">
                    {poolSummary.map((item) => (
                      <div key={item.label} className="backtest-stock-pool-summary-item">
                        <span className="label">{item.label}</span>
                        <span className="value">{item.value}</span>
                      </div>
                    ))}
                  </div>
                ) : null}
                {groupFields.length > 0 ? (
                  <div className="backtest-param-field-list">
                    {groupFields.map((field) => {
                      const currentValue = fieldValue(field, values);
                      return (
                        <div key={field.path} className="backtest-param-field">
                          <div className="backtest-param-label-block">
                            <label
                              className="backtest-param-label-main"
                              htmlFor={`backtest-param-${field.path.replace(/[^a-zA-Z0-9_-]/g, '-')}`}
                            >
                              {field.meta.label}
                            </label>
                            <span className="backtest-param-label-help">{field.meta.help}</span>
                            <span className="backtest-param-default">默认 {displayValue(field.defaultValue)}</span>
                          </div>
                          <div className="backtest-param-control">
                            <ParamControl field={field} value={currentValue} onChange={(value) => onChange(field.path, value)} />
                            {field.meta.unit ? <span className="backtest-param-unit">{field.meta.unit}</span> : null}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <p className="backtest-param-empty">当前策略没有该分组参数。</p>
                )}
              </div>
            </details>
          );
        })}
      </div>
    </div>
  );
};
