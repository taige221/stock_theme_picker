import type React from 'react';
import { useEffect, useMemo, useState } from 'react';
import { Activity, BarChart3, Bell, CheckCheck, Layers3, RefreshCw, SquarePen, Star, Trash2, TrendingUp } from 'lucide-react';
import { Link } from 'react-router-dom';
import { createParsedApiError, getParsedApiError, type ParsedApiError } from '../api/error';
import { watchlistApi, type StockAlertEventItem, type StockAlertLoopStatus, type StockAlertRuleItem, type StockWatchlistItem } from '../api/watchlist';
import { CandlestickChart } from '../components/CandlestickChart';
import { ApiErrorAlert, AppPage, Badge, Button, Card, Drawer, EmptyState, InlineAlert, Input } from '../components/common';

const DEFAULT_GROUP = '核心跟踪';

function signalVariant(signal?: string | null): 'warning' | 'danger' | 'info' | 'default' {
  if (signal === '持有候选') return 'warning';
  if (signal === '短线异动') return 'danger';
  if (signal === '低吸观察') return 'info';
  return 'default';
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

function alertRuleLabel(value: string): string {
  if (value === 'support_retest') return '接近支撑位';
  if (value === 'breakout_confirm') return '突破确认位';
  if (value === 'risk_event') return '明确风险事件';
  return value;
}

function alertEventVariant(ruleType: string, readAt?: string | null): 'warning' | 'danger' | 'info' | 'history' {
  if (readAt) return 'history';
  if (ruleType === 'risk_event') return 'danger';
  if (ruleType === 'breakout_confirm') return 'warning';
  return 'info';
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
    if (distanceRatio !== null) {
      details.push(`离支撑位约 ${formatPercent(distanceRatio)}`);
    }
    return {
      summary: '价格重新靠近你的低吸观察位了，重点看能不能稳住，而不是机械接刀。',
      details,
    };
  }

  if (event.ruleType === 'breakout_confirm') {
    const currentPrice = typeof payload.currentPrice === 'number' ? payload.currentPrice : null;
    const thresholdValue = typeof payload.thresholdValue === 'number' ? payload.thresholdValue : null;
    if (currentPrice !== null && thresholdValue !== null) {
      details.push(`当前价 ${formatThreshold(currentPrice)}，确认位 ${formatThreshold(thresholdValue)}`);
    }
    return {
      summary: '价格已经站上你设定的突破位了，下一步该盯的是量价延续，不是只看“站上过”。',
      details,
    };
  }

  if (event.ruleType === 'risk_event') {
    const riskEvents = isStringArray(payload.riskEvents) ? payload.riskEvents.slice(0, 3) : [];
    const headlines = isStringArray(payload.headlines) ? payload.headlines.slice(0, 2) : [];
    if (riskEvents.length > 0) {
      details.push(`风险项：${riskEvents.join('、')}`);
    }
    if (headlines.length > 0) {
      details.push(`相关新闻：${headlines.join('；')}`);
    }
    return {
      summary: '这不是价格信号，而是新闻层面的风险提醒，先确认事件真假和影响范围，再决定是否降预期或收缩仓位。',
      details,
    };
  }

  return {
    summary: event.message,
    details,
  };
}

