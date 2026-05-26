import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Clock3,
  Search,
  Sparkles,
} from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';
import { createParsedApiError, getParsedApiError, type ParsedApiError } from '../api/error';
import {
  stockQueryApi,
  type StockQueryAnalyzeResponse,
  type StockQueryHistoryItem,
  type StockQueryTaskStatus,
  type StockQueryThemeAttribution,
} from '../api/stockQuery';
import { watchlistApi, type StockAlertRuleItem, type StockWatchlistItem } from '../api/watchlist';
import { ApiErrorAlert, AppPage, Badge, Button, Card, Drawer, EmptyState, InlineAlert, Select } from '../components/common';
import { CandlestickChart } from '../components/CandlestickChart';

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const QUICK_QUERIES = [
  { label: '华丰科技', value: '688629.SH' },
  { label: '优博讯', value: '300531.SZ' },
  { label: '景旺电子', value: '603228.SH' },
  { label: '证券ETF', value: '512880.SH' },
] as const;

const MIN_ALERT_SCAN_INTERVAL_MINUTES = 5;
const STRATEGY_OPTIONS = [
  { value: 'auto', label: '自动决策' },
  { value: 'pullback', label: '低吸回踩' },
  { value: 'breakout', label: '突破确认' },
  { value: 'trend_follow', label: '趋势跟随' },
  { value: 'holding', label: '趋势持有' },
] as const;

/* ------------------------------------------------------------------ */
/*  Utility functions                                                  */
/* ------------------------------------------------------------------ */

function isFiniteNumber(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function formatNumber(value?: number | null, digits = 2): string {
  if (!isFiniteNumber(value)) return '--';
  return value.toFixed(digits);
}

function formatMoney(value?: number | null): string {
  if (!isFiniteNumber(value)) return '--';
  const abs = Math.abs(value);
  if (abs >= 100000000) return `¥${(value / 100000000).toFixed(0)} 亿`;
  if (abs >= 10000) return `¥${(value / 10000).toFixed(1)} 万`;
  return `¥${value.toFixed(0)}`;
}

function formatMoneyCompact(value?: number | null): string {
  if (!isFiniteNumber(value)) return '--';
  const abs = Math.abs(value);
  if (abs >= 100000000) return `${value > 0 ? '+' : ''}${(value / 100000000).toFixed(1)}亿`;
  if (abs >= 10000) return `${value > 0 ? '+' : ''}${(value / 10000).toFixed(1)}万`;
  return value.toFixed(0);
}

function formatHistoryTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date);
}

function formatShortDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: '2-digit' }).format(date);
}

function signalBadgeVariant(signal: string): 'success' | 'info' | 'warning' | 'danger' | 'default' {
  if (signal === '短线异动') return 'danger';
  if (signal === '趋势跟随') return 'success';
  if (signal === '持有候选') return 'warning';
  if (signal === '低吸观察') return 'info';
  if (signal === '不宜追高' || signal === '仅观察') return 'default';
  return 'success';
}

/* ------------------------------------------------------------------ */
/*  Buy-point helpers (derived from strategyDecisions + price levels)  */
/* ------------------------------------------------------------------ */

interface BuyPointEntry {
  index: number;
  key: string;
  name: string;
  nameEn: string;
  badge: string;
  badgeVariant: 'success' | 'info' | 'warning' | 'danger' | 'default';
  zoneLow: number | null;
  zoneHigh: number | null;
  distPct: number | null;
  status: string;
  statusColor: string;
  description: string;
  matched: boolean;
}

const STRATEGY_META: Record<string, { nameEn: string; badge: string; order: number }> = {
  pullback: { nameEn: 'MA20 Pullback', badge: '短线', order: 1 },
  breakout: { nameEn: 'Breakout Retest', badge: '短线', order: 2 },
  trend_follow: { nameEn: 'Trend Follow', badge: '中线', order: 3 },
  holding: { nameEn: 'Hold Quality', badge: '长线', order: 4 },
};

