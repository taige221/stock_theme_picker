import type React from 'react';
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  Clock3,
  Search,
  Sparkles,
  Target,
  TrendingUp,
} from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';
import { createParsedApiError, getParsedApiError, type ParsedApiError } from '../api/error';
import {
  stockQueryApi,
  type StockQueryAnalyzeResponse,
  type StockQueryBoardItem,
  type StockQueryFundamentalBlock,
  type StockQueryFundamentalContext,
  type StockQueryFundamentalDetails,
  type StockQueryHistoryItem,
  type StockQueryTaskStatus,
} from '../api/stockQuery';
import { watchlistApi, type StockAlertRuleItem, type StockWatchlistItem } from '../api/watchlist';
import {
  ApiErrorAlert,
  AppPage,
  Badge,
  Button,
  Drawer,
  EmptyState,
  InlineAlert,
  Input,
  PaperDataBlockCard,
  PaperHeroHeader,
  PaperListBlock,
  PaperMetricCard,
  PaperSectionCard,
  PaperSummaryBlock,
  Select,
} from '../components/common';
import { cn } from '../utils/cn';

const QUICK_QUERIES = [
  { label: '华丰科技', value: '688629.SH', note: '算力链中的高热度样本' },
  { label: '优博讯', value: '300531.SZ', note: '适合看异动与题材归因' },
  { label: '景旺电子', value: '603228.SH', note: '适合看趋势与支撑位' },
  { label: '证券ETF', value: '512880.SH', note: '适合验证 ETF 查询链路' },
] as const;

const FUNDAMENTAL_BLOCK_LABELS: Record<string, string> = {
  valuation: '估值',
  growth: '成长',
  earnings: '盈利',
  institution: '机构',
  capital_flow: '资金流',
  capitalFlow: '资金流',
  dragon_tiger: '龙虎榜',
  dragonTiger: '龙虎榜',
  boards: '所属板块',
};

const MIN_ALERT_SCAN_INTERVAL_MINUTES = 5;
const STRATEGY_OPTIONS = [
  { value: 'auto', label: '自动决策' },
  { value: 'pullback', label: '低吸回踩' },
  { value: 'breakout', label: '突破确认' },
  { value: 'trend_follow', label: '趋势跟随' },
  { value: 'holding', label: '趋势持有' },
] as const;

type StrategyTone = 'buy' | 'breakout' | 'warn';

type EntryPlan = {
  headline: string;
  summary: string;
  supportPrice: number | null;
  entryLower: number | null;
  entryUpper: number | null;
  breakoutPrice: number | null;
  noChasePrice: number | null;
  stopLossPrice: number | null;
  strategies: Array<{
    key: string;
    title: string;
    description: string;
    tone: StrategyTone;
  }>;
  checklist: string[];
};

type HistoryComparison = {
  headline: string;
  description: string;
  secondary: string;
};

type PriceRailModel = {
  points: Array<{
    key: string;
    label: string;
    value: number;
    position: number;
    tone: StrategyTone | 'neutral';
  }>;
  entryStart: number;
  entryEnd: number;
  noChaseStart: number;
};

type SignalOverview = {
  score: number;
  label: string;
  description: string;
};

function isFiniteNumber(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function firstNumber(...values: Array<number | null | undefined>): number | null {
  for (const value of values) {
    if (isFiniteNumber(value)) {
      return value;
    }
  }
  return null;
}

function formatNumber(value?: number | null, digits = 2): string {
  if (!isFiniteNumber(value)) return '--';
  return value.toFixed(digits);
}

function formatPercent(value?: number | null, digits = 1): string {
  if (!isFiniteNumber(value)) return '--';
  return `${value.toFixed(digits)}%`;
}

function formatMoney(value?: number | null): string {
  if (!isFiniteNumber(value)) return '--';
  const abs = Math.abs(value);
  if (abs >= 100000000) return `${(value / 100000000).toFixed(2)}亿`;
  if (abs >= 10000) return `${(value / 10000).toFixed(2)}万`;
  return value.toFixed(0);
}

function formatRange(lower?: number | null, upper?: number | null): string {
  if (isFiniteNumber(lower) && isFiniteNumber(upper)) {
    return `${formatNumber(lower)} - ${formatNumber(upper)}`;
  }
  if (isFiniteNumber(lower)) return formatNumber(lower);
  if (isFiniteNumber(upper)) return formatNumber(upper);
  return '--';
}

function formatHistoryTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date);
}

function signalBadgeVariant(signal: string): 'success' | 'info' | 'warning' | 'danger' | 'default' {
  if (signal === '短线异动') return 'danger';
  if (signal === '趋势跟随') return 'success';
  if (signal === '持有候选') return 'warning';
  if (signal === '低吸观察') return 'info';
  if (signal === '不宜追高' || signal === '仅观察') return 'default';
  return 'success';
}

function strategySignalTone(signal: string): StrategyTone {
  if (signal === '短线异动') return 'breakout';
  if (signal === '不宜追高' || signal === '仅观察') return 'warn';
  return 'buy';
}

function confidenceLabel(value: string): string {
  if (value === 'high') return '高置信';
  if (value === 'medium') return '中置信';
  if (value === 'low') return '低置信';
  return value || '待判定';
}

function relationTypeLabel(value: string): string {
  if (value === 'direct_stock_pool') return '股票池直连';
  if (value === 'concept_board_match') return '概念板块映射';
  if (value === 'manual_map') return '人工映射';
  if (value === 'rule_map') return '规则映射';
  return value || '待判定';
}

function instrumentBadgeLabel(instrumentLabel?: string | null, instrumentType?: string | null): string | null {
  if (instrumentLabel?.trim()) return instrumentLabel.trim();
  if (instrumentType === 'etf') return 'ETF';
  return null;
}

function sourceLabel(value?: string | null): string {
  if (!value) return '--';
  if (value === 'ok') return '聚合完成';
  if (value === 'full') return '聚合完成';
  if (value === 'partial') return '部分可用';
  if (value === 'failed') return '获取失败';
  if (value === 'not_supported') return '未启用';
  if (value === 'fundamental_pipeline') return '基本面聚合';
  if (value === 'tencent') return '腾讯实时';
  if (value === 'eastmoney') return '东方财富实时';
  return value;
}

function signedValueClass(value?: number | null): string {
  if (!isFiniteNumber(value)) return 'text-foreground';
  if (value > 0) return 'text-success';
  if (value < 0) return 'text-danger';
  return 'text-foreground';
}

function fundamentalBlockLabel(value: string): string {
  return FUNDAMENTAL_BLOCK_LABELS[value] ?? value ?? '未知';
}

function coverageStatusLabel(value: string): string {
  if (value === 'ok' || value === 'full') return '已获取';
  if (value === 'partial') return '部分可用';
  if (value === 'failed') return '未取到';
  if (value === 'not_supported') return '不支持';
  return value || '未知';
}

function coverageTone(value: string): string {
  if (value === 'ok' || value === 'full') return 'border-success/15 bg-success/10 text-foreground';
  if (value === 'partial') return 'border-warning/20 bg-warning/10 text-foreground';
  if (value === 'failed') return 'border-danger/15 bg-danger/10 text-foreground';
  if (value === 'not_supported') return 'border-border/60 bg-background/72 text-secondary-text';
  return 'border-border/60 bg-background/72 text-foreground';
}

function boardCaption(board: StockQueryBoardItem): string {
  const tags = [board.type, board.code].filter(Boolean);
  return tags.join(' · ');
}

function boardSourceLabel(source?: string, provider?: string): string {
  if (source === 'cache') return `缓存${provider ? ` · ${provider}` : ''}`;
  if (source === 'online') return `在线${provider ? ` · ${provider}` : ''}`;
  return provider || '--';
}

function supplementItems(value?: string[] | null, fallback?: string[] | null): string[] {
  const selected = (value?.length ? value : fallback) ?? [];
  return selected.filter((item): item is string => typeof item === 'string' && item.trim().length > 0).slice(0, 4);
}

function formatSourceProvider(value?: unknown): string {
  const text = typeof value === 'string' ? value.trim() : '';
  if (!text) return '';
  if (text === 'fundamental_pipeline') return '基本面聚合';
  if (text === 'realtime_quote') return '实时估值';
  if (text === 'text_supplement') return '文本补充';
  if (text === 'akshare') return 'AkShare';
  if (text === 'tencent') return '腾讯';
  if (text === 'sina') return '新浪';
  if (text === 'tushare') return 'Tushare';
  if (text === 'eastmoney') return '东方财富';
  if (text === 'cache') return '缓存';
  if (text === 'online') return '在线';
  return text;
}

function sourceChainSummary(sourceChain?: Array<Record<string, unknown>>): string {
  if (!Array.isArray(sourceChain) || sourceChain.length === 0) return '--';
  const labels: string[] = [];
  for (const item of sourceChain) {
    if (!item || typeof item !== 'object') continue;
    const provider = formatSourceProvider(item.provider);
    const result = typeof item.result === 'string' ? item.result.trim() : '';
    const durationMs = typeof item.durationMs === 'number' ? item.durationMs : undefined;
    const parts = [provider || undefined, result ? coverageStatusLabel(result) : undefined, typeof durationMs === 'number' ? `${durationMs}ms` : undefined]
      .filter(Boolean);
    const label = parts.join(' · ');
    if (label && !labels.includes(label)) {
      labels.push(label);
    }
  }
  return labels.length > 0 ? labels.slice(0, 3).join(' / ') : '--';
}

function hasFundamentalBlockData(block?: StockQueryFundamentalBlock<unknown> | null): boolean {
  if (!block || !block.data || typeof block.data !== 'object') return false;
  return Object.values(block.data as Record<string, unknown>).some((value) => {
    if (value === null || value === undefined) return false;
    if (Array.isArray(value)) return value.length > 0;
    if (typeof value === 'object') return Object.keys(value as Record<string, unknown>).length > 0;
    if (typeof value === 'string') return value.trim().length > 0;
    return true;
  });
}

function fallbackFundamentalBlock<T extends object>(
  data: T | undefined,
  status?: string,
): StockQueryFundamentalBlock<T> | undefined {
  if (!data && !status) return undefined;
  return {
    status: status ?? (data ? 'ok' : 'failed'),
    data,
    sourceChain: [],
    errors: [],
  };
}

function buildFallbackFundamentalContext(
  details?: StockQueryFundamentalDetails,
  coverage?: Record<string, string>,
  errors?: string[],
): StockQueryFundamentalContext | null {
  if (!details && !coverage && (!errors || errors.length === 0)) {
    return null;
  }

  const nextCoverage = coverage ? { ...coverage } : {};
  const context: StockQueryFundamentalContext = {
    status: 'partial',
    coverage: nextCoverage,
    errors: errors ?? [],
    sourceChain: [],
  };

  const valuation = fallbackFundamentalBlock(details?.valuation, nextCoverage.valuation);
  const growth = fallbackFundamentalBlock(details?.growth, nextCoverage.growth);
  const earnings = fallbackFundamentalBlock(details?.earnings, nextCoverage.earnings);
  const institution = fallbackFundamentalBlock(details?.institution, nextCoverage.institution);
  const capitalFlow = fallbackFundamentalBlock(details?.capitalFlow, nextCoverage.capitalFlow);
  const dragonTiger = fallbackFundamentalBlock(details?.dragonTiger, nextCoverage.dragonTiger);
  const boards = fallbackFundamentalBlock(details?.boards, nextCoverage.boards);

  if (valuation) context.valuation = valuation;
  if (growth) context.growth = growth;
  if (earnings) context.earnings = earnings;
  if (institution) context.institution = institution;
  if (capitalFlow) context.capitalFlow = capitalFlow;
  if (dragonTiger) context.dragonTiger = dragonTiger;
  if (boards) context.boards = boards;

  const blockKeys = [
    ['valuation', valuation],
    ['growth', growth],
    ['earnings', earnings],
    ['institution', institution],
    ['capitalFlow', capitalFlow],
    ['dragonTiger', dragonTiger],
    ['boards', boards],
  ] as const;

  for (const [key, block] of blockKeys) {
    if (!(key in nextCoverage) && block?.status) {
      nextCoverage[key] = block.status;
    }
  }

  const statuses = Object.values(nextCoverage);
  if (statuses.length === 0) {
    context.status = 'failed';
  } else if (statuses.every((item) => item === 'ok' || item === 'full')) {
    context.status = 'ok';
  } else if (statuses.every((item) => item === 'not_supported')) {
    context.status = 'not_supported';
  } else if (statuses.some((item) => item === 'partial' || item === 'failed')) {
    context.status = 'partial';
  }

  return context;
}

function newsSentimentLabel(value?: string): string {
  if (value === 'positive') return '偏正向';
  if (value === 'risk') return '偏风险';
  if (value === 'mixed') return '多空交织';
  if (value === 'neutral') return '中性';
  return '待判定';
}

function newsSentimentVariant(value?: string): 'success' | 'warning' | 'danger' | 'default' {
  if (value === 'positive') return 'success';
  if (value === 'risk') return 'danger';
  if (value === 'mixed') return 'warning';
  return 'default';
}

function strategyToneClasses(tone: StrategyTone): string {
  if (tone === 'buy') return 'paper-list-card';
  if (tone === 'breakout') return 'paper-panel-muted';
  return 'paper-alert-card';
}

function buildEntryPlan(result: StockQueryAnalyzeResponse): EntryPlan {
  const supportPrice = firstNumber(result.support, result.ma10, isFiniteNumber(result.currentPrice) ? result.currentPrice * 0.97 : null);
  const entryLower = supportPrice;
  const entryUpper = isFiniteNumber(supportPrice) ? supportPrice * 1.022 : null;
  const breakoutPrice = firstNumber(result.pressure, isFiniteNumber(result.currentPrice) ? result.currentPrice * 1.03 : null);
  const noChasePrice = isFiniteNumber(breakoutPrice)
    ? breakoutPrice * 1.026
    : (isFiniteNumber(result.currentPrice) ? result.currentPrice * 1.05 : null);
  const stopLossPrice = isFiniteNumber(supportPrice) ? supportPrice * 0.975 : null;

  let headline = '先等确认信号，再考虑入场';
  if (result.signal === '不宜追高') {
    headline = '今天不追，等回踩支撑区';
  } else if (result.signal === '低吸观察') {
    headline = '靠近支撑可分批试仓';
  } else if (result.signal === '持有候选') {
    headline = '支撑未破，可回踩承接';
  } else if (result.signal === '趋势跟随') {
    headline = '趋势延续，适合轻仓跟随';
  } else if (result.signal === '短线异动') {
    headline = '只做突破确认，不做盘中追涨';
  }

  let summary = '先观察价格如何靠近理想买点，再决定是低吸试仓还是突破确认。';
  if (isFiniteNumber(result.currentPrice) && isFiniteNumber(entryUpper) && result.currentPrice <= entryUpper) {
    summary = `现价已经接近试仓区 ${formatRange(entryLower, entryUpper)}，更适合轻仓试错，前提是支撑不破。`;
  } else if (isFiniteNumber(result.currentPrice) && isFiniteNumber(breakoutPrice) && result.currentPrice >= breakoutPrice) {
    summary = `价格已经来到突破位附近，更适合等待放量确认后的突破买法，而不是盘中硬追。`;
  } else if (isFiniteNumber(result.currentPrice) && isFiniteNumber(entryUpper)) {
    summary = `当前位置高于理想试仓区 ${formatRange(entryLower, entryUpper)}，优先等待回踩，再考虑第一笔仓位。`;
  }

  const strategies = [
    {
      key: 'low-absorb',
      title: '低吸试仓',
      description: `优先观察 ${formatRange(entryLower, entryUpper)} 一带止跌，再拿 20% - 30% 的试错仓位。`,
      tone: 'buy' as const,
    },
    {
      key: 'breakout',
      title: '突破确认',
      description: `若放量站上 ${formatNumber(breakoutPrice)}，再考虑做第二笔确认仓位。`,
      tone: 'breakout' as const,
    },
    {
      key: 'avoid-chasing',
      title: '禁止追高',
      description: `高于 ${formatNumber(noChasePrice)} 后不再主动追价，等待新的回踩机会。`,
      tone: 'warn' as const,
    },
  ];

  const checklist = [
    `回踩 ${formatRange(entryLower, entryUpper)} 附近时，先看是否出现止跌。`,
    `量比只有继续放大，突破确认价 ${formatNumber(breakoutPrice)} 才更有意义。`,
    isFiniteNumber(result.biasMa10)
      ? `当前偏离 MA10 ${formatPercent(result.biasMa10, 2)}，别在最热的位置强行上车。`
      : '先看价格是否重新靠近均线，再决定是否试仓。',
    `止损线先按 ${formatNumber(stopLossPrice)} 附近考虑，跌破后重新评估。`,
  ];

  return {
    headline,
    summary,
    supportPrice,
    entryLower,
    entryUpper,
    breakoutPrice,
    noChasePrice,
    stopLossPrice,
    strategies,
    checklist,
  };
}

