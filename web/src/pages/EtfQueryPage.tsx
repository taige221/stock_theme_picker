import type React from 'react';
import { useEffect, useMemo, useState } from 'react';
import { Activity, BarChart3, Clock3, Layers3, RefreshCw, Search, ShieldAlert } from 'lucide-react';
import { useLocation } from 'react-router-dom';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import {
  stockQueryApi,
  type EtfMarketBar,
  type EtfDailyMetricsRefreshResponse,
  type EtfQueryHistoryItem,
  type EtfMarketSnapshotResponse,
} from '../api/stockQuery';
import { ApiErrorAlert, AppPage, Badge, Button, Card, Drawer, EmptyState, InlineAlert, Input, PaperHeroHeader } from '../components/common';

const QUICK_ETF_QUERIES = [
  { label: '证券 ETF', value: '512880.SH' },
  { label: '芯片 ETF', value: '159995.SZ' },
  { label: '沪深 300 ETF', value: '510300.SH' },
  { label: '科创 50 ETF', value: '588000.SH' },
] as const;

function formatNumber(value?: number | null, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '--';
  return value.toLocaleString('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function formatSignedPercent(value?: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '--';
  const prefix = value > 0 ? '+' : '';
  return `${prefix}${formatNumber(value, 2)}%`;
}

function formatLargeAmountYi(value?: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '--';
  return `${formatNumber(value, 2)} 亿`;
}

function formatFundShares(value?: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '--';
  if (Math.abs(value) >= 100000000) return `${formatNumber(value / 100000000, 2)} 亿份`;
  if (Math.abs(value) >= 10000) return `${formatNumber(value / 10000, 2)} 万份`;
  return `${formatNumber(value, 0)} 份`;
}

function formatVolume(value?: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '--';
  if (Math.abs(value) >= 100000000) return `${formatNumber(value / 100000000, 2)} 亿`;
  if (Math.abs(value) >= 10000) return `${formatNumber(value / 10000, 2)} 万`;
  return formatNumber(value, 0);
}

function formatPercent(value?: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '--';
  return `${formatNumber(value, 2)}%`;
}

function quoteTone(value?: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return 'text-foreground';
  if (value > 0) return 'text-danger';
  if (value < 0) return 'text-success';
  return 'text-foreground';
}

function analysisBadgeVariant(signal?: string | null): 'default' | 'success' | 'warning' | 'info' {
  switch (signal) {
    case '趋势跟随':
    case '低吸观察':
      return 'success';
    case '不宜追高':
      return 'warning';
    case '短线异动':
      return 'info';
    default:
      return 'default';
  }
}

function resolveLatestBar(bars: EtfMarketBar[]): EtfMarketBar | null {
  if (!bars.length) return null;
  return bars[bars.length - 1] ?? null;
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

function formatDateTime(value?: string | null): string {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date);
}

function formatDailyMetricsCacheStatus(value?: string | null): string {
  switch (value) {
    case 'hit':
      return '本地命中';
    case 'refreshed':
      return '在线刷新';
    case 'stale_fallback':
      return '旧快照回退';
    default:
      return value || '--';
  }
}

const EtfQueryPage: React.FC = () => {
  const location = useLocation();
  const initialQuery = useMemo(() => {
    const params = new URLSearchParams(location.search);
    return params.get('stock') ?? params.get('query') ?? QUICK_ETF_QUERIES[0].value;
  }, [location.search]);

  const [query, setQuery] = useState(initialQuery);
  const [result, setResult] = useState<EtfMarketSnapshotResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [lastResolvedInput, setLastResolvedInput] = useState(initialQuery);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyItems, setHistoryItems] = useState<EtfQueryHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<ParsedApiError | null>(null);
  const [historyRestoreId, setHistoryRestoreId] = useState<string | null>(null);
  const [currentHistoryId, setCurrentHistoryId] = useState<string | null>(null);
  const [dailyMetricsRefreshing, setDailyMetricsRefreshing] = useState(false);
  const [dailyMetricsMessage, setDailyMetricsMessage] = useState<string | null>(null);
  const [dailyMetricsMessageTone, setDailyMetricsMessageTone] = useState<'success' | 'warning'>('success');

  useEffect(() => {
    setQuery(initialQuery);
    setError(null);
  }, [initialQuery]);

  const loadHistory = async (stockCode?: string) => {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const response = await stockQueryApi.getEtfHistory(20, stockCode);
      setHistoryItems(response.items);
    } catch (requestError) {
      setHistoryError(getParsedApiError(requestError));
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    void loadHistory();
  }, []);

  const applySnapshot = async (snapshot: EtfMarketSnapshotResponse, resolvedInput: string) => {
    setResult(snapshot);
    setLastResolvedInput(resolvedInput);
    setCurrentHistoryId(snapshot.queryId ?? null);
  };

  const loadEtfSnapshot = async (rawInput: string) => {
    const normalized = rawInput.trim();
    if (!normalized) return;

    setIsLoading(true);
    setError(null);
    setDailyMetricsMessage(null);
    try {
      const snapshot = await stockQueryApi.getEtfMarketSnapshot(normalized, 60);
      await applySnapshot(snapshot, normalized);
    } catch (requestError) {
      setError(getParsedApiError(requestError));
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await loadEtfSnapshot(query);
  };

  const applyDailyMetricsRefresh = (refreshResult: EtfDailyMetricsRefreshResponse) => {
    setResult((previous) => {
      if (!previous || previous.stockCode !== refreshResult.stockCode) {
        return previous;
      }
      return {
        ...previous,
        dailyMetrics: refreshResult.dailyMetrics,
        dataSources: {
          ...previous.dataSources,
          dailyMetrics: refreshResult.dailyMetrics.dataSource ?? previous.dataSources.dailyMetrics,
        },
        errors: refreshResult.errors.length ? refreshResult.errors : previous.errors,
      };
    });
  };

  const handleDailyMetricsRefresh = async () => {
    const stockCode = result?.stockCode;
    if (!stockCode) return;

    setDailyMetricsRefreshing(true);
    setDailyMetricsMessage(null);
    try {
      const refreshResult = await stockQueryApi.refreshEtfDailyMetrics(stockCode);
      applyDailyMetricsRefresh(refreshResult);
      setDailyMetricsMessageTone(refreshResult.refreshed ? 'success' : 'warning');
      setDailyMetricsMessage(
        refreshResult.refreshed
          ? '日频指标已刷新并回写本地快照。'
          : '在线刷新失败，当前展示的是本地旧快照。',
      );
    } catch (requestError) {
      const parsed = getParsedApiError(requestError);
      setDailyMetricsMessageTone('warning');
      setDailyMetricsMessage(parsed.message || '日频指标刷新失败');
    } finally {
      setDailyMetricsRefreshing(false);
    }
  };

  const latestBar = useMemo(() => resolveLatestBar(result?.dailyBars ?? []), [result?.dailyBars]);
  const quote = result?.quote;
  const orderBook = result?.orderBook;
  const profile = result?.profile;
  const topHoldings = result?.topHoldings ?? [];
  const analysis = result?.analysis;
  const estimatedIopv = result?.estimatedIopv;
  const dailyMetrics = result?.dailyMetrics;
  const hasDailyMetrics = Boolean(
    dailyMetrics && (
      dailyMetrics.fundShares !== null && dailyMetrics.fundShares !== undefined
      || dailyMetrics.nav !== null && dailyMetrics.nav !== undefined
      || dailyMetrics.derivedFundSizeYi !== null && dailyMetrics.derivedFundSizeYi !== undefined
    ),
  );
  const hasPendingInputChange = query.trim() !== (lastResolvedInput || '').trim();

  const handleHistoryRestore = async (item: EtfQueryHistoryItem) => {
    setHistoryRestoreId(item.queryId);
    setHistoryError(null);
    try {
      const detail = await stockQueryApi.getEtfHistoryItem(item.queryId);
      if (detail.result) {
        await applySnapshot(detail.result, detail.stockCode || detail.queryText || query);
      }
      if (detail.stockCode) {
        setQuery(detail.stockCode);
      }
      setHistoryOpen(false);
    } catch (requestError) {
      setHistoryError(getParsedApiError(requestError));
    } finally {
      setHistoryRestoreId(null);
    }
  };

  return (
    <AppPage className="space-y-6 !max-w-[1680px] px-3 md:px-5 lg:px-6">
      <section className="paper-hero">
        <div className="grid gap-6 px-5 py-6 lg:grid-cols-[1.1fr_0.9fr] lg:px-7 lg:py-7">
          <div className="space-y-5">
            <PaperHeroHeader
              eyebrow="ETF Research"
              title="把 ETF 当成独立对象来看"
              description="这里不再混用个股基本面逻辑，优先看价格、流动性、折返区间和最近日线状态。"
              icon={<Layers3 className="h-7 w-7" />}
            />

            <form className="space-y-4" onSubmit={handleSubmit}>
              <Input
                label="ETF 代码或名称"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="例如 512880.SH、159995、证券ETF、沪深300ETF"
                hint="支持 ETF 代码、裸码和常见 ETF 名称；名称不唯一时后端会提示你补充。"
              />
              <div className="flex flex-wrap gap-2">
                {QUICK_ETF_QUERIES.map((item) => (
                  <button
                    key={item.value}
                    type="button"
                    className="paper-chip px-3 py-1.5"
                    onClick={() => setQuery(item.value)}
                  >
                    <Search className="h-3.5 w-3.5" />
                    <span>{item.label}</span>
                  </button>
                ))}
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <Button type="submit" size="lg" isLoading={isLoading} loadingText="正在拉取 ETF 快照...">
                  查询 ETF
                </Button>
                <Button variant="outline" size="lg" onClick={() => {
                  setHistoryOpen(true);
                  void loadHistory();
                }}>
                  <Clock3 className="h-4 w-4" />
                  历史记录
                </Button>
                {result ? (
                  <Button
                    variant="secondary"
                    size="lg"
                    onClick={() => void loadEtfSnapshot(result.stockCode)}
                    disabled={isLoading}
                  >
                    <RefreshCw className="h-4 w-4" />
                    刷新快照
                  </Button>
                ) : null}
                {hasPendingInputChange ? (
                  <Badge variant="info" className="border-0 px-3 py-1">
                    输入已变更，提交后更新结果
                  </Badge>
                ) : null}
              </div>
            </form>
          </div>

          <Card variant="bordered" padding="lg" className="paper-panel rounded-[24px] border-border/60 bg-card/90">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-secondary-text">Why Separate</p>
                <h3 className="mt-1 text-[1.55rem] font-semibold tracking-[-0.02em] text-foreground">ETF 页面只保留 ETF 真正关心的字段</h3>
              </div>
              <Badge variant="info" className="border-0 px-3 py-1">独立菜单</Badge>
            </div>
            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              <Card variant="bordered" padding="md" className="paper-panel-muted">
                <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">流动性</p>
                <p className="mt-2 text-sm leading-6 text-secondary-text">成交额、换手率、量比和盘口更重要。</p>
              </Card>
              <Card variant="bordered" padding="md" className="paper-panel-muted">
                <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">交易区间</p>
                <p className="mt-2 text-sm leading-6 text-secondary-text">涨跌停价、最近 K 线和位置判断更直接。</p>
              </Card>
              <Card variant="bordered" padding="md" className="paper-panel-muted">
                <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">载体属性</p>
                <p className="mt-2 text-sm leading-6 text-secondary-text">ETF 是指数或主题载体，不是公司基本面对象。</p>
              </Card>
              <Card variant="bordered" padding="md" className="paper-panel-muted">
                <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">底层共用</p>
                <p className="mt-2 text-sm leading-6 text-secondary-text">行情抓取、缓存、日 K 补数仍共用统一 market 基础层。</p>
              </Card>
            </div>
          </Card>
        </div>
      </section>

      {error ? (
        <ApiErrorAlert
          error={error}
          actionLabel="重试"
          onAction={() => void loadEtfSnapshot(query)}
          onDismiss={() => setError(null)}
        />
      ) : null}

      {!result && !isLoading ? (
        <EmptyState
          title="先查一只 ETF"
          description="现在既可以输 512880、159995、510300 这类代码，也可以直接输证券ETF、沪深300ETF 这类名称。"
          icon={<Layers3 className="h-7 w-7" />}
        />
      ) : null}

      {result ? (
        <>
          <section className="grid gap-5 xl:grid-cols-[1.15fr_0.85fr]">
            <Card variant="bordered" padding="lg" className="rounded-[24px]">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <div className="flex items-center gap-3">
                    <h3 className="text-[2rem] font-semibold tracking-[-0.03em] text-foreground">{result.stockName}</h3>
                    <Badge variant="info" className="border-0 px-3 py-1">{result.stockCode}</Badge>
                  </div>
                  <p className="mt-2 text-sm text-secondary-text">
                    实时来源 {result.dataSources.quote || '--'}，日线来源 {result.dataSources.dailyBars || '--'}。
                  </p>
                </div>
                <div className="text-right">
                  <p className={`text-[2.15rem] font-semibold tracking-[-0.03em] ${quoteTone(quote?.changePct)}`}>{formatNumber(quote?.price, 3)}</p>
                  <p className={`mt-2 text-sm font-medium ${quoteTone(quote?.changePct)}`}>
                    {formatSignedPercent(quote?.changePct)} / {formatNumber(quote?.changeAmount, 3)}
                  </p>
                </div>
              </div>

              <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <Card variant="bordered" padding="md" className="paper-kpi-card">
                  <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">换手率</p>
                  <p className="mt-2 text-2xl font-semibold text-foreground">{formatSignedPercent(quote?.turnoverRate).replace('+', '')}</p>
                </Card>
                <Card variant="bordered" padding="md" className="paper-kpi-card">
                  <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">量比</p>
                  <p className="mt-2 text-2xl font-semibold text-foreground">{formatNumber(quote?.volumeRatio, 2)}</p>
                </Card>
                <Card variant="bordered" padding="md" className="paper-kpi-card">
                  <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">PB</p>
                  <p className="mt-2 text-2xl font-semibold text-foreground">{formatNumber(quote?.pb, 2)}</p>
                </Card>
                <Card variant="bordered" padding="md" className="paper-kpi-card">
                  <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">PE(TTM)</p>
                  <p className="mt-2 text-2xl font-semibold text-foreground">{formatNumber(quote?.peTtm, 2)}</p>
                </Card>
                <Card variant="bordered" padding="md" className="paper-kpi-card">
                  <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">总市值</p>
                  <p className="mt-2 text-2xl font-semibold text-foreground">{formatLargeAmountYi(quote?.totalMarketValueYi)}</p>
                </Card>
                <Card variant="bordered" padding="md" className="paper-kpi-card">
                  <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">流通市值</p>
                  <p className="mt-2 text-2xl font-semibold text-foreground">{formatLargeAmountYi(quote?.floatMarketValueYi)}</p>
                </Card>
                <Card variant="bordered" padding="md" className="paper-kpi-card">
                  <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">涨停价</p>
                  <p className="mt-2 text-2xl font-semibold text-danger">{formatNumber(quote?.limitUp, 3)}</p>
                </Card>
                <Card variant="bordered" padding="md" className="paper-kpi-card">
                  <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">跌停价</p>
                  <p className="mt-2 text-2xl font-semibold text-success">{formatNumber(quote?.limitDown, 3)}</p>
                </Card>
              </div>
            </Card>

            <Card variant="bordered" padding="lg" className="rounded-[24px]">
              <div className="flex items-center gap-3">
                <Activity className="h-5 w-5 text-foreground" />
                <div>
                  <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-secondary-text">ETF Judgment</p>
                  <h3 className="mt-1 text-[1.55rem] font-semibold tracking-[-0.02em] text-foreground">ETF 专属结论</h3>
                </div>
              </div>
              <div className="mt-5 space-y-4">
                <div className="flex flex-wrap items-center gap-3">
                  <Badge variant={analysisBadgeVariant(analysis?.signal)} className="border-0 px-3 py-1 text-sm">
                    {analysis?.signal || '仅观察'}
                  </Badge>
                  <Badge variant="default" className="border-border/50 px-3 py-1 text-sm">
                    {analysis?.pattern || '--'}
                  </Badge>
                </div>

                <div className="rounded-2xl border border-border/60 bg-card/60 p-4">
                  <p className="text-sm leading-6 text-foreground">
                    {analysis?.summary || '当前 ETF 还没有形成更明确的交易结论。'}
                  </p>
                </div>

                <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
                  <div className="rounded-2xl border border-border/60 bg-card/60 p-4">
                    <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">支撑位</p>
                    <p className="mt-2 text-xl font-semibold text-foreground">{formatNumber(analysis?.support, 3)}</p>
                  </div>
                  <div className="rounded-2xl border border-border/60 bg-card/60 p-4">
                    <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">压力位</p>
                    <p className="mt-2 text-xl font-semibold text-foreground">{formatNumber(analysis?.pressure, 3)}</p>
                  </div>
                  <div className="rounded-2xl border border-border/60 bg-card/60 p-4">
                    <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">MA10</p>
                    <p className="mt-2 text-xl font-semibold text-foreground">{formatNumber(analysis?.ma10, 3)}</p>
                  </div>
                  <div className="rounded-2xl border border-border/60 bg-card/60 p-4">
                    <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">偏离 MA10</p>
                    <p className={`mt-2 text-xl font-semibold ${quoteTone(analysis?.biasMa10)}`}>{formatSignedPercent(analysis?.biasMa10)}</p>
                  </div>
                </div>

                {estimatedIopv?.value ? (
                  <div className="rounded-2xl border border-border/60 bg-card/60 p-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">Estimated IOPV</p>
                        <p className="mt-2 text-2xl font-semibold text-foreground">{formatNumber(estimatedIopv.value, 3)}</p>
                      </div>
                      <div className="text-right">
                        <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">估算折溢价</p>
                        <p className={`mt-2 text-2xl font-semibold ${quoteTone(estimatedIopv.premiumDiscountPct)}`}>
                          {formatSignedPercent(estimatedIopv.premiumDiscountPct)}
                        </p>
                      </div>
                    </div>
                    <div className="mt-4 grid gap-3 sm:grid-cols-3">
                      <div className="rounded-2xl border border-border/50 bg-background/70 p-3">
                        <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">覆盖权重</p>
                        <p className="mt-2 text-lg font-semibold text-foreground">{formatPercent(estimatedIopv.coverageWeightPct)}</p>
                      </div>
                      <div className="rounded-2xl border border-border/50 bg-background/70 p-3">
                        <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">命中持仓</p>
                        <p className="mt-2 text-lg font-semibold text-foreground">
                          {estimatedIopv.matchedHoldingsCount} / {estimatedIopv.totalHoldingsCount}
                        </p>
                      </div>
                      <div className="rounded-2xl border border-border/50 bg-background/70 p-3">
                        <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">披露期</p>
                        <p className="mt-2 text-lg font-semibold text-foreground">{estimatedIopv.reportPeriod || '--'}</p>
                      </div>
                    </div>
                    <p className="mt-4 text-sm leading-6 text-secondary-text">
                      {estimatedIopv.note || '这是估算值，不等同于交易所正式 IOPV。'}
                    </p>
                  </div>
                ) : null}

                {result ? (
                  <div className="rounded-2xl border border-border/60 bg-card/60 p-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">Daily Metrics</p>
                        <p className="mt-2 text-sm leading-6 text-secondary-text">
                          这组是基金日频口径，和盘中成交价、估算 IOPV 不是同一个概念。
                        </p>
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant="default" className="border-border/50 px-3 py-1 text-sm">
                          {dailyMetrics?.tradeDate || '--'}
                        </Badge>
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => void handleDailyMetricsRefresh()}
                          isLoading={dailyMetricsRefreshing}
                          loadingText="刷新中..."
                        >
                          <RefreshCw className="h-4 w-4" />
                          刷新日频
                        </Button>
                      </div>
                    </div>
                    {dailyMetricsMessage ? (
                      <div className="mt-4">
                        <InlineAlert
                          title={dailyMetricsMessageTone === 'success' ? '刷新完成' : '刷新提示'}
                          variant={dailyMetricsMessageTone}
                          message={dailyMetricsMessage}
                        />
                      </div>
                    ) : null}
                    {hasDailyMetrics ? (
                      <>
                        <div className="mt-4 grid gap-3 sm:grid-cols-3">
                          <div className="rounded-2xl border border-border/50 bg-background/70 p-3">
                            <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">基金份额</p>
                            <p className="mt-2 text-lg font-semibold text-foreground">{formatFundShares(dailyMetrics?.fundShares)}</p>
                          </div>
                          <div className="rounded-2xl border border-border/50 bg-background/70 p-3">
                            <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">单位净值</p>
                            <p className="mt-2 text-lg font-semibold text-foreground">{formatNumber(dailyMetrics?.nav, 4)}</p>
                          </div>
                          <div className="rounded-2xl border border-border/50 bg-background/70 p-3">
                            <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">估算规模</p>
                            <p className="mt-2 text-lg font-semibold text-foreground">{formatLargeAmountYi(dailyMetrics?.derivedFundSizeYi)}</p>
                          </div>
                        </div>
                        <div className="mt-4 grid gap-3 sm:grid-cols-3">
                          <div className="rounded-2xl border border-border/50 bg-background/70 p-3">
                            <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">实时成交价</p>
                            <p className="mt-2 text-lg font-semibold text-foreground">{formatNumber(quote?.price, 3)}</p>
                          </div>
                          <div className="rounded-2xl border border-border/50 bg-background/70 p-3">
                            <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">估算 IOPV</p>
                            <p className="mt-2 text-lg font-semibold text-foreground">{formatNumber(estimatedIopv?.value, 3)}</p>
                          </div>
                          <div className="rounded-2xl border border-border/50 bg-background/70 p-3">
                            <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">日频来源</p>
                            <p className="mt-2 text-sm font-semibold text-foreground">
                              {dailyMetrics?.exchange || '--'} / {dailyMetrics?.dataSource || result.dataSources.dailyMetrics || '--'}
                            </p>
                          </div>
                        </div>
                        <div className="mt-4 grid gap-3 sm:grid-cols-2">
                          <div className="rounded-2xl border border-border/50 bg-background/70 p-3">
                            <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">缓存状态</p>
                            <p className="mt-2 text-sm font-semibold text-foreground">
                              {formatDailyMetricsCacheStatus(dailyMetrics?.cacheStatus)}
                            </p>
                          </div>
                          <div className="rounded-2xl border border-border/50 bg-background/70 p-3">
                            <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">上次刷新时间</p>
                            <p className="mt-2 text-sm font-semibold text-foreground">
                              {formatDateTime(dailyMetrics?.updatedAt)}
                            </p>
                          </div>
                        </div>
                        <p className="mt-4 text-sm leading-6 text-secondary-text">
                          `基金份额` 表示一共多少份，`单位净值` 表示每份净资产值多少钱，`估算规模` 是两者相乘后的日频口径结果。
                        </p>
                      </>
                    ) : (
                      <div className="mt-4 rounded-2xl border border-dashed border-border/60 bg-background/60 p-4">
                        <p className="text-sm leading-6 text-secondary-text">
                          当前还没有可用的日频指标，可以先点击右上角 `刷新日频`，拉取基金份额、单位净值和估算规模。
                        </p>
                      </div>
                    )}
                  </div>
                ) : null}

                {analysis?.selectedReasons?.length ? (
                  <div className="rounded-2xl border border-border/60 bg-card/60 p-4">
                    <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">看多理由</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {analysis.selectedReasons.map((item) => (
                        <Badge key={item} variant="success" className="rounded-full border-0 px-3 py-1 text-xs leading-6">
                          {item}
                        </Badge>
                      ))}
                    </div>
                  </div>
                ) : null}

                {analysis?.riskReasons?.length ? (
                  <div className="rounded-2xl border border-border/60 bg-card/60 p-4">
                    <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">风险提示</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {analysis.riskReasons.map((item) => (
                        <Badge key={item} variant="warning" className="rounded-full border-0 px-3 py-1 text-xs leading-6">
                          {item}
                        </Badge>
                      ))}
                    </div>
                  </div>
                ) : null}

                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-2xl border border-border/60 bg-card/60 p-4">
                    <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">成交额</p>
                    <p className="mt-2 text-xl font-semibold text-foreground">{formatNumber(quote?.amountWan, 2)} 万</p>
                  </div>
                  <div className="rounded-2xl border border-border/60 bg-card/60 p-4">
                    <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">振幅</p>
                    <p className="mt-2 text-xl font-semibold text-foreground">{formatSignedPercent(quote?.amplitudePct).replace('+', '')}</p>
                  </div>
                  <div className="rounded-2xl border border-border/60 bg-card/60 p-4">
                    <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">买一 / 卖一</p>
                    <p className="mt-2 text-xl font-semibold text-foreground">
                      {formatNumber(orderBook?.bid1, 3)} / {formatNumber(orderBook?.ask1, 3)}
                    </p>
                  </div>
                  <div className="rounded-2xl border border-border/60 bg-card/60 p-4">
                    <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">买一量 / 卖一量</p>
                    <p className="mt-2 text-xl font-semibold text-foreground">
                      {formatVolume(orderBook?.bidVol1)} / {formatVolume(orderBook?.askVol1)}
                    </p>
                  </div>
                </div>

                {result.errors.length ? (
                  <InlineAlert
                    title="部分数据降级"
                    variant="warning"
                    message={result.errors.slice(0, 3).join('；')}
                  />
                ) : null}
              </div>
            </Card>
          </section>

          <section className="grid gap-5 xl:grid-cols-[1fr_1fr]">
            <Card variant="bordered" padding="lg" className="rounded-[24px]">
              <div className="flex items-center gap-3">
                <BarChart3 className="h-5 w-5 text-foreground" />
                <div>
                  <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-secondary-text">Daily Bars</p>
                  <h3 className="mt-1 text-[1.55rem] font-semibold tracking-[-0.02em] text-foreground">最近日线状态</h3>
                </div>
              </div>
              {latestBar ? (
                <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                  <div className="rounded-2xl border border-border/60 bg-card/60 p-4">
                    <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">最新交易日</p>
                    <p className="mt-2 text-lg font-semibold text-foreground">{latestBar.datetime}</p>
                  </div>
                  <div className="rounded-2xl border border-border/60 bg-card/60 p-4">
                    <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">收盘价</p>
                    <p className="mt-2 text-lg font-semibold text-foreground">{formatNumber(latestBar.close, 3)}</p>
                  </div>
                  <div className="rounded-2xl border border-border/60 bg-card/60 p-4">
                    <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">成交量</p>
                    <p className="mt-2 text-lg font-semibold text-foreground">{formatVolume(latestBar.volume)}</p>
                  </div>
                  <div className="rounded-2xl border border-border/60 bg-card/60 p-4">
                    <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">成交额</p>
                    <p className="mt-2 text-lg font-semibold text-foreground">{formatVolume(latestBar.amount)}</p>
                  </div>
                </div>
              ) : (
                <div className="mt-5">
                  <EmptyState title="暂无日线数据" description="当前 ETF 快照没有返回最近日线。" />
                </div>
              )}
            </Card>

            <Card variant="bordered" padding="lg" className="rounded-[24px]">
              <div className="flex items-center gap-3">
                <ShieldAlert className="h-5 w-5 text-foreground" />
                <div>
                  <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-secondary-text">Tracking Profile</p>
                  <h3 className="mt-1 text-[1.55rem] font-semibold tracking-[-0.02em] text-foreground">跟踪标的与基金档案</h3>
                </div>
              </div>
              <div className="mt-5 grid gap-3">
                <div className="rounded-2xl border border-border/60 bg-card/60 p-4">
                  <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">跟踪标的</p>
                  <p className="mt-2 text-lg font-semibold text-foreground">{profile?.trackingTarget || '--'}</p>
                </div>
                <div className="rounded-2xl border border-border/60 bg-card/60 p-4">
                  <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">业绩比较基准</p>
                  <p className="mt-2 text-sm leading-6 text-secondary-text">{profile?.performanceBenchmark || '--'}</p>
                </div>
                <div className="rounded-2xl border border-border/60 bg-card/60 p-4">
                  <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">基金全称</p>
                  <p className="mt-2 text-sm leading-6 text-secondary-text">{profile?.fundFullName || '--'}</p>
                </div>
                <div className="rounded-2xl border border-border/60 bg-card/60 p-4">
                  <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">投资目标</p>
                  <p className="mt-2 text-sm leading-6 text-secondary-text">{profile?.investmentObjective || '--'}</p>
                </div>
              </div>
            </Card>
          </section>

          <section>
            <Card variant="bordered" padding="lg" className="rounded-[24px]">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-secondary-text">Top Holdings</p>
                  <h3 className="mt-1 text-[1.55rem] font-semibold tracking-[-0.02em] text-foreground">前十重仓股</h3>
                </div>
                <Badge variant="info" className="border-0 px-3 py-1">
                  {topHoldings[0]?.reportPeriod || '最近披露期'}
                </Badge>
              </div>

              {topHoldings.length ? (
                <div className="mt-5 overflow-x-auto">
                  <table className="paper-table min-w-full text-sm">
                    <thead>
                      <tr>
                        <th>排名</th>
                        <th>股票</th>
                        <th>代码</th>
                        <th>占净值比</th>
                        <th>持股数</th>
                        <th>持仓市值</th>
                      </tr>
                    </thead>
                    <tbody>
                      {topHoldings.map((item) => (
                        <tr key={`${item.rank}-${item.stockCode}`}>
                          <td className="font-medium">{item.rank ?? '--'}</td>
                          <td className="font-medium">{item.stockName || '--'}</td>
                          <td className="text-secondary-text">{item.stockCode || '--'}</td>
                          <td>{formatPercent(item.weightPct)}</td>
                          <td>{formatNumber(item.sharesWan, 2)} 万股</td>
                          <td>{formatNumber(item.marketValueWan, 2)} 万元</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="mt-5">
                  <EmptyState title="暂未拿到重仓股" description="当前 ETF 档案没有返回前十持仓，后续可以继续补其他基金档案源兜底。" />
                </div>
              )}
            </Card>
          </section>
        </>
      ) : null}

      <Drawer
        isOpen={historyOpen}
        onClose={() => setHistoryOpen(false)}
        title="ETF 查询历史"
        width="max-w-xl"
        side="right"
      >
        <div className="space-y-4">
          {historyError ? <ApiErrorAlert error={historyError} /> : null}

          {historyLoading ? (
            <InlineAlert
              variant="info"
              title="正在加载历史记录"
              message="正在从后端读取最近的 ETF 查询快照。"
            />
          ) : null}

          {historyItems.length === 0 ? (
            <EmptyState
              title="暂无 ETF 查询历史"
              description="查过几次 ETF 之后，这里会保留最近快照，方便回看和快速恢复。"
              icon={<Clock3 className="h-8 w-8" />}
            />
          ) : null}

          <div className="space-y-3">
            {historyItems.map((item) => {
              const active = item.queryId === currentHistoryId;
              const restoring = historyRestoreId === item.queryId;
              const historyResult = item.result;
              return (
                <div
                  key={item.queryId}
                  className={[
                    'paper-list-card px-4 py-4 transition-colors',
                    active ? 'border-foreground/18 bg-foreground/[0.045]' : 'border-border/60 bg-background/70',
                  ].join(' ')}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-base font-semibold text-foreground">
                        {item.stockName || item.queryText || 'ETF 查询'}{' '}
                        <span className="text-secondary-text">{item.stockCode || '--'}</span>
                      </p>
                      <p className="mt-1 text-sm text-secondary-text">{formatHistoryTime(item.completedAt || item.createdAt)}</p>
                    </div>
                    <Badge variant={item.status === 'completed' ? 'info' : 'warning'} className="border-0">
                      {item.status === 'completed' ? '已完成' : '失败'}
                    </Badge>
                  </div>

                  <div className="mt-3 space-y-2 text-sm">
                    <p className="text-foreground">
                      {historyResult?.stockName || item.stockName || '--'} · 最新价 {formatNumber(historyResult?.quote?.price, 3)}
                    </p>
                    <p className="text-secondary-text">
                      涨跌幅 {formatSignedPercent(historyResult?.quote?.changePct)} · 跟踪标的 {historyResult?.profile?.trackingTarget || '--'}
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
                      disabled={!item.result}
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

export default EtfQueryPage;
