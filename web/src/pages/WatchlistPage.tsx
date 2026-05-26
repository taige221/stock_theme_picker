import type React from 'react';
import { useEffect, useMemo, useState } from 'react';
import { Bell, BarChart3, CheckCheck, Plus, RefreshCw, Search, SquarePen, Trash2 } from 'lucide-react';
import { Link } from 'react-router-dom';
import { createParsedApiError, getParsedApiError, type ParsedApiError } from '../api/error';
import { watchlistApi, type StockAlertEventItem, type StockAlertLoopStatus, type StockAlertRuleItem, type StockWatchlistItem } from '../api/watchlist';
import { CandlestickChart } from '../components/CandlestickChart';
import { ApiErrorAlert, AppPage, Badge, Button, Card, Drawer, EmptyState, InlineAlert, Input } from '../components/common';

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const SIGNAL_FILTERS = [
  { key: 'all', label: '全部' },
  { key: 'hold', label: '继续持有' },
  { key: 'alert', label: '短线异动' },
  { key: 'watch', label: '观察中' },
  { key: 'risk', label: '考虑止损' },
] as const;

type SignalFilterKey = typeof SIGNAL_FILTERS[number]['key'];

/* ------------------------------------------------------------------ */
/*  Utility functions                                                  */
/* ------------------------------------------------------------------ */

function signalBadgeVariant(signal?: string | null): 'success' | 'danger' | 'warning' | 'info' | 'default' {
  if (!signal) return 'default';
  if (signal.includes('持有') || signal === '趋势跟随') return 'success';
  if (signal === '短线异动') return 'danger';
  if (signal.includes('超买') || signal.includes('RSI')) return 'warning';
  if (signal.includes('观察') || signal.includes('横盘')) return 'info';
  if (signal.includes('止损') || signal === '不宜追高') return 'danger';
  return 'default';
}

function signalBadgeClass(signal?: string | null): string {
  if (!signal) return '';
  if (signal.includes('持有') || signal === '趋势跟随') return 'border-success/30 bg-success/90 text-white';
  if (signal === '短线异动') return 'border-warning/30 bg-warning/90 text-white';
  if (signal.includes('超买') || signal.includes('RSI')) return 'border-warning/30 bg-warning/90 text-white';
  if (signal.includes('观察') || signal.includes('横盘')) return 'border-foreground/20 bg-foreground/80 text-background';
  if (signal.includes('止损') || signal === '不宜追高') return 'border-danger/30 bg-danger/90 text-white';
  return '';
}

function formatDateTime(value?: string | null): string {
  if (!value) return '--';
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

function formatShortDate(value?: string | null): string {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: '2-digit' }).format(date);
}

function daysSince(dateStr?: string | null): number {
  if (!dateStr) return 0;
  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) return 0;
  return Math.floor((Date.now() - date.getTime()) / (1000 * 60 * 60 * 24));
}

function alertRuleLabel(value: string): string {
  if (value === 'support_retest') return '价格跌破支撑位';
  if (value === 'breakout_confirm') return '触及前高突破位';
  if (value === 'risk_event') return '风险事件监控';
  return value;
}

function formatThreshold(value?: number | null): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '--';
  return value.toFixed(2);
}

function isPriceRule(ruleType: string): boolean {
  return ruleType === 'support_retest' || ruleType === 'breakout_confirm';
}