function buildPriceRail(result: StockQueryAnalyzeResponse, plan: EntryPlan): PriceRailModel | null {
  const values = [
    plan.stopLossPrice,
    plan.supportPrice,
    plan.entryLower,
    plan.entryUpper,
    result.currentPrice,
    plan.breakoutPrice,
    plan.noChasePrice,
  ].filter(isFiniteNumber);

  if (values.length < 2) {
    return null;
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(max - min, 1);
  const paddedMin = min - span * 0.1;
  const paddedMax = max + span * 0.1;
  const paddedSpan = Math.max(paddedMax - paddedMin, 1);
  const toPosition = (value: number) => ((value - paddedMin) / paddedSpan) * 100;

  const points = [
    { key: 'stop', label: '止损', value: plan.stopLossPrice, tone: 'warn' as const },
    { key: 'support', label: '支撑', value: plan.supportPrice, tone: 'neutral' as const },
    { key: 'entry', label: '试仓', value: plan.entryUpper, tone: 'buy' as const },
    { key: 'current', label: '现价', value: result.currentPrice, tone: 'neutral' as const },
    { key: 'breakout', label: '突破', value: plan.breakoutPrice, tone: 'breakout' as const },
    { key: 'noChase', label: '禁追', value: plan.noChasePrice, tone: 'warn' as const },
  ]
    .filter((item): item is { key: string; label: string; value: number; tone: StrategyTone | 'neutral' } => isFiniteNumber(item.value))
    .map((item) => ({ ...item, position: toPosition(item.value) }));

  return {
    points,
    entryStart: isFiniteNumber(plan.entryLower) ? toPosition(plan.entryLower) : 0,
    entryEnd: isFiniteNumber(plan.entryUpper) ? toPosition(plan.entryUpper) : 0,
    noChaseStart: isFiniteNumber(plan.noChasePrice) ? toPosition(plan.noChasePrice) : 100,
  };
}

function buildHistoryComparison(result: StockQueryAnalyzeResponse, previous: StockQueryHistoryItem): HistoryComparison {
  const previousResult = previous.result;
  const previousPlan = previousResult ? buildEntryPlan(previousResult) : null;
  const currentPrice = result.currentPrice;

  let headline = `上次的核心结论是“${previousPlan?.headline ?? previous.signal ?? '待确认'}”`;
  let description = previousPlan?.summary ?? '上一条记录没有保存完整的入场计划，请重新查看该条历史结果。';

  if (isFiniteNumber(currentPrice) && isFiniteNumber(previousPlan?.entryLower) && isFiniteNumber(previousPlan?.entryUpper)) {
    if (currentPrice >= previousPlan.entryLower && currentPrice <= previousPlan.entryUpper) {
      headline = '现价已经回到上次试仓区';
      description = `上一次给出的试仓区是 ${formatRange(previousPlan.entryLower, previousPlan.entryUpper)}，现在价格已经重新靠近那个区域。`;
    } else if (currentPrice > previousPlan.entryUpper) {
      const diffPct = ((currentPrice - previousPlan.entryUpper) / previousPlan.entryUpper) * 100;
      headline = `现价高于上次试仓上沿 ${formatPercent(diffPct, 1)}`;
      description = `相比 ${formatHistoryTime(previous.completedAt || previous.createdAt)} 的判断，现在更像“等回踩”而不是“直接低吸”。`;
    } else if (currentPrice < previousPlan.entryLower) {
      const diffPct = ((previousPlan.entryLower - currentPrice) / previousPlan.entryLower) * 100;
      headline = `现价低于上次试仓下沿 ${formatPercent(diffPct, 1)}`;
      description = `价格已经跌破上次理想试仓区，先确认支撑是否仍然有效。`;
    }
  }

  const secondary = previous.signal === result.signal
    ? `信号仍是 ${result.signal}，说明大方向没有改写。`
    : `信号从 ${previous.signal ?? '未知'} 变成了 ${result.signal}，交易节奏也应该跟着变化。`;

  return { headline, description, secondary };
}

function getHistoryEntryPlan(item: StockQueryHistoryItem): EntryPlan | null {
  return item.result ? buildEntryPlan(item.result) : null;
}

function getHistoryLabel(item: StockQueryHistoryItem): string {
  const plan = getHistoryEntryPlan(item);
  return plan?.headline ?? item.signal ?? '待确认';
}

function markerToneClasses(tone: StrategyTone | 'neutral', current = false): string {
  if (current) return 'border-foreground bg-card shadow-soft-card';
  if (tone === 'buy') return 'border-foreground/70 bg-foreground';
  if (tone === 'breakout') return 'border-foreground/55 bg-foreground/70';
  if (tone === 'warn') return 'border-foreground/35 bg-foreground/45';
  return 'border-border/70 bg-card';
}

function buildSignalOverview(result: StockQueryAnalyzeResponse, plan: EntryPlan): SignalOverview {
  const baseScore = isFiniteNumber(result.trendScore) ? result.trendScore : 76;
  let score = Math.round(baseScore);
  let label = '保持观察';
  let description = '先等价格靠近理想位置，再决定是否执行交易计划。';

  if (result.signal === '持有候选') {
    score += 8;
    label = '回踩承接';
    description = '趋势结构仍在，优先等回踩支撑后的承接买点。';
  } else if (result.signal === '趋势跟随') {
    score += 6;
    label = '顺势跟随';
    description = '趋势延续结构更强，允许用更轻的仓位沿趋势跟随。';
  } else if (result.signal === '低吸观察') {
    score += 4;
    label = '低吸优先';
    description = '价格靠近试仓区时，优先考虑轻仓分批试错。';
  } else if (result.signal === '短线异动') {
    score -= 3;
    label = '突破确认';
    description = '短线更看放量突破确认，不适合盘中直接追涨。';
  } else if (result.signal === '不宜追高') {
    score -= 8;
    label = '可等待买点';
    description = '信号并不差，但当前更缺一个舒服的入场位置。';
  } else if (result.signal === '仅观察') {
    score -= 12;
    label = '继续观察';
    description = '先等更明确的结构或价格位置出现，再考虑上车。';
  }

  if (isFiniteNumber(result.currentPrice) && isFiniteNumber(plan.entryUpper) && result.currentPrice <= plan.entryUpper) {
    label = '接近试仓区';
    description = `现价已经靠近 ${formatRange(plan.entryLower, plan.entryUpper)}，更适合按试仓计划执行。`;
  }

  score = Math.max(18, Math.min(score, 96));
  return { score, label, description };
}

const SingleStockQueryPage: React.FC = () => {
  const location = useLocation();
  const initialQuery = useMemo(() => {
    const params = new URLSearchParams(location.search);
    return params.get('stock') ?? params.get('query') ?? QUICK_QUERIES[0].value;
  }, [location.search]);

  const [query, setQuery] = useState(initialQuery);
  const [strategy, setStrategy] = useState<string>('auto');
  const [result, setResult] = useState<StockQueryAnalyzeResponse | null>(null);
  const [queryTask, setQueryTask] = useState<StockQueryTaskStatus | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [lastResolvedInput, setLastResolvedInput] = useState(initialQuery);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyItems, setHistoryItems] = useState<StockQueryHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<ParsedApiError | null>(null);
  const [historyRestoreId, setHistoryRestoreId] = useState<string | null>(null);
  const [currentHistoryId, setCurrentHistoryId] = useState<string | null>(null);
  const [watchlistItems, setWatchlistItems] = useState<StockWatchlistItem[]>([]);
  const [stockAlertRules, setStockAlertRules] = useState<StockAlertRuleItem[]>([]);
  const [watchlistLoading, setWatchlistLoading] = useState(false);
  const [alertRuleLoading, setAlertRuleLoading] = useState(false);
  const [alertScanInterval, setAlertScanInterval] = useState<string>(String(MIN_ALERT_SCAN_INTERVAL_MINUTES));
  const [watchlistActionError, setWatchlistActionError] = useState<ParsedApiError | null>(null);
  const [watchlistActionMessage, setWatchlistActionMessage] = useState<string | null>(null);
  const pollTimeoutRef = useRef<number | null>(null);
  const hasPendingInputChange = query.trim() !== (lastResolvedInput || '').trim();

  const loadHistory = async () => {
    setHistoryLoading(true);
    setHistoryError(null);

    try {
      const response = await stockQueryApi.getHistory(20);
      setHistoryItems(response.items);
    } catch (requestError) {
      setHistoryError(getParsedApiError(requestError));
    } finally {
      setHistoryLoading(false);
    }
  };

  const loadWatchlist = async () => {
    try {
      const response = await watchlistApi.listStocks();
      setWatchlistItems(response.items);
    } catch {
      // Ignore passive watchlist load failures on the stock page.
    }
  };

  const loadStockAlertRules = async (stockCode?: string) => {
    if (!stockCode) {
      setStockAlertRules([]);
      return;
    }
    try {
      const response = await watchlistApi.listStockAlertRules(stockCode);
      setStockAlertRules(response.items);
    } catch {
      // Ignore passive alert-rule load failures on the stock page.
    }
  };

  useEffect(() => {
    void loadHistory();
    void loadWatchlist();
  }, []);

  useEffect(() => () => {
    if (pollTimeoutRef.current != null) {
      window.clearTimeout(pollTimeoutRef.current);
    }
  }, []);

  const applyAnalyzeResult = async (response: StockQueryAnalyzeResponse, resolvedInput: string) => {
    setResult(response);
    setStrategy(response.strategy || 'auto');
    setCurrentHistoryId(response.queryId ?? null);
    setLastResolvedInput(resolvedInput);
    setQueryTask(null);
    void loadStockAlertRules(response.stockCode);
    void loadHistory();
  };

  const pollAnalyzeStatus = async (taskId: string, resolvedInput: string) => {
    try {
      const status = await stockQueryApi.getAnalyzeStatus(taskId);
      setQueryTask(status);

      if (status.status === 'completed' && status.result) {
        await applyAnalyzeResult(status.result, resolvedInput);
        setError(null);
        setIsLoading(false);
        pollTimeoutRef.current = null;
        return;
      }

      if (status.status === 'failed') {
        setError(createParsedApiError({
          title: '单股查询失败',
          message: status.error || status.message || '单股查询失败',
          status: 500,
        }));
        setIsLoading(false);
        pollTimeoutRef.current = null;
        void loadHistory();
        return;
      }

      pollTimeoutRef.current = window.setTimeout(() => {
        void pollAnalyzeStatus(taskId, resolvedInput);
      }, 3000);
    } catch (requestError) {
      setError(getParsedApiError(requestError));
      setIsLoading(false);
      pollTimeoutRef.current = null;
    }
  };

  const analyzeStock = async (rawInput: string) => {
    const normalized = rawInput.trim();
    if (!normalized) return;

    if (pollTimeoutRef.current != null) {
      window.clearTimeout(pollTimeoutRef.current);
      pollTimeoutRef.current = null;
    }
    setIsLoading(true);
    setError(null);
    setQueryTask(null);

    try {
      const accepted = await stockQueryApi.analyze({ query: normalized, strategy });
      setCurrentHistoryId(accepted.taskId);
      setQueryTask({
        taskId: accepted.taskId,
        status: accepted.status,
        progress: 0,
        message: accepted.message,
        createdAt: new Date().toISOString(),
      });
      await pollAnalyzeStatus(accepted.taskId, normalized);
    } catch (requestError) {
      setError(getParsedApiError(requestError));
      setIsLoading(false);
    } finally {
      if (pollTimeoutRef.current == null) {
        setIsLoading(false);
      }
    }
  };

  useEffect(() => {
    setQuery(initialQuery);
    setError(null);
  }, [initialQuery]);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await analyzeStock(query);
  };

  const handleQuickQuery = (value: string) => {
    setQuery(value);
  };

  const handleHistoryRestore = async (item: StockQueryHistoryItem) => {
    const restoreQuery = item.stockCode ?? item.queryText ?? '';
    if (!restoreQuery) return;

    setHistoryRestoreId(item.queryId);
    setHistoryError(null);

    try {
      const detail = await stockQueryApi.getHistoryItem(item.queryId);
      const restoredResult = detail.result ?? item.result;
      if (restoredResult) {
        await applyAnalyzeResult(restoredResult, restoreQuery);
      } else {
        if (detail.status === 'pending' || detail.status === 'processing') {
          setCurrentHistoryId(detail.queryId);
          setQueryTask({
            taskId: detail.queryId,
            status: detail.status as StockQueryTaskStatus['status'],
            progress: detail.status === 'processing' ? 15 : 0,
            createdAt: detail.createdAt,
            completedAt: detail.completedAt,
          });
          setIsLoading(true);
          setHistoryOpen(false);
          await pollAnalyzeStatus(detail.queryId, restoreQuery);
          return;
        }
        await analyzeStock(restoreQuery);
        return;
      }
      setCurrentHistoryId(detail.queryId);
      setQuery(detail.stockCode ?? detail.queryText ?? restoreQuery);
      setLastResolvedInput(detail.queryText ?? detail.stockCode ?? restoreQuery);
      setError(null);
      setHistoryOpen(false);
    } catch (requestError) {
      setHistoryError(getParsedApiError(requestError));
    } finally {
      setHistoryRestoreId(null);
    }
  };

  const themeAttributions = result?.themeAttributions ?? result?.themes ?? [];
  const currentStockAlertRules = useMemo(() => {
    if (!result) return [];
    return stockAlertRules.filter((item) => item.stockCode === result.stockCode);
  }, [result, stockAlertRules]);
  const hasStockAlertRules = currentStockAlertRules.length > 0;
  const isInWatchlist = useMemo(() => {
    if (!result) return false;
    return watchlistItems.some((item) => item.stockCode === result.stockCode);
  }, [result, watchlistItems]);
  const topTheme = themeAttributions[0] ?? null;
  const stockContextSupplement = result?.stockContextSupplement ?? null;
  const conceptAttribution = stockContextSupplement?.conceptAttribution ?? null;
  const fundamentalContext = useMemo(
    () => result?.fundamentalContext ?? buildFallbackFundamentalContext(result?.fundamentalDetails, result?.fundamentalCoverage, result?.fundamentalErrors),
    [result?.fundamentalContext, result?.fundamentalDetails, result?.fundamentalCoverage, result?.fundamentalErrors],
  );
  const fundamentalCoverageEntries = Object.entries(fundamentalContext?.coverage ?? {});
  const incompleteFundamentalEntries = fundamentalCoverageEntries.filter(([, status]) => status !== 'ok' && status !== 'full');
  const fundamentalErrorPreview = (fundamentalContext?.errors ?? []).slice(0, 3);
  const valuationBlock = fundamentalContext?.valuation;
  const valuation = valuationBlock?.data;
  const boardsBlock = fundamentalContext?.boards;
  const boardItems = boardsBlock?.data?.items ?? [];
  const boardSource = boardsBlock?.data?.source;
  const boardProvider = boardsBlock?.data?.provider;
  const capitalFlowBlock = fundamentalContext?.capitalFlow;
  const capitalFlow = capitalFlowBlock?.data?.stockFlow;
  const dragonTigerBlock = fundamentalContext?.dragonTiger;
  const dragonTiger = dragonTigerBlock?.data;
  const growthBlock = fundamentalContext?.growth;
  const growth = growthBlock?.data;
  const earningsBlock = fundamentalContext?.earnings;
  const earnings = earningsBlock?.data;
  const institutionBlock = fundamentalContext?.institution;
  const institution = institutionBlock?.data;
  const hasFundamentalBlocks = useMemo(() => {
    if (!fundamentalContext) return false;
    return [
      valuationBlock,
      growthBlock,
      earningsBlock,
      institutionBlock,
      capitalFlowBlock,
      dragonTigerBlock,
      boardsBlock,
    ].some((block) => hasFundamentalBlockData(block) || Boolean(block?.errors?.length));
  }, [boardsBlock, capitalFlowBlock, dragonTigerBlock, earningsBlock, fundamentalContext, growthBlock, institutionBlock, valuationBlock]);
  const stockNewsSummary = result?.stockNewsSummary;
  const profileHighlights = supplementItems(
    stockContextSupplement?.profile?.highlights,
    stockContextSupplement?.profile?.headlines,
  );
  const announcementHighlights = supplementItems(
    stockContextSupplement?.announcements?.highlights,
    stockContextSupplement?.announcements?.headlines,
  );
  const lockupHighlights = supplementItems(
    stockContextSupplement?.lockup?.highlights,
    stockContextSupplement?.lockup?.headlines,
  );
  const entryPlan = useMemo(() => (result ? buildEntryPlan(result) : null), [result]);
  const signalOverview = useMemo(
    () => (result && entryPlan ? buildSignalOverview(result, entryPlan) : null),
    [entryPlan, result],
  );
  const priceRail = useMemo(() => (result && entryPlan ? buildPriceRail(result, entryPlan) : null), [entryPlan, result]);
  const recentHistory = useMemo(() => historyItems.slice(0, 4), [historyItems]);
  const activeHistoryItem = useMemo(() => {
    if (!currentHistoryId) return null;
    return historyItems.find((item) => item.queryId === currentHistoryId) ?? null;
  }, [currentHistoryId, historyItems]);
  const previousSameStock = useMemo(() => {
    if (!result) return null;
    return historyItems.find((item) => item.stockCode === result.stockCode && item.queryId !== currentHistoryId) ?? null;
  }, [currentHistoryId, historyItems, result]);
  const rightRailHistory = useMemo(() => {
    if (result) {
      const sameStockItems = historyItems.filter((item) => item.stockCode === result.stockCode);
      if (sameStockItems.length > 0) {
        return sameStockItems.slice(0, 3);
      }
    }
    return historyItems.slice(0, 3);
  }, [historyItems, result]);
  const historyComparison = useMemo(() => {
    if (!result || !previousSameStock) return null;
    return buildHistoryComparison(result, previousSameStock);
  }, [previousSameStock, result]);
  const historyPreviewItems = useMemo(
    () => (result ? rightRailHistory : recentHistory).slice(0, 2),
    [recentHistory, result, rightRailHistory],
  );
  const historyCardItems = useMemo(
    () => (result ? rightRailHistory : recentHistory).slice(0, 5),
    [recentHistory, result, rightRailHistory],
  );
  const resultTimestamp = activeHistoryItem?.completedAt
    ?? queryTask?.completedAt
    ?? queryTask?.startedAt
    ?? queryTask?.createdAt
    ?? null;

  const handleAddToWatchlist = async () => {
    if (!result) return;
    setWatchlistLoading(true);
    setWatchlistActionError(null);
    setWatchlistActionMessage(null);
    try {
      const item = await watchlistApi.upsertStock({
        stockCode: result.stockCode,
        stockName: result.stockName,
        groupName: '核心跟踪',
        latestSignal: result.signal,
        latestTheme: topTheme?.themeName,
        sourceQueryId: result.queryId ?? undefined,
      });
      setWatchlistItems((prev) => {
        const next = prev.filter((entry) => entry.stockCode !== item.stockCode);
        return [item, ...next];
      });
      setWatchlistActionMessage(`${item.stockName} 已加入观察池`);
    } catch (requestError) {
      setWatchlistActionError(getParsedApiError(requestError));
    } finally {
      setWatchlistLoading(false);
    }
  };

  const handleCreateDefaultAlerts = async () => {
    if (!result) return;
    setAlertRuleLoading(true);
    setWatchlistActionError(null);
    setWatchlistActionMessage(null);
    try {
      const parsedInterval = Number(alertScanInterval.trim() || String(MIN_ALERT_SCAN_INTERVAL_MINUTES));
      if (!Number.isFinite(parsedInterval) || parsedInterval < MIN_ALERT_SCAN_INTERVAL_MINUTES) {
        throw createParsedApiError({
          title: '扫描间隔不正确',
          message: `扫描间隔单位为分钟，最小 ${MIN_ALERT_SCAN_INTERVAL_MINUTES} 分钟。`,
          category: 'unknown',
        });
      }
      await watchlistApi.upsertStock({
        stockCode: result.stockCode,
        stockName: result.stockName,
        groupName: '核心跟踪',
        latestSignal: result.signal,
        latestTheme: topTheme?.themeName,
        alertEnabled: true,
        sourceQueryId: result.queryId ?? undefined,
      });
      const response = await watchlistApi.createDefaultStockAlertRules({
        stockCode: result.stockCode,
        stockName: result.stockName,
        supportPrice: result.support,
        breakoutPrice: result.pressure,
        scanIntervalMinutes: Math.round(parsedInterval),
        sourceQueryId: result.queryId ?? undefined,
      });
      setStockAlertRules((prev) => {
        const next = prev.filter((entry) => entry.stockCode !== result.stockCode);
        return [...response.items, ...next];
      });
      setWatchlistItems((prev) => prev.map((item) => (item.stockCode === result.stockCode ? { ...item, alertEnabled: true } : item)));
      setWatchlistActionMessage(`${result.stockName} 已创建 ${response.items.length} 条默认告警规则`);
    } catch (requestError) {
      setWatchlistActionError(getParsedApiError(requestError));
    } finally {
      setAlertRuleLoading(false);
      void loadWatchlist();
    }
  };

  const useRedesignedLayout = true;

  if (useRedesignedLayout) {
    return (
      <AppPage className="!max-w-[1680px] px-3 md:px-5 lg:px-6">
        <section className="paper-hero text-foreground">
          <div className="px-5 py-6 lg:px-7">
            <div className="space-y-4">
              <div className="flex flex-wrap items-end justify-between gap-4 border-b border-border/70 pb-4">
                <div>
                  <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-secondary-text">Stock Query</p>
                  <h1 className="mt-2 text-[1.7rem] font-semibold tracking-[-0.03em] text-foreground">单股查询</h1>
                </div>
                <p className="max-w-[520px] text-sm leading-6 text-secondary-text">
                  检索、回看、信号和历史扫描记录收在同一页里，优先保证高频判断顺手。
                </p>
              </div>

              <form className="paper-panel-subtle space-y-3 px-4 py-4 md:px-5" onSubmit={handleSubmit}>
                <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_240px_120px]">
                  <Input
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="输入股票或 ETF 代码/名称，例如 688629.SH / 512880.SH / 华丰科技"
                    className="h-12 rounded-2xl border-border/60 bg-background/78 text-foreground placeholder:text-muted-text"
                    hint="支持股票与 ETF 代码/名称。查询成功后会自动写入后端历史，方便回看和恢复查看。"
                  />
                  <Select
                    value={strategy}
                    onChange={setStrategy}
                    options={STRATEGY_OPTIONS.map((item) => ({ value: item.value, label: item.label }))}
                    label="策略视角"
                  />
                  <Button
                    type="submit"
                    size="lg"
                    isLoading={isLoading}
                    loadingText="正在分析..."
                    className="h-12 rounded-2xl"
                  >
                    <Search className="h-4 w-4" />
                    开始查询
                  </Button>
                </div>

                <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_136px]">
                  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                    {QUICK_QUERIES.map((item) => (
                      <button
                        key={item.value}
                        type="button"
                        onClick={() => handleQuickQuery(item.value)}
                        className={cn(
                          'paper-list-card text-left transition-colors',
                          query === item.value
                            ? 'border-foreground/16 bg-foreground/[0.05]'
                            : 'hover:border-foreground/12 hover:bg-card',
                        )}
                      >
                        <p className="text-sm font-semibold text-foreground">{item.label}</p>
                        <p className="mt-2 text-xs leading-5 text-secondary-text">{item.note}</p>
                      </button>
                    ))}
                  </div>
                  <Button
                    type="button"
                    variant="secondary"
                    size="lg"
                    className="h-full min-h-12 rounded-2xl border-border/60 bg-background/78 text-foreground hover:bg-card"
                    onClick={() => setHistoryOpen(true)}
                  >
                    <Clock3 className="h-4 w-4" />
                    历史查询
                  </Button>
                </div>
              </form>

              <div className="paper-panel-subtle flex flex-col gap-3 px-4 py-3 md:flex-row md:items-center md:justify-between">
                <div>
                  <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-secondary-text">History</p>
                  <p className="mt-1 text-sm leading-6 text-secondary-text">最近回看</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {historyPreviewItems.length > 0 ? (
                    historyPreviewItems.map((item) => (
                      <button
                        key={item.queryId}
                        type="button"
                        onClick={() => void handleHistoryRestore(item)}
                        className="paper-chip rounded-full px-3 py-2 text-xs font-medium text-foreground transition hover:border-foreground/12 hover:bg-card"
                      >
                        {item.stockName || item.queryText || item.stockCode || '历史记录'}
                      </button>
                    ))
                  ) : (
                    <span className="text-sm text-secondary-text">执行几次查询后，这里会出现最近回看链接。</span>
                  )}
                  <Button variant="ghost" size="sm" className="text-secondary-text hover:bg-foreground/4 hover:text-foreground" onClick={() => setHistoryOpen(true)}>
                    查看全部
                  </Button>
                </div>
              </div>

              {error ? <ApiErrorAlert error={error} /> : null}
              {watchlistActionError ? <ApiErrorAlert error={watchlistActionError} /> : null}
              {watchlistActionMessage ? (
                <InlineAlert variant="success" title="观察池已更新" message={watchlistActionMessage} />
              ) : null}

              {isLoading && queryTask ? (
                <InlineAlert
                  variant="info"
                  title="单股查询正在后台处理"
                  message={queryTask.message || '正在获取日线、实时行情和基本面，请稍候。'}
                />
              ) : null}

              {result && hasPendingInputChange ? (
                <InlineAlert
                  title="输入已更新，当前结果还没有刷新"
                  message={`现在输入框里是 ${query.trim() || '--'}，页面仍然展示上一次查询：${lastResolvedInput || '--'}。点击“开始查询”后会重新分析。`}
                  variant="info"
                />
              ) : null}

              <div className="grid gap-4 xl:grid-cols-[minmax(0,1.12fr)_minmax(0,0.88fr)]">
                <div className="space-y-4">
                  <PaperSectionCard
                    eyebrow="个股信息"
                    title={result ? `${result.stockName} · ${result.stockCode}` : '个股信息'}
                    description={result
                      ? '价格、估值、资金和补充信息放在一张主卡里。'
                      : '查询成功后展示价格概览、基本面和补充信息。'}
                    className="px-5 py-5"
                    actions={result ? (
                      <div className="flex flex-wrap items-center gap-2">
                        {instrumentBadgeLabel(result.instrumentLabel, result.instrumentType) ? (
                          <Badge variant="info" className="border-0 px-3 py-1">
                            {instrumentBadgeLabel(result.instrumentLabel, result.instrumentType)}
                          </Badge>
                        ) : null}
                        <Badge variant={signalBadgeVariant(result.signal)} className="border-0 px-3 py-1">
                          {result.signal}
                        </Badge>
                      </div>
                    ) : null}
                  >
                    {result ? (
                      <div className="space-y-4">
                        <div className="grid gap-3 xl:grid-cols-[minmax(0,1.06fr)_minmax(0,0.94fr)]">
                          <div className="paper-panel-subtle px-4 py-4">
                            <div className="flex flex-wrap items-start justify-between gap-3">
                              <div className="min-w-0">
                                <p className="text-base font-semibold text-foreground">
                                  {result.stockCode} {result.stockName}
                                </p>
                                <p className="mt-1 text-sm text-secondary-text">{resultTimestamp ? `数据更新 ${formatHistoryTime(resultTimestamp)}` : '等待更新时间'}</p>
                              </div>
                              <div className="text-right">
                                <p className="text-[2rem] font-semibold tracking-[-0.03em] text-foreground">{formatNumber(result.currentPrice)}</p>
                                <p className={`mt-1 text-lg font-semibold ${signedValueClass(result.pctChg)}`}>
                                  {formatPercent(result.pctChg, 2)}
                                </p>
                              </div>
                            </div>
                            <div className="mt-4 flex flex-wrap gap-2">
                              <span className="paper-chip px-3 py-2 text-xs font-medium text-foreground">{result.strategyLabel || '自动决策'}</span>
                              <span className="paper-chip px-3 py-2 text-xs font-medium text-foreground">{result.trendStatus || result.pattern || '等待结构确认'}</span>
                            </div>
                          </div>

                          <div className="grid gap-3 sm:grid-cols-2">
                            <PaperMetricCard label="换手率" value={formatPercent(result.turnoverRate, 2)} tone="muted" />
                            <PaperMetricCard label="量比" value={formatNumber(result.volumeRatio, 2)} tone="muted" />
                            <PaperMetricCard label="趋势分" value={formatNumber(result.trendScore, 1)} tone="default" />
                            <PaperMetricCard label="PE / PB" value={`PE ${formatNumber(result.peRatio)} / PB ${formatNumber(result.pbRatio)}`} tone="muted" />
                          </div>
                        </div>

                        {hasFundamentalBlocks ? (
                          <div className="grid gap-3 xl:grid-cols-2">
                            <PaperDataBlockCard
                              title="估值"
                              subtitle={`来源 ${sourceChainSummary(valuationBlock?.sourceChain)}`}
                              status={(
                                <Badge variant={valuationBlock?.status === 'ok' || valuationBlock?.status === 'full' ? 'success' : valuationBlock?.status === 'partial' ? 'warning' : 'default'} className="border-0 px-2 py-1">
                                  {coverageStatusLabel(valuationBlock?.status || 'failed')}
                                </Badge>
                              )}
                              footer={valuationBlock?.errors?.length ? <p className="text-xs leading-5 text-secondary-text">错误: {valuationBlock.errors.slice(0, 2).join(' | ')}</p> : null}
                            >
                              <div className="grid gap-3 sm:grid-cols-2">
                                <MiniMetric label="PE" value={formatNumber(valuation?.peRatio)} tone="neutral" />
                                <MiniMetric label="PB" value={formatNumber(valuation?.pbRatio)} tone="neutral" />
                                <MiniMetric label="总市值" value={formatMoney(valuation?.totalMv)} tone="neutral" />
                                <MiniMetric label="流通市值" value={formatMoney(valuation?.circMv)} tone="neutral" />
                              </div>
                            </PaperDataBlockCard>

                            <PaperDataBlockCard
                              title="成长"
                              subtitle={`来源 ${sourceChainSummary(growthBlock?.sourceChain)}`}
                              status={(
                                <Badge variant={growthBlock?.status === 'ok' || growthBlock?.status === 'full' ? 'success' : growthBlock?.status === 'partial' ? 'warning' : 'default'} className="border-0 px-2 py-1">
                                  {coverageStatusLabel(growthBlock?.status || 'failed')}
                                </Badge>
                              )}
                              footer={growthBlock?.errors?.length ? <p className="text-xs leading-5 text-secondary-text">错误: {growthBlock.errors.slice(0, 2).join(' | ')}</p> : null}
                            >
                              <div className="grid gap-3 sm:grid-cols-2">
                                <MiniMetric label="营收同比" value={formatPercent(growth?.revenueYoy, 1)} tone="neutral" />
                                <MiniMetric label="净利同比" value={formatPercent(growth?.netProfitYoy, 1)} tone="neutral" />
                                <MiniMetric label="ROE" value={formatPercent(growth?.roe, 1)} tone="neutral" />
                                <MiniMetric label="毛利率" value={formatPercent(growth?.grossMargin, 1)} tone="neutral" />
                              </div>
                            </PaperDataBlockCard>

                            <PaperDataBlockCard
                              title="资金流"
                              subtitle={`来源 ${sourceChainSummary(capitalFlowBlock?.sourceChain)}`}
                              status={(
                                <Badge variant={capitalFlowBlock?.status === 'ok' || capitalFlowBlock?.status === 'full' ? 'success' : capitalFlowBlock?.status === 'partial' ? 'warning' : 'default'} className="border-0 px-2 py-1">
                                  {coverageStatusLabel(capitalFlowBlock?.status || 'failed')}
                                </Badge>
                              )}
                              footer={capitalFlowBlock?.errors?.length ? <p className="text-xs leading-5 text-secondary-text">错误: {capitalFlowBlock.errors.slice(0, 2).join(' | ')}</p> : null}
                            >
                              <div className="grid gap-3 sm:grid-cols-3">
                                <MiniMetric label="主力净流入" value={formatMoney(capitalFlow?.mainNetInflow)} tone="neutral" />
                                <MiniMetric label="5日净流入" value={formatMoney(capitalFlow?.inflow5d)} tone="neutral" />
                                <MiniMetric label="10日净流入" value={formatMoney(capitalFlow?.inflow10d)} tone="neutral" />
                              </div>
                            </PaperDataBlockCard>

                            <PaperDataBlockCard
                              title="龙虎榜"
                              subtitle={`来源 ${sourceChainSummary(dragonTigerBlock?.sourceChain)}`}
                              status={(
                                <Badge variant={dragonTigerBlock?.status === 'ok' || dragonTigerBlock?.status === 'full' ? 'success' : dragonTigerBlock?.status === 'partial' ? 'warning' : 'default'} className="border-0 px-2 py-1">
                                  {coverageStatusLabel(dragonTigerBlock?.status || 'failed')}
                                </Badge>
                              )}
                              footer={dragonTiger?.reason ? <p className="text-xs leading-5 text-secondary-text">上榜原因：{dragonTiger.reason}</p> : null}
                            >
                              <div className="grid gap-3 sm:grid-cols-2">
                                <MiniMetric label="近20日状态" value={dragonTiger?.isOnList ? `上榜 ${dragonTiger.recentCount ?? 0} 次` : '未识别到上榜'} tone="neutral" />
                                <MiniMetric label="最近日期" value={dragonTiger?.latestDate ?? '--'} tone="neutral" />
                                <MiniMetric label="净买额" value={formatMoney(dragonTiger?.netBuyAmount)} tone="neutral" />
                                <MiniMetric label="机构净买" value={formatMoney(dragonTiger?.institutionNetBuy)} tone="neutral" />
                              </div>
                            </PaperDataBlockCard>
                          </div>
                        ) : null}

                        {(stockContextSupplement?.profile || stockContextSupplement?.announcements || stockContextSupplement?.lockup) ? (
                          <div className="grid gap-3 xl:grid-cols-3">
                            <PaperSummaryBlock title="公司画像" summary={stockContextSupplement?.profile?.summary} items={profileHighlights} />
                            <PaperSummaryBlock title="近期公告" summary={stockContextSupplement?.announcements?.summary} items={announcementHighlights} />
                            <PaperSummaryBlock title="解禁提示" summary={stockContextSupplement?.lockup?.summary} items={lockupHighlights} danger />
                          </div>
                        ) : null}

                        {fundamentalCoverageEntries.length > 0 ? (
                          <div className="paper-panel-subtle px-4 py-4">
                            <div className="flex flex-wrap items-center justify-between gap-3">
                              <div>
                                <p className="text-sm font-semibold text-foreground">数据覆盖</p>
                                <p className="mt-1 text-xs leading-6 text-secondary-text">日线、实时和基本面返回状态。</p>
                              </div>
                              <Badge variant={incompleteFundamentalEntries.length > 0 ? 'warning' : 'success'} className="border-0 px-3 py-1">
                                {incompleteFundamentalEntries.length > 0 ? `仍缺 ${incompleteFundamentalEntries.length} 项` : '已完整返回'}
                              </Badge>
                            </div>
                            <div className="mt-4 grid gap-3 sm:grid-cols-3">
                              <PaperMetricCard label="日线" value={sourceLabel(result.dataSources.daily)} valueClassName="text-sm font-medium" tone="muted" />
                              <PaperMetricCard label="实时" value={sourceLabel(result.dataSources.realtime)} valueClassName="text-sm font-medium" tone="muted" />
                              <PaperMetricCard label="基本面" value={sourceLabel(result.dataSources.fundamental ?? fundamentalContext?.status)} valueClassName="text-sm font-medium" tone="muted" />
                            </div>
                            {fundamentalErrorPreview.length > 0 ? (
                              <p className="mt-4 text-xs leading-6 text-secondary-text">最近错误: {fundamentalErrorPreview.join(' | ')}</p>
                            ) : null}
                          </div>
                        ) : null}
                      </div>
                    ) : (
                      <InlineAlert
                        variant="info"
                        title="等待个股信息"
                        message="查询成功后，这里会先收纳股票本身的概览、估值、资金、公司画像和数据覆盖。"
                      />
                    )}
                  </PaperSectionCard>

                  <PaperSectionCard
                    eyebrow="K 线"
                    title={result ? 'K 线与价格结构' : 'K 线'}
                    description={result
                      ? '先用支撑、试仓区、现价和突破位表达当前结构。'
                      : '查询成功后展示 K 线相关结构。'}
                    className="px-5 py-5"
                  >
                    {result && entryPlan ? (
                      <div className="space-y-4">
                        {priceRail ? (
                          <div className="paper-panel-muted px-5 py-6">
                            <div className="relative h-24">
                              <div className="absolute left-4 right-4 top-10 h-2.5 rounded-full bg-border/90" />
                              <div
                                className="absolute top-[37px] h-3.5 rounded-full bg-foreground/88"
                                style={{
                                  left: `calc(${priceRail.entryStart}% + 1rem)`,
                                  width: `${Math.max(priceRail.entryEnd - priceRail.entryStart, 2)}%`,
                                }}
                              />
                              <div
                                className="absolute top-[37px] h-3.5 rounded-full bg-foreground/55"
                                style={{
                                  left: `calc(${priceRail.points.find((point) => point.key === 'breakout')?.position ?? priceRail.noChaseStart}% + 1rem)`,
                                  width: `${Math.max(priceRail.noChaseStart - (priceRail.points.find((point) => point.key === 'breakout')?.position ?? priceRail.noChaseStart), 2)}%`,
                                }}
                              />
                              <div
                                className="absolute top-[37px] h-3.5 rounded-full bg-foreground/28"
                                style={{
                                  left: `calc(${priceRail.noChaseStart}% + 1rem)`,
                                  right: '1rem',
                                }}
                              />

                              {priceRail.points.map((point) => {
                                const isCurrent = point.key === 'current';
                                return (
                                  <div
                                    key={point.key}
                                    className="absolute top-2 flex -translate-x-1/2 flex-col items-center gap-2"
                                    style={{ left: `calc(${point.position}% + 1rem)` }}
                                  >
                                    <div className={`h-5 w-5 rounded-full border-4 ${markerToneClasses(point.tone, isCurrent)}`} />
                                    <div className="min-w-[78px] text-center">
                                      <p className="text-xs font-semibold text-foreground">{point.label}</p>
                                      <p className="mt-1 text-xs text-secondary-text">{formatNumber(point.value)}</p>
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        ) : (
                          <InlineAlert
                            variant="info"
                            title="价格结构暂时无法计算"
                            message="当前价格或关键位信息不够完整，先参考下面的结构位卡片。"
                          />
                        )}

                        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                          <MiniMetric label="当前价" value={formatNumber(result.currentPrice)} tone="neutral" />
                          <MiniMetric label="支撑位" value={formatNumber(entryPlan.supportPrice)} tone="buy" />
                          <MiniMetric label="试仓区" value={formatRange(entryPlan.entryLower, entryPlan.entryUpper)} tone="buy" />
                          <MiniMetric label="突破位" value={formatNumber(entryPlan.breakoutPrice)} tone="breakout" />
                          <MiniMetric label="MA10 / MA20" value={`${formatNumber(result.ma10)} / ${formatNumber(result.ma20)}`} tone="neutral" />
                          <MiniMetric label="禁追区" value={`${formatNumber(entryPlan.noChasePrice)} 以上`} tone="warn" />
                        </div>
                      </div>
                    ) : (
                      <InlineAlert
                        variant="info"
                        title="等待 K 线结构"
                        message="查询成功后，这里会把买点刻度尺和关键价格结构集中展示。"
                      />
                    )}
                  </PaperSectionCard>

                  <PaperSectionCard
                    eyebrow="技术信号"
                    title={result ? (signalOverview?.label ?? result.signal) : '技术信号'}
                    description={result
                      ? (signalOverview?.description ?? '趋势、形态、动量和催化风险放在同一张卡里。')
                      : '查询成功后展示技术信号、趋势结构和催化/风险。'}
                    className="px-5 py-5"
                    actions={result ? (
                      <Badge variant={signalBadgeVariant(result.signal)} className="border-0 px-3 py-1">
                        {result.signal}
                      </Badge>
                    ) : null}
                  >
                    {result ? (
                      <div className="space-y-4">
                        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                          <PaperMetricCard label="信号分" value={signalOverview?.score ?? '--'} valueClassName="text-[1.35rem]" tone="default" />
                          <PaperMetricCard label="趋势状态" value={result.trendStatus ?? '--'} tone="muted" />
                          <PaperMetricCard label="形态结构" value={result.pattern ?? '--'} tone="muted" />
                          <PaperMetricCard label="动量信号" value={result.buySignal ?? result.signal} tone="muted" />
                        </div>

                        <div className="grid gap-3 xl:grid-cols-2">
                          <PaperListBlock>
                            <p className="text-sm font-semibold text-foreground">值得继续看的信号</p>
                            <div className="mt-3 space-y-2">
                              {result.selectedReasons.length > 0 ? (
                                result.selectedReasons.slice(0, 3).map((reason) => (
                                  <div key={reason} className="paper-panel-subtle px-4 py-3 text-sm leading-6 text-foreground">
                                    {reason}
                                  </div>
                                ))
                              ) : (
                                <p className="text-sm leading-6 text-secondary-text">当前没有特别强的做多理由。</p>
                              )}
                            </div>
                          </PaperListBlock>

                          <div className="paper-alert-card px-4 py-4">
                            <p className="text-sm font-semibold text-foreground">需要等待或规避的信号</p>
                            <div className="mt-3 space-y-2">
                              {result.excludedReasons.length > 0 ? (
                                result.excludedReasons.slice(0, 3).map((reason) => (
                                  <div key={reason} className="paper-panel-subtle px-4 py-3 text-sm leading-6 text-foreground">
                                    {reason}
                                  </div>
                                ))
                              ) : (
                                <p className="text-sm leading-6 text-secondary-text">当前没有特别显眼的排除项，但仍需结合买点执行。</p>
                              )}
                            </div>
                          </div>
                        </div>

                        {stockNewsSummary ? (
                          <div className="grid gap-3 xl:grid-cols-3">
                            <PaperListBlock>
                              <div className="flex items-center justify-between gap-3">
                                <p className="text-sm font-semibold text-foreground">新闻摘要</p>
                                <Badge variant={newsSentimentVariant(stockNewsSummary.sentiment)} className="border-0 px-2.5 py-1 text-[11px]">
                                  {newsSentimentLabel(stockNewsSummary.sentiment)}
                                </Badge>
                              </div>
                              <p className="mt-3 text-sm leading-6 text-secondary-text">{stockNewsSummary.summary || '当前没有拿到足够清晰的新闻摘要。'}</p>
                            </PaperListBlock>

                            <PaperListBlock>
                              <p className="text-sm font-semibold text-foreground">正向催化</p>
                              <div className="mt-3 flex flex-wrap gap-2">
                                {(stockNewsSummary.catalysts?.length ? stockNewsSummary.catalysts : ['暂无明确催化']).map((item) => (
                                  <span key={item} className="paper-chip px-3 py-2 text-xs font-medium text-foreground">
                                    {item}
                                  </span>
                                ))}
                              </div>
                            </PaperListBlock>

                            <div className="paper-alert-card px-4 py-4">
                              <p className="text-sm font-semibold text-foreground">明确风险</p>
                              <div className="mt-3 flex flex-wrap gap-2">
                                {(stockNewsSummary.riskEvents?.length ? stockNewsSummary.riskEvents : ['暂未识别明显利空']).map((item) => (
                                  <span key={item} className="paper-chip px-3 py-2 text-xs font-medium text-foreground">
                                    {item}
                                  </span>
                                ))}
                              </div>
                            </div>
                          </div>
                        ) : null}
                      </div>
                    ) : (
                      <InlineAlert
                        variant="info"
                        title="等待技术信号"
                        message="查询成功后，这里会展示趋势、形态、动量和催化/风险判断。"
                      />
                    )}
                  </PaperSectionCard>
                </div>

                <div className="space-y-4">
                  <PaperSectionCard
                    eyebrow="相关主题"
                    title={topTheme?.themeName || '相关主题'}
                    description={topTheme
                      ? '主题归因、概念映射和关联板块。'
                      : '查询成功后展示主题归因、概念摘要和关联板块。'}
                    className="px-5 py-5"
                    actions={themeAttributions.length > 0 ? (
                      <Badge variant="info" className="border-0 px-3 py-1">
                        {themeAttributions.length} 个主题
                      </Badge>
                    ) : null}
                  >
                    {(topTheme || themeAttributions.length > 0 || conceptAttribution || boardItems.length > 0) ? (
                      <div className="space-y-4">
                        {topTheme ? (
                          <div className="paper-panel-subtle px-4 py-4">
                            <div className="flex flex-wrap items-start justify-between gap-3">
                              <div>
                                <p className="text-sm font-semibold text-foreground">{topTheme.themeName}</p>
                                <p className="mt-1 text-xs leading-6 text-secondary-text">
                                  {confidenceLabel(topTheme.confidence)} · {relationTypeLabel(topTheme.relationType)}
                                </p>
                              </div>
                              <Badge variant="default" className="border-0 px-3 py-1">
                                主主题
                              </Badge>
                            </div>
                            <p className="mt-3 text-sm leading-6 text-foreground">{topTheme.reason}</p>
                          </div>
                        ) : null}

                        {themeAttributions.slice(1, 4).length > 0 ? (
                          <div className="grid gap-3">
                            {themeAttributions.slice(1, 4).map((theme) => (
                              <PaperListBlock key={`${theme.themeName}-${theme.relationType}`}>
                                <div className="flex items-center justify-between gap-3">
                                  <p className="text-sm font-semibold text-foreground">{theme.themeName}</p>
                                  <span className="text-xs text-secondary-text">{confidenceLabel(theme.confidence)}</span>
                                </div>
                                <p className="mt-2 text-sm leading-6 text-secondary-text">{theme.reason}</p>
                              </PaperListBlock>
                            ))}
                          </div>
                        ) : null}

                        {conceptAttribution ? (
                          <PaperListBlock>
                            <p className="text-sm font-semibold text-foreground">概念归因</p>
                            <p className="mt-2 text-sm leading-6 text-secondary-text">{conceptAttribution.summary}</p>
                            {conceptAttribution.conceptNames?.length ? (
                              <div className="mt-3 flex flex-wrap gap-2">
                                {conceptAttribution.conceptNames.slice(0, 6).map((item) => (
                                  <span key={item} className="paper-chip px-3 py-2 text-xs font-medium text-foreground">
                                    {item}
                                  </span>
                                ))}
                              </div>
                            ) : null}
                          </PaperListBlock>
                        ) : null}

                        {boardItems.length > 0 ? (
                          <PaperListBlock>
                            <div className="flex flex-wrap items-center justify-between gap-3">
                              <p className="text-sm font-semibold text-foreground">关联板块</p>
                              <span className="text-xs text-secondary-text">{boardSourceLabel(boardSource, boardProvider)}</span>
                            </div>
                            <div className="mt-3 flex flex-wrap gap-2">
                              {boardItems.slice(0, 10).map((board) => (
                                <span key={`${board.name}-${board.code ?? ''}`} className="paper-chip px-3 py-2 text-xs font-medium text-foreground">
                                  {board.name}
                                </span>
                              ))}
                            </div>
                          </PaperListBlock>
                        ) : null}
                      </div>
                    ) : (
                      <InlineAlert
                        variant="info"
                        title="等待主题归因"
                        message="查询成功后，这里会把最相关的主题、概念和板块映射出来。"
                      />
                    )}
                  </PaperSectionCard>

                  <PaperSectionCard
                    eyebrow="信号点"
                    title={entryPlan?.headline || '信号点'}
                    description={entryPlan?.summary || '这里只放真正影响出手动作的信号点。'}
                    className="px-5 py-5"
                    actions={result && entryPlan ? (
                      <div className="space-y-2 text-right">
                        <Badge variant={signalBadgeVariant(result.signal)} className="border-0 px-3 py-1">
                          {result.signal}
                        </Badge>
                        <p className="text-xs leading-6 text-secondary-text">{result.stockCode}</p>
                      </div>
                    ) : null}
                  >
                    {result && entryPlan ? (
                      <div className="space-y-4">
                        <div className="grid gap-3 sm:grid-cols-2">
                          <PaperMetricCard label="试仓区" value={formatRange(entryPlan.entryLower, entryPlan.entryUpper)} detail="优先等回踩到位" tone="muted" />
                          <PaperMetricCard label="突破确认" value={formatNumber(entryPlan.breakoutPrice)} detail="放量再跟" tone="muted" />
                          <PaperMetricCard label="止损线" value={formatNumber(entryPlan.stopLossPrice)} detail="跌破减仓" tone="alert" />
                          <PaperMetricCard label="禁追区" value={formatNumber(entryPlan.noChasePrice)} detail="超过这里尽量不追" tone="alert" />
                        </div>

                        <div className="grid gap-3 xl:grid-cols-3">
                          {entryPlan.strategies.map((strategy) => (
                            <PaperListBlock key={strategy.key} className={strategyToneClasses(strategy.tone)}>
                              <p className="text-sm font-semibold text-foreground">{strategy.title}</p>
                              <p className="mt-2 text-sm leading-6 text-secondary-text">{strategy.description}</p>
                            </PaperListBlock>
                          ))}
                        </div>

                        <div className="grid gap-3">
                          {entryPlan.checklist.map((item) => (
                            <PaperListBlock key={item} className="text-sm leading-6 text-foreground">
                              {item}
                            </PaperListBlock>
                          ))}
                        </div>

                        {result.strategyDecisions && result.strategyDecisions.length > 0 ? (
                          <div className="paper-panel-muted p-4">
                            <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-secondary-text">Strategy Matrix</p>
                            <div className="mt-4 grid gap-3 xl:grid-cols-2">
                              {result.strategyDecisions.map((decision) => (
                                <PaperListBlock
                                  key={decision.key}
                                  className={decision.matched ? strategyToneClasses(strategySignalTone(decision.signal)) : 'paper-panel-subtle text-secondary-text'}
                                >
                                  <div className="flex items-center justify-between gap-3">
                                    <p className="text-sm font-semibold text-foreground">{decision.label}</p>
                                    <Badge variant={signalBadgeVariant(decision.signal)} className="border-0 px-2.5 py-1 text-[11px]">
                                      {decision.signal}
                                    </Badge>
                                  </div>
                                  <p className="mt-2 text-sm leading-6 text-secondary-text">
                                    {(decision.matched ? decision.selectedReasons : decision.excludedReasons)?.[0]
                                      ?? (decision.matched ? '当前更适合从这套策略视角切入。' : '当前还不满足这套策略的出手条件。')}
                                  </p>
                                </PaperListBlock>
                              ))}
                            </div>
                          </div>
                        ) : null}

                        <div className="grid gap-3 sm:grid-cols-3">
                          <Link
                            to={
                              result.queryId
                                ? `/deep-analysis?queryId=${encodeURIComponent(result.queryId)}&stock=${encodeURIComponent(result.stockCode)}&name=${encodeURIComponent(result.stockName)}`
                                : '/deep-analysis'
                            }
                            className="inline-flex min-h-12 items-center justify-center rounded-2xl border border-foreground/15 bg-foreground px-4 py-3 text-sm font-medium text-background shadow-soft-card transition hover:opacity-92"
                          >
                            发起深度分析
                          </Link>
                          <Button
                            type="button"
                            isLoading={watchlistLoading}
                            loadingText="加入中..."
                            disabled={!result || isInWatchlist}
                            onClick={() => void handleAddToWatchlist()}
                            className="min-h-12 rounded-2xl border border-border/60 bg-card px-4 py-3 text-sm font-medium text-foreground transition hover:bg-background"
                          >
                            {isInWatchlist ? '已在观察池' : '加入观察池'}
                          </Button>
                          <button
                            type="button"
                            disabled={!result || hasStockAlertRules || alertRuleLoading}
                            onClick={() => void handleCreateDefaultAlerts()}
                            className="paper-panel-subtle inline-flex min-h-12 items-center justify-center rounded-2xl px-4 py-3 text-sm font-medium text-foreground enabled:cursor-pointer enabled:hover:border-foreground/12 enabled:hover:bg-card disabled:opacity-60"
                          >
                            {alertRuleLoading ? '创建中...' : hasStockAlertRules ? '告警已设置' : '设置告警'}
                          </button>
                        </div>

                        <div className="grid gap-3 md:grid-cols-[minmax(0,220px)_1fr]">
                          <Input
                            label="告警扫描间隔(分钟)"
                            value={alertScanInterval}
                            onChange={(event) => setAlertScanInterval(event.target.value)}
                            placeholder={`默认 ${MIN_ALERT_SCAN_INTERVAL_MINUTES}`}
                            className="h-11 rounded-2xl"
                          />
                          <div className="paper-panel-muted flex items-center justify-between gap-3 px-4 py-3">
                            <div>
                              <p className="text-sm font-medium text-foreground">扫描频率由输入决定</p>
                              <p className="mt-1 text-xs leading-6 text-secondary-text">单位分钟，最小 {MIN_ALERT_SCAN_INTERVAL_MINUTES} 分钟。创建默认规则时会同步写入每条规则。</p>
                            </div>
                            <Badge variant="info" className="border-0 px-3 py-1">
                              默认 {MIN_ALERT_SCAN_INTERVAL_MINUTES} 分钟
                            </Badge>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <InlineAlert
                        variant="info"
                        title="等待信号点"
                        message="查询成功后，这里会展示试仓区、突破位、止损线、策略矩阵和后续动作。"
                      />
                    )}
                  </PaperSectionCard>

                  <PaperSectionCard
                    eyebrow="历史扫描记录"
                    title={result ? `${result.stockName} 的最近记录` : '历史扫描记录'}
                    description="保留同票回看和历史扫描记录。"
                    className="px-5 py-5"
                    actions={(
                      <Button variant="ghost" size="sm" className="text-secondary-text hover:bg-foreground/4 hover:text-foreground" onClick={() => setHistoryOpen(true)}>
                        全部历史
                      </Button>
                    )}
                  >
                    <div className="space-y-3">
                      {historyError ? <ApiErrorAlert error={historyError} /> : null}
                      {historyLoading ? (
                        <InlineAlert
                          variant="info"
                          title="正在读取历史记录"
                          message="正在从后端加载最近的单股查询记录。"
                        />
                      ) : null}

                      {historyComparison ? (
                        <PaperListBlock>
                          <p className="text-sm font-semibold text-foreground">{historyComparison.headline}</p>
                          <p className="mt-2 text-sm leading-6 text-secondary-text">{historyComparison.description}</p>
                        </PaperListBlock>
                      ) : null}

                      {historyCardItems.length > 0 ? (
                        historyCardItems.map((item) => (
                          <button
                            key={item.queryId}
                            type="button"
                            onClick={() => void handleHistoryRestore(item)}
                            className="block w-full text-left"
                          >
                            <PaperListBlock className="transition-colors hover:border-foreground/15 hover:bg-card">
                              <div className="flex items-center justify-between gap-3">
                                <p className="text-xs text-secondary-text">{formatHistoryTime(item.completedAt || item.createdAt)}</p>
                                <Badge variant={signalBadgeVariant(item.signal || '仅观察')} className="border-0 px-2.5 py-1 text-[11px]">
                                  {item.signal || '仅观察'}
                                </Badge>
                              </div>
                              <p className="mt-2 text-sm font-semibold text-foreground">{getHistoryLabel(item)}</p>
                              <p className="mt-2 text-xs leading-6 text-secondary-text">
                                试仓区 {formatRange(getHistoryEntryPlan(item)?.entryLower, getHistoryEntryPlan(item)?.entryUpper)}
                              </p>
                            </PaperListBlock>
                          </button>
                        ))
                      ) : (
                        <InlineAlert
                          variant="info"
                          title="还没有扫描记录"
                          message="执行过几次单股查询后，这里会自动加载最近结果，方便回看。"
                        />
                      )}
                    </div>
                  </PaperSectionCard>
                </div>
              </div>
            </div>
          </div>
        </section>

        <Drawer
          isOpen={historyOpen}
          onClose={() => setHistoryOpen(false)}
          title="单股查询历史"
          width="max-w-xl"
          side="right"
        >
          <div className="space-y-4">
            {historyError ? <ApiErrorAlert error={historyError} /> : null}

            {historyLoading ? (
              <InlineAlert
                variant="info"
                title="正在加载历史记录"
                message="正在从后端读取最近的单股查询结果。"
              />
            ) : null}

            {historyItems.length === 0 ? (
              <EmptyState
                title="暂无单股查询历史"
                description="查过几次股票之后，这里会从后端返回最近记录，方便你恢复查看和对照买点。"
                icon={<Clock3 className="h-8 w-8" />}
              />
            ) : null}

            <div className="space-y-3">
              {historyItems.map((item) => {
                const active = item.queryId === currentHistoryId;
                const restoring = historyRestoreId === item.queryId;
                const historyPlan = getHistoryEntryPlan(item);
                return (
                  <PaperListBlock
                    key={item.queryId}
                    className={[
                      'transition-colors',
                      active ? 'border-foreground/18 bg-foreground/[0.045]' : 'border-border/60 bg-background/70',
                    ].join(' ')}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-base font-semibold text-foreground">
                          {item.stockName || item.queryText || '单股查询'} <span className="text-secondary-text">{item.stockCode || '--'}</span>
                        </p>
                        <p className="mt-1 text-sm text-secondary-text">{formatHistoryTime(item.completedAt || item.createdAt)}</p>
                      </div>
                      <Badge variant={signalBadgeVariant(item.signal || '仅观察')} className="border-0">
                        {item.signal || '仅观察'}
                      </Badge>
                    </div>

                    <div className="mt-3 space-y-2 text-sm">
                      <p className="text-foreground">{getHistoryLabel(item)}</p>
                      <p className="text-secondary-text">
                        试仓区 {formatRange(historyPlan?.entryLower, historyPlan?.entryUpper)} · 突破 {formatNumber(historyPlan?.breakoutPrice)}
                      </p>
                    </div>

                    <div className="mt-4 flex items-center justify-end gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={!item.stockCode}
                        onClick={() => {
                          if (item.stockCode) {
                            setQuery(item.stockCode);
                          }
                        }}
                      >
                        填入代码
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        isLoading={restoring}
                        loadingText="恢复中..."
                        onClick={() => void handleHistoryRestore(item)}
                      >
                        恢复查看
                      </Button>
                    </div>
                  </PaperListBlock>
                );
              })}
            </div>
          </div>
        </Drawer>
      </AppPage>
    );
  }

  return (
    <AppPage className="!max-w-[1680px] px-3 md:px-5 lg:px-6">
      <section className="paper-hero text-foreground">
        <div className="grid xl:grid-cols-[minmax(0,1fr)_430px]">
          <div className="border-b border-border/70 px-5 py-6 lg:px-7 xl:border-b-0 xl:border-r">
            <div className="space-y-6">
              <PaperHeroHeader
                eyebrow="Single Stock Query"
                title="单股查询"
                description="把高频用到的输入、买点、历史回看和右侧总览收成一套更稳定的交易工作台，先回答现在怎么做，再展开辅助信息。"
                icon={<Target className="h-7 w-7" />}
              />

              <form className="paper-panel-subtle space-y-4 px-4 py-4 md:px-5" onSubmit={handleSubmit}>
                <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_110px_110px]">
                  <Input
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="输入股票或 ETF 代码/名称，例如 688629.SH / 512880.SH / 华丰科技"
                    className="h-12 rounded-2xl border-border/60 bg-background/78 text-foreground placeholder:text-muted-text"
                    hint="支持股票与 ETF 代码/名称。查询成功后会自动写入后端历史，方便回看和恢复查看。"
                  />
                  <Button
                    type="submit"
                    size="lg"
                    isLoading={isLoading}
                    loadingText="正在分析..."
                    className="h-12 rounded-2xl"
                  >
                    <Search className="h-4 w-4" />
                    开始查询
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    size="lg"
                    className="h-12 rounded-2xl border-border/60 bg-background/78 text-foreground hover:bg-card"
                    onClick={() => setHistoryOpen(true)}
                  >
                    <Clock3 className="h-4 w-4" />
                    历史查询
                  </Button>
                </div>

                <div className="grid gap-3 xl:grid-cols-[280px_minmax(0,1fr)]">
                  <Select
                    value={strategy}
                    onChange={setStrategy}
                    options={STRATEGY_OPTIONS.map((item) => ({ value: item.value, label: item.label }))}
                    label="策略视角"
                    className="max-w-[320px]"
                  />
                  <div className="paper-panel px-4 py-3 text-sm leading-6 text-secondary-text">
                    自动模式会并行评估低吸回踩、突破确认、趋势跟随和趋势持有；如果你已经知道自己只想看某一种买点，可以直接锁定对应策略。
                  </div>
                </div>

                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                  {QUICK_QUERIES.map((item) => (
                    <button
                      key={item.value}
                      type="button"
                      onClick={() => handleQuickQuery(item.value)}
                      className={cn(
                        'paper-list-card text-left transition-colors',
                        query === item.value
                          ? 'border-foreground/16 bg-foreground/[0.05]'
                          : 'hover:border-foreground/12 hover:bg-card',
                      )}
                    >
                      <p className="text-sm font-semibold text-foreground">{item.label}</p>
                      <p className="mt-2 text-xs leading-5 text-secondary-text">{item.note}</p>
                    </button>
                  ))}
                </div>
              </form>

              {error ? <ApiErrorAlert error={error} /> : null}
              {watchlistActionError ? <ApiErrorAlert error={watchlistActionError} /> : null}
              {watchlistActionMessage ? (
                <InlineAlert variant="success" title="观察池已更新" message={watchlistActionMessage} />
              ) : null}

              {isLoading && queryTask ? (
                <InlineAlert
                  variant="info"
                  title="单股查询正在后台处理"
                  message={queryTask.message || '正在获取日线、实时行情和基本面，请稍候。'}
                />
              ) : null}

              {result && hasPendingInputChange ? (
                <InlineAlert
                  title="输入已更新，当前结果还没有刷新"
                  message={`现在输入框里是 ${query.trim() || '--'}，页面仍然展示上一次查询：${lastResolvedInput || '--'}。点击“开始查询”后会重新分析。`}
                  variant="info"
                />
              ) : null}

              <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_310px]">
                <PaperSectionCard
                  eyebrow="Entry Decision"
                  title={result && entryPlan ? entryPlan.headline : '先回答现在能不能上，再展开辅助分析'}
                  description={result && entryPlan
                    ? entryPlan.summary
                    : '查询成功后，这里会先告诉你该低吸、等突破，还是暂时不要追，不再把所有字段一口气堆到首屏。'}
                  className="overflow-hidden"
                  actions={result && entryPlan ? (
                    <div className="space-y-2 xl:min-w-[228px]">
                      <Badge variant={signalBadgeVariant(result.signal)} className="border-0 px-3 py-1">
                        {result.signal}
                      </Badge>
                      <p className="text-xs leading-6 text-secondary-text">
                        {result.stockCode} {resultTimestamp ? `· 数据更新 ${formatHistoryTime(resultTimestamp)}` : ''}
                      </p>
                    </div>
                  ) : null}
                >
                  {result && entryPlan ? (
                    <div className="space-y-5">
                      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                        <PaperMetricCard
                          label="当前价格"
                          value={formatNumber(result.currentPrice)}
                          detail={formatPercent(result.pctChg, 2)}
                          valueClassName="text-[1.45rem]"
                          detailClassName={signedValueClass(result.pctChg)}
                          tone="default"
                        />
                        <PaperMetricCard
                          label="试仓区"
                          value={formatRange(entryPlan.entryLower, entryPlan.entryUpper)}
                          detail="优先等回踩到位"
                          tone="muted"
                        />
                        <PaperMetricCard
                          label="突破确认"
                          value={formatNumber(entryPlan.breakoutPrice)}
                          detail="放量再跟"
                          tone="muted"
                        />
                        <PaperMetricCard
                          label="禁追区"
                          value={formatNumber(entryPlan.noChasePrice)}
                          detail="超过这里尽量不追"
                          tone="alert"
                        />
                      </div>

                      <div className="flex flex-wrap items-center gap-3">
                        <Badge variant="default" className="border border-foreground/10 bg-foreground/5 px-3 py-1 text-xs text-foreground">
                          {result.strategyLabel || '自动决策'}
                        </Badge>
                        <Badge variant="default" className="border border-border/60 bg-background/70 px-3 py-1 text-xs text-foreground">
                          {result.trendStatus || result.pattern || '等待结构确认'}
                        </Badge>
                      </div>

                      <div className="grid gap-3 xl:grid-cols-3">
                        {entryPlan.strategies.map((strategy) => (
                          <PaperListBlock key={strategy.key} className={strategyToneClasses(strategy.tone)}>
                            <p className="text-sm font-semibold text-foreground">{strategy.title}</p>
                            <p className="mt-2 text-sm leading-6 text-secondary-text">{strategy.description}</p>
                          </PaperListBlock>
                        ))}
                      </div>

                      {result.strategyDecisions && result.strategyDecisions.length > 0 ? (
                        <div className="paper-panel-muted p-4">
                          <div className="flex items-center justify-between gap-3">
                            <div>
                              <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-secondary-text">Strategy Matrix</p>
                              <p className="mt-2 text-sm text-secondary-text">同一只票在不同策略视角下，会给出不同的买点判断。</p>
                            </div>
                          </div>
                          <div className="mt-4 grid gap-3 xl:grid-cols-2">
                            {result.strategyDecisions.map((decision) => (
                              <PaperListBlock
                                key={decision.key}
                                className={decision.matched ? strategyToneClasses(strategySignalTone(decision.signal)) : 'paper-panel-subtle text-secondary-text'}
                              >
                                <div className="flex items-center justify-between gap-3">
                                  <p className="text-sm font-semibold text-foreground">{decision.label}</p>
                                  <Badge variant={signalBadgeVariant(decision.signal)} className="border-0 px-2.5 py-1 text-[11px]">
                                    {decision.signal}
                                  </Badge>
                                </div>
                                <p className="mt-2 text-sm leading-6 text-secondary-text">
                                  {(decision.matched ? decision.selectedReasons : decision.excludedReasons)?.[0]
                                    ?? (decision.matched ? '当前更适合从这套策略视角切入。' : '当前还不满足这套策略的出手条件。')}
                                </p>
                                {decision.pattern ? (
                                  <p className="mt-3 text-xs uppercase tracking-[0.14em] text-secondary-text">{decision.pattern}</p>
                                ) : null}
                              </PaperListBlock>
                            ))}
                          </div>
                        </div>
                      ) : null}
                    </div>
                  ) : (
                    <div className="grid gap-3 xl:grid-cols-3">
                      {[
                        '买点优先：试仓区、突破位、止损线放在最前面。',
                        '历史前置：最近结论直接放进首屏，不再藏在二级页面。',
                        '辅助下沉：题材归因、数据覆盖改到右侧详情栏补充。',
                      ].map((item) => (
                        <PaperListBlock key={item} className="text-sm leading-6 text-secondary-text">
                          {item}
                        </PaperListBlock>
                      ))}
                    </div>
                  )}
                </PaperSectionCard>

                <PaperSectionCard
                  eyebrow="History Snapshot"
                  title="最近回看"
                  description="保留最近两次判断做对照，完整历史放到右侧详情和抽屉。"
                  actions={(
                    <Button variant="ghost" size="sm" className="text-secondary-text hover:bg-foreground/4 hover:text-foreground" onClick={() => setHistoryOpen(true)}>
                      全部历史
                    </Button>
                  )}
                >
                  <div className="space-y-3">
                    {historyError ? <ApiErrorAlert error={historyError} /> : null}
                    {historyLoading ? (
                      <InlineAlert
                        variant="info"
                        title="正在读取历史记录"
                        message="正在从后端加载最近的单股查询记录。"
                      />
                    ) : null}

                    {historyPreviewItems.length > 0 ? (
                      historyPreviewItems.map((item) => (
                        <button
                          key={item.queryId}
                          type="button"
                          onClick={() => void handleHistoryRestore(item)}
                          className="block w-full text-left"
                        >
                          <PaperListBlock className="transition-colors hover:border-foreground/10 hover:bg-card">
                            <p className="text-xs text-secondary-text">{formatHistoryTime(item.completedAt || item.createdAt)}</p>
                            <p className="mt-2 text-sm font-semibold text-foreground">
                              {(item.stockName || item.queryText || '单股查询')}
                              <span className="text-secondary-text">{` · ${item.signal || '仅观察'}`}</span>
                            </p>
                            <p className="mt-2 text-xs leading-6 text-secondary-text">
                              低吸 {formatRange(getHistoryEntryPlan(item)?.entryLower, getHistoryEntryPlan(item)?.entryUpper)}
                            </p>
                          </PaperListBlock>
                        </button>
                      ))
                    ) : (
                      <InlineAlert
                        variant="info"
                        title="还没有单股查询历史"
                        message="执行过几次单股查询后，这里会自动加载最近结果，方便你和今天的买点做对照。"
                      />
                    )}
                  </div>
                </PaperSectionCard>
              </div>

              {isLoading && !result ? (
                <PaperSectionCard eyebrow="Loading" title="正在拉取单股诊断结果" description="会先解析股票输入，再生成入场计划、买点区间和后端历史对照。">
                  <div className="flex items-center gap-4">
                    <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-border/60 bg-card text-foreground">
                      <Sparkles className="h-5 w-5 animate-pulse" />
                    </div>
                  </div>
                </PaperSectionCard>
              ) : null}

              {!result && !isLoading ? (
                <PaperSectionCard
                  eyebrow="Buy Point Ruler"
                  title="买点刻度尺会放在这里"
                  description="查询成功后，这里会把试仓区、现价、突破位和禁追区放到一条线上，让你第一眼看清离买点还有多远。"
                >
                  <div />
                </PaperSectionCard>
              ) : null}

              {result && entryPlan ? (
                <>
                  <PaperSectionCard
                    eyebrow="Buy Point Ruler"
                    title="买点刻度尺"
                    description="支撑、试仓区、当前价、突破位、禁追区放在一条线上，让页面第一眼就能读出离买点还有多远。"
                    actions={(
                      <div className="paper-panel-muted px-4 py-3 text-sm text-secondary-text">
                        当前建议：<span className="font-semibold text-foreground">{entryPlan.headline}</span>
                      </div>
                    )}
                  >
                    {priceRail ? (
                      <div className="paper-panel-muted px-5 py-6">
                        <div className="relative h-24">
                          <div className="absolute left-4 right-4 top-10 h-2.5 rounded-full bg-border/90" />
                          <div
                            className="absolute top-[37px] h-3.5 rounded-full bg-foreground/88"
                            style={{
                              left: `calc(${priceRail.entryStart}% + 1rem)`,
                              width: `${Math.max(priceRail.entryEnd - priceRail.entryStart, 2)}%`,
                            }}
                          />
                          <div
                            className="absolute top-[37px] h-3.5 rounded-full bg-foreground/55"
                            style={{
                              left: `calc(${priceRail.points.find((point) => point.key === 'breakout')?.position ?? priceRail.noChaseStart}% + 1rem)`,
                              width: `${Math.max(priceRail.noChaseStart - (priceRail.points.find((point) => point.key === 'breakout')?.position ?? priceRail.noChaseStart), 2)}%`,
                            }}
                          />
                          <div
                            className="absolute top-[37px] h-3.5 rounded-full bg-foreground/28"
                            style={{
                              left: `calc(${priceRail.noChaseStart}% + 1rem)`,
                              right: '1rem',
                            }}
                          />

                          {priceRail.points.map((point) => {
                            const isCurrent = point.key === 'current';
                            return (
                              <div
                                key={point.key}
                                className="absolute top-2 flex -translate-x-1/2 flex-col items-center gap-2"
                                style={{ left: `calc(${point.position}% + 1rem)` }}
                              >
                                <div className={`h-5 w-5 rounded-full border-4 ${markerToneClasses(point.tone, isCurrent)}`} />
                                <div className="min-w-[78px] text-center">
                                  <p className="text-xs font-semibold text-foreground">{point.label}</p>
                                  <p className="mt-1 text-xs text-secondary-text">{formatNumber(point.value)}</p>
                                </div>
                              </div>
                            );
                          })}
                        </div>

                        <div className="mt-8 grid gap-3 xl:grid-cols-4">
                          <MiniMetric label="试仓区" value={formatRange(entryPlan.entryLower, entryPlan.entryUpper)} tone="buy" />
                          <MiniMetric label="突破确认价" value={formatNumber(entryPlan.breakoutPrice)} tone="breakout" />
                          <MiniMetric label="止损线" value={formatNumber(entryPlan.stopLossPrice)} tone="warn" />
                          <MiniMetric label="禁追区" value={`${formatNumber(entryPlan.noChasePrice)} 以上`} tone="warn" />
                        </div>
                      </div>
                    ) : (
                      <InlineAlert
                        variant="info"
                        title="买点刻度尺暂时无法计算"
                        message="当前价格或关键位信息不够完整，先参考下方的入场清单和风险说明。"
                      />
                    )}
                  </PaperSectionCard>

                  <div className="grid gap-5 xl:grid-cols-[0.88fr_1.06fr_1.06fr]">
                    <PaperSectionCard eyebrow="Checklist" title="入场前 checklist" icon={<Target className="h-5 w-5" />} className="px-5 py-5">
                      <div className="space-y-3">
                        {entryPlan.checklist.map((item) => (
                          <PaperListBlock key={item} className="text-sm leading-6 text-foreground">
                            {item}
                          </PaperListBlock>
                        ))}
                      </div>
                    </PaperSectionCard>

                    <PaperSectionCard eyebrow="Why Watch" title="为什么还值得继续看" icon={<TrendingUp className="h-5 w-5" />} className="px-5 py-5">
                      <div className="space-y-3">
                        {result.selectedReasons.length > 0 ? (
                          result.selectedReasons.slice(0, 2).map((reason) => (
                            <PaperListBlock key={reason} className="text-sm leading-6 text-foreground">
                              {reason}
                            </PaperListBlock>
                          ))
                        ) : (
                          <InlineAlert
                            variant="info"
                            title="当前没有特别强的关注理由"
                            message="系统没有识别到足够明确的强势条件，这时候更适合继续观察。"
                          />
                        )}
                      </div>

                      <div className="mt-5 grid gap-3 sm:grid-cols-2">
                        <MiniMetric label="趋势分" value={formatNumber(result.trendScore, 1)} tone="buy" />
                        <MiniMetric label="趋势状态" value={result.trendStatus ?? '--'} tone="neutral" />
                      </div>
                    </PaperSectionCard>

                    <PaperSectionCard eyebrow="Why Wait" title="为什么现在不能太激进" icon={<AlertTriangle className="h-5 w-5" />} className="px-5 py-5">
                      <div className="space-y-3">
                        {result.excludedReasons.length > 0 ? (
                          result.excludedReasons.slice(0, 2).map((reason) => (
                            <div key={reason} className="paper-alert-card px-4 py-4 text-sm leading-6 text-foreground">
                              {reason}
                            </div>
                          ))
                        ) : (
                          <InlineAlert
                            variant="success"
                            title="当前没有强排除项"
                            message="这不等于可以无脑上车，只代表系统没有识别到特别显眼的风险标签。"
                          />
                        )}
                      </div>

                      <div className="paper-alert-card mt-5 px-4 py-4">
                        <p className="text-sm leading-6 text-foreground">{entryPlan.summary}</p>
                      </div>
                    </PaperSectionCard>
                  </div>

                  {hasFundamentalBlocks ? (
                    <PaperSectionCard
                      eyebrow="Fundamental Context"
                      title="基本面分块上下文"
                      description="这里优先展示底层基本面拿到了什么、缺了什么、是否能直接作为交易判断依据，比近期催化更靠前。"
                      actions={(
                        <Badge variant={fundamentalContext?.status === 'ok' ? 'success' : 'warning'} className="border-0 px-3 py-1">
                          {coverageStatusLabel(fundamentalContext?.status || 'partial')}
                        </Badge>
                      )}
                    >
                      <div className="grid gap-3 xl:grid-cols-3">
                        <PaperDataBlockCard
                          title="估值"
                          subtitle={`来源 ${sourceChainSummary(valuationBlock?.sourceChain)}`}
                          status={(
                            <Badge variant={valuationBlock?.status === 'ok' || valuationBlock?.status === 'full' ? 'success' : valuationBlock?.status === 'partial' ? 'warning' : 'default'} className="border-0 px-2 py-1">
                              {coverageStatusLabel(valuationBlock?.status || 'failed')}
                            </Badge>
                          )}
                          footer={valuationBlock?.errors?.length ? <p className="text-xs leading-5 text-secondary-text">错误: {valuationBlock.errors.slice(0, 2).join(' | ')}</p> : null}
                        >
                          <div className="grid gap-3 sm:grid-cols-2">
                            <MiniMetric label="PE" value={formatNumber(valuation?.peRatio)} tone="neutral" />
                            <MiniMetric label="PB" value={formatNumber(valuation?.pbRatio)} tone="neutral" />
                            <MiniMetric label="总市值" value={formatMoney(valuation?.totalMv)} tone="neutral" />
                            <MiniMetric label="流通市值" value={formatMoney(valuation?.circMv)} tone="neutral" />
                          </div>
                        </PaperDataBlockCard>

                        <PaperDataBlockCard
                          title="成长"
                          subtitle={`来源 ${sourceChainSummary(growthBlock?.sourceChain)}`}
                          status={(
                            <Badge variant={growthBlock?.status === 'ok' || growthBlock?.status === 'full' ? 'success' : growthBlock?.status === 'partial' ? 'warning' : 'default'} className="border-0 px-2 py-1">
                              {coverageStatusLabel(growthBlock?.status || 'failed')}
                            </Badge>
                          )}
                          footer={growthBlock?.errors?.length ? <p className="text-xs leading-5 text-secondary-text">错误: {growthBlock.errors.slice(0, 2).join(' | ')}</p> : null}
                        >
                          <div className="grid gap-3 sm:grid-cols-2">
                            <MiniMetric label="营收同比" value={formatPercent(growth?.revenueYoy, 1)} tone="neutral" />
                            <MiniMetric label="净利同比" value={formatPercent(growth?.netProfitYoy, 1)} tone="neutral" />
                            <MiniMetric label="ROE" value={formatPercent(growth?.roe, 1)} tone="neutral" />
                            <MiniMetric label="毛利率" value={formatPercent(growth?.grossMargin, 1)} tone="neutral" />
                          </div>
                        </PaperDataBlockCard>

                        <PaperDataBlockCard
                          title="盈利"
                          subtitle={`来源 ${sourceChainSummary(earningsBlock?.sourceChain)}`}
                          status={(
                            <Badge variant={earningsBlock?.status === 'ok' || earningsBlock?.status === 'full' ? 'success' : earningsBlock?.status === 'partial' ? 'warning' : 'default'} className="border-0 px-2 py-1">
                              {coverageStatusLabel(earningsBlock?.status || 'failed')}
                            </Badge>
                          )}
                          footer={(
                            <>
                              <p className="text-xs leading-5 text-secondary-text">
                                {earnings?.forecastSummary || earnings?.quickReportSummary || '当前没有拿到明确的业绩预告摘要。'}
                              </p>
                              {earningsBlock?.errors?.length ? <p className="text-xs leading-5 text-secondary-text">错误: {earningsBlock.errors.slice(0, 2).join(' | ')}</p> : null}
                            </>
                          )}
                        >
                          <div className="grid gap-3 sm:grid-cols-2">
                            <MiniMetric label="报告期" value={earnings?.financialReport?.reportDate ?? '--'} tone="neutral" />
                            <MiniMetric label="股息率" value={formatPercent(earnings?.dividend?.ttmDividendYieldPct, 2)} tone="neutral" />
                            <MiniMetric label="营收" value={formatMoney(earnings?.financialReport?.revenue)} tone="neutral" />
                            <MiniMetric label="净利润" value={formatMoney(earnings?.financialReport?.netProfitParent)} tone="neutral" />
                          </div>
                        </PaperDataBlockCard>
                      </div>

                      <div className="mt-3 grid gap-3 xl:grid-cols-2">
                        <PaperDataBlockCard
                          title="机构"
                          subtitle={`来源 ${sourceChainSummary(institutionBlock?.sourceChain)}`}
                          status={(
                            <Badge variant={institutionBlock?.status === 'ok' || institutionBlock?.status === 'full' ? 'success' : institutionBlock?.status === 'partial' ? 'warning' : 'default'} className="border-0 px-2 py-1">
                              {coverageStatusLabel(institutionBlock?.status || 'failed')}
                            </Badge>
                          )}
                          footer={(
                            <>
                              {institution?.textSummary ? (
                                <p className="text-xs leading-5 text-secondary-text">
                                  文本补充{institution.textProvider ? ` · ${institution.textProvider}` : ''}：{institution.textSummary}
                                </p>
                              ) : null}
                              {institutionBlock?.errors?.length ? <p className="text-xs leading-5 text-secondary-text">错误: {institutionBlock.errors.slice(0, 2).join(' | ')}</p> : null}
                            </>
                          )}
                        >
                          <div className="grid gap-3 sm:grid-cols-2">
                            <MiniMetric label="机构持仓变化" value={formatPercent(institution?.institutionHoldingChange, 1)} tone="neutral" />
                            <MiniMetric label="前十股东变化" value={formatPercent(institution?.top10HolderChange, 1)} tone="neutral" />
                          </div>
                        </PaperDataBlockCard>

                        <PaperDataBlockCard
                          title="资金流"
                          subtitle={`来源 ${sourceChainSummary(capitalFlowBlock?.sourceChain)}`}
                          status={(
                            <Badge variant={capitalFlowBlock?.status === 'ok' || capitalFlowBlock?.status === 'full' ? 'success' : capitalFlowBlock?.status === 'partial' ? 'warning' : 'default'} className="border-0 px-2 py-1">
                              {coverageStatusLabel(capitalFlowBlock?.status || 'failed')}
                            </Badge>
                          )}
                          footer={capitalFlowBlock?.errors?.length ? <p className="text-xs leading-5 text-secondary-text">错误: {capitalFlowBlock.errors.slice(0, 2).join(' | ')}</p> : null}
                        >
                          <div className="grid gap-3 sm:grid-cols-3">
                            <MiniMetric label="主力净流入" value={formatMoney(capitalFlow?.mainNetInflow)} tone="neutral" />
                            <MiniMetric label="5日净流入" value={formatMoney(capitalFlow?.inflow5d)} tone="neutral" />
                            <MiniMetric label="10日净流入" value={formatMoney(capitalFlow?.inflow10d)} tone="neutral" />
                          </div>
                        </PaperDataBlockCard>
                      </div>

                      <div className="mt-3 grid gap-3 xl:grid-cols-[0.85fr_1.15fr]">
                        <PaperDataBlockCard
                          title="龙虎榜"
                          subtitle={`来源 ${sourceChainSummary(dragonTigerBlock?.sourceChain)}`}
                          status={(
                            <Badge variant={dragonTigerBlock?.status === 'ok' || dragonTigerBlock?.status === 'full' ? 'success' : dragonTigerBlock?.status === 'partial' ? 'warning' : 'default'} className="border-0 px-2 py-1">
                              {coverageStatusLabel(dragonTigerBlock?.status || 'failed')}
                            </Badge>
                          )}
                          footer={(
                            <>
                              {dragonTiger?.reason ? <p className="text-xs leading-5 text-secondary-text">上榜原因：{dragonTiger.reason}</p> : null}
                              {dragonTiger?.buySeats?.length ? <p className="text-xs leading-5 text-secondary-text">买入席位：{dragonTiger.buySeats.slice(0, 3).join(' / ')}</p> : null}
                              {dragonTiger?.sellSeats?.length ? <p className="text-xs leading-5 text-secondary-text">卖出席位：{dragonTiger.sellSeats.slice(0, 3).join(' / ')}</p> : null}
                              {dragonTigerBlock?.errors?.length ? <p className="text-xs leading-5 text-secondary-text">错误: {dragonTigerBlock.errors.slice(0, 2).join(' | ')}</p> : null}
                            </>
                          )}
                        >
                          <div className="grid gap-3 sm:grid-cols-2">
                            <MiniMetric
                              label="近20日状态"
                              value={dragonTiger?.isOnList ? `上榜 ${dragonTiger.recentCount ?? 0} 次` : '未识别到上榜'}
                              tone="neutral"
                            />
                            <MiniMetric label="最近日期" value={dragonTiger?.latestDate ?? '--'} tone="neutral" />
                            <MiniMetric label="净买额" value={formatMoney(dragonTiger?.netBuyAmount)} tone="neutral" />
                            <MiniMetric label="机构净买" value={formatMoney(dragonTiger?.institutionNetBuy)} tone="neutral" />
                          </div>
                        </PaperDataBlockCard>

                        <PaperDataBlockCard
                          title="所属板块"
                          subtitle={`板块来源 ${boardSourceLabel(boardSource, boardProvider)}`}
                          status={(
                            <Badge variant={boardsBlock?.status === 'ok' || boardsBlock?.status === 'full' ? 'success' : boardsBlock?.status === 'partial' ? 'warning' : 'default'} className="border-0 px-2 py-1">
                              {coverageStatusLabel(boardsBlock?.status || 'failed')}
                            </Badge>
                          )}
                          footer={boardsBlock?.errors?.length ? <p className="text-xs leading-5 text-secondary-text">错误: {boardsBlock.errors.slice(0, 2).join(' | ')}</p> : null}
                        >
                          {boardItems.length > 0 ? (
                            <div className="flex flex-wrap gap-2">
                              {boardItems.slice(0, 10).map((board) => (
                                <div key={`${board.name}-${board.code ?? ''}`} className="paper-chip px-3 py-2">
                                  <p className="text-sm font-medium text-foreground">{board.name}</p>
                                  {boardCaption(board) ? (
                                    <p className="mt-1 text-[11px] text-secondary-text">{boardCaption(board)}</p>
                                  ) : null}
                                </div>
                              ))}
                            </div>
                          ) : null}
                        </PaperDataBlockCard>
                      </div>
                    </PaperSectionCard>
                  ) : null}
                </>
              ) : null}
            </div>
          </div>

          <aside className="paper-panel px-5 py-6 lg:px-6">
            <div className="space-y-5 xl:sticky xl:top-24">
              <div>
                <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-secondary-text">Result Overview</p>
                <h3 className="mt-1 text-lg font-semibold text-foreground">股票详情</h3>
                <div className="mt-3 h-px bg-border/70" />
              </div>

              <div className="paper-panel-subtle px-4 py-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-end gap-3">
                      <h4 className="text-[2rem] font-semibold tracking-[-0.03em] text-foreground">{result?.stockName ?? '等待查询结果'}</h4>
                      <span className="text-sm text-secondary-text">{result?.stockCode ?? '--'}</span>
                    </div>
                    <p className="mt-2 text-xs leading-6 text-secondary-text">
                      {resultTimestamp ? `数据更新 ${formatHistoryTime(resultTimestamp)}` : '查询完成后会展示最新结果时间'}
                    </p>
                  </div>
                  {instrumentBadgeLabel(result?.instrumentLabel, result?.instrumentType) ? (
                    <Badge variant="info" className="border-0 px-3 py-1">
                      {instrumentBadgeLabel(result?.instrumentLabel, result?.instrumentType)}
                    </Badge>
                  ) : null}
                </div>
                <div className="mt-5 flex flex-wrap items-end gap-3">
                  <p className="text-[2.15rem] font-semibold tracking-[-0.03em] text-foreground">{formatNumber(result?.currentPrice)}</p>
                  <p className={`text-[1.55rem] font-semibold ${signedValueClass(result?.pctChg)}`}>
                    {formatPercent(result?.pctChg, 2)}
                  </p>
                </div>
                <p className="mt-3 text-sm leading-6 text-secondary-text">
                  {result && entryPlan
                    ? '右侧只保留高频复核信息，尽量让你在一列里完成二次确认。'
                    : '查询成功后，这里会汇总股票详情、关键信号、关键位和最近几次判断。'}
                </p>
              </div>

              <PaperSectionCard eyebrow="交易总览" title={signalOverview?.label ?? '等待信号'} className="px-5 py-5">
                <p className="text-sm leading-6 text-secondary-text">
                  {signalOverview?.description ?? '先完成一次查询，这里会告诉你更适合等回踩、等突破，还是保持观察。'}
                </p>
                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  <PaperMetricCard label="信号分" value={signalOverview?.score ?? '--'} valueClassName="text-[1.4rem]" tone="default" />
                  <PaperMetricCard label="主信号" value={result?.signal ?? '--'} tone="muted" />
                  <PaperMetricCard label="策略视角" value={result?.strategyLabel || '自动决策'} tone="muted" />
                  <PaperMetricCard label="试仓区" value={formatRange(entryPlan?.entryLower, entryPlan?.entryUpper)} tone="muted" />
                  <PaperMetricCard label="突破位" value={formatNumber(entryPlan?.breakoutPrice)} tone="muted" />
                  <PaperMetricCard label="止损线" value={formatNumber(entryPlan?.stopLossPrice)} tone="alert" />
                </div>
              </PaperSectionCard>

              <PaperSectionCard eyebrow="技术结构" className="px-5 py-5" bodyClassName="space-y-0">
                <div className="mt-5 space-y-4">
                  <DetailMetricRow label="趋势方向" value={result?.trendStatus ?? '--'} accent="success" />
                  <DetailMetricRow label="形态结构" value={result?.pattern ?? '--'} accent="success" />
                  <DetailMetricRow label="动量状态" value={result?.buySignal ?? result?.signal ?? '--'} accent="success" />
                </div>
              </PaperSectionCard>

              <div className="grid gap-4 sm:grid-cols-2">
                <PaperSectionCard eyebrow="关键位" className="px-5 py-5" bodyClassName="space-y-0">
                  <div className="mt-5 space-y-3">
                    <DetailMetricRow label="支撑位" value={formatNumber(entryPlan?.supportPrice)} accent="success" />
                    <DetailMetricRow label="强支撑" value={formatNumber(entryPlan?.stopLossPrice)} accent="neutral" />
                    <DetailMetricRow label="突破位" value={formatNumber(entryPlan?.breakoutPrice)} accent="warning" />
                  </div>
                </PaperSectionCard>

                <PaperSectionCard eyebrow="均线位置" className="px-5 py-5" bodyClassName="space-y-0">
                  <div className="mt-5 space-y-3">
                    <DetailMetricRow label="MA10" value={formatNumber(result?.ma10)} accent="neutral" />
                    <DetailMetricRow label="MA20" value={formatNumber(result?.ma20)} accent="neutral" />
                    <DetailMetricRow label="PE / PB" value={`PE ${formatNumber(result?.peRatio)} / PB ${formatNumber(result?.pbRatio)}`} accent="neutral" />
                  </div>
                </PaperSectionCard>
              </div>

              <PaperSectionCard eyebrow="查询历史" title="这只票最近怎么看" className="px-5 py-5">
                <div className="mt-4 space-y-3">
                  {historyComparison ? (
                    <PaperListBlock>
                      <p className="text-sm font-semibold text-foreground">{historyComparison.headline}</p>
                      <p className="mt-2 text-sm leading-6 text-secondary-text">{historyComparison.description}</p>
                    </PaperListBlock>
                  ) : null}

                  {rightRailHistory.length > 0 ? (
                    rightRailHistory.map((item) => (
                      <button
                        key={item.queryId}
                        type="button"
                        onClick={() => void handleHistoryRestore(item)}
                        className="block w-full text-left"
                      >
                        <PaperListBlock className="py-3 transition-colors hover:border-foreground/15 hover:bg-card">
                          <p className="text-xs text-secondary-text">{formatHistoryTime(item.completedAt || item.createdAt)}</p>
                          <p className="mt-1 text-sm text-foreground">{getHistoryLabel(item)}</p>
                        </PaperListBlock>
                      </button>
                    ))
                  ) : (
                    <p className="text-sm leading-6 text-secondary-text">查过几次之后，这里会直接显示最近几次对这只票的判断。</p>
                  )}
                </div>
              </PaperSectionCard>

              <PaperSectionCard
                eyebrow="联动操作"
                title="把这次判断接到后续动作"
                description="如果这只票值得继续跟，就在这里直接接深度分析、观察池和默认告警。"
                className="px-5 py-5"
              >
                <div className="grid gap-3 sm:grid-cols-3">
                  <Link
                    to={
                      result?.queryId
                        ? `/deep-analysis?queryId=${encodeURIComponent(result.queryId)}&stock=${encodeURIComponent(result.stockCode)}&name=${encodeURIComponent(result.stockName)}`
                        : '/deep-analysis'
                    }
                    className="inline-flex min-h-12 items-center justify-center rounded-2xl border border-foreground/15 bg-foreground px-4 py-3 text-sm font-medium text-background shadow-soft-card transition hover:opacity-92"
                  >
                    发起深度分析
                  </Link>
                  <Button
                    type="button"
                    isLoading={watchlistLoading}
                    loadingText="加入中..."
                    disabled={!result || isInWatchlist}
                    onClick={() => void handleAddToWatchlist()}
                    className="min-h-12 rounded-2xl border border-border/60 bg-card px-4 py-3 text-sm font-medium text-foreground transition hover:bg-background"
                  >
                    {isInWatchlist ? '已在观察池' : '加入观察池'}
                  </Button>
                  <button
                    type="button"
                    disabled={!result || hasStockAlertRules || alertRuleLoading}
                    onClick={() => void handleCreateDefaultAlerts()}
                    className="paper-panel-subtle inline-flex min-h-12 items-center justify-center rounded-2xl px-4 py-3 text-sm font-medium text-foreground enabled:cursor-pointer enabled:hover:border-foreground/12 enabled:hover:bg-card disabled:opacity-60"
                  >
                    {alertRuleLoading ? '创建中...' : hasStockAlertRules ? '告警已设置' : '设置告警'}
                  </button>
                </div>

                <div className="mt-4 grid gap-3 md:grid-cols-[minmax(0,220px)_1fr]">
                  <Input
                    label="告警扫描间隔(分钟)"
                    value={alertScanInterval}
                    onChange={(event) => setAlertScanInterval(event.target.value)}
                    placeholder={`默认 ${MIN_ALERT_SCAN_INTERVAL_MINUTES}`}
                    className="h-11 rounded-2xl"
                  />
                  <div className="paper-panel-muted flex items-center justify-between gap-3 px-4 py-3">
                    <div>
                      <p className="text-sm font-medium text-foreground">扫描频率由输入决定</p>
                      <p className="mt-1 text-xs leading-6 text-secondary-text">单位分钟，最小 {MIN_ALERT_SCAN_INTERVAL_MINUTES} 分钟。创建默认规则时会同步写入每条规则。</p>
                    </div>
                    <Badge variant="info" className="border-0 px-3 py-1">
                      默认 {MIN_ALERT_SCAN_INTERVAL_MINUTES} 分钟
                    </Badge>
                  </div>
                </div>
              </PaperSectionCard>

              {(topTheme || conceptAttribution || stockContextSupplement || fundamentalCoverageEntries.length > 0) ? (
                <div className="space-y-4">
                  {topTheme ? (
                    <PaperSectionCard eyebrow="辅助题材" title={topTheme.themeName} className="px-5 py-5" actions={<Badge variant="info" className="border-0 px-3 py-1">{themeAttributions.length} 个主题</Badge>}>
                      <p className="mt-3 text-sm leading-6 text-secondary-text">
                        {confidenceLabel(topTheme.confidence)} · {relationTypeLabel(topTheme.relationType)}
                      </p>
                      <p className="mt-2 text-sm leading-6 text-foreground">{topTheme.reason}</p>
                      {topTheme.matchedBoards?.length ? (
                        <div className="mt-3 flex flex-wrap gap-2">
                          {topTheme.matchedBoards.slice(0, 4).map((item) => (
                            <span key={item} className="paper-chip px-3 py-2 text-xs font-medium text-foreground">
                              {item}
                            </span>
                          ))}
                        </div>
                      ) : null}
                      {conceptAttribution?.summary ? (
                        <p className="mt-3 text-xs leading-6 text-secondary-text">{conceptAttribution.summary}</p>
                      ) : null}
                    </PaperSectionCard>
                  ) : null}

                  {(conceptAttribution || stockContextSupplement?.profile || stockContextSupplement?.announcements || stockContextSupplement?.lockup) ? (
                    <PaperSectionCard
                      eyebrow="补充信息"
                      title="公司画像 / 公告 / 解禁"
                      className="px-5 py-5"
                      actions={<Badge variant="default" className="border-0 px-3 py-1">{stockContextSupplement?.profile?.provider || stockContextSupplement?.announcements?.provider || 'search'}</Badge>}
                    >

                      {conceptAttribution?.summary ? (
                        <div className="paper-list-card mt-4 px-4 py-4">
                          <p className="text-sm font-semibold text-foreground">概念归因</p>
                          <p className="mt-2 text-sm leading-6 text-secondary-text">{conceptAttribution.summary}</p>
                          {conceptAttribution.conceptNames?.length ? (
                            <div className="mt-3 flex flex-wrap gap-2">
                              {conceptAttribution.conceptNames.slice(0, 5).map((item) => (
                                <span key={item} className="paper-chip px-3 py-2 text-xs font-medium text-foreground">
                                  {item}
                                </span>
                              ))}
                            </div>
                          ) : null}
                        </div>
                      ) : null}

                      <div className="mt-4 space-y-3">
                        <PaperSummaryBlock
                          title="公司画像"
                          summary={stockContextSupplement?.profile?.summary}
                          items={profileHighlights}
                        />
                        <PaperSummaryBlock
                          title="近期公告"
                          summary={stockContextSupplement?.announcements?.summary}
                          items={announcementHighlights}
                        />
                        <PaperSummaryBlock
                          title="解禁提示"
                          summary={stockContextSupplement?.lockup?.summary}
                          items={lockupHighlights}
                          danger
                        />
                      </div>
                    </PaperSectionCard>
                  ) : null}

                  {stockNewsSummary ? (
                    <PaperSectionCard
                      eyebrow="近期催化"
                      title="近期催化 / 新闻摘要"
                      className="px-5 py-5"
                      actions={(
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant={newsSentimentVariant(stockNewsSummary.sentiment)} className="border-0 px-3 py-1">
                            {newsSentimentLabel(stockNewsSummary.sentiment)}
                          </Badge>
                          <Badge variant="default" className="border-0 px-3 py-1">
                            {stockNewsSummary.provider || 'search'}
                          </Badge>
                        </div>
                      )}
                    >

                      <p className="mt-4 text-sm leading-6 text-secondary-text">
                        {stockNewsSummary.summary || '当前没有拿到足够清晰的新闻摘要。'}
                      </p>

                      <div className="mt-4 space-y-3">
                        <div className="paper-list-card px-4 py-4">
                          <p className="text-sm font-semibold text-foreground">正向催化</p>
                          <div className="mt-3 flex flex-wrap gap-2">
                            {(stockNewsSummary.catalysts?.length ? stockNewsSummary.catalysts : ['暂无明确催化']).map((item) => (
                              <span key={item} className="paper-chip px-3 py-2 text-xs font-medium text-foreground">
                                {item}
                              </span>
                            ))}
                          </div>
                        </div>

                        <div className="paper-alert-card px-4 py-4">
                          <p className="text-sm font-semibold text-foreground">明确风险</p>
                          <div className="mt-3 flex flex-wrap gap-2">
                            {(stockNewsSummary.riskEvents?.length ? stockNewsSummary.riskEvents : ['暂未识别明显利空']).map((item) => (
                              <span key={item} className="paper-chip px-3 py-2 text-xs font-medium text-foreground">
                                {item}
                              </span>
                            ))}
                          </div>
                        </div>

                        <div className="paper-list-card px-4 py-4">
                          <p className="text-sm font-semibold text-foreground">最近三条标题</p>
                          <div className="mt-3 space-y-2">
                            {(stockNewsSummary.headlines?.length ? stockNewsSummary.headlines : ['当前没有拿到明确的相关新闻标题。']).map((headline) => (
                              <div key={headline} className="paper-panel-subtle px-4 py-3">
                                <p className="text-sm leading-6 text-foreground">{headline}</p>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    </PaperSectionCard>
                  ) : null}

                  {fundamentalCoverageEntries.length > 0 ? (
                    <PaperSectionCard
                      eyebrow="数据覆盖"
                      title="基本面与数据源"
                      className="px-5 py-5"
                      actions={<Badge variant={incompleteFundamentalEntries.length > 0 ? 'warning' : 'success'} className="border-0 px-3 py-1">{incompleteFundamentalEntries.length > 0 ? `仍缺 ${incompleteFundamentalEntries.length} 项` : '已完整返回'}</Badge>}
                    >
                      <div className="mt-4 grid gap-3 sm:grid-cols-2">
                        <PaperMetricCard label="日线" value={sourceLabel(result?.dataSources.daily)} valueClassName="text-sm font-medium" />
                        <PaperMetricCard label="实时" value={sourceLabel(result?.dataSources.realtime)} valueClassName="text-sm font-medium" />
                        <PaperMetricCard label="筹码" value={sourceLabel(result?.dataSources.chip)} valueClassName="text-sm font-medium" />
                        <PaperMetricCard label="基本面" value={sourceLabel(result?.dataSources.fundamental ?? fundamentalContext?.status)} valueClassName="text-sm font-medium" />
                        <PaperMetricCard label="总状态" value={coverageStatusLabel(fundamentalContext?.status || '--')} valueClassName="text-sm font-medium" />
                        <PaperMetricCard label="耗时" value={fundamentalContext?.elapsedMs ? `${fundamentalContext.elapsedMs}ms` : '--'} valueClassName="text-sm font-medium" />
                      </div>

                      <div className="mt-4 grid gap-3 sm:grid-cols-2">
                        {fundamentalCoverageEntries.map(([key, status]) => (
                          <div key={key} className={`rounded-[18px] border px-4 py-3 ${coverageTone(status)}`}>
                            <p className="text-sm font-semibold">{fundamentalBlockLabel(key)}</p>
                            <p className="mt-1 text-sm">{coverageStatusLabel(status)}</p>
                          </div>
                        ))}
                      </div>

                      {fundamentalErrorPreview.length > 0 ? (
                        <p className="mt-4 text-xs leading-6 text-secondary-text">最近错误: {fundamentalErrorPreview.join(' | ')}</p>
                      ) : null}
                    </PaperSectionCard>
                  ) : null}
                </div>
              ) : null}
            </div>
          </aside>
        </div>
      </section>

      <Drawer
        isOpen={historyOpen}
        onClose={() => setHistoryOpen(false)}
        title="单股查询历史"
        width="max-w-xl"
        side="right"
      >
        <div className="space-y-4">
          {historyError ? <ApiErrorAlert error={historyError} /> : null}

          {historyLoading ? (
            <InlineAlert
              variant="info"
              title="正在加载历史记录"
              message="正在从后端读取最近的单股查询结果。"
            />
          ) : null}

          {historyItems.length === 0 ? (
            <EmptyState
              title="暂无单股查询历史"
              description="查过几次股票之后，这里会从后端返回最近记录，方便你恢复查看和对照买点。"
              icon={<Clock3 className="h-8 w-8" />}
            />
          ) : null}

          <div className="space-y-3">
            {historyItems.map((item) => {
              const active = item.queryId === currentHistoryId;
              const restoring = historyRestoreId === item.queryId;
              const historyPlan = getHistoryEntryPlan(item);
              return (
                <PaperListBlock
                  key={item.queryId}
                  className={[
                    'transition-colors',
                    active ? 'border-foreground/18 bg-foreground/[0.045]' : 'border-border/60 bg-background/70',
                  ].join(' ')}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-base font-semibold text-foreground">
                        {item.stockName || item.queryText || '单股查询'} <span className="text-secondary-text">{item.stockCode || '--'}</span>
                      </p>
                      <p className="mt-1 text-sm text-secondary-text">{formatHistoryTime(item.completedAt || item.createdAt)}</p>
                    </div>
                    <Badge variant={signalBadgeVariant(item.signal || '仅观察')} className="border-0">
                      {item.signal || '仅观察'}
                    </Badge>
                  </div>

                  <div className="mt-3 space-y-2 text-sm">
                    <p className="text-foreground">{getHistoryLabel(item)}</p>
                    <p className="text-secondary-text">
                      试仓区 {formatRange(historyPlan?.entryLower, historyPlan?.entryUpper)} · 突破 {formatNumber(historyPlan?.breakoutPrice)}
                    </p>
                  </div>

                  <div className="mt-4 flex items-center justify-end gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={!item.stockCode}
                      onClick={() => {
                        if (item.stockCode) {
                          setQuery(item.stockCode);
                        }
                      }}
                    >
                      填入代码
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      isLoading={restoring}
                      loadingText="恢复中..."
                      onClick={() => void handleHistoryRestore(item)}
                    >
                      恢复查看
                    </Button>
                  </div>
                </PaperListBlock>
              );
            })}
          </div>
        </div>
      </Drawer>
    </AppPage>
  );
};

type MiniMetricProps = {
  label: string;
  value: string;
  tone: StrategyTone | 'neutral';
};

const MiniMetric: React.FC<MiniMetricProps> = ({ label, value, tone }) => {
  const toneClass = tone === 'buy'
    ? 'paper-list-card'
    : tone === 'breakout'
      ? 'paper-panel-muted'
      : tone === 'warn'
        ? 'paper-alert-card'
        : 'paper-panel';

  return (
    <div className={`${toneClass} px-4 py-4`}>
      <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">{label}</p>
      <p className="mt-3 text-sm font-semibold text-foreground">{value}</p>
    </div>
  );
};

type DetailMetricRowProps = {
  label: string;
  value: string;
  accent?: 'success' | 'warning' | 'neutral';
};

const DetailMetricRow: React.FC<DetailMetricRowProps> = ({ label, value, accent = 'neutral' }) => {
  const valueClass = accent === 'success'
    ? 'text-foreground'
    : accent === 'warning'
      ? 'text-foreground'
      : 'text-foreground';

  return (
    <div className="flex items-center justify-between gap-4 text-sm">
      <span className="text-secondary-text">{label}</span>
      <span className={`text-right font-semibold ${valueClass}`}>{value}</span>
    </div>
  );
};

export default SingleStockQueryPage;
