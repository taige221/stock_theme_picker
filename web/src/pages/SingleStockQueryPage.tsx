import type React from 'react';
import { useEffect, useEffectEvent, useMemo, useRef, useState } from 'react';
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
import { ApiErrorAlert, AppPage, Badge, Button, Drawer, EmptyState, InlineAlert, Input } from '../components/common';

const QUICK_QUERIES = [
  { label: '华丰科技', value: '688629.SH', note: '算力链中的高热度样本' },
  { label: '优博讯', value: '300531.SZ', note: '适合看异动与题材归因' },
  { label: '景旺电子', value: '603228.SH', note: '适合看趋势与支撑位' },
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
  if (signal === '持有候选') return 'warning';
  if (signal === '低吸观察') return 'info';
  if (signal === '不宜追高' || signal === '仅观察') return 'default';
  return 'success';
}

function confidenceLabel(value: string): string {
  if (value === 'high') return '高置信';
  if (value === 'medium') return '中置信';
  if (value === 'low') return '低置信';
  return value || '待判定';
}

function relationTypeLabel(value: string): string {
  if (value === 'direct_stock_pool') return '股票池直连';
  if (value === 'manual_map') return '人工映射';
  if (value === 'rule_map') return '规则映射';
  return value || '待判定';
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
  if (tone === 'buy') return 'border-cyan/30 bg-cyan/10';
  if (tone === 'breakout') return 'border-warning/20 bg-warning/10';
  return 'border-danger/20 bg-danger/10';
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
  if (current) return 'border-cyan bg-card shadow-lg shadow-cyan/20';
  if (tone === 'buy') return 'border-success/50 bg-success';
  if (tone === 'breakout') return 'border-warning/40 bg-warning';
  if (tone === 'warn') return 'border-danger/40 bg-danger';
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

  const loadHistory = useEffectEvent(async () => {
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
  });

  const loadWatchlist = useEffectEvent(async () => {
    try {
      const response = await watchlistApi.listStocks();
      setWatchlistItems(response.items);
    } catch {
      // Ignore passive watchlist load failures on the stock page.
    }
  });

  const loadStockAlertRules = useEffectEvent(async (stockCode?: string) => {
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
  });

  useEffect(() => {
    void loadHistory();
    void loadWatchlist();
  }, []);

  useEffect(() => () => {
    if (pollTimeoutRef.current != null) {
      window.clearTimeout(pollTimeoutRef.current);
    }
  }, []);

  const applyAnalyzeResult = useEffectEvent(async (response: StockQueryAnalyzeResponse, resolvedInput: string) => {
    setResult(response);
    setCurrentHistoryId(response.queryId ?? null);
    setLastResolvedInput(resolvedInput);
    setQueryTask(null);
    void loadStockAlertRules(response.stockCode);
    void loadHistory();
  });

  const pollAnalyzeStatus = useEffectEvent(async (taskId: string, resolvedInput: string) => {
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
  });

  const analyzeStock = useEffectEvent(async (rawInput: string) => {
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
      const accepted = await stockQueryApi.analyze({ query: normalized });
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
  });

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
  const entryPlan = useMemo(() => (result ? buildEntryPlan(result) : null), [result]);
  const signalOverview = useMemo(
    () => (result && entryPlan ? buildSignalOverview(result, entryPlan) : null),
    [entryPlan, result],
  );
  const priceRail = useMemo(() => (result && entryPlan ? buildPriceRail(result, entryPlan) : null), [entryPlan, result]);
  const recentHistory = useMemo(() => historyItems.slice(0, 4), [historyItems]);
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

  const handleAddToWatchlist = useEffectEvent(async () => {
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
  });

  const handleCreateDefaultAlerts = useEffectEvent(async () => {
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
  });

  return (
    <AppPage className="!max-w-[1680px] px-3 md:px-5 lg:px-6">
      <section className="overflow-hidden rounded-[32px] border border-slate-800/80 bg-[radial-gradient(circle_at_top_left,_rgba(29,182,255,0.14),_transparent_24%),radial-gradient(circle_at_top_right,_rgba(91,124,255,0.12),_transparent_22%),linear-gradient(180deg,#07111f,#091a2d)] text-slate-50 shadow-soft-card">
        <div className="grid xl:grid-cols-[minmax(0,1fr)_430px]">
          <div className="border-b border-slate-800/80 px-5 py-6 lg:px-7 xl:border-b-0 xl:border-r">
            <div className="space-y-6">
              <div>
                <h2 className="text-3xl font-semibold tracking-tight text-white">单股查询</h2>
                <p className="mt-2 max-w-3xl text-sm leading-7 text-slate-400">
                  围绕“如何入场”和“买点在哪”重组信息层级，首屏先给交易结论，再把历史和辅助信息压到更合适的位置。
                </p>
              </div>

              <form className="space-y-3" onSubmit={handleSubmit}>
                <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_104px_118px]">
                  <Input
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="输入股票代码或名称，例如 688629.SH / 华丰科技"
                    className="h-12 rounded-2xl border-slate-700/80 bg-[#0A1A2E] text-slate-100 placeholder:text-slate-500"
                    hint="支持股票代码和股票名称。查询成功后会自动写入后端历史，方便回看和恢复查看。"
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
                    className="h-12 rounded-2xl border-slate-700/80 bg-[#0B2038] text-slate-100 hover:bg-[#102744]"
                    onClick={() => setHistoryOpen(true)}
                  >
                    <Clock3 className="h-4 w-4" />
                    历史查询
                  </Button>
                </div>

                <div className="flex flex-wrap gap-3">
                  {QUICK_QUERIES.map((item) => (
                    <button
                      key={item.value}
                      type="button"
                      onClick={() => handleQuickQuery(item.value)}
                      className={[
                        'rounded-2xl border px-4 py-2 text-sm font-medium transition-all',
                        query === item.value
                          ? 'border-cyan/30 bg-primary-gradient text-white shadow-lg shadow-cyan/20'
                          : 'border-slate-700/80 bg-[#0E1F36] text-slate-200 hover:border-cyan/20 hover:bg-[#112640]',
                      ].join(' ')}
                    >
                      {item.label}
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
                <div className="overflow-hidden rounded-[28px] border border-slate-700/80 bg-[radial-gradient(circle_at_top_left,_rgba(24,167,255,0.18),_transparent_28%),radial-gradient(circle_at_bottom_right,_rgba(77,93,255,0.18),_transparent_32%),linear-gradient(180deg,rgba(13,42,70,0.98),rgba(12,27,47,0.98))] px-5 py-6">
                  {result && entryPlan ? (
                    <div className="space-y-5">
                      <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
                        <div className="min-w-0">
                          <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Entry Decision</p>
                          <p className="mt-4 text-3xl font-semibold tracking-tight text-white">{entryPlan.headline}</p>
                          <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-300">{entryPlan.summary}</p>
                          <div className="mt-5 flex flex-wrap items-center gap-3">
                            <Badge variant={signalBadgeVariant(result.signal)} className="border-0 px-3 py-1">
                              {result.signal}
                            </Badge>
                            <Badge variant="default" className="border border-slate-700/80 bg-slate-950/35 px-3 py-1 text-xs text-slate-100">
                              {result.trendStatus || result.pattern || '等待结构确认'}
                            </Badge>
                          </div>
                        </div>

                        <div className="rounded-[24px] border border-slate-700/80 bg-slate-950/35 px-5 py-4 xl:min-w-[248px]">
                          <p className="text-xs uppercase tracking-[0.16em] text-slate-400">当前价格</p>
                          <p className="mt-3 text-4xl font-semibold text-white">{formatNumber(result.currentPrice)}</p>
                          <p className={`mt-2 text-sm font-medium ${signedValueClass(result.pctChg)}`}>
                            {formatPercent(result.pctChg, 2)}
                          </p>
                          <p className="mt-3 text-xs leading-6 text-slate-400">
                            结论：{`回踩 ${formatRange(entryPlan.entryLower, entryPlan.entryUpper)} 再做第一笔，或站上 ${formatNumber(entryPlan.breakoutPrice)} 后做确认买点。`}
                          </p>
                        </div>
                      </div>

                      <div className="grid gap-3 xl:grid-cols-3">
                        {entryPlan.strategies.map((strategy) => (
                          <div key={strategy.key} className={`rounded-[22px] border px-4 py-4 ${strategyToneClasses(strategy.tone)}`}>
                            <p className="text-sm font-semibold text-white">{strategy.title}</p>
                            <p className="mt-2 text-sm leading-6 text-slate-200">{strategy.description}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-5">
                      <div>
                        <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Entry Decision</p>
                        <p className="mt-4 text-3xl font-semibold tracking-tight text-white">先回答现在能不能上，再展开辅助分析</p>
                        <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-300">
                          查询成功后，这里会先告诉你该低吸、等突破，还是暂时不要追，不再把所有字段一口气堆到首屏。
                        </p>
                      </div>

                      <div className="grid gap-3 xl:grid-cols-3">
                        {[
                          '买点优先：试仓区、突破位、止损线放在最前面。',
                          '历史前置：最近结论直接放进首屏，不再藏在二级页面。',
                          '辅助下沉：题材归因、数据覆盖改到右侧详情栏补充。',
                        ].map((item) => (
                          <div key={item} className="rounded-[22px] border border-slate-700/80 bg-slate-950/35 px-4 py-4 text-sm leading-6 text-slate-200">
                            {item}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                <div className="rounded-[28px] border border-slate-700/80 bg-[#0A1A2D] px-5 py-5">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-xs uppercase tracking-[0.18em] text-slate-400">History Snapshot</p>
                      <h3 className="mt-3 text-2xl font-semibold text-white">历史入口前置</h3>
                      <p className="mt-2 text-sm leading-6 text-slate-400">最近几次对这只票的判断，直接放在右上首屏。</p>
                    </div>
                    <Button variant="ghost" size="sm" className="text-slate-300 hover:bg-slate-800/60 hover:text-white" onClick={() => setHistoryOpen(true)}>
                      全部历史
                    </Button>
                  </div>

                  <div className="mt-5 space-y-3">
                    {historyError ? <ApiErrorAlert error={historyError} /> : null}
                    {historyLoading ? (
                      <InlineAlert
                        variant="info"
                        title="正在读取历史记录"
                        message="正在从后端加载最近的单股查询记录。"
                      />
                    ) : null}

                    {(result ? rightRailHistory : recentHistory).slice(0, 2).length > 0 ? (
                      (result ? rightRailHistory : recentHistory).slice(0, 2).map((item) => (
                        <button
                          key={item.queryId}
                          type="button"
                          onClick={() => void handleHistoryRestore(item)}
                          className="w-full rounded-[22px] border border-slate-700/80 bg-[#0D223A] px-4 py-4 text-left transition-colors hover:border-cyan/25 hover:bg-[#112945]"
                        >
                          <p className="text-xs text-slate-400">{formatHistoryTime(item.completedAt || item.createdAt)}</p>
                          <p className="mt-2 text-sm font-semibold text-slate-100">
                            {(item.stockName || item.queryText || '单股查询')}
                            <span className="text-slate-400">{` · ${item.signal || '仅观察'}`}</span>
                          </p>
                          <p className="mt-2 text-xs leading-6 text-slate-400">
                            低吸 {formatRange(getHistoryEntryPlan(item)?.entryLower, getHistoryEntryPlan(item)?.entryUpper)}
                          </p>
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
                </div>
              </div>

              {isLoading && !result ? (
                <div className="rounded-[28px] border border-slate-700/80 bg-slate-950/35 px-5 py-5">
                  <div className="flex items-center gap-4">
                    <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-cyan/10 text-cyan">
                      <Sparkles className="h-5 w-5 animate-pulse" />
                    </div>
                    <div>
                      <p className="text-lg font-semibold text-white">正在拉取单股诊断结果</p>
                      <p className="mt-1 text-sm text-slate-400">会先解析股票输入，再生成入场计划、买点区间和后端历史对照。</p>
                    </div>
                  </div>
                </div>
              ) : null}

              {!result && !isLoading ? (
                <div className="rounded-[28px] border border-slate-800/80 bg-[#0A1628] px-5 py-5">
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Buy Point Ruler</p>
                  <p className="mt-3 text-2xl font-semibold text-white">买点刻度尺会放在这里</p>
                  <p className="mt-2 text-sm leading-7 text-slate-400">
                    查询成功后，这里会把试仓区、现价、突破位和禁追区放到一条线上，让你第一眼看清“离买点还有多远”。
                  </p>
                </div>
              ) : null}

              {result && entryPlan ? (
                <>
                  <div className="rounded-[28px] border border-slate-800/80 bg-[#0A1628] px-5 py-5">
                    <div className="flex flex-wrap items-start justify-between gap-4">
                      <div>
                        <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Buy Point Ruler</p>
                        <h3 className="mt-3 text-2xl font-semibold text-white">买点刻度尺</h3>
                        <p className="mt-2 text-sm leading-7 text-slate-400">
                          支撑、试仓区、当前价、突破位、禁追区放在一条线上，让页面第一眼就能读出“离买点还有多远”。
                        </p>
                      </div>
                      <div className="rounded-[22px] border border-slate-700/80 bg-slate-950/35 px-4 py-3 text-sm text-slate-300">
                        当前建议：<span className="font-semibold text-white">{entryPlan.headline}</span>
                      </div>
                    </div>

                    {priceRail ? (
                      <div className="mt-8 rounded-[24px] border border-slate-800/80 bg-[#0B1C2E] px-5 py-6">
                        <div className="relative h-24">
                          <div className="absolute left-4 right-4 top-10 h-2.5 rounded-full bg-slate-700/80" />
                          <div
                            className="absolute top-[37px] h-3.5 rounded-full bg-success/80"
                            style={{
                              left: `calc(${priceRail.entryStart}% + 1rem)`,
                              width: `${Math.max(priceRail.entryEnd - priceRail.entryStart, 2)}%`,
                            }}
                          />
                          <div
                            className="absolute top-[37px] h-3.5 rounded-full bg-warning/75"
                            style={{
                              left: `calc(${priceRail.points.find((point) => point.key === 'breakout')?.position ?? priceRail.noChaseStart}% + 1rem)`,
                              width: `${Math.max(priceRail.noChaseStart - (priceRail.points.find((point) => point.key === 'breakout')?.position ?? priceRail.noChaseStart), 2)}%`,
                            }}
                          />
                          <div
                            className="absolute top-[37px] h-3.5 rounded-full bg-danger/70"
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
                                  <p className="text-xs font-semibold text-slate-100">{point.label}</p>
                                  <p className="mt-1 text-xs text-slate-400">{formatNumber(point.value)}</p>
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
                  </div>

                  <div className="grid gap-5 xl:grid-cols-[0.88fr_1.06fr_1.06fr]">
                    <div className="rounded-[28px] border border-slate-800/80 bg-[#0A1728] px-5 py-5">
                      <div className="flex items-center gap-3">
                        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-cyan/10 text-cyan">
                          <Target className="h-5 w-5" />
                        </div>
                        <div>
                          <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Checklist</p>
                          <h3 className="mt-1 text-2xl font-semibold text-white">入场前 checklist</h3>
                        </div>
                      </div>
                      <div className="mt-5 space-y-3">
                        {entryPlan.checklist.map((item) => (
                          <div key={item} className="rounded-[22px] border border-slate-800/80 bg-[#0C2236] px-4 py-4 text-sm leading-6 text-slate-100">
                            {item}
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="rounded-[28px] border border-slate-800/80 bg-[#0A1728] px-5 py-5">
                      <div className="flex items-center gap-3">
                        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-success/10 text-success">
                          <TrendingUp className="h-5 w-5" />
                        </div>
                        <div>
                          <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Why Watch</p>
                          <h3 className="mt-1 text-2xl font-semibold text-white">为什么还值得继续看</h3>
                        </div>
                      </div>

                      <div className="mt-5 space-y-3">
                        {result.selectedReasons.length > 0 ? (
                          result.selectedReasons.slice(0, 2).map((reason) => (
                            <div key={reason} className="rounded-[22px] border border-slate-800/80 bg-[#0C2236] px-4 py-4 text-sm leading-6 text-slate-100">
                              {reason}
                            </div>
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
                    </div>

                    <div className="rounded-[28px] border border-slate-800/80 bg-[#0A1728] px-5 py-5">
                      <div className="flex items-center gap-3">
                        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-warning/10 text-warning">
                          <AlertTriangle className="h-5 w-5" />
                        </div>
                        <div>
                          <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Why Wait</p>
                          <h3 className="mt-1 text-2xl font-semibold text-white">为什么现在不能太激进</h3>
                        </div>
                      </div>

                      <div className="mt-5 space-y-3">
                        {result.excludedReasons.length > 0 ? (
                          result.excludedReasons.slice(0, 2).map((reason) => (
                            <div key={reason} className="rounded-[22px] border border-slate-800/80 bg-[#2A1624] px-4 py-4 text-sm leading-6 text-slate-100">
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

                      <div className="mt-5 rounded-[22px] border border-slate-800/80 bg-[#2A1624] px-4 py-4">
                        <p className="text-sm leading-7 text-slate-100">{entryPlan.summary}</p>
                      </div>
                    </div>
                  </div>

                  {hasFundamentalBlocks ? (
                    <div className="rounded-[28px] border border-slate-800/80 bg-[#09192C] px-5 py-5">
                      <div className="flex flex-wrap items-start justify-between gap-4">
                        <div className="max-w-4xl">
                          <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Fundamental Context</p>
                          <h3 className="mt-1 text-2xl font-semibold text-white">基本面分块上下文</h3>
                          <p className="mt-3 max-w-4xl text-sm leading-7 text-slate-300">
                            这里优先展示底层基本面拿到了什么、缺了什么、是否能直接作为交易判断依据，比近期催化更靠前。
                          </p>
                        </div>
                        <Badge variant={fundamentalContext?.status === 'ok' ? 'success' : 'warning'} className="border-0 px-3 py-1">
                          {coverageStatusLabel(fundamentalContext?.status || 'partial')}
                        </Badge>
                      </div>

                      <div className="mt-5 grid gap-3 xl:grid-cols-3">
                        <FundamentalBlockCard
                          title="估值"
                          status={valuationBlock?.status}
                          sourceChain={valuationBlock?.sourceChain}
                          errors={valuationBlock?.errors}
                        >
                          <div className="grid gap-3 sm:grid-cols-2">
                            <MiniMetric label="PE" value={formatNumber(valuation?.peRatio)} tone="neutral" />
                            <MiniMetric label="PB" value={formatNumber(valuation?.pbRatio)} tone="neutral" />
                            <MiniMetric label="总市值" value={formatMoney(valuation?.totalMv)} tone="neutral" />
                            <MiniMetric label="流通市值" value={formatMoney(valuation?.circMv)} tone="neutral" />
                          </div>
                        </FundamentalBlockCard>

                        <FundamentalBlockCard
                          title="成长"
                          status={growthBlock?.status}
                          sourceChain={growthBlock?.sourceChain}
                          errors={growthBlock?.errors}
                        >
                          <div className="grid gap-3 sm:grid-cols-2">
                            <MiniMetric label="营收同比" value={formatPercent(growth?.revenueYoy, 1)} tone="neutral" />
                            <MiniMetric label="净利同比" value={formatPercent(growth?.netProfitYoy, 1)} tone="neutral" />
                            <MiniMetric label="ROE" value={formatPercent(growth?.roe, 1)} tone="neutral" />
                            <MiniMetric label="毛利率" value={formatPercent(growth?.grossMargin, 1)} tone="neutral" />
                          </div>
                        </FundamentalBlockCard>

                        <FundamentalBlockCard
                          title="盈利"
                          status={earningsBlock?.status}
                          sourceChain={earningsBlock?.sourceChain}
                          errors={earningsBlock?.errors}
                        >
                          <div className="grid gap-3 sm:grid-cols-2">
                            <MiniMetric label="报告期" value={earnings?.financialReport?.reportDate ?? '--'} tone="neutral" />
                            <MiniMetric label="股息率" value={formatPercent(earnings?.dividend?.ttmDividendYieldPct, 2)} tone="neutral" />
                            <MiniMetric label="营收" value={formatMoney(earnings?.financialReport?.revenue)} tone="neutral" />
                            <MiniMetric label="净利润" value={formatMoney(earnings?.financialReport?.netProfitParent)} tone="neutral" />
                          </div>
                          <p className="mt-3 text-xs leading-5 text-slate-400">
                            {earnings?.forecastSummary || earnings?.quickReportSummary || '当前没有拿到明确的业绩预告摘要。'}
                          </p>
                        </FundamentalBlockCard>
                      </div>

                      <div className="mt-3 grid gap-3 xl:grid-cols-2">
                        <FundamentalBlockCard
                          title="机构"
                          status={institutionBlock?.status}
                          sourceChain={institutionBlock?.sourceChain}
                          errors={institutionBlock?.errors}
                        >
                          <div className="grid gap-3 sm:grid-cols-2">
                            <MiniMetric label="机构持仓变化" value={formatPercent(institution?.institutionHoldingChange, 1)} tone="neutral" />
                            <MiniMetric label="前十股东变化" value={formatPercent(institution?.top10HolderChange, 1)} tone="neutral" />
                          </div>
                          {institution?.textSummary ? (
                            <p className="mt-3 text-xs leading-5 text-slate-300">
                              文本补充{institution.textProvider ? ` · ${institution.textProvider}` : ''}：{institution.textSummary}
                            </p>
                          ) : null}
                        </FundamentalBlockCard>

                        <FundamentalBlockCard
                          title="资金流"
                          status={capitalFlowBlock?.status}
                          sourceChain={capitalFlowBlock?.sourceChain}
                          errors={capitalFlowBlock?.errors}
                        >
                          <div className="grid gap-3 sm:grid-cols-3">
                            <MiniMetric label="主力净流入" value={formatMoney(capitalFlow?.mainNetInflow)} tone="neutral" />
                            <MiniMetric label="5日净流入" value={formatMoney(capitalFlow?.inflow5d)} tone="neutral" />
                            <MiniMetric label="10日净流入" value={formatMoney(capitalFlow?.inflow10d)} tone="neutral" />
                          </div>
                        </FundamentalBlockCard>
                      </div>

                      <div className="mt-3 grid gap-3 xl:grid-cols-[0.85fr_1.15fr]">
                        <FundamentalBlockCard
                          title="龙虎榜"
                          status={dragonTigerBlock?.status}
                          sourceChain={dragonTigerBlock?.sourceChain}
                          errors={dragonTigerBlock?.errors}
                        >
                          <div className="grid gap-3 sm:grid-cols-2">
                            <MiniMetric
                              label="近20日状态"
                              value={dragonTiger?.isOnList ? `上榜 ${dragonTiger.recentCount ?? 0} 次` : '未识别到上榜'}
                              tone="neutral"
                            />
                            <MiniMetric label="最近日期" value={dragonTiger?.latestDate ?? '--'} tone="neutral" />
                          </div>
                        </FundamentalBlockCard>

                        <FundamentalBlockCard
                          title="所属板块"
                          status={boardsBlock?.status}
                          sourceChain={boardsBlock?.sourceChain}
                          errors={boardsBlock?.errors}
                        >
                          <p className="text-xs text-slate-400">板块来源 {boardSourceLabel(boardSource, boardProvider)}</p>
                          {boardItems.length > 0 ? (
                            <div className="mt-3 flex flex-wrap gap-2">
                              {boardItems.slice(0, 10).map((board) => (
                                <div key={`${board.name}-${board.code ?? ''}`} className="rounded-full border border-cyan/20 bg-cyan/10 px-3 py-2">
                                  <p className="text-sm font-medium text-slate-100">{board.name}</p>
                                  {boardCaption(board) ? (
                                    <p className="mt-1 text-[11px] text-slate-400">{boardCaption(board)}</p>
                                  ) : null}
                                </div>
                              ))}
                            </div>
                          ) : null}
                        </FundamentalBlockCard>
                      </div>
                    </div>
                  ) : null}
                </>
              ) : null}
            </div>
          </div>

          <aside className="bg-[linear-gradient(180deg,rgba(10,22,39,0.92),rgba(8,17,31,0.96))] px-5 py-6 lg:px-6">
            <div className="space-y-5 xl:sticky xl:top-24">
              <div>
                <h3 className="text-lg font-semibold text-white">股票详情</h3>
                <div className="mt-3 h-px bg-slate-800/80" />
              </div>

              <div>
                <div className="flex flex-wrap items-end gap-3">
                  <h4 className="text-3xl font-semibold text-white">{result?.stockName ?? '等待查询结果'}</h4>
                  <span className="text-sm text-slate-400">{result?.stockCode ?? '--'}</span>
                </div>
                <div className="mt-5 flex flex-wrap items-end gap-3">
                  <p className="text-4xl font-semibold text-white">{formatNumber(result?.currentPrice)}</p>
                  <p className={`text-2xl font-semibold ${signedValueClass(result?.pctChg)}`}>
                    {formatPercent(result?.pctChg, 2)}
                  </p>
                </div>
                <p className="mt-3 text-sm leading-7 text-slate-400">
                  {result && entryPlan
                    ? '右侧延续全站的详情栏语言，但内容集中服务于单股交易视图。'
                    : '查询成功后，这里会汇总股票详情、关键信号、关键位和最近几次判断。'}
                </p>
              </div>

              <div className="rounded-[24px] border border-slate-800/80 bg-[#0A1A2E] px-5 py-5">
                <p className="text-xs uppercase tracking-[0.18em] text-slate-400">主信号相关度</p>
                <div className="mt-4 flex items-center justify-between gap-4">
                  <div className="space-y-2">
                    <p className="text-2xl font-semibold text-cyan">{signalOverview?.label ?? '等待信号'}</p>
                    <p className="max-w-[190px] text-sm leading-6 text-slate-400">
                      {signalOverview?.description ?? '先完成一次查询，这里会告诉你更适合等回踩、等突破，还是保持观察。'}
                    </p>
                  </div>
                  <div
                    className="relative flex h-28 w-28 items-center justify-center rounded-full p-2"
                    style={{
                      background: signalOverview
                        ? `conic-gradient(from 210deg, #22c55e 0deg, #1db6ff ${signalOverview.score * 3.6}deg, rgba(30,41,59,0.88) ${signalOverview.score * 3.6}deg 360deg)`
                        : 'conic-gradient(from 210deg, rgba(51,65,85,0.95) 0deg, rgba(51,65,85,0.95) 360deg)',
                    }}
                  >
                    <div className="flex h-full w-full flex-col items-center justify-center rounded-full bg-[#081322]">
                      <span className="text-2xl font-semibold text-white">{signalOverview?.score ?? '--'}</span>
                      <span className="mt-1 text-[11px] text-slate-400">{signalOverview ? '可等待买点' : '等待结果'}</span>
                    </div>
                  </div>
                </div>
              </div>

              <div className="rounded-[24px] border border-slate-800/80 bg-[#0A1A2E] px-5 py-5">
                <p className="text-xs uppercase tracking-[0.18em] text-slate-400">技术结构</p>
                <div className="mt-5 space-y-4">
                  <DetailMetricRow label="趋势方向" value={result?.trendStatus ?? '--'} accent="success" />
                  <DetailMetricRow label="形态结构" value={result?.pattern ?? '--'} accent="success" />
                  <DetailMetricRow label="动量状态" value={result?.buySignal ?? result?.signal ?? '--'} accent="success" />
                </div>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="rounded-[24px] border border-slate-800/80 bg-[#0A1A2E] px-5 py-5">
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-400">关键位</p>
                  <div className="mt-5 space-y-3">
                    <DetailMetricRow label="支撑位" value={formatNumber(entryPlan?.supportPrice)} accent="success" />
                    <DetailMetricRow label="强支撑" value={formatNumber(entryPlan?.stopLossPrice)} accent="neutral" />
                    <DetailMetricRow label="突破位" value={formatNumber(entryPlan?.breakoutPrice)} accent="warning" />
                  </div>
                </div>

                <div className="rounded-[24px] border border-slate-800/80 bg-[#0A1A2E] px-5 py-5">
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-400">均线位置</p>
                  <div className="mt-5 space-y-3">
                    <DetailMetricRow label="MA10" value={formatNumber(result?.ma10)} accent="neutral" />
                    <DetailMetricRow label="MA20" value={formatNumber(result?.ma20)} accent="neutral" />
                    <DetailMetricRow label="PE / PB" value={`PE ${formatNumber(result?.peRatio)} / PB ${formatNumber(result?.pbRatio)}`} accent="neutral" />
                  </div>
                </div>
              </div>

              <div className="rounded-[24px] border border-slate-800/80 bg-[#0A1A2E] px-5 py-5">
                <p className="text-xs uppercase tracking-[0.18em] text-slate-400">查询历史</p>
                <h4 className="mt-3 text-lg font-semibold text-white">这只票之前怎么看过</h4>

                <div className="mt-4 space-y-3">
                  {historyComparison ? (
                    <div className="rounded-[20px] border border-slate-800/80 bg-[#0D223A] px-4 py-4">
                      <p className="text-sm font-semibold text-slate-100">{historyComparison.headline}</p>
                      <p className="mt-2 text-sm leading-6 text-slate-400">{historyComparison.description}</p>
                    </div>
                  ) : null}

                  {rightRailHistory.length > 0 ? (
                    rightRailHistory.map((item) => (
                      <button
                        key={item.queryId}
                        type="button"
                        onClick={() => void handleHistoryRestore(item)}
                        className="block w-full rounded-[20px] border border-slate-800/80 bg-slate-950/35 px-4 py-3 text-left transition-colors hover:border-cyan/25 hover:bg-[#102744]"
                      >
                        <p className="text-xs text-slate-400">{formatHistoryTime(item.completedAt || item.createdAt)}</p>
                        <p className="mt-1 text-sm text-slate-100">{getHistoryLabel(item)}</p>
                      </button>
                    ))
                  ) : (
                    <p className="text-sm leading-6 text-slate-400">查过几次之后，这里会直接显示最近几次对这只票的判断。</p>
                  )}
                </div>
              </div>

              <div className="grid gap-3 sm:grid-cols-3">
                <Link
                  to={
                    result?.queryId
                      ? `/deep-analysis?queryId=${encodeURIComponent(result.queryId)}&stock=${encodeURIComponent(result.stockCode)}&name=${encodeURIComponent(result.stockName)}`
                      : '/deep-analysis'
                  }
                  className="inline-flex items-center justify-center rounded-2xl border border-cyan/30 bg-primary-gradient px-4 py-3 text-sm font-medium text-white shadow-lg shadow-cyan/20 transition hover:brightness-105"
                >
                  发起深度分析
                </Link>
                <Button
                  type="button"
                  isLoading={watchlistLoading}
                  loadingText="加入中..."
                  disabled={!result || isInWatchlist}
                  onClick={() => void handleAddToWatchlist()}
                  className="rounded-2xl border border-purple/30 bg-gradient-to-r from-[#6444E9] to-[#8456FF] px-4 py-3 text-sm font-medium text-white shadow-lg shadow-purple/20 transition hover:brightness-105"
                >
                  {isInWatchlist ? '已在观察池' : '加入观察池'}
                </Button>
                <button
                  type="button"
                  disabled={!result || hasStockAlertRules || alertRuleLoading}
                  onClick={() => void handleCreateDefaultAlerts()}
                  className="inline-flex items-center justify-center rounded-2xl border border-slate-700/80 bg-[#101C2F] px-4 py-3 text-sm font-medium text-slate-300 enabled:cursor-pointer enabled:hover:bg-[#16253D] enabled:hover:text-white disabled:opacity-60"
                >
                  {alertRuleLoading ? '创建中...' : hasStockAlertRules ? '告警已设置' : '设置告警'}
                </button>
              </div>

              <div className="flex flex-col gap-3 rounded-[24px] border border-slate-800/80 bg-[#0A1A2E] px-4 py-4 md:grid-cols-[minmax(0,220px)_1fr]">
                <Input
                  label="告警扫描间隔(分钟)"
                  value={alertScanInterval}
                  onChange={(event) => setAlertScanInterval(event.target.value)}
                  placeholder={`默认 ${MIN_ALERT_SCAN_INTERVAL_MINUTES}`}
                  className="h-11 rounded-2xl border-slate-700/80 bg-[#071628] text-slate-100 placeholder:text-slate-500"
                />
                <div className="flex items-center justify-between gap-3 rounded-[20px] border border-slate-800/80 bg-slate-950/30 px-4 py-3">
                  <div>
                    <p className="text-sm font-medium text-slate-100">扫描频率由输入决定</p>
                    <p className="mt-1 text-xs leading-6 text-slate-400">单位分钟，最小 {MIN_ALERT_SCAN_INTERVAL_MINUTES} 分钟。创建默认规则时会同步写入每条规则。</p>
                  </div>
                  <Badge variant="info" className="border-0 px-3 py-1">
                    默认 {MIN_ALERT_SCAN_INTERVAL_MINUTES} 分钟
                  </Badge>
                </div>
              </div>

              {(topTheme || fundamentalCoverageEntries.length > 0) ? (
                <div className="space-y-4">
                  {topTheme ? (
                    <div className="rounded-[24px] border border-slate-800/80 bg-[#0A1A2E] px-5 py-5">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <p className="text-xs uppercase tracking-[0.18em] text-slate-400">辅助题材</p>
                          <h4 className="mt-2 text-lg font-semibold text-white">{topTheme.themeName}</h4>
                        </div>
                        <Badge variant="info" className="border-0 px-3 py-1">
                          {themeAttributions.length} 个主题
                        </Badge>
                      </div>
                      <p className="mt-3 text-sm leading-6 text-slate-400">
                        {confidenceLabel(topTheme.confidence)} · {relationTypeLabel(topTheme.relationType)}
                      </p>
                      <p className="mt-2 text-sm leading-6 text-slate-100">{topTheme.reason}</p>
                    </div>
                  ) : null}

                  {stockNewsSummary ? (
                    <div className="rounded-[24px] border border-slate-800/80 bg-[#0A1A2E] px-5 py-5">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Recent Catalyst</p>
                          <h4 className="mt-2 text-lg font-semibold text-white">近期催化 / 新闻摘要</h4>
                        </div>
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant={newsSentimentVariant(stockNewsSummary.sentiment)} className="border-0 px-3 py-1">
                            {newsSentimentLabel(stockNewsSummary.sentiment)}
                          </Badge>
                          <Badge variant="default" className="border-0 px-3 py-1">
                            {stockNewsSummary.provider || 'search'}
                          </Badge>
                        </div>
                      </div>

                      <p className="mt-4 text-sm leading-7 text-slate-300">
                        {stockNewsSummary.summary || '当前没有拿到足够清晰的新闻摘要。'}
                      </p>

                      <div className="mt-4 space-y-3">
                        <div className="rounded-[20px] border border-slate-800/80 bg-[#0C2236] px-4 py-4">
                          <p className="text-sm font-semibold text-slate-100">正向催化</p>
                          <div className="mt-3 flex flex-wrap gap-2">
                            {(stockNewsSummary.catalysts?.length ? stockNewsSummary.catalysts : ['暂无明确催化']).map((item) => (
                              <span key={item} className="rounded-full border border-cyan/20 bg-cyan/10 px-3 py-2 text-xs font-medium text-slate-100">
                                {item}
                              </span>
                            ))}
                          </div>
                        </div>

                        <div className="rounded-[20px] border border-slate-800/80 bg-[#1B1424] px-4 py-4">
                          <p className="text-sm font-semibold text-slate-100">明确风险</p>
                          <div className="mt-3 flex flex-wrap gap-2">
                            {(stockNewsSummary.riskEvents?.length ? stockNewsSummary.riskEvents : ['暂未识别明显利空']).map((item) => (
                              <span key={item} className="rounded-full border border-danger/20 bg-danger/10 px-3 py-2 text-xs font-medium text-slate-100">
                                {item}
                              </span>
                            ))}
                          </div>
                        </div>

                        <div className="rounded-[20px] border border-slate-800/80 bg-slate-950/35 px-4 py-4">
                          <p className="text-sm font-semibold text-slate-100">最近三条标题</p>
                          <div className="mt-3 space-y-2">
                            {(stockNewsSummary.headlines?.length ? stockNewsSummary.headlines : ['当前没有拿到明确的相关新闻标题。']).map((headline) => (
                              <div key={headline} className="rounded-[18px] border border-slate-800/80 bg-[#102744] px-4 py-3">
                                <p className="text-sm leading-6 text-slate-100">{headline}</p>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>
                  ) : null}

                  {fundamentalCoverageEntries.length > 0 ? (
                    <div className="rounded-[24px] border border-slate-800/80 bg-[#0A1A2E] px-5 py-5">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <p className="text-xs uppercase tracking-[0.18em] text-slate-400">数据覆盖</p>
                          <h4 className="mt-2 text-lg font-semibold text-white">基本面与数据源</h4>
                        </div>
                        <Badge variant={incompleteFundamentalEntries.length > 0 ? 'warning' : 'success'} className="border-0 px-3 py-1">
                          {incompleteFundamentalEntries.length > 0 ? `仍缺 ${incompleteFundamentalEntries.length} 项` : '已完整返回'}
                        </Badge>
                      </div>

                      <div className="mt-4 grid gap-3 sm:grid-cols-2">
                        <MiniMetric label="日线" value={sourceLabel(result?.dataSources.daily)} tone="neutral" />
                        <MiniMetric label="实时" value={sourceLabel(result?.dataSources.realtime)} tone="neutral" />
                        <MiniMetric label="筹码" value={sourceLabel(result?.dataSources.chip)} tone="neutral" />
                        <MiniMetric label="基本面" value={sourceLabel(result?.dataSources.fundamental ?? fundamentalContext?.status)} tone="neutral" />
                        <MiniMetric label="总状态" value={coverageStatusLabel(fundamentalContext?.status || '--')} tone="neutral" />
                        <MiniMetric label="耗时" value={fundamentalContext?.elapsedMs ? `${fundamentalContext.elapsedMs}ms` : '--'} tone="neutral" />
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
                        <p className="mt-4 text-xs leading-6 text-slate-400">最近错误: {fundamentalErrorPreview.join(' | ')}</p>
                      ) : null}
                    </div>
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
                <div
                  key={item.queryId}
                  className={[
                    'rounded-2xl border px-4 py-4 transition-colors',
                    active ? 'border-cyan/40 bg-cyan/6' : 'border-border/60 bg-background/70',
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
                </div>
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

type FundamentalBlockCardProps = {
  title: string;
  status?: string;
  sourceChain?: Array<Record<string, unknown>>;
  errors?: string[];
  children?: React.ReactNode;
};

const FundamentalBlockCard: React.FC<FundamentalBlockCardProps> = ({ title, status, sourceChain, errors, children }) => (
  <div className="rounded-[20px] border border-slate-800/80 bg-slate-950/35 px-4 py-4">
    <div className="flex items-start justify-between gap-3">
      <div>
        <p className="text-sm font-semibold text-slate-100">{title}</p>
        <p className="mt-1 text-xs text-slate-400">来源 {sourceChainSummary(sourceChain)}</p>
      </div>
      <Badge variant={status === 'ok' || status === 'full' ? 'success' : status === 'partial' ? 'warning' : 'default'} className="border-0 px-2 py-1">
        {coverageStatusLabel(status || 'failed')}
      </Badge>
    </div>

    <div className="mt-3 space-y-3">
      {children}
      {errors && errors.length > 0 ? (
        <p className="text-xs leading-5 text-slate-400">错误: {errors.slice(0, 2).join(' | ')}</p>
      ) : null}
    </div>
  </div>
);

const MiniMetric: React.FC<MiniMetricProps> = ({ label, value, tone }) => {
  const toneClass = tone === 'buy'
    ? 'border-success/15 bg-success/10'
    : tone === 'breakout'
      ? 'border-warning/20 bg-warning/10'
      : tone === 'warn'
        ? 'border-danger/15 bg-danger/10'
        : 'border-slate-700/80 bg-slate-950/35';

  return (
    <div className={`rounded-[22px] border px-4 py-4 ${toneClass}`}>
      <p className="text-xs uppercase tracking-[0.14em] text-slate-400">{label}</p>
      <p className="mt-3 text-sm font-semibold text-slate-100">{value}</p>
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
    ? 'text-success'
    : accent === 'warning'
      ? 'text-warning'
      : 'text-slate-100';

  return (
    <div className="flex items-center justify-between gap-4 text-sm">
      <span className="text-slate-400">{label}</span>
      <span className={`text-right font-semibold ${valueClass}`}>{value}</span>
    </div>
  );
};

export default SingleStockQueryPage;