function hasUsableThreshold(rule: Pick<StockAlertRuleItem, 'ruleType' | 'thresholdValue'>): boolean {
  return !isPriceRule(rule.ruleType) || (typeof rule.thresholdValue === 'number' && Number.isFinite(rule.thresholdValue) && rule.thresholdValue > 0);
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string' && item.trim().length > 0);
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function matchesSignalFilter(signal: string | null | undefined, filter: SignalFilterKey): boolean {
  if (filter === 'all') return true;
  if (!signal) return filter === 'watch';
  if (filter === 'hold') return signal.includes('持有') || signal === '趋势跟随';
  if (filter === 'alert') return signal === '短线异动';
  if (filter === 'watch') return signal.includes('观察') || signal.includes('横盘') || signal.includes('等待');
  if (filter === 'risk') return signal.includes('止损') || signal === '不宜追高';
  return true;
}

function buildDeepAnalysisHref(params: {
  analysisId?: string | null;
  sourceQueryId?: string | null;
  stockCode?: string | null;
  stockName?: string | null;
}): string | null {
  const nextParams = new URLSearchParams();
  if (params.analysisId) nextParams.set('analysisId', params.analysisId);
  if (params.sourceQueryId) nextParams.set('queryId', params.sourceQueryId);
  if (params.stockCode) nextParams.set('stock', params.stockCode);
  if (params.stockName) nextParams.set('name', params.stockName);
  const serialized = nextParams.toString();
  return serialized ? `/deep-analysis?${serialized}` : null;
}

function buildEventInsight(event: StockAlertEventItem): { summary: string; details: string[] } {
  const payload = event.payload ?? {};
  const details: string[] = [];

  if (event.ruleType === 'support_retest') {
    const currentPrice = typeof payload.currentPrice === 'number' ? payload.currentPrice : null;
    const thresholdValue = typeof payload.thresholdValue === 'number' ? payload.thresholdValue : null;
    const distanceRatio = typeof payload.distanceRatio === 'number' ? payload.distanceRatio : null;
    if (currentPrice !== null && thresholdValue !== null) {
      details.push(`当前价 ${formatThreshold(currentPrice)}，支撑位 ${formatThreshold(thresholdValue)}`);
    }
    if (distanceRatio !== null) details.push(`离支撑位约 ${formatPercent(distanceRatio)}`);
    return { summary: '价格重新靠近你的低吸观察位了，重点看能不能稳住。', details };
  }
  if (event.ruleType === 'breakout_confirm') {
    const currentPrice = typeof payload.currentPrice === 'number' ? payload.currentPrice : null;
    const thresholdValue = typeof payload.thresholdValue === 'number' ? payload.thresholdValue : null;
    if (currentPrice !== null && thresholdValue !== null) {
      details.push(`当前价 ${formatThreshold(currentPrice)}，确认位 ${formatThreshold(thresholdValue)}`);
    }
    return { summary: '价格已站上突破位，下一步盯量价延续。', details };
  }
  if (event.ruleType === 'risk_event') {
    const riskEvents = isStringArray(payload.riskEvents) ? payload.riskEvents.slice(0, 3) : [];
    const headlines = isStringArray(payload.headlines) ? payload.headlines.slice(0, 2) : [];
    if (riskEvents.length > 0) details.push(`风险项：${riskEvents.join('、')}`);
    if (headlines.length > 0) details.push(`相关新闻：${headlines.join('；')}`);
    return { summary: '新闻层面风险提醒，先确认事件真假和影响范围。', details };
  }
  return { summary: event.message, details };
}

/* ------------------------------------------------------------------ */
/*  Main component                                                     */
/* ------------------------------------------------------------------ */

const WatchlistPage: React.FC = () => {
  const [items, setItems] = useState<StockWatchlistItem[]>([]);
  const [alertRules, setAlertRules] = useState<StockAlertRuleItem[]>([]);
  const [alertEvents, setAlertEvents] = useState<StockAlertEventItem[]>([]);
  const [alertLoopStatus, setAlertLoopStatus] = useState<StockAlertLoopStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [actionError, setActionError] = useState<ParsedApiError | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [deletingCode, setDeletingCode] = useState<string | null>(null);
  const [deletingRuleId, setDeletingRuleId] = useState<number | null>(null);
  const [editingRuleId, setEditingRuleId] = useState<number | null>(null);
  const [editingThreshold, setEditingThreshold] = useState('');
  const [editingScanInterval, setEditingScanInterval] = useState('5');
  const [editingNote, setEditingNote] = useState('');
  const [savingRuleId, setSavingRuleId] = useState<number | null>(null);
  const [readingEventId, setReadingEventId] = useState<number | null>(null);
  const [markingAllRead, setMarkingAllRead] = useState(false);
  const [runningScan, setRunningScan] = useState(false);
  const [chartStock, setChartStock] = useState<{ code: string; name: string } | null>(null);
  const [signalFilter, setSignalFilter] = useState<SignalFilterKey>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [eventDrawerOpen, setEventDrawerOpen] = useState(false);
  const [showNewRuleForm, setShowNewRuleForm] = useState(false);
  const [newRuleStockCode, setNewRuleStockCode] = useState('');
  const [newRuleSupportPrice, setNewRuleSupportPrice] = useState('');
  const [newRuleBreakoutPrice, setNewRuleBreakoutPrice] = useState('');
  const [creatingRule, setCreatingRule] = useState(false);

  /* ---- data loaders ---- */

  const loadWatchlist = async () => {
    setLoading(true);
    setError(null);
    try {
      const [stockResponse, ruleResponse, eventResponse, loopStatusResponse] = await Promise.all([
        watchlistApi.listStocks(),
        watchlistApi.listStockAlertRules(),
        watchlistApi.listStockAlertEvents({ limit: 20 }),
        watchlistApi.getStockAlertLoopStatus(),
      ]);
      setItems(stockResponse.items);
      setAlertRules(ruleResponse.items);
      setAlertEvents(eventResponse.items);
      setAlertLoopStatus(loopStatusResponse);
    } catch (requestError) {
      setError(getParsedApiError(requestError));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const init = async () => { await loadWatchlist(); };
    void init();
  }, []);

  /* ---- handlers ---- */

  const handleDelete = async (stockCode: string) => {
    setDeletingCode(stockCode);
    setActionError(null);
    setMessage(null);
    try {
      await watchlistApi.deleteStock(stockCode);
      setItems((prev) => prev.filter((item) => item.stockCode !== stockCode));
      setMessage(`${stockCode} 已从观察池移除`);
    } catch (requestError) {
      setActionError(getParsedApiError(requestError));
    } finally {
      setDeletingCode(null);
    }
  };

  const handleDeleteAlertRule = async (ruleId: number) => {
    setDeletingRuleId(ruleId);
    setActionError(null);
    setMessage(null);
    try {
      await watchlistApi.deleteStockAlertRule(ruleId);
      setAlertRules((prev) => prev.filter((item) => item.id !== ruleId));
      setMessage('已删除一条单股告警规则');
      void loadWatchlist();
    } catch (requestError) {
      setActionError(getParsedApiError(requestError));
    } finally {
      setDeletingRuleId(null);
    }
  };

  const startEditingRule = (rule: StockAlertRuleItem) => {
    setEditingRuleId(rule.id);
    setEditingThreshold(rule.thresholdValue !== null && rule.thresholdValue !== undefined ? String(rule.thresholdValue) : '');
    setEditingScanInterval(String(Math.max(5, rule.scanIntervalMinutes || 5)));
    setEditingNote(rule.note ?? '');
  };

  const cancelEditingRule = () => {
    setEditingRuleId(null);
    setEditingThreshold('');
    setEditingScanInterval('5');
    setEditingNote('');
  };

  const handleToggleAlertRule = async (rule: StockAlertRuleItem) => {
    setSavingRuleId(rule.id);
    setActionError(null);
    setMessage(null);
    try {
      if (!rule.enabled && !hasUsableThreshold(rule)) {
        throw createParsedApiError({
          title: '价格阈值还没配置',
          message: '这条价格规则缺少有效阈值，先补上阈值后再启用。',
          category: 'unknown',
        });
      }
      const updated = await watchlistApi.updateStockAlertRule({
        ruleId: rule.id,
        thresholdValue: rule.thresholdValue,
        scanIntervalMinutes: rule.scanIntervalMinutes,
        enabled: !rule.enabled,
        note: rule.note ?? undefined,
      });
      setAlertRules((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      setMessage(`${rule.stockName} 的规则已${updated.enabled ? '启用' : '停用'}`);
      void loadWatchlist();
    } catch (requestError) {
      setActionError(getParsedApiError(requestError));
    } finally {
      setSavingRuleId(null);
    }
  };

  const handleSaveRule = async (rule: StockAlertRuleItem) => {
    setSavingRuleId(rule.id);
    setActionError(null);
    setMessage(null);
    try {
      const nextThreshold = editingThreshold.trim() === '' ? null : Number(editingThreshold.trim());
      const nextScanInterval = Number(editingScanInterval.trim() || '5');
      if (isPriceRule(rule.ruleType) && (nextThreshold === null || !Number.isFinite(nextThreshold) || nextThreshold <= 0)) {
        throw createParsedApiError({ title: '价格阈值还没填好', message: '价格规则必须填写大于 0 的有效阈值。', category: 'unknown' });
      }
      if (!Number.isFinite(nextScanInterval) || nextScanInterval < 5) {
        throw createParsedApiError({ title: '扫描间隔不正确', message: '扫描间隔单位为分钟，最小 5 分钟。', category: 'unknown' });
      }
      const updated = await watchlistApi.updateStockAlertRule({
        ruleId: rule.id,
        thresholdValue: rule.ruleType === 'risk_event' ? null : nextThreshold,
        scanIntervalMinutes: Math.round(nextScanInterval),
        enabled: rule.enabled,
        note: editingNote.trim() || undefined,
      });
      setAlertRules((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      setMessage(`${rule.stockName} 的规则已更新`);
      cancelEditingRule();
    } catch (requestError) {
      setActionError(getParsedApiError(requestError));
    } finally {
      setSavingRuleId(null);
    }
  };

  const handleMarkEventRead = async (eventId: number) => {
    setReadingEventId(eventId);
    setActionError(null);
    setMessage(null);
    try {
      const updated = await watchlistApi.markStockAlertEventRead(eventId);
      setAlertEvents((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
    } catch (requestError) {
      setActionError(getParsedApiError(requestError));
    } finally {
      setReadingEventId(null);
    }
  };

  const handleMarkAllEventsRead = async () => {
    setMarkingAllRead(true);
    setActionError(null);
    setMessage(null);
    try {
      const response = await watchlistApi.markAllStockAlertEventsRead();
      if (response.updated > 0) {
        setAlertEvents((prev) => prev.map((item) => ({ ...item, readAt: item.readAt ?? new Date().toISOString() })));
      }
      setMessage(`已标记 ${response.updated} 条告警事件为已读`);
    } catch (requestError) {
      setActionError(getParsedApiError(requestError));
    } finally {
      setMarkingAllRead(false);
    }
  };

  const handleRunScanOnce = async () => {
    setRunningScan(true);
    setActionError(null);
    setMessage(null);
    try {
      const summary = await watchlistApi.runStockAlertLoopOnce();
      const [eventResponse, loopStatusResponse] = await Promise.all([
        watchlistApi.listStockAlertEvents({ limit: 20 }),
        watchlistApi.getStockAlertLoopStatus(),
      ]);
      setAlertEvents(eventResponse.items);
      setAlertLoopStatus(loopStatusResponse);
      setMessage(`手动扫描完成：到期 ${summary.dueRules} 条，触发 ${summary.triggeredEvents} 条事件`);
    } catch (requestError) {
      setActionError(getParsedApiError(requestError));
    } finally {
      setRunningScan(false);
    }
  };

  const handleCreateDefaultRules = async (stockCode: string) => {
    const item = items.find((i) => i.stockCode === stockCode);
    if (!item) return;
    setCreatingRule(true);
    setActionError(null);
    setMessage(null);
    try {
      const supportPrice = newRuleSupportPrice.trim() ? Number(newRuleSupportPrice.trim()) : null;
      const breakoutPrice = newRuleBreakoutPrice.trim() ? Number(newRuleBreakoutPrice.trim()) : null;
      await watchlistApi.createDefaultStockAlertRules({
        stockCode: item.stockCode,
        stockName: item.stockName,
        supportPrice,
        breakoutPrice,
      });
      setMessage(`已为 ${item.stockName} 创建默认告警规则`);
      setShowNewRuleForm(false);
      setNewRuleStockCode('');
      setNewRuleSupportPrice('');
      setNewRuleBreakoutPrice('');
      void loadWatchlist();
    } catch (requestError) {
      setActionError(getParsedApiError(requestError));
    } finally {
      setCreatingRule(false);
    }
  };

  /* ---- derived data ---- */

  const alertEnabledCount = useMemo(() => alertRules.filter((r) => r.enabled).length, [alertRules]);
  const unreadEventCount = useMemo(() => alertEvents.filter((e) => !e.readAt).length, [alertEvents]);

  const latestAnalysisBySourceQueryId = useMemo(() => {
    const map = new Map<string, StockAlertEventItem['linkedAnalysisId']>();
    for (const event of alertEvents) {
      if (event.sourceQueryId && event.linkedAnalysisId && !map.has(event.sourceQueryId)) {
        map.set(event.sourceQueryId, event.linkedAnalysisId);
      }
    }
    return map;
  }, [alertEvents]);

  const avgDaysHeld = useMemo(() => {
    if (items.length === 0) return 0;
    const total = items.reduce((sum, item) => sum + daysSince(item.createdAt), 0);
    return Math.round(total / items.length * 10) / 10;
  }, [items]);

  const filterCounts = useMemo(() => {
    const counts: Record<SignalFilterKey, number> = { all: items.length, hold: 0, alert: 0, watch: 0, risk: 0 };
    for (const item of items) {
      for (const f of SIGNAL_FILTERS) {
        if (f.key !== 'all' && matchesSignalFilter(item.latestSignal, f.key)) {
          counts[f.key]++;
        }
      }
    }
    return counts;
  }, [items]);

  const filteredItems = useMemo(() => {
    let result = items;
    if (signalFilter !== 'all') {
      result = result.filter((item) => matchesSignalFilter(item.latestSignal, signalFilter));
    }
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      result = result.filter((item) =>
        item.stockName.toLowerCase().includes(q)
        || item.stockCode.toLowerCase().includes(q)
        || (item.latestTheme ?? '').toLowerCase().includes(q),
      );
    }
    return result;
  }, [items, signalFilter, searchQuery]);

  /* Count today's triggers per rule */
  const todayTriggersByRule = useMemo(() => {
    const today = new Date().toISOString().slice(0, 10);
    const counts = new Map<number, number>();
    for (const event of alertEvents) {
      if (event.createdAt.startsWith(today)) {
        counts.set(event.ruleId, (counts.get(event.ruleId) ?? 0) + 1);
      }
    }
    return counts;
  }, [alertEvents]);

  const todayTotalTriggers = useMemo(() => {
    const today = new Date().toISOString().slice(0, 10);
    return alertEvents.filter((e) => e.createdAt.startsWith(today)).length;
  }, [alertEvents]);

  const stocksWithoutRules = useMemo(() => {
    const codesWithRules = new Set(alertRules.map((r) => r.stockCode));
    return items.filter((i) => !codesWithRules.has(i.stockCode));
  }, [items, alertRules]);

  /* ================================================================ */
  /*  RENDER                                                           */
  /* ================================================================ */

  return (
    <AppPage className="!max-w-none px-4 md:px-8 lg:px-12 xl:px-16">

      {/* ---- Breadcrumb + Search ---- */}
      <div className="search-bar-card flex flex-wrap items-center gap-3 lg:gap-4">
        <p className="shrink-0 text-sm text-secondary-text">
          观察池 / <span className="font-semibold text-foreground">全部持有</span>
        </p>
        <div className="relative min-w-0 flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-secondary-text" />
          <input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="在观察池中搜索..."
            className="h-10 w-full rounded-xl border border-border bg-card pl-9 pr-3 text-sm text-foreground placeholder:text-secondary-text/60 focus:border-foreground/30 focus:outline-none"
          />
        </div>
        <p className="shrink-0 text-sm text-secondary-text">
          共 {items.length} 个持仓{alertRules.length > 0 ? ` · ${alertEnabledCount} 条提醒` : ''}
        </p>
      </div>

      {/* ---- Stats Cards ---- */}
      <div className="mt-5 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Card padding="lg" className="!rounded-2xl">
          <p className="text-xs uppercase tracking-wider text-secondary-text">持 仓 数</p>
          <p className="mt-2 text-4xl font-bold text-foreground">{items.length}</p>
          <p className="mt-1 text-sm text-secondary-text">
            {items.length > 0 ? `平均持有 ${avgDaysHeld} 天` : '暂无观察项'}
          </p>
        </Card>
        <Card padding="lg" className="!rounded-2xl">
          <p className="text-xs uppercase tracking-wider text-secondary-text">观 察 池 市 值</p>
          <p className="mt-2 text-4xl font-bold text-foreground">--</p>
          <p className="mt-1 text-sm text-secondary-text">待接入实时行情</p>
        </Card>
        <Card padding="lg" className="!rounded-2xl border-success/20 bg-success/5">
          <p className="text-xs uppercase tracking-wider text-secondary-text">本 周 盈 亏</p>
          <p className="mt-2 text-4xl font-bold text-success">--</p>
          <p className="mt-1 text-sm text-secondary-text">待接入实时行情</p>
        </Card>
        <Card padding="lg" className="!rounded-2xl">
          <p className="text-xs uppercase tracking-wider text-secondary-text">今 日 触 发 提 醒</p>
          <p className="mt-2 text-4xl font-bold text-foreground">{todayTotalTriggers}</p>
          <p className="mt-1 text-sm text-secondary-text">
            {unreadEventCount > 0 ? `${unreadEventCount} 条未读` : '无未读提醒'}
          </p>
        </Card>
      </div>

      {/* ---- Filter tabs + sort ---- */}
      <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          {SIGNAL_FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              onClick={() => setSignalFilter(f.key)}
              className={[
                'rounded-full border px-4 py-1.5 text-sm font-medium transition-colors',
                signalFilter === f.key
                  ? 'border-foreground/30 bg-foreground text-background'
                  : 'border-border bg-card text-foreground hover:border-foreground/30',
              ].join(' ')}
            >
              {f.label} {filterCounts[f.key] > 0 ? filterCounts[f.key] : ''}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            className="rounded-xl"
            isLoading={runningScan}
            loadingText="扫描中..."
            onClick={() => void handleRunScanOnce()}
          >
            <RefreshCw className="h-3.5 w-3.5" />
            手动扫描
          </Button>
          <span className="text-xs text-secondary-text">
            按加入时间排序 · 倒序
          </span>
        </div>
      </div>

      {/* ---- Alerts ---- */}
      {error ? <div className="mt-4"><ApiErrorAlert error={error} /></div> : null}
      {actionError ? <div className="mt-4"><ApiErrorAlert error={actionError} /></div> : null}
      {message ? <div className="mt-4"><InlineAlert variant="success" title="操作成功" message={message} /></div> : null}

      {/* ---- Main two-column grid ---- */}
      <div className="mt-5 grid gap-5 xl:grid-cols-[1fr_360px]">

        {/* ======================== LEFT COLUMN ======================== */}
        <div className="space-y-5">

          {/* ---- Stock Table ---- */}
          <Card padding="none" className="!rounded-2xl overflow-hidden">
            {/* Table header */}
            <div className="flex items-center justify-between border-b border-border px-5 py-4">
              <h3 className="text-lg font-semibold text-foreground">
                持仓股票 · Stocks in Pool
              </h3>
              <p className="text-sm text-secondary-text">
                {filteredItems.length} / {items.length} 显示
              </p>
            </div>

            {/* Column headers */}
            {loading ? (
              <div className="flex items-center justify-center px-5 py-4">
                <p className="text-sm text-secondary-text">正在加载观察池数据...</p>
              </div>
            ) : null}

            {/* Column headers */}
            <div className="hidden border-b border-border/60 px-5 py-2.5 text-xs text-secondary-text lg:grid lg:grid-cols-[1fr_180px_140px_100px_80px_100px]">
              <span>名称 / 主题</span>
              <span>加入理由</span>
              <span>当前信号</span>
              <span>加入天数</span>
              <span>提醒</span>
              <span className="text-right">操作</span>
            </div>

            {/* Stock rows */}
            {filteredItems.length === 0 ? (
              <div className="px-5 py-10">
                <EmptyState
                  title={items.length === 0 ? '观察池还是空的' : '没有匹配的持仓'}
                  description={items.length === 0
                    ? '先从单股查询页把一只股票加入观察池，这里就会开始积累。'
                    : '尝试切换筛选条件或修改搜索关键词。'}
                />
              </div>
            ) : (
              <div className="divide-y divide-border/40">
                {filteredItems.map((item) => {
                  const days = daysSince(item.createdAt);
                  return (
                    <div
                      key={item.stockCode}
                      className="grid items-center gap-3 px-5 py-4 transition-colors hover:bg-elevated/30 lg:grid-cols-[1fr_180px_140px_100px_80px_100px]"
                    >
                      {/* Name + theme */}
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-base font-bold text-foreground">{item.stockName}</span>
                          <span className="text-sm text-secondary-text">{item.stockCode}</span>
                        </div>
                        <p className="mt-0.5 truncate text-xs text-secondary-text">
                          {item.latestTheme || '--'} · 加入 {days} 天 · {formatShortDate(item.createdAt)}
                        </p>
                      </div>

                      {/* Reason / note */}
                      <p className="truncate text-sm text-secondary-text">
                        {item.note || item.latestTheme || '--'}
                      </p>

                      {/* Signal badge */}
                      <div>
                        <Badge
                          variant={signalBadgeVariant(item.latestSignal)}
                          size="sm"
                          className={signalBadgeClass(item.latestSignal)}
                        >
                          {item.latestSignal || '未记录'}
                        </Badge>
                      </div>

                      {/* Days held */}
                      <p className="text-sm font-medium text-foreground">{days} 天</p>

                      {/* Alert status */}
                      <Badge variant={item.alertEnabled ? 'success' : 'default'} size="sm">
                        {item.alertEnabled ? '已开' : '未开'}
                      </Badge>

                      {/* Actions */}
                      <div className="flex items-center justify-end gap-1">
                        <button
                          type="button"
                          onClick={() => setChartStock({ code: item.stockCode, name: item.stockName })}
                          className="rounded-lg px-1.5 py-1 text-xs text-secondary-text transition-colors hover:text-foreground"
                          title="查看 K 线"
                        >
                          <BarChart3 className="h-3.5 w-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={() => void handleDelete(item.stockCode)}
                          disabled={deletingCode === item.stockCode}
                          className="rounded-lg px-1.5 py-1 text-xs text-secondary-text transition-colors hover:text-danger"
                          title="移除"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                        <Link
                          to={`/stock-query?stock=${encodeURIComponent(item.stockCode)}`}
                          className="rounded-lg px-2 py-1 text-sm text-foreground/70 transition-colors hover:bg-elevated hover:text-foreground"
                        >
                          详情 →
                        </Link>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </Card>

          {/* ---- Alert Events (if any) ---- */}
          {alertEvents.length > 0 ? (
            <Card padding="lg" className="!rounded-2xl">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold text-foreground">
                  告警事件 · {unreadEventCount > 0 ? `${unreadEventCount} 条未读` : '已全部已读'}
                </h3>
                <div className="flex items-center gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    className="rounded-xl"
                    isLoading={markingAllRead}
                    loadingText="处理中..."
                    onClick={() => void handleMarkAllEventsRead()}
                    disabled={unreadEventCount === 0}
                  >
                    <CheckCheck className="h-3.5 w-3.5" />
                    全部已读
                  </Button>
                  <button
                    type="button"
                    onClick={() => setEventDrawerOpen(true)}
                    className="text-sm text-foreground/70 hover:text-foreground"
                  >
                    查看全部 →
                  </button>
                </div>
              </div>

              <div className="mt-4 space-y-2">
                {alertEvents.slice(0, 3).map((event) => {
                  const insight = buildEventInsight(event);
                  return (
                    <div
                      key={event.id}
                      className={`flex items-start justify-between gap-3 rounded-xl px-3 py-3 transition-colors ${event.readAt ? 'opacity-60' : 'bg-elevated/30'}`}
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-medium text-foreground">{event.title}</p>
                          {!event.readAt ? <span className="h-2 w-2 shrink-0 rounded-full bg-danger" /> : null}
                        </div>
                        <p className="mt-0.5 text-xs text-secondary-text">
                          {event.stockName} · {formatDateTime(event.createdAt)}
                        </p>
                        <p className="mt-1 text-sm text-secondary-text">{insight.summary}</p>
                      </div>
                      {!event.readAt ? (
                        <button
                          type="button"
                          onClick={() => void handleMarkEventRead(event.id)}
                          disabled={readingEventId === event.id}
                          className="shrink-0 text-xs text-secondary-text hover:text-foreground"
                        >
                          标记已读
                        </button>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </Card>
          ) : null}
        </div>

        {/* ======================== RIGHT COLUMN ======================== */}
        <div className="space-y-5">

          {/* ---- 主题观察池 ---- */}
          <Card padding="lg" className="!rounded-2xl">
            <h3 className="text-lg font-semibold text-foreground">
              主题观察池 · {items.length > 0 ? `${new Set(items.map((i) => i.latestTheme).filter(Boolean)).size} 个` : '待添加'}
            </h3>

            {items.length > 0 ? (
              <div className="mt-4 space-y-3">
                {Array.from(new Set(items.map((i) => i.latestTheme).filter(Boolean))).map((theme) => {
                  const themeItems = items.filter((i) => i.latestTheme === theme);
                  return (
                    <div key={theme} className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="font-medium text-foreground">{theme}</p>
                        <p className="mt-0.5 text-xs text-secondary-text">
                          {themeItems.length} 关联标的
                        </p>
                      </div>
                      <span className="text-sm text-secondary-text">--</span>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="mt-4 text-sm text-secondary-text">
                从单股查询加入观察池后，主题会自动归类到这里。
              </p>
            )}

            <button
              type="button"
              className="mt-4 w-full rounded-xl border border-dashed border-border py-2.5 text-sm text-secondary-text transition-colors hover:border-foreground/30 hover:text-foreground"
            >
              + 添加主题到观察池
            </button>
          </Card>

          {/* ---- 提醒规则 ---- */}
          <Card padding="lg" className="!rounded-2xl">
            <h3 className="text-lg font-semibold text-foreground">
              提醒规则 · {alertEnabledCount > 0 ? `${alertEnabledCount} 条启用` : '无规则'}
            </h3>

            {alertRules.length > 0 ? (
              <div className="mt-4 space-y-3">
                {alertRules.map((rule) => {
                  const todayCount = todayTriggersByRule.get(rule.id) ?? 0;
                  const isEditing = editingRuleId === rule.id;
                  return (
                    <div key={rule.id}>
                      <div className="flex items-center justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium text-foreground">
                            {rule.stockName} · {alertRuleLabel(rule.ruleType)}
                          </p>
                          {isPriceRule(rule.ruleType) ? (
                            <p className="mt-0.5 text-xs text-secondary-text">阈值 {formatThreshold(rule.thresholdValue)}</p>
                          ) : null}
                        </div>
                        <div className="flex shrink-0 items-center gap-2">
                          {todayCount > 0 ? (
                            <span className="rounded-md bg-danger/15 px-2 py-0.5 text-xs font-medium text-danger">
                              今日 {todayCount}
                            </span>
                          ) : null}
                          {/* Toggle switch */}
                          <button
                            type="button"
                            onClick={() => void handleToggleAlertRule(rule)}
                            disabled={savingRuleId === rule.id}
                            className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full transition-colors ${rule.enabled ? 'bg-foreground' : 'bg-border'}`}
                          >
                            <span className={`inline-block h-4 w-4 rounded-full bg-background transition-transform ${rule.enabled ? 'translate-x-6' : 'translate-x-1'}`} />
                          </button>
                        </div>
                      </div>

                      {/* Inline edit actions */}
                      {!isEditing ? (
                        <div className="mt-1 flex items-center gap-2">
                          <button type="button" onClick={() => startEditingRule(rule)} className="text-xs text-secondary-text hover:text-foreground">
                            <SquarePen className="mr-0.5 inline h-3 w-3" />编辑
                          </button>
                          <button
                            type="button"
                            onClick={() => void handleDeleteAlertRule(rule.id)}
                            disabled={deletingRuleId === rule.id}
                            className="text-xs text-secondary-text hover:text-danger"
                          >
                            <Trash2 className="mr-0.5 inline h-3 w-3" />删除
                          </button>
                          {buildDeepAnalysisHref({ analysisId: rule.sourceQueryId ? (latestAnalysisBySourceQueryId.get(rule.sourceQueryId) ?? null) : null, sourceQueryId: rule.sourceQueryId, stockCode: rule.stockCode, stockName: rule.stockName }) ? (
                            <Link
                              to={buildDeepAnalysisHref({ analysisId: rule.sourceQueryId ? (latestAnalysisBySourceQueryId.get(rule.sourceQueryId) ?? null) : null, sourceQueryId: rule.sourceQueryId, stockCode: rule.stockCode, stockName: rule.stockName }) || '/deep-analysis'}
                              className="text-xs text-secondary-text hover:text-foreground"
                            >
                              回看分析
                            </Link>
                          ) : null}
                        </div>
                      ) : (
                        <div className="mt-3 space-y-2 rounded-xl border border-border bg-elevated/30 p-3">
                          {rule.ruleType !== 'risk_event' ? (
                            <Input
                              label="阈值"
                              value={editingThreshold}
                              onChange={(e) => setEditingThreshold(e.target.value)}
                              placeholder="输入新的价格阈值"
                              className="h-9"
                            />
                          ) : null}
                          <Input
                            label="扫描间隔(分钟)"
                            value={editingScanInterval}
                            onChange={(e) => setEditingScanInterval(e.target.value)}
                            placeholder="最小 5"
                            className="h-9"
                          />
                          <Input
                            label="备注"
                            value={editingNote}
                            onChange={(e) => setEditingNote(e.target.value)}
                            placeholder="可选备注"
                            className="h-9"
                          />
                          <div className="flex items-center gap-2">
                            <Button size="sm" className="rounded-lg" isLoading={savingRuleId === rule.id} loadingText="保存中..." onClick={() => void handleSaveRule(rule)}>
                              保存
                            </Button>
                            <Button variant="secondary" size="sm" className="rounded-lg" onClick={cancelEditingRule}>
                              取消
                            </Button>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="mt-4 text-sm text-secondary-text">
                观察池中的股票还没有告警规则，点击下方按钮快速创建。
              </p>
            )}

            {/* ---- New rule creation ---- */}
            {!showNewRuleForm ? (
              <button
                type="button"
                onClick={() => {
                  setShowNewRuleForm(true);
                  if (stocksWithoutRules.length > 0) setNewRuleStockCode(stocksWithoutRules[0].stockCode);
                  else if (items.length > 0) setNewRuleStockCode(items[0].stockCode);
                }}
                disabled={items.length === 0}
                className="mt-4 flex w-full items-center justify-center gap-1.5 rounded-xl border border-dashed border-border py-2.5 text-sm text-secondary-text transition-colors hover:border-foreground/30 hover:text-foreground disabled:opacity-40"
              >
                <Plus className="h-3.5 w-3.5" />
                为股票创建告警规则
              </button>
            ) : (
              <div className="mt-4 space-y-3 rounded-xl border border-border bg-elevated/30 p-4">
                <p className="text-sm font-medium text-foreground">新建默认告警规则</p>
                <div>
                  <label className="mb-1 block text-xs text-secondary-text">选择股票</label>
                  <select
                    value={newRuleStockCode}
                    onChange={(e) => setNewRuleStockCode(e.target.value)}
                    className="h-9 w-full rounded-lg border border-border bg-card px-3 text-sm text-foreground focus:border-foreground/30 focus:outline-none"
                  >
                    {stocksWithoutRules.length > 0 ? (
                      <optgroup label="尚无规则">
                        {stocksWithoutRules.map((item) => (
                          <option key={item.stockCode} value={item.stockCode}>
                            {item.stockName} {item.stockCode}
                          </option>
                        ))}
                      </optgroup>
                    ) : null}
                    {items.filter((i) => !stocksWithoutRules.includes(i)).length > 0 ? (
                      <optgroup label="已有规则（将追加）">
                        {items.filter((i) => !stocksWithoutRules.includes(i)).map((item) => (
                          <option key={item.stockCode} value={item.stockCode}>
                            {item.stockName} {item.stockCode}
                          </option>
                        ))}
                      </optgroup>
                    ) : null}
                  </select>
                </div>
                <Input
                  label="支撑价（选填）"
                  value={newRuleSupportPrice}
                  onChange={(e) => setNewRuleSupportPrice(e.target.value)}
                  placeholder="如 25.50"
                  className="h-9"
                />
                <Input
                  label="突破价（选填）"
                  value={newRuleBreakoutPrice}
                  onChange={(e) => setNewRuleBreakoutPrice(e.target.value)}
                  placeholder="如 30.00"
                  className="h-9"
                />
                <p className="text-xs text-secondary-text">
                  将自动创建：支撑位回测 + 突破确认 + 风险事件 三条默认规则
                </p>
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    className="rounded-lg"
                    isLoading={creatingRule}
                    loadingText="创建中..."
                    onClick={() => void handleCreateDefaultRules(newRuleStockCode)}
                    disabled={!newRuleStockCode}
                  >
                    创建规则
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    className="rounded-lg"
                    onClick={() => { setShowNewRuleForm(false); setNewRuleStockCode(''); setNewRuleSupportPrice(''); setNewRuleBreakoutPrice(''); }}
                  >
                    取消
                  </Button>
                </div>
              </div>
            )}
          </Card>

          {/* ---- 扫描状态 ---- */}
          <Card padding="lg" className="!rounded-2xl">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-foreground">后台扫描</h3>
              <div className="flex items-center gap-2">
                <Badge variant={alertLoopStatus?.enabled ? 'success' : 'default'} size="sm">
                  {alertLoopStatus?.enabled ? '已开启' : '未开启'}
                </Badge>
                <Badge variant={alertLoopStatus?.running ? 'info' : 'default'} size="sm">
                  {alertLoopStatus?.running ? '运行中' : '未运行'}
                </Badge>
              </div>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-3 text-xs text-secondary-text">
              <div>
                <p>基础 tick</p>
                <p className="mt-0.5 font-medium text-foreground">{alertLoopStatus?.baseTickSeconds ?? 60}s</p>
              </div>
              <div>
                <p>最近完成</p>
                <p className="mt-0.5 font-medium text-foreground">{formatDateTime(alertLoopStatus?.lastFinishedAt)}</p>
              </div>
            </div>
            {alertLoopStatus?.lastError ? (
              <p className="mt-2 text-xs text-danger">错误：{alertLoopStatus.lastError}</p>
            ) : null}
          </Card>
        </div>
      </div>

      {/* ---- K-Line Drawer ---- */}
      <Drawer
        isOpen={chartStock !== null}
        onClose={() => setChartStock(null)}
        title={chartStock ? `${chartStock.name} K线图` : ''}
        width="max-w-4xl"
      >
        {chartStock ? (
          <CandlestickChart key={chartStock.code} stockCode={chartStock.code} stockName={chartStock.name} />
        ) : null}
      </Drawer>

      {/* ---- Events Drawer ---- */}
      <Drawer isOpen={eventDrawerOpen} onClose={() => setEventDrawerOpen(false)} title="告警事件" width="max-w-xl" side="right">
        <div className="space-y-3">
          {alertEvents.length === 0 ? (
            <EmptyState title="还没有告警事件" description="等后台扫描命中规则之后，这里会显示真实事件流。" icon={<Bell className="h-8 w-8" />} />
          ) : (
            alertEvents.map((event) => {
              const insight = buildEventInsight(event);
              return (
                <div key={event.id} className={`rounded-xl border px-4 py-3 ${event.readAt ? 'border-border/40 opacity-60' : 'border-border bg-elevated/20'}`}>
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-foreground">{event.title}</p>
                      <p className="mt-1 text-sm text-secondary-text">{insight.summary}</p>
                      {insight.details.length > 0 ? (
                        <div className="mt-2 rounded-lg bg-elevated/40 px-3 py-2">
                          {insight.details.map((d) => <p key={d} className="text-xs text-secondary-text">{d}</p>)}
                        </div>
                      ) : null}
                      <p className="mt-2 text-xs text-secondary-text">{event.stockName} · {formatDateTime(event.createdAt)}</p>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      {!event.readAt ? (
                        <Button variant="ghost" size="sm" isLoading={readingEventId === event.id} onClick={() => void handleMarkEventRead(event.id)}>
                          标记已读
                        </Button>
                      ) : null}
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </Drawer>
    </AppPage>
  );
};

export default WatchlistPage;
