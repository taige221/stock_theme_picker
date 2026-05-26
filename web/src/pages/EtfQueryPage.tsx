import type React from 'react';
import { useEffect, useMemo, useState } from 'react';
import { Clock3, Layers3, RefreshCw, Search } from 'lucide-react';
import { useLocation } from 'react-router-dom';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import {
  stockQueryApi,
  type EtfMarketBar,
  type EtfDailyMetricsRefreshResponse,
  type EtfQueryHistoryItem,
  type EtfMarketSnapshotResponse,
} from '../api/stockQuery';
import { ApiErrorAlert, AppPage, Badge, Button, Card, Drawer, EmptyState, InlineAlert } from '../components/common';
import { CandlestickChart } from '../components/CandlestickChart';

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const QUICK_ETF_QUERIES = [
  { label: '证券 ETF', value: '512880.SH' },
  { label: '芯片 ETF', value: '159995.SZ' },
  { label: '沪深 300 ETF', value: '510300.SH' },
  { label: '科创 50 ETF', value: '588000.SH' },
] as const;

const ETF_CATEGORY_TABS = [
  { key: 'theme', label: '主题 ETF' },
  { key: 'broad', label: '宽基' },
  { key: 'industry', label: '行业' },
  { key: 'cross', label: '跨境' },
  { key: 'commodity', label: '商品' },
  { key: 'bond', label: '债券' },
] as const;

/* ------------------------------------------------------------------ */
/*  Utility functions                                                  */
/* ------------------------------------------------------------------ */

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
  return `¥${formatNumber(value, 1)} 亿`;
}

function formatAmountYi(value?: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '--';
  return `¥${formatNumber(value, 1)} 亿`;
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

function formatHistoryTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(date);
}

function resolveLatestBar(bars: EtfMarketBar[]): EtfMarketBar | null {
  if (!bars.length) return null;
  return bars[bars.length - 1] ?? null;
}

function analysisBadgeVariant(signal?: string | null): 'default' | 'success' | 'warning' | 'info' {
  switch (signal) {
    case '趋势跟随': case '低吸观察': return 'success';
    case '不宜追高': return 'warning';
    case '短线异动': return 'info';
    default: return 'default';
  }
}

function deriveTrendStatus(
  ma5?: number | null, ma10?: number | null, ma20?: number | null,
): { label: string; variant: 'success' | 'warning' | 'danger' | 'default' | 'info' } {
  if (ma5 == null || ma10 == null || ma20 == null) return { label: '数据不足', variant: 'default' };
  if (ma5 > ma10 && ma10 > ma20) return { label: '多头排列', variant: 'success' };
  if (ma5 < ma10 && ma10 < ma20) return { label: '空头排列', variant: 'danger' };
  return { label: '震荡整理', variant: 'info' };
}

function deriveVolumeSignal(volumeRatio?: number | null): { label: string; variant: 'success' | 'warning' | 'danger' | 'default' | 'info' } {
  if (volumeRatio == null) return { label: '--', variant: 'default' };
  if (volumeRatio > 2.0) return { label: `显著放量 ${formatNumber(volumeRatio, 1)}x`, variant: 'warning' };
  if (volumeRatio > 1.2) return { label: `温和放量 ${formatNumber(volumeRatio, 1)}x`, variant: 'info' };
  if (volumeRatio >= 0.8) return { label: `量能平稳 ${formatNumber(volumeRatio, 1)}x`, variant: 'default' };
  return { label: `缩量 ${formatNumber(volumeRatio, 1)}x`, variant: 'default' };
}

function derivePremiumSignal(pct?: number | null): { label: string; variant: 'success' | 'warning' | 'danger' | 'default' | 'info' } {
  if (pct == null) return { label: '--', variant: 'default' };
  if (pct > 2) return { label: `溢价偏高 ${formatSignedPercent(pct)}`, variant: 'warning' };
  if (pct > 0.5) return { label: `小幅溢价 ${formatSignedPercent(pct)}`, variant: 'info' };
  if (pct >= -0.5) return { label: `基本平价 ${formatSignedPercent(pct)}`, variant: 'default' };
  if (pct >= -2) return { label: `小幅折价 ${formatSignedPercent(pct)}`, variant: 'success' };
  return { label: `深度折价 ${formatSignedPercent(pct)}`, variant: 'warning' };
}