function computeBuyPoints(
  decisions: StockQueryStrategyDecision[],
  currentPrice?: number | null,
  support?: number | null,
  pressure?: number | null,
  ma10?: number | null,
  ma20?: number | null,
): BuyPointEntry[] {
  const cp = isFiniteNumber(currentPrice) ? currentPrice : null;
  const points: BuyPointEntry[] = [];

  for (const d of decisions) {
    const meta = STRATEGY_META[d.key];
    if (!meta) continue;

    // Derive buy zone from key + available price levels
    let zoneLow: number | null = null;
    let zoneHigh: number | null = null;
    let desc = '';

    if (d.key === 'pullback') {
      // Buy near MA20
      if (isFiniteNumber(ma20)) {
        zoneHigh = ma20;
        zoneLow = Math.round((ma20 * 0.985) * 100) / 100;
        desc = 'MA20 动态支撑，趋势未破前首选入场点。';
      } else if (isFiniteNumber(support)) {
        zoneHigh = support;
        zoneLow = Math.round((support * 0.985) * 100) / 100;
        desc = '支撑位附近低吸，注意观察量能配合。';
      } else {
        desc = '回踩均线附近择机低吸。';
      }
    } else if (d.key === 'breakout') {
      // Buy near pressure breakout zone
      if (isFiniteNumber(pressure) && isFiniteNumber(support)) {
        zoneLow = Math.round((support * 0.995) * 100) / 100;
        zoneHigh = Math.round((support * 1.005) * 100) / 100;
        desc = `突破 ${formatNumber(pressure)} 前高后回踩确认有效性。`;
      } else if (isFiniteNumber(pressure)) {
        zoneHigh = pressure;
        zoneLow = Math.round((pressure * 0.985) * 100) / 100;
        desc = '突破前高后回踩确认有效性。';
      } else {
        desc = '等待突破确认后择机介入。';
      }
    } else if (d.key === 'trend_follow') {
      // Middle zone between MA10 and MA20
      if (isFiniteNumber(ma10) && isFiniteNumber(ma20)) {
        const lo = Math.min(ma10, ma20);
        const hi = Math.max(ma10, ma20);
        zoneLow = Math.round(lo * 100) / 100;
        zoneHigh = Math.round(hi * 100) / 100;
        desc = 'MA10-MA20 区间顺势加仓，适合趋势确立后介入。';
      } else if (isFiniteNumber(ma10)) {
        zoneHigh = ma10;
        zoneLow = Math.round((ma10 * 0.98) * 100) / 100;
        desc = '短期均线附近趋势跟随。';
      } else {
        desc = '趋势确认后顺势介入。';
      }
    } else if (d.key === 'holding') {
      // Wider support zone for long-term
      if (isFiniteNumber(support) && isFiniteNumber(ma20)) {
        zoneLow = Math.round(Math.min(support, ma20) * 100) / 100;
        zoneHigh = Math.round((Math.min(support, ma20) * 1.02) * 100) / 100;
        desc = '长线安全边际区间，适合分批建仓。';
      } else if (isFiniteNumber(support)) {
        zoneLow = Math.round((support * 0.97) * 100) / 100;
        zoneHigh = support;
        desc = '长线持有候选，支撑位下方分批布局。';
      } else {
        desc = '中长线持有，等待估值回落。';
      }
    }

    // Use selectedReasons as description if available
    if (d.selectedReasons && d.selectedReasons.length > 0) {
      desc = d.selectedReasons.slice(0, 2).join('；');
    }

    // Compute distance pct
    let distPct: number | null = null;
    if (cp != null && zoneHigh != null) {
      const mid = zoneLow != null ? (zoneLow + zoneHigh) / 2 : zoneHigh;
      distPct = Math.round(((mid - cp) / cp) * 1000) / 10;
    }

    // Derive status label
    let status: string;
    let statusColor: string;
    if (d.signal === '不宜追高') {
      status = '不宜追高';
      statusColor = 'text-danger';
    } else if (d.matched) {
      status = '可操作';
      statusColor = 'text-success';
    } else if (distPct != null && Math.abs(distPct) < 2) {
      status = '接近';
      statusColor = 'text-warning';
    } else if (distPct != null && distPct < -5) {
      status = '远离';
      statusColor = 'text-secondary-text';
    } else {
      status = '等待验证';
      statusColor = 'text-secondary-text';
    }

    points.push({
      index: meta.order,
      key: d.key,
      name: d.label,
      nameEn: meta.nameEn,
      badge: meta.badge,
      badgeVariant: d.matched ? 'success' : 'default',
      zoneLow,
      zoneHigh,
      distPct,
      status,
      statusColor,
      description: desc,
      matched: d.matched,
    });
  }

  points.sort((a, b) => a.index - b.index);
  return points;
}

function signedValueClass(value?: number | null): string {
  if (!isFiniteNumber(value)) return 'text-foreground';
  if (value > 0) return 'text-success';
  if (value < 0) return 'text-danger';
  return 'text-foreground';
}

function signedChange(price?: number | null, pctChg?: number | null): string {
  if (!isFiniteNumber(pctChg)) return '--';
  const sign = pctChg > 0 ? '+' : '';
  const priceStr = isFiniteNumber(price) && isFiniteNumber(pctChg)
    ? `${sign}${(price * pctChg / (100 + pctChg)).toFixed(2)} `
    : '';
  return `${priceStr}(${sign}${pctChg.toFixed(2)}%)`;
}

function volumeRatioLabel(value?: number | null): string {
  if (!isFiniteNumber(value)) return '--';
  if (value >= 3) return '显著放量';
  if (value >= 2) return '放量';
  if (value >= 1.2) return '温和放量';
  if (value >= 0.8) return '正常';
  return '缩量';
}

function instrumentBadgeLabel(instrumentLabel?: string | null, instrumentType?: string | null): string | null {
  if (instrumentLabel?.trim()) return instrumentLabel.trim();
  if (instrumentType === 'etf') return 'ETF';
  return null;
}

function themeStatusBadge(theme: StockQueryThemeAttribution): 'TRIGGERED' | 'WATCH' {
  if (theme.confidence === 'high') return 'TRIGGERED';
  return 'WATCH';
}

function confidenceLabel(value: string): string {
  if (value === 'high') return '高置信';
  if (value === 'medium') return '中置信';
  if (value === 'low') return '低置信';
  return value || '待判定';
}

function rsScoreColor(score?: number | null): string {
  if (!isFiniteNumber(score)) return 'text-secondary-text';
  if (score >= 80) return 'text-success';
  if (score >= 60) return 'text-foreground';
  if (score >= 40) return 'text-warning';
  return 'text-danger';
}

function techBarColor(label: string): string {
  if (label === '显著放量' || label === '放量' || label === '活跃') return 'bg-success';
  if (label === '温和放量' || label === '正常') return 'bg-warning';
  return 'bg-danger';
}

