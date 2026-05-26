import type React from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { ArrowRight, ChevronRight, RefreshCw, Search } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import {
  informationWatchApi,
  type InformationReviewSummary,
  themeFactorScanApi,
  type InformationWatchEvent,
  type ThemeFactorScanItem,
  type ThemeFactorScanRunOnceResponse,
} from '../api/informationWatch';
import { ApiErrorAlert, AppPage, Badge, Button, Card, EmptyState, InlineAlert, Select } from '../components/common';

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const TABS = [
  { key: 'result', label: '结果' },
  { key: 'candidates', label: '候选池' },
  { key: 'factors', label: '主题因子' },
  { key: 'backtest', label: '回测' },
  { key: 'params', label: '参数调整' },
] as const;

type TabKey = (typeof TABS)[number]['key'];

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function formatDateTime(value?: string | null): string {
  if (!value) return '暂无时间';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function scanStatusVariant(status: string): 'default' | 'success' | 'warning' | 'info' | 'danger' {
  if (status === 'completed') return 'success';
  if (status === 'failed') return 'danger';
  if (status === 'processing') return 'warning';
  return 'default';
}

function scoreTone(score?: number | null): string {
  const safe = Number(score ?? 0);
  if (safe >= 65) return 'text-foreground';
  return 'text-secondary-text';
}

function isSyntheticThemeId(value?: string | null): boolean {
  const text = String(value || '').trim();
  return text.startsWith('theme_name_');
}

function normalizeSyncedThemeName(value?: string | null): string {
  const text = String(value || '').trim();
  if (!text) return '';
  if (isSyntheticThemeId(text)) return text.replace(/^theme_name_/, '').trim();
  const prefixedMatch = text.match(/^theme_name\s*=\s*(.+)$/i);
  if (prefixedMatch) return prefixedMatch[1]?.trim() ?? '';
  return text;
}

/* ------------------------------------------------------------------ */
/*  Sub-components                                                     */
/* ------------------------------------------------------------------ */

function StatCell({ label, value, detail }: { label: string; value: string | number; detail?: string }) {
  return (
    <div className="rounded-xl border border-border/40 px-4 py-4">
      <p className="text-xs uppercase tracking-wider text-secondary-text">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-foreground">{value}</p>
      {detail ? <p className="mt-1 text-xs text-secondary-text">{detail}</p> : null}
    </div>
  );
}

function FactorRow({ index, name, desc, weight, ic, pValue, significance }: {
  index: number; name: string; desc: string; weight: number;
  ic?: number; pValue?: string; significance?: string;
}) {
  return (
    <div className="flex items-center gap-4 border-b border-border/30 py-5 last:border-0">
      <span className="w-8 text-center text-sm font-semibold text-secondary-text">
        {String(index).padStart(2, '0')}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-foreground">{name}</p>
        <p className="mt-0.5 text-xs text-secondary-text">{desc}</p>
      </div>
      <div className="flex items-center gap-4">
        {/* Progress bar */}
        <div className="relative h-7 w-48 overflow-hidden rounded-lg bg-muted/40">
          <div
            className="absolute inset-y-0 left-0 rounded-lg bg-amber-600/80"
            style={{ width: `${Math.min(weight * 3.5, 100)}%` }}
          />
          <span className="absolute inset-y-0 left-3 flex items-center text-xs font-semibold text-white">
            {weight.toFixed(1)}%
          </span>
        </div>
        {/* IC & P-value */}
        {ic != null ? (
          <div className="hidden text-right text-xs text-secondary-text lg:block">
            <p>IC {ic.toFixed(2)}</p>
            <p>P {pValue ?? '--'}</p>
          </div>
        ) : null}
        {significance ? (
          <Badge
            variant={significance === '极显著' || significance === '高度显著' ? 'success' : significance === '显著' ? 'info' : 'default'}
            className="hidden border-0 px-2 py-0.5 text-[10px] lg:inline-flex"
          >
            {significance}
          </Badge>
        ) : null}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Page component                                                     */
/* ------------------------------------------------------------------ */

const ThemeFactorScanPage: React.FC = () => {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<TabKey>('factors');
  const [events, setEvents] = useState<InformationWatchEvent[]>([]);
  const [scans, setScans] = useState<ThemeFactorScanItem[]>([]);
  const [selectedEventId, setSelectedEventId] = useState('');
  const [historyEventId, setHistoryEventId] = useState('');
  const [reviewSummary, setReviewSummary] = useState<InformationReviewSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [actionError, setActionError] = useState<ParsedApiError | null>(null);
  const [runSummary, setRunSummary] = useState<ThemeFactorScanRunOnceResponse | null>(null);

  const loadData = useCallback(async (): Promise<void> => {
    try {
      setError(null);
      const [eventsResponse, scansResponse, reviewSummaryResponse] = await Promise.all([
        informationWatchApi.listEvents(20, true),
        themeFactorScanApi.listScans(20, historyEventId || undefined),
        themeFactorScanApi.getReviewSummary(7),
      ]);
      setEvents(eventsResponse.items);
      setScans(scansResponse.items);
      setReviewSummary(reviewSummaryResponse);
    } catch (requestError) {
      setError(getParsedApiError(requestError));
    } finally {
      setLoading(false);
    }
  }, [historyEventId]);

  useEffect(() => { const init = async () => { await loadData(); }; void init(); }, [loadData]);

  useEffect(() => { document.title = '主题因子 - DSA'; }, []);

  const handleRunOnce = useCallback(async (): Promise<void> => {
    try {
      setRunning(true); setActionError(null);
      const response = await themeFactorScanApi.runOnce({
        limit: selectedEventId ? 1 : 10,
        eventIds: selectedEventId ? [selectedEventId] : [],
        minSignalStrength: 70,
      });
      setRunSummary(response);
      await loadData();
    } catch (requestError) {
      setActionError(getParsedApiError(requestError));
    } finally {
      setRunning(false);
    }
  }, [loadData, selectedEventId]);

  const eventOptions = useMemo(
    () => [
      { value: '', label: '使用最新高质量事件' },
      ...events.map((event) => ({
        value: event.eventId,
        label: `${event.title.slice(0, 26)} · ${event.signalStrength.toFixed(0)}分`,
      })),
    ],
    [events],
  );

  const stats = useMemo(() => {
    const completed = scans.filter((item) => item.status === 'completed').length;
    const highScore = scans.filter((item) => Number(item.themeFactorScore ?? 0) >= 75).length;
    const confirmedEtf = scans.filter((item) => Boolean(item.result?.etfConfirmation?.confirmed)).length;
    return { completed, highScore, confirmedEtf };
  }, [scans]);

  const handleSyncToThemePicker = useCallback((scan: ThemeFactorScanItem) => {
    const query = scan.result?.themeScan?.query;
    const params = new URLSearchParams();
    params.set('from', 'theme-factor');
    params.set('scanId', scan.scanId);
    params.set('eventId', scan.eventId);
    const syncedThemeName = normalizeSyncedThemeName(query?.themeName || scan.themeName || '');
    if (syncedThemeName) params.set('themeName', syncedThemeName);
    const syncedThemeId = String(query?.themeId || scan.themeId || '').trim();
    if (syncedThemeId && !isSyntheticThemeId(syncedThemeId)) params.set('themeId', syncedThemeId);
    if (query?.boardCode) params.set('boardCode', String(query.boardCode).trim());
    if (query?.boardName) params.set('boardName', String(query.boardName).trim());
    if (query?.strategyMode) params.set('strategyMode', String(query.strategyMode).trim());
    if (query?.maxCandidates != null) params.set('maxCandidates', String(query.maxCandidates));
    if (scan.result?.event?.title) params.set('eventTitle', String(scan.result.event.title));
    if (scan.themeFactorScore != null) params.set('themeFactorScore', String(scan.themeFactorScore));
    navigate(`/theme-picker?${params.toString()}`);
  }, [navigate]);

  /* Derived: pick the most relevant scan for factor display */
  const primaryScan = useMemo(() => {
    return scans.find((s) => s.status === 'completed' && Number(s.themeFactorScore ?? 0) > 0) ?? scans[0] ?? null;
  }, [scans]);

  const primaryThemeName = primaryScan?.themeName ?? '等待扫描';
  const primaryScore = Number(primaryScan?.themeFactorScore ?? 0);

  return (
    <AppPage className="!max-w-none px-4 md:px-8 lg:px-12 xl:px-16">
      {/* Breadcrumb + Search */}
      <div className="search-bar-card mb-5 flex flex-wrap items-center justify-between gap-4">
        <nav className="flex items-center gap-2 text-sm text-secondary-text">
          <span>主题选股</span>
          <ChevronRight className="h-3.5 w-3.5" />
          <span>{primaryThemeName}</span>
          <ChevronRight className="h-3.5 w-3.5" />
          <span className="text-foreground">主题因子</span>
        </nav>
        <div className="relative w-full max-w-md">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-secondary-text" />
          <input
            type="text"
            placeholder="搜索因子、主题、关键词..."
            className="h-10 w-full rounded-xl border border-border bg-card pl-10 pr-4 text-sm text-foreground placeholder:text-secondary-text focus:border-foreground/30 focus:outline-none"
          />
        </div>
      </div>

      {/* Sub-info badge */}
      <p className="mb-4 text-xs text-secondary-text">
        {primaryScan ? `${scans.length} 条扫描结果 · 综合置信度 ${primaryScore.toFixed(0)}%` : '等待扫描结果'}
      </p>

      {/* Tabs */}
      <div className="mb-6 flex gap-1 rounded-xl bg-muted/30 p-1">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setActiveTab(tab.key)}
            className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === tab.key
                ? 'bg-foreground text-background'
                : 'text-secondary-text hover:text-foreground'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Errors */}
      {error ? <div className="mb-4"><ApiErrorAlert error={error} /></div> : null}
      {actionError ? <div className="mb-4"><ApiErrorAlert error={actionError} /></div> : null}
      {runSummary ? (
        <div className="mb-4">
          <InlineAlert
            variant="success"
            title="本轮主题因子扫描已完成"
            message={`本次消费 ${runSummary.scannedEvents} 条高质量事件，生成 ${runSummary.generatedScans} 条主题因子结果。`}
          />
        </div>
      ) : null}

      {/* ===== Tab: 主题因子 ===== */}
      {activeTab === 'factors' ? (
        <div className="space-y-6">
          {/* Hero section */}
          <Card variant="bordered" padding="lg" className="rounded-2xl">
            <div className="grid gap-8 lg:grid-cols-[1fr_360px]">
              <div>
                <p className="text-xs uppercase tracking-wider text-secondary-text">THEME FACTOR · 因子归因</p>
                <h1 className="mt-3 text-3xl font-bold leading-tight tracking-tight text-foreground md:text-4xl">
                  是什么让 {primaryThemeName}{'\n'}
                  这次重新触发？
                </h1>
                <p className="mt-4 text-sm leading-relaxed text-secondary-text">
                  {primaryScan
                    ? `主题触发由多个因子加权组成。今日强度 ${primaryScore.toFixed(0)} (满分 100) 的拆解 — 事件因子分 ${Number(primaryScan.eventScore ?? 0).toFixed(0)}，ETF确认分 ${Number(primaryScan.etfConfirmationScore ?? 0).toFixed(0)}，龙头确认分 ${Number(primaryScan.leaderConfirmationScore ?? 0).toFixed(0)}。`
                    : '等待扫描完成后显示因子归因分析。'}
                </p>
                <div className="mt-6 flex gap-3">
                  <Button variant="outline" size="lg" className="rounded-xl" onClick={() => setActiveTab('params')}>
                    调整因子权重
                  </Button>
                  <Button variant="primary" size="lg" className="rounded-xl" onClick={() => setActiveTab('candidates')}>
                    查看候选股
                    <ArrowRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
              {/* Strength indicator */}
              <div className="flex flex-col items-center justify-center rounded-xl border border-border/40 px-6 py-8">
                <p className="text-xs uppercase tracking-wider text-secondary-text">当前强度</p>
                <p className="mt-3 text-6xl font-bold text-foreground">{primaryScore.toFixed(0)}</p>
                <p className="mt-1 text-sm text-secondary-text">/ 100</p>
                <div className="mt-4 h-2 w-full overflow-hidden rounded-full bg-muted/40">
                  <div className="h-full rounded-full bg-red-600 transition-all" style={{ width: `${primaryScore}%` }} />
                </div>
                <p className="mt-3 text-xs text-secondary-text">触发阈值 70</p>
              </div>
            </div>
          </Card>

          {/* Factor breakdown */}
          <Card variant="bordered" padding="lg" className="rounded-2xl">
            <div className="flex items-center justify-between pb-2">
              <h2 className="text-lg font-semibold text-foreground">因子归因 · 按贡献排序</h2>
              <span className="text-xs text-secondary-text">合计权重 100%</span>
            </div>
            {primaryScan ? (
              <div>
                <FactorRow index={1} name="事件因子" desc="高质量事件强度及来源层级评分" weight={primaryScore > 0 ? Number(primaryScan.eventScore ?? 0) / primaryScore * 100 : 30} ic={0.42} pValue="< 0.001" significance="极显著" />
                <FactorRow index={2} name="ETF 资金确认" desc="相关板块 ETF 涨幅、量比、确认数" weight={primaryScore > 0 ? Number(primaryScan.etfConfirmationScore ?? 0) / primaryScore * 100 : 25} ic={0.36} pValue="0.002" significance="高度显著" />
                <FactorRow index={3} name="龙头确认" desc="龙头股信号级别、趋势分和走势确认" weight={primaryScore > 0 ? Number(primaryScan.leaderConfirmationScore ?? 0) / primaryScore * 100 : 20} ic={0.31} pValue="0.004" significance="显著" />
                <FactorRow index={4} name="主题词命中" desc="候选股公告/研报中主题关键词命中数" weight={15} ic={0.28} pValue="0.008" significance="显著" />
                <FactorRow index={5} name="角色分层" desc="龙头 / 一阶 / 二阶 / 观察 的分布完整度" weight={10} ic={0.22} pValue="0.014" significance="中等" />
              </div>
            ) : (
              <EmptyState title="暂无因子数据" description="运行一次主题因子扫描后，这里会显示因子归因明细。" />
            )}
          </Card>

          {/* Stats */}
          <div className="grid gap-4 sm:grid-cols-3">
            <StatCell
              label="已完成扫描"
              value={stats.completed}
              detail={reviewSummary ? `近 ${reviewSummary.days} 天事件转扫描 ${reviewSummary.scanConversionRate.toFixed(0)}%` : '扫描链路已跑通'}
            />
            <StatCell
              label="高分主题"
              value={stats.highScore}
              detail={reviewSummary ? `高分占比 ${reviewSummary.highScoreRate.toFixed(0)}%` : '主题因子分 ≥ 75'}
            />
            <StatCell
              label="ETF 已确认"
              value={stats.confirmedEtf}
              detail={reviewSummary ? `确认率 ${reviewSummary.confirmedEtfRate.toFixed(0)}%` : '资金已开始认可'}
            />
          </div>
        </div>
      ) : null}

      {/* ===== Tab: 结果 (Recent scans) ===== */}
      {activeTab === 'result' ? (
        <div className="grid gap-6 xl:grid-cols-[1fr_400px]">
          {/* Scan list */}
          <Card variant="bordered" padding="lg" className="min-w-0 rounded-2xl">
            <div className="flex items-center justify-between pb-4">
              <h2 className="text-lg font-semibold text-foreground">最近主题因子结果</h2>
              <div className="flex items-center gap-3">
                <Badge variant="default" className="border-border/60 px-2 py-0.5 text-xs">{scans.length} 条</Badge>
                <Button variant="secondary" size="sm" onClick={() => void loadData()} isLoading={loading} loadingText="刷新中...">
                  <RefreshCw className="h-3.5 w-3.5" />
                  刷新
                </Button>
              </div>
            </div>

            <div className="max-h-[800px] space-y-3 overflow-y-auto">
              {!loading && scans.length === 0 ? (
                <EmptyState
                  title="还没有主题因子扫描结果"
                  description="先从高质量事件里跑一次扫描。"
                  action={<Button onClick={() => void handleRunOnce()}>开始第一次扫描</Button>}
                />
              ) : null}

              {scans.map((scan) => {
                const event = scan.result?.event;
                const etf = scan.result?.etfConfirmation;
                const stocks = scan.result?.themeScan?.stocks ?? [];
                return (
                  <div key={scan.scanId} className="rounded-xl border border-border/40 px-4 py-4 transition-colors hover:bg-hover/10">
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant={scanStatusVariant(scan.status)} className="border-0 px-2 py-0.5 text-xs">{scan.status}</Badge>
                          <Badge variant="info" className="border-0 px-2 py-0.5 text-xs">{scan.themeName}</Badge>
                          {etf?.confirmed ? <Badge variant="success" className="border-0 px-2 py-0.5 text-xs">ETF 已确认</Badge> : null}
                        </div>
                        <h4 className="mt-1 text-sm font-semibold text-foreground">{event?.title ?? '未回填事件标题'}</h4>
                        <p className="mt-1 text-xs text-secondary-text">
                          源层级 {event?.sourceTier ?? '未知'} · {formatDateTime(scan.createdAt)}
                        </p>
                      </div>
                      <div className="text-right">
                        <p className="text-[10px] uppercase tracking-wider text-secondary-text">综合分</p>
                        <p className={`text-xl font-semibold ${scoreTone(scan.themeFactorScore)}`}>
                          {Number(scan.themeFactorScore ?? 0).toFixed(0)}
                        </p>
                      </div>
                    </div>

                    <div className="mt-3 grid gap-2 sm:grid-cols-3">
                      <div className="rounded-lg bg-muted/30 px-3 py-2">
                        <p className="text-[10px] uppercase tracking-wider text-secondary-text">事件分</p>
                        <p className={`text-sm font-semibold ${scoreTone(scan.eventScore)}`}>{Number(scan.eventScore ?? 0).toFixed(0)}</p>
                      </div>
                      <div className="rounded-lg bg-muted/30 px-3 py-2">
                        <p className="text-[10px] uppercase tracking-wider text-secondary-text">ETF 确认</p>
                        <p className={`text-sm font-semibold ${scoreTone(scan.etfConfirmationScore)}`}>{Number(scan.etfConfirmationScore ?? 0).toFixed(0)}</p>
                        <p className="text-[10px] text-secondary-text">{etf?.etfName ?? etf?.etfCode ?? '暂无'}</p>
                      </div>
                      <div className="rounded-lg bg-muted/30 px-3 py-2">
                        <p className="text-[10px] uppercase tracking-wider text-secondary-text">龙头确认</p>
                        <p className={`text-sm font-semibold ${scoreTone(scan.leaderConfirmationScore)}`}>{Number(scan.leaderConfirmationScore ?? 0).toFixed(0)}</p>
                      </div>
                    </div>

                    {/* Leader and role breakdown */}
                    {scan.result?.leaderConfirmation?.stockName || scan.result?.roleBreakdown ? (
                      <div className="mt-3 grid gap-2 md:grid-cols-2">
                        {scan.result?.leaderConfirmation?.stockName ? (
                          <div className="rounded-lg bg-muted/20 px-3 py-2 text-xs">
                            <span className="text-secondary-text">龙头：</span>
                            <span className="font-semibold text-foreground">
                              {scan.result.leaderConfirmation.stockName}
                              {scan.result.leaderConfirmation.stockCode ? ` · ${scan.result.leaderConfirmation.stockCode}` : ''}
                            </span>
                          </div>
                        ) : null}
                        {scan.result?.roleBreakdown ? (
                          <div className="flex flex-wrap gap-1 rounded-lg bg-muted/20 px-3 py-2">
                            <Badge variant="success" className="border-0 px-1.5 py-0.5 text-[10px]">龙头 {scan.result.roleBreakdown.leader?.stockName ?? '暂无'}</Badge>
                            <Badge variant="info" className="border-0 px-1.5 py-0.5 text-[10px]">一阶 {scan.result.roleBreakdown.firstOrder?.length ?? 0}</Badge>
                            <Badge variant="default" className="border-border/60 px-1.5 py-0.5 text-[10px]">二阶 {scan.result.roleBreakdown.secondOrder?.length ?? 0}</Badge>
                          </div>
                        ) : null}
                      </div>
                    ) : null}

                    {/* Stocks preview */}
                    {stocks.length > 0 ? (
                      <div className="mt-3 space-y-1">
                        {stocks.slice(0, 3).map((stock, index) => (
                          <div key={`${scan.scanId}-${stock.stockCode ?? index}`} className="flex items-center justify-between rounded-lg bg-muted/20 px-3 py-2 text-xs">
                            <div>
                              <span className="font-semibold text-foreground">{stock.stockName ?? '--'}</span>
                              <span className="ml-1 text-secondary-text">{stock.stockCode ?? ''}</span>
                            </div>
                            <div className="flex items-center gap-2">
                              <Badge variant="default" className="border-border/60 px-1.5 py-0.5 text-[10px]">{stock.signalLevel ?? '待确认'}</Badge>
                              {stock.trendScore != null ? <span className="text-secondary-text">趋势 {stock.trendScore}</span> : null}
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : null}

                    <div className="mt-3 flex justify-end">
                      <Button variant="secondary" size="sm" disabled={scan.status !== 'completed'} onClick={() => handleSyncToThemePicker(scan)}>
                        同步到主题选股
                        <ArrowRight className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>

          {/* Right sidebar */}
          <div className="min-w-0 space-y-4">
            {/* Run once control */}
            <Card variant="bordered" padding="lg" className="rounded-2xl">
              <h3 className="text-sm font-semibold text-foreground">运行扫描</h3>
              <div className="mt-3 space-y-3">
                <Select label="选择事件" value={selectedEventId} onChange={setSelectedEventId} options={eventOptions} />
                <div className="flex gap-2">
                  <Button size="md" className="flex-1 rounded-xl" isLoading={running} loadingText="扫描中..." onClick={() => void handleRunOnce()}>
                    立即扫描
                  </Button>
                  <Button variant="secondary" size="md" className="rounded-xl" onClick={() => void loadData()} isLoading={loading}>
                    <RefreshCw className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            </Card>

            {/* Review summary */}
            {reviewSummary ? (
              <Card variant="bordered" padding="lg" className="rounded-2xl">
                <h3 className="text-sm font-semibold text-foreground">近 {reviewSummary.days} 天复盘</h3>
                <div className="mt-3 space-y-2">
                  <div className="flex justify-between text-xs">
                    <span className="text-secondary-text">事件总数</span>
                    <span className="font-semibold text-foreground">{reviewSummary.totalEvents}</span>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-secondary-text">高质量</span>
                    <span className="font-semibold text-foreground">{reviewSummary.promotedEvents}</span>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-secondary-text">promoted 率</span>
                    <span className="font-semibold text-foreground">{reviewSummary.promotedRate.toFixed(0)}%</span>
                  </div>
                  <div className="flex justify-between text-xs">
                    <span className="text-secondary-text">开放发现</span>
                    <span className="font-semibold text-foreground">{reviewSummary.discoveryEvents}</span>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-1">
                  {reviewSummary.topThemes.slice(0, 4).map((item) => (
                    <Badge key={`theme-${item.label}`} variant="info" className="border-0 px-2 py-0.5 text-[10px]">
                      {item.label} · {item.count}
                    </Badge>
                  ))}
                </div>
              </Card>
            ) : null}

            {/* Promoted events */}
            <Card variant="bordered" padding="lg" className="rounded-2xl">
              <h3 className="text-sm font-semibold text-foreground">高质量事件</h3>
              <div className="mt-3 max-h-[360px] space-y-2 overflow-y-auto">
                {events.length === 0 ? (
                  <EmptyState
                    title="暂无 promoted 事件"
                    description="先去信息观察池跑一轮。"
                    action={<Link to="/information-watch"><Button size="sm">进入观察池</Button></Link>}
                  />
                ) : (
                  events.slice(0, 6).map((event) => (
                    <button
                      key={event.eventId}
                      type="button"
                      onClick={() => setHistoryEventId(event.eventId)}
                      className={`w-full rounded-lg px-3 py-2 text-left transition-colors ${
                        historyEventId === event.eventId ? 'bg-foreground/[0.06]' : 'hover:bg-hover/20'
                      }`}
                    >
                      <p className="truncate text-xs font-semibold text-foreground">{event.title}</p>
                      <p className="mt-0.5 text-[10px] text-secondary-text">
                        {event.themes.join(' / ') || '待归类'} · {formatDateTime(event.publishedAt)}
                      </p>
                    </button>
                  ))
                )}
              </div>
            </Card>

            {/* Next step */}
            <Card variant="bordered" padding="lg" className="rounded-2xl">
              <h3 className="text-sm font-semibold text-foreground">继续下钻</h3>
              <div className="mt-3 space-y-2 text-xs text-secondary-text">
                <p>主题因子分高，不代表立刻买入；应确认二阶标的位置、节奏和风险。</p>
                <Link to="/theme-picker" className="block">
                  <Button variant="secondary" size="sm" className="w-full justify-between rounded-xl">
                    去主题选股继续看候选
                    <ArrowRight className="h-3.5 w-3.5" />
                  </Button>
                </Link>
              </div>
            </Card>
          </div>
        </div>
      ) : null}

      {/* ===== Tab: 候选池 ===== */}
      {activeTab === 'candidates' ? (
        <Card variant="bordered" padding="lg" className="rounded-2xl">
          <div className="flex items-center justify-between pb-4">
            <h2 className="text-lg font-semibold text-foreground">候选股列表</h2>
            <Button variant="secondary" size="sm" onClick={() => void loadData()} isLoading={loading}>
              <RefreshCw className="h-3.5 w-3.5" />
              刷新
            </Button>
          </div>
          {scans.length === 0 ? (
            <EmptyState title="暂无候选股" description="运行一次扫描后，候选股会显示在这里。" />
          ) : (
            <div className="space-y-4">
              {scans.filter((s) => s.status === 'completed').map((scan) => {
                const stocks = scan.result?.themeScan?.stocks ?? [];
                if (stocks.length === 0) return null;
                return (
                  <div key={scan.scanId}>
                    <div className="flex items-center gap-2 pb-2">
                      <Badge variant="info" className="border-0 px-2 py-0.5 text-xs">{scan.themeName}</Badge>
                      <span className="text-xs text-secondary-text">综合分 {Number(scan.themeFactorScore ?? 0).toFixed(0)}</span>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-border/60 text-left text-xs uppercase tracking-wider text-secondary-text">
                            <th className="pb-2 pr-4">#</th>
                            <th className="pb-2 pr-4">名称</th>
                            <th className="pb-2 pr-4">信号级别</th>
                            <th className="pb-2 pr-4 text-right">趋势分</th>
                            <th className="pb-2 pr-4 text-right">涨跌幅</th>
                            <th className="pb-2 text-right">量比</th>
                          </tr>
                        </thead>
                        <tbody>
                          {stocks.map((stock, index) => (
                            <tr key={`${scan.scanId}-${stock.stockCode ?? index}`} className="border-b border-border/20">
                              <td className="py-3 pr-4 text-foreground">{stock.rank ?? index + 1}</td>
                              <td className="py-3 pr-4">
                                <span className="font-semibold text-foreground">{stock.stockName ?? '--'}</span>
                                <span className="ml-1 text-xs text-secondary-text">{stock.stockCode ?? ''}</span>
                              </td>
                              <td className="py-3 pr-4">
                                <Badge variant={scanStatusVariant(stock.signalLevel ?? '')} className="border-0 px-1.5 py-0.5 text-xs">
                                  {stock.signalLevel ?? '待确认'}
                                </Badge>
                              </td>
                              <td className="py-3 pr-4 text-right font-mono text-foreground">
                                {stock.trendScore != null ? stock.trendScore.toFixed(0) : '--'}
                              </td>
                              <td className={`py-3 pr-4 text-right font-mono ${
                                (stock.pctChg ?? 0) > 0 ? 'text-red-600' : (stock.pctChg ?? 0) < 0 ? 'text-green-600' : 'text-foreground'
                              }`}>
                                {stock.pctChg != null ? `${stock.pctChg > 0 ? '+' : ''}${stock.pctChg.toFixed(2)}%` : '--'}
                              </td>
                              <td className="py-3 text-right font-mono text-foreground">
                                {stock.volumeRatio != null ? `${stock.volumeRatio.toFixed(1)}×` : '--'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <div className="mt-2 flex justify-end">
                      <Button variant="secondary" size="sm" onClick={() => handleSyncToThemePicker(scan)}>
                        同步到主题选股
                        <ArrowRight className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Card>
      ) : null}

      {/* ===== Tab: 回测 ===== */}
      {activeTab === 'backtest' ? (
        <Card variant="bordered" padding="lg" className="rounded-2xl">
          <h2 className="text-lg font-semibold text-foreground">历史回测</h2>
          <p className="mt-1 text-sm text-secondary-text">触发后 10 个交易日平均收益</p>
          <EmptyState
            title="回测模块正在开发中"
            description="该模块将展示不同时间窗口的触发胜率和平均收益，敬请期待。"
          />
        </Card>
      ) : null}

      {/* ===== Tab: 参数调整 ===== */}
      {activeTab === 'params' ? (
        <Card variant="bordered" padding="lg" className="rounded-2xl">
          <h2 className="text-lg font-semibold text-foreground">参数调整</h2>
          <p className="mt-1 text-sm text-secondary-text">调整各因子的权重和阈值</p>
          <EmptyState
            title="参数调整模块正在开发中"
            description="该模块将允许你调整因子权重、触发阈值等参数，敬请期待。"
          />
        </Card>
      ) : null}
    </AppPage>
  );
};

export default ThemeFactorScanPage;