/* ------------------------------------------------------------------ */
/*  Main component                                                     */
/* ------------------------------------------------------------------ */

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
  const [activeCategory, setActiveCategory] = useState('theme');
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
    const sync = async () => {
      setQuery(initialQuery);
      setError(null);
    };
    void sync();
  }, [initialQuery]);

  /* ---- data loaders ---- */

  const loadHistory = async (stockCode?: string) => {
    setHistoryLoading(true); setHistoryError(null);
    try {
      const response = await stockQueryApi.getEtfHistory(20, stockCode);
      setHistoryItems(response.items);
    } catch (requestError) { setHistoryError(getParsedApiError(requestError)); }
    finally { setHistoryLoading(false); }
  };

  useEffect(() => { const init = async () => { await loadHistory(); }; void init(); }, []);

  const applySnapshot = async (snapshot: EtfMarketSnapshotResponse, resolvedInput: string) => {
    setResult(snapshot);
    setLastResolvedInput(resolvedInput);
    setCurrentHistoryId(snapshot.queryId ?? null);
  };

  const loadEtfSnapshot = async (rawInput: string) => {
    const normalized = rawInput.trim();
    if (!normalized) return;
    setIsLoading(true); setError(null); setDailyMetricsMessage(null);
    try {
      const snapshot = await stockQueryApi.getEtfMarketSnapshot(normalized, 60);
      await applySnapshot(snapshot, normalized);
    } catch (requestError) { setError(getParsedApiError(requestError)); }
    finally { setIsLoading(false); }
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await loadEtfSnapshot(query);
  };

  const applyDailyMetricsRefresh = (refreshResult: EtfDailyMetricsRefreshResponse) => {
    setResult((previous) => {
      if (!previous || previous.stockCode !== refreshResult.stockCode) return previous;
      return {
        ...previous,
        dailyMetrics: refreshResult.dailyMetrics,
        dataSources: { ...previous.dataSources, dailyMetrics: refreshResult.dailyMetrics.dataSource ?? previous.dataSources.dailyMetrics },
        errors: refreshResult.errors.length ? refreshResult.errors : previous.errors,
      };
    });
  };

  const handleDailyMetricsRefresh = async () => {
    const stockCode = result?.stockCode;
    if (!stockCode) return;
    setDailyMetricsRefreshing(true); setDailyMetricsMessage(null);
    try {
      const refreshResult = await stockQueryApi.refreshEtfDailyMetrics(stockCode);
      applyDailyMetricsRefresh(refreshResult);
      setDailyMetricsMessageTone(refreshResult.refreshed ? 'success' : 'warning');
      setDailyMetricsMessage(refreshResult.refreshed ? '日频指标已刷新并回写本地快照。' : '在线刷新失败，当前展示的是本地旧快照。');
    } catch (requestError) {
      const parsed = getParsedApiError(requestError);
      setDailyMetricsMessageTone('warning');
      setDailyMetricsMessage(parsed.message || '日频指标刷新失败');
    } finally { setDailyMetricsRefreshing(false); }
  };

  const handleHistoryRestore = async (item: EtfQueryHistoryItem) => {
    setHistoryRestoreId(item.queryId); setHistoryError(null);
    try {
      const detail = await stockQueryApi.getEtfHistoryItem(item.queryId);
      if (detail.result) await applySnapshot(detail.result, detail.stockCode || detail.queryText || query);
      if (detail.stockCode) setQuery(detail.stockCode);
      setHistoryOpen(false);
    } catch (requestError) { setHistoryError(getParsedApiError(requestError)); }
    finally { setHistoryRestoreId(null); }
  };

  /* ---- derived data ---- */

  const latestBar = useMemo(() => resolveLatestBar(result?.dailyBars ?? []), [result?.dailyBars]);
  const quote = result?.quote;
  const orderBook = result?.orderBook;
  const profile = result?.profile;
  const topHoldings = result?.topHoldings ?? [];
  const analysis = result?.analysis;
  const estimatedIopv = result?.estimatedIopv;
  const dailyMetrics = result?.dailyMetrics;
  const hasPendingInputChange = query.trim() !== (lastResolvedInput || '').trim();

  /* ================================================================ */
  /*  RENDER                                                           */
  /* ================================================================ */

  return (
    <AppPage className="!max-w-none px-4 md:px-8 lg:px-12 xl:px-16">

      {/* ---- Breadcrumb + Search ---- */}
      <div className="search-bar-card flex flex-wrap items-center gap-3 lg:gap-4">
        <p className="shrink-0 text-sm text-secondary-text">
          ETF 查询
          {result ? (
            <> / <span className="text-secondary-text">{result.instrumentLabel || '主题类'}</span> / <span className="font-semibold text-foreground">{result.stockName}</span>{' '}<span>{result.stockCode}</span></>
          ) : null}
        </p>

        <form className="relative min-w-0 flex-1" onSubmit={handleSubmit}>
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-secondary-text" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="输入 ETF 代码、名称或跟踪指数..."
            className="h-10 w-full rounded-xl border border-border bg-card pl-9 pr-20 text-sm text-foreground placeholder:text-secondary-text/60 focus:border-foreground/30 focus:outline-none"
          />
          <div className="absolute right-2 top-1/2 flex -translate-y-1/2 items-center gap-1">
            {hasPendingInputChange ? (
              <button type="submit" className="rounded-lg bg-foreground px-3 py-1 text-xs font-medium text-background">
                查询
              </button>
            ) : null}
            <button type="button" onClick={() => { setHistoryOpen(true); void loadHistory(); }} className="rounded-lg px-2 py-1 text-xs text-secondary-text hover:text-foreground">
              关 K
            </button>
          </div>
        </form>

        <p className="shrink-0 text-sm text-secondary-text">
          {result?.profile?.trackingTarget ? (
            <>跟踪 {result.profile.trackingTarget}</>
          ) : null}
        </p>
      </div>

      {/* ---- Category tabs ---- */}
      <div className="mt-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-1.5">
          {ETF_CATEGORY_TABS.map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => setActiveCategory(tab.key)}
              className={`rounded-lg px-4 py-1.5 text-sm font-medium transition-colors ${
                activeCategory === tab.key
                  ? 'bg-foreground text-background'
                  : 'text-secondary-text hover:bg-elevated hover:text-foreground'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          {QUICK_ETF_QUERIES.map((item) => (
            <button key={item.value} type="button" onClick={() => setQuery(item.value)} className="rounded-lg border border-border px-3 py-1 text-xs text-secondary-text transition-colors hover:border-foreground/30 hover:text-foreground">
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {/* ---- Error alerts ---- */}
      {error ? <div className="mt-4"><ApiErrorAlert error={error} actionLabel="重试" onAction={() => void loadEtfSnapshot(query)} onDismiss={() => setError(null)} /></div> : null}

      {/* ---- Empty state ---- */}
      {!result && !isLoading ? (
        <div className="mt-6">
          <EmptyState
            title="先查一只 ETF"
            description="现在既可以输 512880、159995、510300 这类代码，也可以直接输证券ETF、沪深300ETF 这类名称。"
            icon={<Layers3 className="h-7 w-7" />}
            action={<Button onClick={() => void loadEtfSnapshot(query)} className="rounded-xl">查询 ETF</Button>}
          />
        </div>
      ) : null}

      {/* ---- Loading state ---- */}
      {isLoading && !result ? (
        <div className="mt-6">
          <Card padding="lg" className="!rounded-2xl">
            <div className="flex items-center gap-4">
              <RefreshCw className="h-5 w-5 animate-spin text-foreground" />
              <p className="text-lg font-semibold text-foreground">正在拉取 ETF 快照...</p>
            </div>
          </Card>
        </div>
      ) : null}

      {/* ---- Main content (when result loaded) ---- */}
      {result ? (
        <div className="mt-5 grid min-w-0 gap-5 xl:grid-cols-[1fr_380px]">

          {/* ======================== LEFT COLUMN ======================== */}
          <div className="min-w-0 space-y-5">

            {/* ---- ETF header card ---- */}
            <Card padding="lg" className="!rounded-2xl">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <div className="flex items-center gap-3">
                    <h2 className="text-3xl font-bold text-foreground">{result.stockName}</h2>
                    <span className="rounded-md border border-border px-2 py-0.5 text-sm text-secondary-text">{result.stockCode}</span>
                  </div>
                  {/* Badges */}
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    {result.instrumentLabel ? (
                      <Badge variant="danger" size="sm" className="border-danger/30 bg-danger/90 text-white">
                        {result.instrumentLabel}
                      </Badge>
                    ) : null}
                    {profile?.trackingTarget ? (
                      <span className="rounded-full border border-border bg-elevated/60 px-3 py-1 text-xs font-medium text-foreground">
                        跟踪 {profile.trackingTarget}
                      </span>
                    ) : null}
                    {analysis?.signal ? (
                      <Badge variant={analysisBadgeVariant(analysis.signal)} size="sm">{analysis.signal}</Badge>
                    ) : null}
                    {analysis?.pattern ? (
                      <span className="rounded-full border border-border bg-elevated/60 px-3 py-1 text-xs font-medium text-foreground">
                        {analysis.pattern}
                      </span>
                    ) : null}
                  </div>
                </div>

                <div className="flex items-center gap-6">
                  {/* Price */}
                  <div className="text-right">
                    <p className={`text-3xl font-bold ${quoteTone(quote?.changePct)}`}>{formatNumber(quote?.price, 3)}</p>
                    <p className={`mt-0.5 text-lg font-semibold ${quoteTone(quote?.changePct)}`}>
                      {quote?.changeAmount != null ? `${quote.changeAmount > 0 ? '+' : ''}${formatNumber(quote.changeAmount, 3)}` : '--'}
                      {' '}({formatSignedPercent(quote?.changePct)})
                    </p>
                  </div>
                  {/* Refresh */}
                  <Button
                    variant="secondary"
                    size="sm"
                    className="rounded-xl"
                    onClick={() => void loadEtfSnapshot(result.stockCode)}
                    disabled={isLoading}
                  >
                    <RefreshCw className="h-3.5 w-3.5" />
                    刷新
                  </Button>
                </div>
              </div>

              {/* Stats row */}
              <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
                <StatCell label="基金规模" value={formatLargeAmountYi(dailyMetrics?.derivedFundSizeYi)} />
                <StatCell label="今日成交" value={formatAmountYi(quote?.amountWan != null ? quote.amountWan / 10000 : null)} />
                <StatCell label="折溢价" value={formatSignedPercent(estimatedIopv?.premiumDiscountPct)} tone={quoteTone(estimatedIopv?.premiumDiscountPct)} />
                <StatCell label="跟踪误差" value={formatSignedPercent(analysis?.biasMa10)} sub="偏离 MA10" />
                <StatCell label="指数 PE" value={formatNumber(quote?.peTtm, 1)} sub={quote?.peTtm != null ? 'PE(TTM)' : undefined} />
              </div>
            </Card>

            {/* ---- K-line chart ---- */}
            <Card padding="lg" className="!rounded-2xl">
              <div className="flex items-center justify-between gap-3">
                <h3 className="text-lg font-semibold text-foreground">近 50 日 K 线 · 含 IOPV 跟踪</h3>
              </div>
              <div className="mt-4">
                <CandlestickChart stockCode={result.stockCode} stockName={result.stockName} bars={50} />
              </div>
            </Card>

            {/* ---- Component stock movement table ---- */}
            {topHoldings.length > 0 ? (
              <Card padding="lg" className="!rounded-2xl">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="text-lg font-semibold text-foreground">成分股异动 · Component Movement</h3>
                  <p className="text-sm text-secondary-text">共 {topHoldings.length} 只 · {topHoldings[0]?.reportPeriod || '最近披露期'}</p>
                </div>
                <div className="mt-4 overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border text-left">
                        <th className="pb-3 pr-4 font-medium text-secondary-text">股票名称</th>
                        <th className="pb-3 pr-4 text-right font-medium text-secondary-text">权重</th>
                        <th className="pb-3 pr-4 font-medium text-secondary-text">占比</th>
                        <th className="pb-3 pr-4 text-right font-medium text-secondary-text">持仓市值</th>
                      </tr>
                    </thead>
                    <tbody>
                      {topHoldings.map((item) => (
                        <tr key={`${item.rank}-${item.stockCode}`} className="border-b border-border/50">
                          <td className="py-3 pr-4">
                            <p className="font-medium text-foreground">{item.stockName || '--'}</p>
                            <p className="text-xs text-secondary-text">{item.stockCode || '--'}</p>
                          </td>
                          <td className="py-3 pr-4 text-right font-medium text-foreground">{formatPercent(item.weightPct)}</td>
                          <td className="py-3 pr-4">
                            <div className="h-1.5 w-full max-w-[120px] rounded-full bg-foreground/10">
                              <div className="h-1.5 rounded-full bg-foreground/60" style={{ width: `${Math.min((item.weightPct ?? 0) * 10, 100)}%` }} />
                            </div>
                          </td>
                          <td className="py-3 text-right text-secondary-text">{formatNumber(item.marketValueWan, 0)} 万</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            ) : null}

            {/* ---- 今日申赎数据 ---- */}
            {dailyMetrics ? (
              <Card padding="lg" className="!rounded-2xl">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="text-lg font-semibold text-foreground">今日申赎数据 · Create / Redeem</h3>
                  <div className="flex items-center gap-2">
                    <Badge variant="default" size="sm">{dailyMetrics.tradeDate || '--'}</Badge>
                    <Button variant="secondary" size="sm" className="rounded-lg" isLoading={dailyMetricsRefreshing} loadingText="刷新中..." onClick={() => void handleDailyMetricsRefresh()}>
                      <RefreshCw className="h-3.5 w-3.5" />
                      刷新日频
                    </Button>
                  </div>
                </div>

                {dailyMetricsMessage ? (
                  <div className="mt-3"><InlineAlert title={dailyMetricsMessageTone === 'success' ? '刷新完成' : '刷新提示'} variant={dailyMetricsMessageTone} message={dailyMetricsMessage} /></div>
                ) : null}

                <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
                  <div className="rounded-xl border border-border bg-elevated/20 px-4 py-3">
                    <p className="text-xs text-secondary-text">基金份额</p>
                    <p className="mt-1 text-xl font-bold text-foreground">
                      {dailyMetrics.fundShares != null
                        ? (Math.abs(dailyMetrics.fundShares) >= 100000000
                          ? `${formatNumber(dailyMetrics.fundShares / 100000000, 2)} 亿份`
                          : `${formatNumber(dailyMetrics.fundShares / 10000, 2)} 万份`)
                        : '--'}
                    </p>
                  </div>
                  <div className="rounded-xl border border-border bg-elevated/20 px-4 py-3">
                    <p className="text-xs text-secondary-text">单位净值</p>
                    <p className="mt-1 text-xl font-bold text-foreground">{formatNumber(dailyMetrics.nav, 4)}</p>
                  </div>
                  <div className="rounded-xl border border-border bg-elevated/20 px-4 py-3">
                    <p className="text-xs text-secondary-text">估算规模</p>
                    <p className="mt-1 text-xl font-bold text-foreground">{formatLargeAmountYi(dailyMetrics.derivedFundSizeYi)}</p>
                  </div>
                </div>

                {/* IOPV section */}
                {estimatedIopv?.value ? (
                  <div className="mt-4 rounded-xl border border-border bg-elevated/10 px-4 py-3">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="text-xs text-secondary-text">Estimated IOPV</p>
                        <p className="mt-1 text-xl font-bold text-foreground">{formatNumber(estimatedIopv.value, 3)}</p>
                      </div>
                      <div className="text-right">
                        <p className="text-xs text-secondary-text">估算折溢价</p>
                        <p className={`mt-1 text-xl font-bold ${quoteTone(estimatedIopv.premiumDiscountPct)}`}>
                          {formatSignedPercent(estimatedIopv.premiumDiscountPct)}
                        </p>
                      </div>
                    </div>
                    <div className="mt-3 grid grid-cols-3 gap-3">
                      <div className="rounded-lg border border-border/50 bg-background/70 px-3 py-2">
                        <p className="text-xs text-secondary-text">覆盖权重</p>
                        <p className="mt-1 text-sm font-semibold text-foreground">{formatPercent(estimatedIopv.coverageWeightPct)}</p>
                      </div>
                      <div className="rounded-lg border border-border/50 bg-background/70 px-3 py-2">
                        <p className="text-xs text-secondary-text">命中持仓</p>
                        <p className="mt-1 text-sm font-semibold text-foreground">{estimatedIopv.matchedHoldingsCount} / {estimatedIopv.totalHoldingsCount}</p>
                      </div>
                      <div className="rounded-lg border border-border/50 bg-background/70 px-3 py-2">
                        <p className="text-xs text-secondary-text">披露期</p>
                        <p className="mt-1 text-sm font-semibold text-foreground">{estimatedIopv.reportPeriod || '--'}</p>
                      </div>
                    </div>
                    <p className="mt-3 text-xs text-secondary-text">{estimatedIopv.note || '这是估算值，不等同于交易所正式 IOPV。'}</p>
                  </div>
                ) : null}
              </Card>
            ) : null}

            {/* ---- Analysis summary ---- */}
            {analysis?.summary ? (
              <Card padding="lg" className="!rounded-2xl">
                <h3 className="text-lg font-semibold text-foreground">ETF 专属结论</h3>
                <p className="mt-3 text-sm leading-7 text-foreground">{analysis.summary}</p>

                {(analysis.selectedReasons?.length ?? 0) > 0 || (analysis.riskReasons?.length ?? 0) > 0 ? (
                  <div className="mt-4 flex flex-wrap gap-2">
                    {analysis.selectedReasons?.map((r) => (
                      <Badge key={r} variant="success" size="sm" className="rounded-full border-0">{r}</Badge>
                    ))}
                    {analysis.riskReasons?.map((r) => (
                      <Badge key={r} variant="warning" size="sm" className="rounded-full border-0">{r}</Badge>
                    ))}
                  </div>
                ) : null}
              </Card>
            ) : null}
          </div>

          {/* ======================== RIGHT COLUMN ======================== */}
          <div className="min-w-0 space-y-5">

            {/* ---- 跟踪指数 ---- */}
            {profile?.trackingTarget ? (
              <Card padding="lg" className="!rounded-2xl">
                <h3 className="text-lg font-semibold text-foreground">跟踪指数 · {profile.trackingTarget}</h3>
                <div className="mt-4 space-y-3">
                  {profile.fundFullName ? (
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm text-secondary-text">基金全称</span>
                      <span className="text-right text-sm text-foreground">{profile.fundFullName}</span>
                    </div>
                  ) : null}
                  {profile.performanceBenchmark ? (
                    <div className="flex items-start justify-between gap-2">
                      <span className="shrink-0 text-sm text-secondary-text">基准</span>
                      <span className="text-right text-sm text-foreground">{profile.performanceBenchmark}</span>
                    </div>
                  ) : null}
                  {profile.investmentObjective ? (
                    <div className="flex items-start justify-between gap-2">
                      <span className="shrink-0 text-sm text-secondary-text">投资目标</span>
                      <span className="text-right text-sm text-foreground">{profile.investmentObjective}</span>
                    </div>
                  ) : null}
                </div>
              </Card>
            ) : null}

            {/* ---- 技术支撑压力 ---- */}
            {analysis ? (
              <Card padding="lg" className="!rounded-2xl">
                <h3 className="text-lg font-semibold text-foreground">支撑 / 压力</h3>
                <div className="mt-4 grid grid-cols-2 gap-3">
                  <div className="rounded-xl border border-border bg-elevated/20 px-3 py-3">
                    <p className="text-xs text-secondary-text">支撑位</p>
                    <p className="mt-1 text-xl font-bold text-foreground">{formatNumber(analysis.support, 3)}</p>
                  </div>
                  <div className="rounded-xl border border-border bg-elevated/20 px-3 py-3">
                    <p className="text-xs text-secondary-text">压力位</p>
                    <p className="mt-1 text-xl font-bold text-foreground">{formatNumber(analysis.pressure, 3)}</p>
                  </div>
                  <div className="rounded-xl border border-border bg-elevated/20 px-3 py-3">
                    <p className="text-xs text-secondary-text">MA10</p>
                    <p className="mt-1 text-xl font-bold text-foreground">{formatNumber(analysis.ma10, 3)}</p>
                  </div>
                  <div className="rounded-xl border border-border bg-elevated/20 px-3 py-3">
                    <p className="text-xs text-secondary-text">偏离 MA10</p>
                    <p className={`mt-1 text-xl font-bold ${quoteTone(analysis.biasMa10)}`}>{formatSignedPercent(analysis.biasMa10)}</p>
                  </div>
                </div>
              </Card>
            ) : null}

            {/* ---- 技术面参考 ---- */}
            {analysis ? (() => {
              const trend = deriveTrendStatus(analysis.ma5, analysis.ma10, analysis.ma20);
              const volume = deriveVolumeSignal(quote?.volumeRatio);
              const premium = derivePremiumSignal(estimatedIopv?.premiumDiscountPct);
              const currentPrice = quote?.price;
              const priceMa10Bias = (currentPrice != null && analysis.ma10 != null && analysis.ma10 > 0)
                ? ((currentPrice - analysis.ma10) / analysis.ma10 * 100) : null;
              return (
                <Card padding="lg" className="!rounded-2xl">
                  <h3 className="text-lg font-semibold text-foreground">技术面参考</h3>
                  <div className="mt-4 space-y-3">
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-sm text-secondary-text">趋势状态</span>
                      <Badge variant={trend.variant} size="sm">{trend.label}</Badge>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-sm text-secondary-text">量能</span>
                      <Badge variant={volume.variant} size="sm">{volume.label}</Badge>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-sm text-secondary-text">折溢价</span>
                      <Badge variant={premium.variant} size="sm">{premium.label}</Badge>
                    </div>
                    {priceMa10Bias != null ? (
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-sm text-secondary-text">偏离 MA10</span>
                        <span className={`text-sm font-medium ${quoteTone(priceMa10Bias)}`}>{formatSignedPercent(priceMa10Bias)}</span>
                      </div>
                    ) : null}
                  </div>
                  {/* MA values */}
                  <div className="mt-4 rounded-xl border border-border bg-elevated/10 px-3 py-2.5">
                    <div className="grid grid-cols-3 gap-2 text-center">
                      <div>
                        <p className="text-xs text-secondary-text">MA5</p>
                        <p className="mt-0.5 text-sm font-semibold text-foreground">{formatNumber(analysis.ma5, 3)}</p>
                      </div>
                      <div>
                        <p className="text-xs text-secondary-text">MA10</p>
                        <p className="mt-0.5 text-sm font-semibold text-foreground">{formatNumber(analysis.ma10, 3)}</p>
                      </div>
                      <div>
                        <p className="text-xs text-secondary-text">MA20</p>
                        <p className="mt-0.5 text-sm font-semibold text-foreground">{formatNumber(analysis.ma20, 3)}</p>
                      </div>
                    </div>
                  </div>
                </Card>
              );
            })() : null}

            {/* ---- 行情数据 ---- */}
            <Card padding="lg" className="!rounded-2xl">
              <h3 className="text-lg font-semibold text-foreground">行情数据</h3>
              <div className="mt-4 space-y-2.5">
                <InfoRow label="换手率" value={formatSignedPercent(quote?.turnoverRate).replace('+', '')} />
                <InfoRow label="量比" value={formatNumber(quote?.volumeRatio, 2)} />
                <InfoRow label="振幅" value={formatSignedPercent(quote?.amplitudePct).replace('+', '')} />
                <InfoRow label="总市值" value={formatLargeAmountYi(quote?.totalMarketValueYi)} />
                <InfoRow label="流通市值" value={formatLargeAmountYi(quote?.floatMarketValueYi)} />
                <InfoRow label="PB" value={formatNumber(quote?.pb, 2)} />
                <InfoRow label="涨停价" value={formatNumber(quote?.limitUp, 3)} tone="text-danger" />
                <InfoRow label="跌停价" value={formatNumber(quote?.limitDown, 3)} tone="text-success" />
                {orderBook ? (
                  <>
                    <InfoRow label="买一 / 卖一" value={`${formatNumber(orderBook.bid1, 3)} / ${formatNumber(orderBook.ask1, 3)}`} />
                  </>
                ) : null}
              </div>
            </Card>

            {/* ---- 最近日线 ---- */}
            {latestBar ? (
              <Card padding="lg" className="!rounded-2xl">
                <h3 className="text-lg font-semibold text-foreground">最近日线</h3>
                <div className="mt-4 space-y-2.5">
                  <InfoRow label="交易日" value={latestBar.datetime} />
                  <InfoRow label="收盘价" value={formatNumber(latestBar.close, 3)} />
                  <InfoRow label="最高" value={formatNumber(latestBar.high, 3)} />
                  <InfoRow label="最低" value={formatNumber(latestBar.low, 3)} />
                </div>
              </Card>
            ) : null}

            {/* ---- Quick actions ---- */}
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => { setHistoryOpen(true); void loadHistory(); }}
                className="flex-1 rounded-xl border border-border bg-card py-2.5 text-center text-sm text-foreground transition-colors hover:bg-elevated"
              >
                <Clock3 className="mr-1.5 inline h-3.5 w-3.5" />
                历史记录
              </button>
              <button
                type="button"
                onClick={() => void loadEtfSnapshot(result.stockCode)}
                disabled={isLoading}
                className="flex-1 rounded-xl border border-border bg-card py-2.5 text-center text-sm text-foreground transition-colors hover:bg-elevated disabled:opacity-50"
              >
                <RefreshCw className="mr-1.5 inline h-3.5 w-3.5" />
                刷新快照
              </button>
            </div>

            {/* ---- Errors ---- */}
            {result.errors.length > 0 ? (
              <InlineAlert title="部分数据降级" variant="warning" message={result.errors.slice(0, 3).join('；')} />
            ) : null}
          </div>
        </div>
      ) : null}

      {/* ---- History Drawer ---- */}
      <Drawer isOpen={historyOpen} onClose={() => setHistoryOpen(false)} title="ETF 查询历史" width="max-w-xl" side="right">
        <div className="space-y-4">
          {historyError ? <ApiErrorAlert error={historyError} /> : null}
          {historyLoading ? <InlineAlert variant="info" title="正在加载" message="正在读取最近的 ETF 查询历史。" /> : null}
          {!historyLoading && historyItems.length === 0 ? (
            <EmptyState title="暂无 ETF 查询历史" description="查过几次 ETF 之后，这里会保留最近快照。" icon={<Clock3 className="h-8 w-8" />} />
          ) : null}
          <div className="space-y-3">
            {historyItems.map((item) => {
              const active = item.queryId === currentHistoryId;
              const restoring = historyRestoreId === item.queryId;
              const historyResult = item.result;
              return (
                <div key={item.queryId} className={`rounded-2xl border px-4 py-4 transition-colors ${active ? 'border-foreground/20 bg-foreground/5' : 'border-border/60 bg-background/70'}`}>
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
                  <p className="mt-2 text-sm text-secondary-text">
                    最新价 {formatNumber(historyResult?.quote?.price, 3)} · {formatSignedPercent(historyResult?.quote?.changePct)}
                  </p>
                  <div className="mt-3 flex justify-end gap-2">
                    <Button variant="ghost" size="sm" disabled={!item.stockCode} onClick={() => { if (item.stockCode) setQuery(item.stockCode); }}>填入代码</Button>
                    <Button variant="outline" size="sm" isLoading={restoring} loadingText="恢复中..." disabled={!item.result} onClick={() => void handleHistoryRestore(item)}>恢复查看</Button>
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

const StatCell: React.FC<{ label: string; value: string; sub?: string; tone?: string }> = ({ label, value, sub, tone }) => (
  <div>
    <p className="text-xs text-secondary-text">{label}</p>
    <p className={`mt-1 text-2xl font-bold ${tone || 'text-foreground'}`}>{value}</p>
    {sub ? <p className="mt-0.5 text-xs text-secondary-text">{sub}</p> : null}
  </div>
);

const InfoRow: React.FC<{ label: string; value: string; tone?: string }> = ({ label, value, tone }) => (
  <div className="flex items-center justify-between gap-3">
    <span className="text-sm text-secondary-text">{label}</span>
    <span className={`text-sm font-medium ${tone || 'text-foreground'}`}>{value}</span>
  </div>
);

export default EtfQueryPage;