function turnoverLabel(value?: number | null): string {
  if (!isFiniteNumber(value)) return '--';
  if (value >= 10) return '极度活跃';
  if (value >= 5) return '活跃';
  if (value >= 2) return '正常';
  return '低迷';
}

/* ------------------------------------------------------------------ */
/*  Main component                                                     */
/* ------------------------------------------------------------------ */

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
  const [alertScanInterval] = useState<string>(String(MIN_ALERT_SCAN_INTERVAL_MINUTES));
  const [watchlistActionError, setWatchlistActionError] = useState<ParsedApiError | null>(null);
  const [watchlistActionMessage, setWatchlistActionMessage] = useState<string | null>(null);
  const pollTimeoutRef = useRef<number | null>(null);
  const hasPendingInputChange = query.trim() !== (lastResolvedInput || '').trim();

  /* ---- data loaders ---- */

  const loadHistory = async () => {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const response = await stockQueryApi.getHistory(20);
      setHistoryItems(response.items);
      return response;
    } catch (requestError) {
      setHistoryError(getParsedApiError(requestError));
      return null;
    } finally {
      setHistoryLoading(false);
    }
  };

  const loadWatchlist = async () => {
    try {
      const response = await watchlistApi.listStocks();
      setWatchlistItems(response.items);
    } catch {
      /* ignore */
    }
  };

  const loadStockAlertRules = async (stockCode?: string) => {
    if (!stockCode) { setStockAlertRules([]); return; }
    try {
      const response = await watchlistApi.listStockAlertRules(stockCode);
      setStockAlertRules(response.items);
    } catch {
      /* ignore */
    }
  };

  /* ---- analyze flow ---- */

  const applyAnalyzeResult = useCallback(async (response: StockQueryAnalyzeResponse, resolvedInput: string) => {
    setResult(response);
    setStrategy(response.strategy || 'auto');
    setCurrentHistoryId(response.queryId ?? null);
    setLastResolvedInput(resolvedInput);
    setQueryTask(null);
    void loadStockAlertRules(response.stockCode);
    void loadHistory();
  }, []);

  useEffect(() => {
    const init = async () => {
      const [historyResponse] = await Promise.all([loadHistory(), loadWatchlist()]);
      // Auto-restore the latest completed history item on first load
      if (historyResponse && historyResponse.items.length > 0) {
        const latest = historyResponse.items.find((item) => item.status === 'completed' && item.result);
        if (latest?.result) {
          const resolvedInput = latest.stockCode ?? latest.queryText ?? '';
          await applyAnalyzeResult(latest.result, resolvedInput);
          setQuery(latest.stockCode ?? latest.queryText ?? initialQuery);
        }
      }
    };
    void init();
  }, [applyAnalyzeResult, initialQuery]);
  useEffect(() => () => { if (pollTimeoutRef.current != null) window.clearTimeout(pollTimeoutRef.current); }, []);

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
        setError(createParsedApiError({ title: '单股查询失败', message: status.error || status.message || '单股查询失败', status: 500 }));
        setIsLoading(false);
        pollTimeoutRef.current = null;
        void loadHistory();
        return;
      }
      pollTimeoutRef.current = window.setTimeout(() => { void pollAnalyzeStatus(taskId, resolvedInput); }, 3000);
    } catch (requestError) {
      setError(getParsedApiError(requestError));
      setIsLoading(false);
      pollTimeoutRef.current = null;
    }
  };

  const analyzeStock = async (rawInput: string) => {
    const normalized = rawInput.trim();
    if (!normalized) return;
    if (pollTimeoutRef.current != null) { window.clearTimeout(pollTimeoutRef.current); pollTimeoutRef.current = null; }
    setIsLoading(true);
    setError(null);
    setQueryTask(null);
    try {
      const accepted = await stockQueryApi.analyze({ query: normalized, strategy });
      setCurrentHistoryId(accepted.taskId);
      setQueryTask({ taskId: accepted.taskId, status: accepted.status, progress: 0, message: accepted.message, createdAt: new Date().toISOString() });
      await pollAnalyzeStatus(accepted.taskId, normalized);
    } catch (requestError) {
      setError(getParsedApiError(requestError));
      setIsLoading(false);
    } finally {
      if (pollTimeoutRef.current == null) setIsLoading(false);
    }
  };

  useEffect(() => {
    const syncQuery = () => { setQuery(initialQuery); setError(null); };
    syncQuery();
  }, [initialQuery]);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => { event.preventDefault(); await analyzeStock(query); };
  const handleQuickQuery = (value: string) => { setQuery(value); };

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
          setQueryTask({ taskId: detail.queryId, status: detail.status as StockQueryTaskStatus['status'], progress: detail.status === 'processing' ? 15 : 0, createdAt: detail.createdAt, completedAt: detail.completedAt });
          setIsLoading(true);
          setHistoryOpen(false);
          await pollAnalyzeStatus(detail.queryId, restoreQuery);
          return;
        }
        // No saved result — just fill the input, user can trigger query manually
        setQuery(restoreQuery);
        setHistoryOpen(false);
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

  /* ---- watchlist / alert actions ---- */

  const themeAttributions = useMemo(() => result?.themeAttributions ?? result?.themes ?? [], [result?.themeAttributions, result?.themes]);
  const topTheme = themeAttributions[0] ?? null;
  const currentStockAlertRules = useMemo(() => {
    if (!result) return [];
    return stockAlertRules.filter((item) => item.stockCode === result.stockCode);
  }, [result, stockAlertRules]);
  const hasStockAlertRules = currentStockAlertRules.length > 0;
  const isInWatchlist = useMemo(() => {
    if (!result) return false;
    return watchlistItems.some((item) => item.stockCode === result.stockCode);
  }, [result, watchlistItems]);

  const recentHistoryNames = useMemo(() => historyItems.slice(0, 3), [historyItems]);

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
        throw createParsedApiError({ title: '扫描间隔不正确', message: `扫描间隔单位为分钟，最小 ${MIN_ALERT_SCAN_INTERVAL_MINUTES} 分钟。`, category: 'unknown' });
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

  /* ---- derived data for technicals ---- */

  const capitalFlow = result?.fundamentalContext?.capitalFlow?.data?.stockFlow;
  const rsScore = isFiniteNumber(result?.trendScore) ? Math.round(result.trendScore) : null;

  /* ---- buy points from strategyDecisions ---- */
  const buyPoints = useMemo(() => {
    if (!result?.strategyDecisions?.length) return [];
    return computeBuyPoints(
      result.strategyDecisions,
      result.currentPrice,
      result.support,
      result.pressure,
      result.ma10,
      result.ma20,
    );
  }, [result]);

  /* ---- build signal items ---- */

  const signalItems = useMemo(() => {
    if (!result) return [];
    const items: Array<{ title: string; detail: string; value: string }> = [];

    if (isFiniteNumber(result.pressure) && isFiniteNumber(result.currentPrice)) {
      const diff = ((result.currentPrice - result.pressure) / result.pressure * 100);
      if (diff > 0) {
        items.push({ title: `突破前期高点 ${formatNumber(result.pressure)}`, detail: `收盘 ${formatNumber(result.currentPrice)}，放量突破前期震荡区间上沿`, value: `+${diff.toFixed(1)}%` });
      }
    }

    if (isFiniteNumber(result.volumeRatio)) {
      const label = volumeRatioLabel(result.volumeRatio);
      items.push({ title: `量比 ${result.volumeRatio.toFixed(1)}× · 5日均值`, detail: `本次成交量为近 5 日均值的 ${result.volumeRatio.toFixed(1)} 倍，${label === '显著放量' || label === '放量' ? '资金主动买入' : '资金参与一般'}`, value: label === '显著放量' || label === '放量' ? '强' : '弱' });
    }

    if (themeAttributions.length > 0) {
      const triggered = themeAttributions.filter((t) => t.confidence === 'high').length;
      items.push({ title: `主题词命中 ${triggered} 项`, detail: themeAttributions.slice(0, 3).map((t) => `"${t.themeName}"`).join('、') + ' 同时命中', value: `${triggered} / ${themeAttributions.length}` });
    }

    if (result.trendStatus || result.pattern) {
      const statusText = result.trendStatus ?? result.pattern ?? '';
      items.push({ title: `${result.ma20 ? 'MA20' : '均线'} ${statusText.includes('上') || statusText.includes('多') ? '多头排列' : '趋势判断'}`, detail: result.ma10 && result.ma20 ? `${result.ma10 > result.ma20 ? '短期均线在长期均线之上' : '短期均线在长期均线之下'}，趋势确认` : '均线结构分析', value: statusText.includes('上') || statusText.includes('多') || statusText.includes('强') ? '强' : '弱' });
    }

    if (isFiniteNumber(capitalFlow?.mainNetInflow)) {
      items.push({ title: `资金流入 ${formatMoneyCompact(capitalFlow.mainNetInflow)}`, detail: '近期大单净流入显著，机构席位活跃', value: formatMoneyCompact(capitalFlow.mainNetInflow) });
    }

    // Fill from selectedReasons if we have fewer than 5
    for (const reason of result.selectedReasons) {
      if (items.length >= 5) break;
      if (!items.some((item) => reason.includes(item.title.slice(0, 4)))) {
        items.push({ title: reason, detail: '', value: '' });
      }
    }

    return items.slice(0, 5);
  }, [result, themeAttributions, capitalFlow]);

  /* ================================================================ */
  /*  RENDER                                                           */
  /* ================================================================ */

  return (
    <AppPage className="!max-w-none px-4 md:px-8 lg:px-12 xl:px-16">

      {/* ---- Top search bar ---- */}
      <div className="search-bar-card flex flex-wrap items-center gap-3 lg:gap-4">
        {/* Breadcrumb */}
        <p className="shrink-0 text-sm text-secondary-text">
          单股查询
          {result ? (
            <> / <span className="font-semibold text-foreground">{result.stockName}</span>{' '}<span>{result.stockCode}</span></>
          ) : null}
        </p>

        {/* Search form */}
        <form className="flex min-w-0 flex-1 items-center gap-2" onSubmit={handleSubmit}>
          <div className="relative min-w-0 flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-secondary-text" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="输入代码、名称或拼音首字母..."
              className="h-10 w-full rounded-xl border border-border bg-card pl-9 pr-3 text-sm text-foreground placeholder:text-secondary-text/60 focus:border-foreground/30 focus:outline-none"
            />
          </div>
          <Select
            value={strategy}
            onChange={setStrategy}
            options={STRATEGY_OPTIONS.map((item) => ({ value: item.value, label: item.label }))}
            label=""
            className="h-10 w-28"
          />
          <Button type="submit" size="sm" isLoading={isLoading} loadingText="查询中..." className="h-10 rounded-xl px-4">
            <Search className="h-3.5 w-3.5" />
            开始查询
          </Button>
        </form>

        {/* History quick links */}
        <div className="flex shrink-0 items-center gap-2 text-sm text-secondary-text">
          <span>历史</span>
          {recentHistoryNames.map((item) => (
            <button
              key={item.queryId}
              type="button"
              onClick={() => void handleHistoryRestore(item)}
              className="text-foreground/80 transition-colors hover:text-foreground"
            >
              {item.stockName || item.queryText || '查询'}
            </button>
          ))}
          {recentHistoryNames.length > 0 ? <span className="text-border">·</span> : null}
          <button type="button" onClick={() => setHistoryOpen(true)} className="font-medium text-foreground/80 hover:text-foreground">
            {recentHistoryNames.length > 0 ? '查看全部' : '历史查询'}
          </button>
        </div>
      </div>

      {/* ---- Alerts / Loading ---- */}
      <div className="mt-4 space-y-3">
        {error ? <ApiErrorAlert error={error} /> : null}
        {watchlistActionError ? <ApiErrorAlert error={watchlistActionError} /> : null}
        {watchlistActionMessage ? <InlineAlert variant="success" title="操作成功" message={watchlistActionMessage} /> : null}
        {isLoading && queryTask ? (
          <InlineAlert variant="info" title="正在后台分析" message={queryTask.message || '正在获取日线、实时行情和基本面，请稍候。'} />
        ) : null}
        {result && hasPendingInputChange ? (
          <InlineAlert variant="info" title="输入已变更" message={`当前输入 ${query.trim() || '--'}，页面仍展示 ${lastResolvedInput || '--'} 的结果。`} />
        ) : null}
      </div>

      {/* ---- Main two-column grid ---- */}
      <div className="mt-5 grid gap-5 xl:grid-cols-[1fr_360px]">

        {/* ======================== LEFT COLUMN ======================== */}
        <div className="space-y-5">

          {/* ---- Stock header card ---- */}
          <Card padding="lg" className="!rounded-2xl">
            {result ? (
              <div>
                {/* Top row: name + price */}
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <div className="flex items-center gap-3">
                      <h2 className="text-3xl font-bold text-foreground">{result.stockName}</h2>
                      <span className="rounded-md border border-border px-2 py-0.5 text-sm text-secondary-text">{result.stockCode}</span>
                      {instrumentBadgeLabel(result.instrumentLabel, result.instrumentType) ? (
                        <Badge variant="info">{instrumentBadgeLabel(result.instrumentLabel, result.instrumentType)}</Badge>
                      ) : null}
                    </div>
                    {/* Tags */}
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      {isInWatchlist ? (
                        <span className="rounded-full bg-danger/90 px-3 py-1 text-xs font-medium text-white">
                          观察池
                        </span>
                      ) : null}
                      {themeAttributions.slice(0, 5).map((theme) => (
                        <span key={theme.themeId} className="rounded-full border border-border bg-elevated/60 px-3 py-1 text-xs font-medium text-foreground">
                          {theme.themeName}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-4xl font-bold text-foreground">{formatNumber(result.currentPrice)}</p>
                    <p className={`mt-1 text-lg font-semibold ${signedValueClass(result.pctChg)}`}>
                      {signedChange(result.currentPrice, result.pctChg)}
                    </p>
                  </div>
                </div>

                {/* Key metrics row */}
                <div className="mt-5 grid grid-cols-2 gap-4 border-t border-border pt-5 sm:grid-cols-3 lg:grid-cols-6">
                  <MetricCell label="市值" value={formatMoney(result.totalMv ?? result.fundamentalContext?.valuation?.data?.totalMv)} sub={`流通 ${formatMoney(result.circMv ?? result.fundamentalContext?.valuation?.data?.circMv)}`} />
                  <MetricCell label="PE(TTM)" value={formatNumber(result.peRatio)} sub={`量比 ${formatNumber(result.volumeRatio, 2)}`} />
                  <MetricCell label="今日成交" value={formatMoney(capitalFlow?.mainNetInflow ? undefined : undefined)} sub="" />
                  <MetricCell label="支撑 / 压力" value={`${formatNumber(result.support)} — ${formatNumber(result.pressure)}`} sub="" />
                  <MetricCell label="主题数" value={`${themeAttributions.length}`} sub={`${themeAttributions.filter((t) => t.confidence === 'high').length} 触发中`} />
                  <MetricCell label="RS 评分" value={rsScore != null ? String(rsScore) : '--'} valueClass={rsScoreColor(rsScore)} sub={topTheme ? `${topTheme.themeName}` : ''} />
                </div>
              </div>
            ) : (
              /* Empty state for stock header */
              <div>
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h2 className="text-3xl font-bold text-foreground">单股查询</h2>
                    <p className="mt-2 max-w-xl text-sm leading-7 text-secondary-text">
                      检索、回看、信号和历史扫描记录收在同一页里，优先保证高频判断顺手。
                    </p>
                    {/* Quick query buttons */}
                    <div className="mt-4 flex flex-wrap gap-2">
                      {QUICK_QUERIES.map((item) => (
                        <button
                          key={item.value}
                          type="button"
                          onClick={() => handleQuickQuery(item.value)}
                          className={[
                            'rounded-full border px-4 py-1.5 text-sm font-medium transition-colors',
                            query === item.value
                              ? 'border-foreground/30 bg-foreground text-background'
                              : 'border-border bg-card text-foreground hover:border-foreground/30',
                          ].join(' ')}
                        >
                          {item.label}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-4xl font-bold text-foreground/20">--</p>
                    <p className="mt-1 text-lg text-secondary-text">等待查询</p>
                  </div>
                </div>
              </div>
            )}
          </Card>

          {/* ---- Loading skeleton ---- */}
          {isLoading && !result ? (
            <Card padding="lg" className="!rounded-2xl">
              <div className="flex items-center gap-4">
                <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-cyan/10 text-cyan">
                  <Sparkles className="h-5 w-5 animate-pulse" />
                </div>
                <div>
                  <p className="text-lg font-semibold text-foreground">正在分析...</p>
                  <p className="mt-1 text-sm text-secondary-text">解析股票输入，获取日线、实时行情和基本面数据。</p>
                </div>
              </div>
            </Card>
          ) : null}

          {/* ---- K-Line card ---- */}
          {result ? (
            <Card padding="lg" className="!rounded-2xl">
              <CandlestickChart
                stockCode={result.stockCode}
                stockName={result.stockName}
                bars={120}
              />
            </Card>
          ) : null}

          {/* ---- Signal Breakdown ---- */}
          <Card padding="lg" className="!rounded-2xl">
            <div className="flex items-center justify-between gap-4">
              <h3 className="text-lg font-semibold text-foreground">
                {result ? '为什么被选中 · Signal Breakdown' : '信号点'}
              </h3>
              {result && rsScore != null ? (
                <p className="text-sm text-secondary-text">
                  {signalItems.length}/{result.selectedReasons.length + result.excludedReasons.length} 信号触发 · 综合 RS {rsScore}
                </p>
              ) : null}
            </div>

            {result ? (
              <div className="mt-5 space-y-1">
                {signalItems.length > 0 ? (
                  signalItems.map((item, index) => (
                    <div key={item.title} className="flex items-start gap-4 rounded-xl px-2 py-3 transition-colors hover:bg-elevated/40">
                      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-border text-sm font-semibold text-foreground">
                        {String(index + 1).padStart(2, '0')}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="font-medium text-foreground">{item.title}</p>
                        {item.detail ? <p className="mt-0.5 text-sm text-secondary-text">{item.detail}</p> : null}
                      </div>
                      {item.value ? (
                        <span className={`shrink-0 text-right text-sm font-semibold ${item.value.startsWith('+') ? 'text-success' : item.value === '强' ? 'text-foreground' : 'text-secondary-text'}`}>
                          {item.value}
                        </span>
                      ) : null}
                    </div>
                  ))
                ) : (
                  <p className="py-6 text-center text-sm text-secondary-text">当前没有明确的入选信号。</p>
                )}
              </div>
            ) : (
              <div className="mt-4 rounded-xl border border-dashed border-border bg-elevated/30 px-4 py-6">
                <p className="text-sm text-secondary-text">这里只放真正影响出手动作的信号点。</p>
                <p className="mt-1 text-sm text-secondary-text">查询成功后，这里会展示试仓区、突破位、止损线、策略矩阵和后续动作。</p>
              </div>
            )}
          </Card>

          {/* ---- Same-theme stocks ---- */}
          {result && topTheme ? (
            <Card padding="lg" className="!rounded-2xl">
              <div className="flex items-center justify-between gap-4">
                <h3 className="text-lg font-semibold text-foreground">
                  同主题股票：{themeAttributions.slice(0, 2).map((t) => t.themeName).join(' / ')}
                </h3>
                <p className="text-sm text-secondary-text">按 RS 排序</p>
              </div>
              <div className="mt-4 flex h-32 items-center justify-center rounded-xl border border-dashed border-border bg-elevated/30">
                <p className="text-sm text-secondary-text">同主题股票比较功能正在开发中</p>
              </div>
            </Card>
          ) : null}
        </div>

        {/* ======================== RIGHT COLUMN ======================== */}
        <div className="space-y-5">

          {/* ---- 所属主题 ---- */}
          <Card padding="lg" className="!rounded-2xl">
            <h3 className="text-lg font-semibold text-foreground">
              所属主题 · {themeAttributions.length > 0 ? `${themeAttributions.length} 个` : '待查询'}
            </h3>

            {themeAttributions.length > 0 ? (
              <div className="mt-4 space-y-3">
                {themeAttributions.map((theme) => {
                  const status = themeStatusBadge(theme);
                  return (
                    <div key={theme.themeId} className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="font-medium text-foreground">{theme.themeName}</p>
                        <p className="mt-0.5 text-xs text-secondary-text">
                          {confidenceLabel(theme.confidence)} · {theme.reason?.slice(0, 20) || ''}
                        </p>
                      </div>
                      <Badge
                        variant={status === 'TRIGGERED' ? 'danger' : 'default'}
                        size="sm"
                        className={status === 'TRIGGERED' ? 'border-danger/30 bg-danger/90 text-white' : ''}
                      >
                        {status}
                      </Badge>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="mt-4 text-sm text-secondary-text">查询成功后展示主题归因、概念摘要和关联板块。</p>
            )}
          </Card>

          {/* ---- 技术信号 ---- */}
          <Card padding="lg" className="!rounded-2xl">
            <h3 className="text-lg font-semibold text-foreground">技术信号 · Technicals</h3>

            {result ? (
              <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-5">
                <TechMetricItem label="趋势分" value={rsScore != null ? String(rsScore) : '--'} bar={rsScore != null ? rsScoreColor(rsScore).replace('text-', 'bg-') : 'bg-secondary-text/30'} sub={result.trendStatus || result.pattern || '--'} />
                <TechMetricItem label="偏离 MA10" value={isFiniteNumber(result.biasMa10) ? `${result.biasMa10 > 0 ? '+' : ''}${result.biasMa10.toFixed(1)}%` : '--'} bar={isFiniteNumber(result.biasMa10) ? (Math.abs(result.biasMa10) > 5 ? 'bg-danger' : 'bg-success') : 'bg-secondary-text/30'} sub={isFiniteNumber(result.biasMa10) ? (Math.abs(result.biasMa10) > 5 ? '偏离较大' : '偏离适中') : '--'} />
                <TechMetricItem label="量比" value={isFiniteNumber(result.volumeRatio) ? result.volumeRatio.toFixed(2) : '--'} bar={techBarColor(volumeRatioLabel(result.volumeRatio))} sub={volumeRatioLabel(result.volumeRatio)} />
                <TechMetricItem label="换手率" value={isFiniteNumber(result.turnoverRate) ? `${result.turnoverRate.toFixed(2)}%` : '--'} bar={techBarColor(turnoverLabel(result.turnoverRate))} sub={turnoverLabel(result.turnoverRate)} />
                <TechMetricItem label="MA10" value={formatNumber(result.ma10)} bar="bg-secondary-text/30" sub="" />
                <TechMetricItem label="MA20" value={formatNumber(result.ma20)} bar="bg-secondary-text/30" sub="" />
              </div>
            ) : (
              <p className="mt-4 text-sm text-secondary-text">查询成功后展示 RSI、MACD、量比、换手率等技术指标。</p>
            )}
          </Card>

          {/* ---- 买入决策 ---- */}
          <Card padding="lg" className="!rounded-2xl">
            <div className="flex items-baseline justify-between gap-3">
              <h3 className="text-lg font-semibold text-foreground">买入决策 · Buy Points</h3>
              {isFiniteNumber(result?.currentPrice) ? (
                <p className="text-xs tracking-widest text-secondary-text">
                  <span className="uppercase">现价 now</span>{' '}
                  <span className="ml-1 text-sm font-bold text-foreground">{formatNumber(result.currentPrice)}</span>
                </p>
              ) : null}
            </div>

            {buyPoints.length > 0 ? (
              <div className="mt-4 space-y-0">
                <p className="mb-3 text-xs text-secondary-text">{buyPoints.length} 种策略的入场建议</p>
                {buyPoints.map((bp) => (
                  <div key={bp.key} className={`flex gap-3 rounded-xl px-2 py-3 ${bp.matched ? 'bg-success/6' : ''}`}>
                    {/* number */}
                    <span className="mt-0.5 shrink-0 text-lg font-black text-foreground/15">
                      {String(bp.index).padStart(2, '0')}
                    </span>
                    {/* body */}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <p className="font-medium text-foreground">{bp.name}</p>
                        <span className="text-xs text-secondary-text">{bp.nameEn}</span>
                        <Badge variant={bp.badgeVariant} size="sm">{bp.badge}</Badge>
                      </div>
                      {/* buy zone */}
                      {bp.zoneLow != null && bp.zoneHigh != null ? (
                        <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-secondary-text">
                          <span>
                            建议买入区间{' '}
                            <span className="font-semibold text-foreground">{formatNumber(bp.zoneLow)}</span>
                            {' – '}
                            <span className="font-semibold text-foreground">{formatNumber(bp.zoneHigh)}</span>
                          </span>
                          {bp.distPct != null ? (
                            <span>
                              距现价{' '}
                              <span className={bp.distPct > 0 ? 'text-success' : bp.distPct < -5 ? 'text-danger' : 'text-foreground'}>
                                {bp.distPct > 0 ? '+' : ''}{bp.distPct.toFixed(1)}%
                              </span>
                            </span>
                          ) : null}
                        </div>
                      ) : null}
                      {/* status + description */}
                      <div className="mt-1 flex items-center gap-2">
                        <span className={`text-xs font-medium ${bp.statusColor}`}>{bp.status}</span>
                        {bp.description ? <span className="text-xs text-secondary-text">{bp.description}</span> : null}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="mt-4 text-sm text-secondary-text">查询成功后展示策略维度的入场建议与买入区间。</p>
            )}
          </Card>

          {/* ---- 历史扫描记录 ---- */}
          <Card padding="lg" className="!rounded-2xl">
            <h3 className="text-lg font-semibold text-foreground">历史扫描记录 · Activity</h3>

            {historyItems.length > 0 ? (
              <div className="mt-4 space-y-0">
                {historyItems.slice(0, 8).map((item) => {
                  const isActive = item.queryId === currentHistoryId;
                  return (
                    <button
                      key={item.queryId}
                      type="button"
                      onClick={() => void handleHistoryRestore(item)}
                      className={`flex w-full items-start gap-3 rounded-lg px-2 py-2.5 text-left transition-colors hover:bg-elevated/40 ${isActive ? 'bg-elevated/40' : ''}`}
                    >
                      <span className="mt-1 shrink-0 text-xs text-secondary-text">{formatShortDate(item.completedAt || item.createdAt)}</span>
                      <div className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${item.signal === '短线异动' || item.signal === '趋势跟随' || item.signal === '持有候选' ? 'bg-danger' : 'bg-foreground/40'}`} />
                      <p className="min-w-0 text-sm text-foreground">
                        {item.stockName || item.queryText || '查询'}{item.signal ? ` · ${item.signal}` : ''}
                      </p>
                    </button>
                  );
                })}
              </div>
            ) : (
              <p className="mt-4 text-sm text-secondary-text">查过几次之后，这里会自动显示最近几次扫描记录。</p>
            )}
          </Card>

          {/* ---- 下一步 action card ---- */}
          <div className="rounded-2xl bg-foreground px-5 py-5 text-background">
            <p className="text-xs uppercase tracking-widest text-background/60">下 一 步</p>
            <h3 className="mt-2 text-xl font-bold">
              {result
                ? isInWatchlist ? '已在观察池 · 继续持有' : '加入观察池 · 持续跟踪'
                : '查询后查看下一步建议'}
            </h3>
            {result ? (
              <>
                <p className="mt-3 text-sm leading-6 text-background/70">
                  {rsScore != null ? `当前位置 ${rsScore > 80 ? '较高' : rsScore > 60 ? '中等' : '偏低'} 分位` : ''}
                  {isFiniteNumber(result.pressure) ? `，距前高 ${formatNumber(result.pressure)} ${isFiniteNumber(result.currentPrice) && isFiniteNumber(result.pressure) ? `仅 ${((result.pressure - result.currentPrice) / result.currentPrice * 100).toFixed(1)}%` : ''}` : ''}
                  {isFiniteNumber(result.support) ? `。可考虑设置 ${formatNumber(result.support)} 跟踪止盈。` : '。'}
                </p>
                <div className="mt-4 grid grid-cols-2 gap-3">
                  <Button
                    type="button"
                    isLoading={watchlistLoading || alertRuleLoading}
                    loadingText="处理中..."
                    disabled={isInWatchlist && hasStockAlertRules}
                    onClick={() => {
                      if (!isInWatchlist) { void handleAddToWatchlist(); }
                      else { void handleCreateDefaultAlerts(); }
                    }}
                    className="rounded-xl border border-background/20 bg-background/10 px-4 py-2.5 text-sm font-medium text-background hover:bg-background/20"
                  >
                    {isInWatchlist ? (hasStockAlertRules ? '告警已设置' : '设置止盈') : '加入观察池'}
                  </Button>
                  <Link
                    to={result?.queryId ? `/deep-analysis?queryId=${encodeURIComponent(result.queryId)}&stock=${encodeURIComponent(result.stockCode)}&name=${encodeURIComponent(result.stockName)}` : '/deep-analysis'}
                    className="inline-flex items-center justify-center rounded-xl border border-background/20 bg-background px-4 py-2.5 text-sm font-medium text-foreground hover:bg-background/90"
                  >
                    深度分析 →
                  </Link>
                </div>
              </>
            ) : (
              <p className="mt-3 text-sm text-background/60">完成查询后，这里会给出观察池和深度分析的操作入口。</p>
            )}
          </div>
        </div>
      </div>

      {/* ---- History Drawer ---- */}
      <Drawer isOpen={historyOpen} onClose={() => setHistoryOpen(false)} title="单股查询历史" width="max-w-xl" side="right">
        <div className="space-y-4">
          {historyError ? <ApiErrorAlert error={historyError} /> : null}
          {historyLoading ? <InlineAlert variant="info" title="正在加载历史记录" message="正在从后端读取最近的单股查询结果。" /> : null}
          {historyItems.length === 0 ? (
            <EmptyState title="暂无单股查询历史" description="查过几次股票之后，这里会从后端返回最近记录。" icon={<Clock3 className="h-8 w-8" />} />
          ) : null}
          <div className="space-y-3">
            {historyItems.map((item) => {
              const active = item.queryId === currentHistoryId;
              const restoring = historyRestoreId === item.queryId;
              return (
                <div key={item.queryId} className={['rounded-2xl border px-4 py-4 transition-colors', active ? 'border-cyan/40 bg-cyan/6' : 'border-border/60 bg-background/70'].join(' ')}>
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
                  <div className="mt-4 flex items-center justify-end gap-2">
                    <Button variant="ghost" size="sm" disabled={!item.stockCode} onClick={() => { if (item.stockCode) setQuery(item.stockCode); }}>
                      填入代码
                    </Button>
                    <Button variant="outline" size="sm" isLoading={restoring} loadingText="恢复中..." onClick={() => void handleHistoryRestore(item)}>
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

/* ------------------------------------------------------------------ */
/*  Sub-components                                                     */
/* ------------------------------------------------------------------ */

type MetricCellProps = {
  label: string;
  value: string;
  sub?: string;
  valueClass?: string;
};

const MetricCell: React.FC<MetricCellProps> = ({ label, value, sub, valueClass }) => (
  <div>
    <p className="text-xs text-secondary-text">{label}</p>
    <p className={`mt-1 text-xl font-bold ${valueClass || 'text-foreground'}`}>{value}</p>
    {sub ? <p className="mt-0.5 text-xs text-secondary-text">{sub}</p> : null}
  </div>
);

type TechMetricItemProps = {
  label: string;
  value: string;
  bar: string;
  sub: string;
};

const TechMetricItem: React.FC<TechMetricItemProps> = ({ label, value, bar, sub }) => (
  <div>
    <p className="text-xs text-secondary-text">{label}</p>
    <p className="mt-1 text-2xl font-bold text-foreground">{value}</p>
    <div className={`mt-1.5 h-1 w-full rounded-full ${bar}`} />
    <p className="mt-1 text-xs text-secondary-text">{sub}</p>
  </div>
);

export default SingleStockQueryPage;