function buildDeepAnalysisHref(params: {
  analysisId?: string | null;
  sourceQueryId?: string | null;
  stockCode?: string | null;
  stockName?: string | null;
}): string | null {
  const nextParams = new URLSearchParams();
  if (params.analysisId) {
    nextParams.set('analysisId', params.analysisId);
  }
  if (params.sourceQueryId) {
    nextParams.set('queryId', params.sourceQueryId);
  }
  if (params.stockCode) {
    nextParams.set('stock', params.stockCode);
  }
  if (params.stockName) {
    nextParams.set('name', params.stockName);
  }
  const serialized = nextParams.toString();
  return serialized ? `/deep-analysis?${serialized}` : null;
}

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
    void loadWatchlist();
  }, []);

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

  const groups = useMemo(() => {
    const values = new Set<string>();
    values.add(DEFAULT_GROUP);
    items.forEach((item) => {
      if (item.groupName?.trim()) {
        values.add(item.groupName.trim());
      }
    });
    return Array.from(values);
  }, [items]);

  const alertEnabledCount = useMemo(() => items.filter((item) => item.alertEnabled).length, [items]);
  const unreadEventCount = useMemo(() => alertEvents.filter((event) => !event.readAt).length, [alertEvents]);
  const latestAnalysisBySourceQueryId = useMemo(() => {
    const map = new Map<string, StockAlertEventItem['linkedAnalysisId']>();
    for (const event of alertEvents) {
      if (event.sourceQueryId && event.linkedAnalysisId && !map.has(event.sourceQueryId)) {
        map.set(event.sourceQueryId, event.linkedAnalysisId);
      }
    }
    return map;
  }, [alertEvents]);

  const handleDeleteAlertRule = async (ruleId: number) => {
    setDeletingRuleId(ruleId);
    setActionError(null);
    setMessage(null);
    try {
      await watchlistApi.deleteStockAlertRule(ruleId);
      setAlertRules((prev) => prev.filter((item) => item.id !== ruleId));
      setMessage(`已删除一条单股告警规则`);
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
          message: '这条价格规则缺少有效阈值，先补上阈值后再启用，不然它不会触发。',
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
        throw createParsedApiError({
          title: '价格阈值还没填好',
          message: '价格规则必须填写大于 0 的有效阈值，不然它不会触发。',
          category: 'unknown',
        });
      }
      if (!Number.isFinite(nextScanInterval) || nextScanInterval < 5) {
        throw createParsedApiError({
          title: '扫描间隔不正确',
          message: '扫描间隔单位为分钟，最小 5 分钟。',
          category: 'unknown',
        });
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
      setMessage('已标记一条告警事件为已读');
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

  return (
    <AppPage className="space-y-6 !max-w-[1680px] px-3 md:px-5 lg:px-6">
      <section className="overflow-hidden rounded-[32px] border border-border/60 bg-[radial-gradient(circle_at_top_left,_rgba(34,24,16,0.08),_transparent_34%),linear-gradient(180deg,rgba(248,244,236,0.98),rgba(241,235,226,0.96))] shadow-soft-card">
        <div className="grid gap-6 px-5 py-6 lg:grid-cols-[1fr_0.9fr] lg:px-7 lg:py-7">
          <div className="space-y-5">
            <div className="flex items-center gap-4">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-border/60 bg-card/90 text-foreground shadow-soft-card">
                <Star className="h-7 w-7" />
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-secondary-text">Persistent Workflow</p>
                <h2 className="mt-1 text-3xl font-semibold tracking-tight text-foreground">把高价值股票沉淀成观察池</h2>
                <p className="mt-2 max-w-3xl text-sm leading-7 text-secondary-text">
                  这一版先把单股查询接成真实持久化观察池。股票会保存到后端 SQLite，支持回看和移除。
                </p>
              </div>
            </div>

            <div className="flex flex-wrap gap-2">
              {groups.map((group, index) => (
                <span
                  key={group}
                  className={[
                    'inline-flex items-center rounded-full border px-4 py-2 text-sm transition-all',
                    index === 0
                      ? 'border-foreground/15 bg-foreground text-background shadow-soft-card'
                      : 'border-border/60 bg-background/80 text-secondary-text',
                  ].join(' ')}
                >
                  {group}
                </span>
              ))}
            </div>
          </div>

          <Card variant="bordered" padding="lg" className="rounded-[28px] border-border/60 bg-card/90">
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <div className="rounded-[22px] border border-border/60 bg-background/72 px-4 py-4">
                <p className="text-xs uppercase tracking-[0.16em] text-secondary-text">观察股票</p>
                <p className="mt-3 text-3xl font-semibold text-foreground">{items.length}</p>
                <p className="mt-2 text-sm text-secondary-text">已持久化到后端 SQLite</p>
              </div>
              <div className="rounded-[22px] border border-border/60 bg-background/72 px-4 py-4">
                <p className="text-xs uppercase tracking-[0.16em] text-secondary-text">分组数量</p>
                <p className="mt-3 text-3xl font-semibold text-foreground">{groups.length}</p>
                <p className="mt-2 text-sm text-secondary-text">当前默认使用核心跟踪</p>
              </div>
              <div className="rounded-[22px] border border-border/60 bg-background/72 px-4 py-4">
                <p className="text-xs uppercase tracking-[0.16em] text-secondary-text">提醒规则</p>
                <p className="mt-3 text-3xl font-semibold text-foreground">{alertRules.length}</p>
                <p className="mt-2 text-sm text-secondary-text">{alertEnabledCount} 只股票已开启提醒</p>
              </div>
              <div className="rounded-[22px] border border-border/60 bg-background/72 px-4 py-4">
                <p className="text-xs uppercase tracking-[0.16em] text-secondary-text">告警事件</p>
                <p className="mt-3 text-3xl font-semibold text-foreground">{alertEvents.length}</p>
                <p className="mt-2 text-sm text-secondary-text">{unreadEventCount} 条未读</p>
              </div>
            </div>
          </Card>
        </div>
      </section>

      {error ? <ApiErrorAlert error={error} /> : null}
      {actionError ? <ApiErrorAlert error={actionError} /> : null}
      {message ? <InlineAlert variant="success" title="观察池已更新" message={message} /> : null}

      <Card variant="bordered" padding="lg" className="rounded-[28px]">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-border/60 bg-background/80 text-foreground">
              <Activity className="h-5 w-5" />
            </div>
            <div>
              <span className="label-uppercase">Alert Loop</span>
              <h3 className="mt-1 text-xl font-semibold text-foreground">后台扫描状态</h3>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={alertLoopStatus?.enabled ? 'success' : 'default'} className="border-0 px-3 py-1">
              {alertLoopStatus?.enabled ? '已开启' : '未开启'}
            </Badge>
            <Badge variant={alertLoopStatus?.running ? 'info' : 'history'} className="border-0 px-3 py-1">
              {alertLoopStatus?.running ? '运行中' : '未运行'}
            </Badge>
            <Button
              variant="secondary"
              size="sm"
              className="rounded-xl"
              isLoading={runningScan}
              loadingText="扫描中..."
              onClick={() => void handleRunScanOnce()}
            >
              <RefreshCw className="h-4 w-4" />
              手动扫描
            </Button>
          </div>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-4">
          <div className="rounded-[18px] border border-border/60 bg-background/72 px-4 py-3">
            <p className="text-xs text-secondary-text">基础 tick</p>
            <p className="mt-2 text-lg font-semibold text-foreground">{alertLoopStatus?.baseTickSeconds ?? 60}s</p>
          </div>
          <div className="rounded-[18px] border border-border/60 bg-background/72 px-4 py-3">
            <p className="text-xs text-secondary-text">最近完成</p>
            <p className="mt-2 text-sm font-medium text-foreground">{formatDateTime(alertLoopStatus?.lastFinishedAt)}</p>
          </div>
          <div className="rounded-[18px] border border-border/60 bg-background/72 px-4 py-3">
            <p className="text-xs text-secondary-text">最近到期</p>
            <p className="mt-2 text-lg font-semibold text-foreground">{alertLoopStatus?.lastSummary?.dueRules ?? 0}</p>
          </div>
          <div className="rounded-[18px] border border-border/60 bg-background/72 px-4 py-3">
            <p className="text-xs text-secondary-text">最近触发</p>
            <p className="mt-2 text-lg font-semibold text-foreground">{alertLoopStatus?.lastSummary?.triggeredEvents ?? 0}</p>
          </div>
        </div>
        {alertLoopStatus?.lastError ? (
          <p className="mt-3 text-sm text-danger">最近错误：{alertLoopStatus.lastError}</p>
        ) : null}
      </Card>

      <section className="grid gap-5 xl:grid-cols-[1.05fr_0.95fr]">
        <Card variant="bordered" padding="lg" className="rounded-[28px]">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-border/60 bg-background/80 text-foreground">
                <TrendingUp className="h-5 w-5" />
              </div>
              <div>
                <span className="label-uppercase">Watched Stocks</span>
                <h3 className="mt-1 text-2xl font-semibold text-foreground">股票观察项</h3>
              </div>
            </div>
            <Button variant="secondary" className="rounded-2xl" onClick={() => void loadWatchlist()} isLoading={loading} loadingText="刷新中...">
              刷新列表
            </Button>
          </div>

          <div className="mt-5 space-y-3">
            {!loading && items.length === 0 ? (
              <EmptyState
                title="观察池还是空的"
                description="先从单股查询页把一只股票加入观察池，这里就会开始积累真实观察项。"
              />
            ) : null}

            {items.map((item) => (
              <div key={item.stockCode} className="rounded-[24px] border border-border/60 bg-background/72 px-5 py-4">
                <div className="grid gap-4 xl:grid-cols-[1fr_130px_160px_170px] xl:items-center">
                  <div>
                    <div className="flex items-center gap-3">
                      <h4 className="text-lg font-semibold text-foreground">{item.stockName}</h4>
                      <span className="text-sm text-secondary-text">{item.stockCode}</span>
                    </div>
                    <p className="mt-2 text-sm text-secondary-text">
                      {item.latestTheme || '暂无题材摘要'} · 分组 {item.groupName || DEFAULT_GROUP}
                    </p>
                    <p className="mt-1 text-xs text-secondary-text">更新于 {formatDateTime(item.updatedAt)}</p>
                  </div>
                  <Badge variant={signalVariant(item.latestSignal)} className="w-fit border-0 px-3 py-1">
                    {item.latestSignal || '未记录'}
                  </Badge>
                  <p className="text-sm text-secondary-text">{item.note || '当前没有备注，后续可再补编辑能力。'}</p>
                  <div className="flex items-center justify-end gap-2">
                    <Badge variant={item.alertEnabled ? 'success' : 'default'} className="border-0 px-3 py-1">
                      {item.alertEnabled ? '提醒已开' : '提醒未开'}
                    </Badge>
                    <Button
                      variant="secondary"
                      size="sm"
                      className="rounded-xl"
                      onClick={() => setChartStock({ code: item.stockCode, name: item.stockName })}
                    >
                      <BarChart3 className="h-4 w-4" />
                      K线
                    </Button>
                    <Button
                      variant="danger-subtle"
                      size="sm"
                      className="rounded-xl"
                      isLoading={deletingCode === item.stockCode}
                      loadingText="移除中..."
                      onClick={() => void handleDelete(item.stockCode)}
                    >
                      <Trash2 className="h-4 w-4" />
                      移除
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Card>

        <div className="space-y-5">
          <Card variant="bordered" padding="lg" className="rounded-[28px]">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-border/60 bg-background/80 text-foreground">
                  <Bell className="h-5 w-5" />
                </div>
                <div>
                  <span className="label-uppercase">Notification Center</span>
                  <h3 className="mt-1 text-2xl font-semibold text-foreground">告警事件</h3>
                </div>
              </div>
              <Button
                variant="secondary"
                size="sm"
                className="rounded-xl"
                isLoading={markingAllRead}
                loadingText="处理中..."
                onClick={() => void handleMarkAllEventsRead()}
                disabled={unreadEventCount === 0}
              >
                <CheckCheck className="h-4 w-4" />
                全部已读
              </Button>
            </div>
            <div className="mt-5 space-y-3">
              {alertEvents.length === 0 ? (
                <EmptyState
                  title="还没有告警事件"
                  description="等后台扫描命中规则之后，这里会显示真实事件流。"
                />
              ) : (
                alertEvents.map((event) => {
                  const insight = buildEventInsight(event);
                  return (
                    <div key={event.id} className="rounded-[22px] border border-border/60 bg-background/72 px-4 py-4">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <p className="text-sm font-semibold text-foreground">{event.title}</p>
                            <Badge variant={alertEventVariant(event.ruleType, event.readAt)} className="border-0 px-3 py-1">
                              {event.readAt ? '已读' : '未读'}
                            </Badge>
                            <Badge variant="default" className="border-0 px-3 py-1">
                              {alertRuleLabel(event.ruleType)}
                            </Badge>
                          </div>
                          <p className="mt-2 text-sm leading-6 text-foreground">{insight.summary}</p>
                          <p className="mt-2 text-sm leading-6 text-secondary-text">{event.message}</p>
                          {insight.details.length > 0 ? (
                            <div className="mt-3 rounded-2xl border border-border/50 bg-background/80 px-3 py-3">
                              {insight.details.map((detail) => (
                                <p key={detail} className="text-xs leading-6 text-secondary-text">
                                  {detail}
                                </p>
                              ))}
                            </div>
                          ) : null}
                          <p className="mt-2 text-xs text-secondary-text">
                            {event.stockName} · {event.stockCode} · {formatDateTime(event.createdAt)}
                          </p>
                          {event.sourceQueryId || event.linkedAnalysisId ? (
                            <p className="mt-1 text-xs text-secondary-text">
                              来源 queryId {event.sourceQueryId || '--'}
                            </p>
                          ) : null}
                        </div>
                        <div className="flex shrink-0 items-center gap-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            className="rounded-xl"
                            isLoading={readingEventId === event.id}
                            loadingText="处理中..."
                            disabled={Boolean(event.readAt)}
                            onClick={() => void handleMarkEventRead(event.id)}
                          >
                            标记已读
                          </Button>
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </Card>

          <Card variant="bordered" padding="lg" className="rounded-[28px]">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-border/60 bg-background/80 text-foreground">
                <Layers3 className="h-5 w-5" />
              </div>
              <div>
                <span className="label-uppercase">Watched Themes</span>
                <h3 className="mt-1 text-2xl font-semibold text-foreground">主题观察项</h3>
              </div>
            </div>
            <EmptyState
              className="mt-5"
              title="主题观察池还没接真实持久化"
              description="这一轮先把股票观察项打通；主题观察项会在下一步和主题扫描结果页一起接上。"
            />
          </Card>

          <Card variant="bordered" padding="lg" className="rounded-[28px]">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-border/60 bg-background/80 text-foreground">
                <Bell className="h-5 w-5" />
              </div>
              <div>
                <span className="label-uppercase">Rules</span>
                <h3 className="mt-1 text-2xl font-semibold text-foreground">提醒规则</h3>
              </div>
            </div>
            <div className="mt-5 space-y-3 text-sm leading-6 text-secondary-text">
              {alertRules.length === 0 ? (
                <EmptyState
                  title="还没有单股告警规则"
                  description="先在单股查询页点击“设置告警”，系统会按当前结果生成默认三条规则。"
                />
              ) : (
                alertRules.map((rule) => {
                  const missingThreshold = isPriceRule(rule.ruleType) && !hasUsableThreshold(rule);
                  return (
                    <div key={rule.id} className="rounded-[22px] border border-border/60 bg-background/72 px-4 py-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="flex flex-wrap items-center gap-2">
                            <p className="text-sm font-semibold text-foreground">{rule.stockName} · {alertRuleLabel(rule.ruleType)}</p>
                            {missingThreshold ? (
                              <Badge variant="danger" className="border-0 px-3 py-1">
                                阈值缺失
                              </Badge>
                            ) : null}
                          </div>
                          <p className="mt-1 text-sm text-secondary-text">
                            {rule.ruleType === 'risk_event' ? '监控新闻中的明确风险事件' : `阈值 ${formatThreshold(rule.thresholdValue)}`}
                          </p>
                          {missingThreshold ? (
                            <p className="mt-1 text-xs text-danger">这是一条价格规则，但当前没有有效阈值，所以它不会触发提醒。</p>
                          ) : null}
                          <p className="mt-1 text-xs text-secondary-text">扫描间隔 {Math.max(5, rule.scanIntervalMinutes || 5)} 分钟</p>
                          <p className="mt-1 text-xs text-secondary-text">更新于 {formatDateTime(rule.updatedAt)}</p>
                          <p className="mt-1 text-xs text-secondary-text">{rule.note || '当前没有备注'}</p>
                          {rule.sourceQueryId ? (
                            <p className="mt-1 text-xs text-secondary-text">来源 queryId {rule.sourceQueryId}</p>
                          ) : null}
                        </div>
                        <div className="flex items-center gap-2">
                          <Badge variant={missingThreshold ? 'danger' : rule.enabled ? 'success' : 'default'} className="border-0 px-3 py-1">
                            {missingThreshold ? '不会触发' : rule.enabled ? '已启用' : '已停用'}
                          </Badge>
                          {buildDeepAnalysisHref({
                            analysisId: rule.sourceQueryId ? (latestAnalysisBySourceQueryId.get(rule.sourceQueryId) ?? null) : null,
                            sourceQueryId: rule.sourceQueryId,
                            stockCode: rule.stockCode,
                            stockName: rule.stockName,
                          }) ? (
                            <Link
                              to={buildDeepAnalysisHref({
                                analysisId: rule.sourceQueryId ? (latestAnalysisBySourceQueryId.get(rule.sourceQueryId) ?? null) : null,
                                sourceQueryId: rule.sourceQueryId,
                                stockCode: rule.stockCode,
                                stockName: rule.stockName,
                              }) || '/deep-analysis'}
                            >
                              <Button variant="secondary" size="sm" className="rounded-xl">
                                回看分析
                              </Button>
                            </Link>
                          ) : null}
                          <Button
                            variant="secondary"
                            size="sm"
                            className="rounded-xl"
                            isLoading={savingRuleId === rule.id}
                            loadingText="处理中..."
                            onClick={() => void handleToggleAlertRule(rule)}
                          >
                            {rule.enabled ? '停用' : '启用'}
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="rounded-xl"
                            onClick={() => startEditingRule(rule)}
                          >
                            <SquarePen className="h-4 w-4" />
                            编辑
                          </Button>
                          <Button
                            variant="danger-subtle"
                            size="sm"
                            className="rounded-xl"
                            isLoading={deletingRuleId === rule.id}
                            loadingText="移除中..."
                            onClick={() => void handleDeleteAlertRule(rule.id)}
                          >
                            <Trash2 className="h-4 w-4" />
                            删除
                          </Button>
                        </div>
                      </div>

                      {editingRuleId === rule.id ? (
                        <div className="mt-4 grid gap-3 rounded-[18px] border border-border/60 bg-card/70 p-4 md:grid-cols-[1fr_1fr_1fr_auto]">
                          {rule.ruleType !== 'risk_event' ? (
                            <Input
                              label="阈值"
                              value={editingThreshold}
                              onChange={(event) => setEditingThreshold(event.target.value)}
                              placeholder="输入新的价格阈值"
                              className="h-10"
                              hint="价格规则必须填写大于 0 的阈值。"
                            />
                          ) : (
                            <div />
                          )}
                          <Input
                            label="扫描间隔(分钟)"
                            value={editingScanInterval}
                            onChange={(event) => setEditingScanInterval(event.target.value)}
                            placeholder="最小 5"
                            className="h-10"
                          />
                          <Input
                            label="备注"
                            value={editingNote}
                            onChange={(event) => setEditingNote(event.target.value)}
                            placeholder="可选备注"
                            className="h-10"
                          />
                          <div className="flex items-end gap-2">
                            <Button
                              size="sm"
                              className="rounded-xl"
                              isLoading={savingRuleId === rule.id}
                              loadingText="保存中..."
                              onClick={() => void handleSaveRule(rule)}
                            >
                              保存
                            </Button>
                            <Button variant="secondary" size="sm" className="rounded-xl" onClick={cancelEditingRule}>
                              取消
                            </Button>
                          </div>
                        </div>
                      ) : null}
                    </div>
                  );
                })
              )}
            </div>
          </Card>
        </div>
      </section>
      <Drawer
        isOpen={chartStock !== null}
        onClose={() => setChartStock(null)}
        title={chartStock ? `${chartStock.name} K线图` : ''}
        width="max-w-4xl"
      >
        {chartStock ? (
          <CandlestickChart
            key={chartStock.code}
            stockCode={chartStock.code}
            stockName={chartStock.name}
          />
        ) : null}
      </Drawer>
    </AppPage>
  );
};

export default WatchlistPage;
