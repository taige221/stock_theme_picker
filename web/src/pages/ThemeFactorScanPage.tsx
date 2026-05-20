import type React from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { ArrowRight, Orbit, Radar, RefreshCw, Sparkles, Workflow } from 'lucide-react';
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

function formatDateTime(value?: string | null): string {
  if (!value) return '暂无时间';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function scanStatusVariant(status: string): 'default' | 'success' | 'warning' | 'info' | 'danger' {
  if (status === 'completed') return 'success';
  if (status === 'failed') return 'danger';
  if (status === 'processing') return 'warning';
  return 'default';
}

function scoreTone(score?: number | null): string {
  const safe = Number(score ?? 0);
  if (safe >= 80) return 'text-success';
  if (safe >= 65) return 'text-cyan';
  if (safe >= 50) return 'text-warning';
  return 'text-secondary-text';
}

function isSyntheticThemeId(value?: string | null): boolean {
  const text = String(value || '').trim();
  return text.startsWith('theme_name_');
}

function normalizeSyncedThemeName(value?: string | null): string {
  const text = String(value || '').trim();
  if (!text) return '';
  if (isSyntheticThemeId(text)) {
    return text.replace(/^theme_name_/, '').trim();
  }
  const prefixedMatch = text.match(/^theme_name\s*=\s*(.+)$/i);
  if (prefixedMatch) {
    return prefixedMatch[1]?.trim() ?? '';
  }
  return text;
}

const RECENT_SCAN_SCROLL_CLASS = 'max-h-[860px] overflow-y-auto pr-1';
const REVIEW_SCROLL_CLASS = 'max-h-[300px] overflow-y-auto pr-1';
const PROMOTED_EVENT_SCROLL_CLASS = 'max-h-[360px] overflow-y-auto pr-1';

const ThemeFactorScanPage: React.FC = () => {
  const navigate = useNavigate();
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

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const handleRunOnce = useCallback(async (): Promise<void> => {
    try {
      setRunning(true);
      setActionError(null);
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

  const selectedEvent = useMemo(
    () => events.find((event) => event.eventId === selectedEventId) ?? null,
    [events, selectedEventId],
  );

  const historyEvent = useMemo(
    () => events.find((event) => event.eventId === historyEventId) ?? null,
    [events, historyEventId],
  );

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
    if (syncedThemeName) {
      params.set('themeName', syncedThemeName);
    }
    const syncedThemeId = String(query?.themeId || scan.themeId || '').trim();
    if (syncedThemeId && !isSyntheticThemeId(syncedThemeId)) {
      params.set('themeId', syncedThemeId);
    }
    if (query?.boardCode) {
      params.set('boardCode', String(query.boardCode).trim());
    }
    if (query?.boardName) {
      params.set('boardName', String(query.boardName).trim());
    }
    if (query?.strategyMode) {
      params.set('strategyMode', String(query.strategyMode).trim());
    }
    if (query?.maxCandidates != null) {
      params.set('maxCandidates', String(query.maxCandidates));
    }
    if (scan.result?.event?.title) {
      params.set('eventTitle', String(scan.result.event.title));
    }
    if (scan.themeFactorScore != null) {
      params.set('themeFactorScore', String(scan.themeFactorScore));
    }
    navigate(`/theme-picker?${params.toString()}`);
  }, [navigate]);

  return (
    <AppPage className="space-y-6 !max-w-[1680px] px-3 md:px-5 lg:px-6">
      <section className="overflow-hidden rounded-[32px] border border-border/60 bg-[radial-gradient(circle_at_top_left,_rgba(16,185,129,0.16),_transparent_30%),radial-gradient(circle_at_bottom_right,_rgba(6,182,212,0.16),_transparent_28%),linear-gradient(180deg,rgba(255,255,255,0.98),rgba(246,249,252,0.96))] shadow-soft-card dark:bg-[radial-gradient(circle_at_top_left,_rgba(16,185,129,0.16),_transparent_30%),radial-gradient(circle_at_bottom_right,_rgba(34,211,238,0.14),_transparent_28%),linear-gradient(180deg,rgba(10,15,26,0.98),rgba(14,20,32,0.96))]">
        <div className="grid gap-6 px-5 py-6 lg:grid-cols-12 lg:px-7 lg:py-7">
          <div className="space-y-5 lg:col-span-7">
            <div className="flex items-center gap-4">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-success/10 text-success shadow-soft-card">
                <Workflow className="h-7 w-7" />
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-secondary-text">Theme Factor Scan</p>
                <h2 className="mt-1 text-3xl font-semibold tracking-tight text-foreground">只让高质量事件继续推动主题筛选</h2>
                <p className="mt-2 max-w-3xl text-sm leading-7 text-secondary-text">
                  这层消费信息观察池里已经过线的事件，再加 ETF 确认、龙头状态和候选股技术面，产出今天最值得继续看的方向。
                </p>
              </div>
            </div>

          </div>

          <Card variant="bordered" padding="lg" className="rounded-[28px] border-border/60 bg-card/90 lg:col-span-5 lg:min-h-[248px]">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-secondary-text">Run Once</p>
                <h3 className="mt-1 text-2xl font-semibold text-foreground">先选事件，再跑主题因子</h3>
              </div>
              <Badge variant="info" className="border-0 px-3 py-1">MVP</Badge>
            </div>
            <div className="mt-5 space-y-4">
              <Select
                label="选择高质量事件"
                value={selectedEventId}
                onChange={setSelectedEventId}
                options={eventOptions}
              />
              <Card variant="bordered" padding="md" className="rounded-[22px] border-border/60 bg-background/75">
                <p className="text-sm font-semibold text-foreground">{selectedEvent?.title ?? '默认使用最新高质量事件'}</p>
                <p className="mt-2 text-sm leading-6 text-secondary-text">
                  {selectedEvent
                    ? `当前事件强度 ${selectedEvent.signalStrength.toFixed(0)}，主题 ${selectedEvent.themes.join(' / ') || '待归类'}。`
                    : '未手动指定事件时，系统会从最新 promoted 事件里挑选高质量输入。'}
                </p>
              </Card>
              <div className="flex flex-wrap gap-3">
                <Button size="lg" isLoading={running} loadingText="正在跑主题因子扫描..." onClick={() => void handleRunOnce()}>
                  立即扫描
                </Button>
                <Button variant="secondary" size="lg" onClick={() => void loadData()} isLoading={loading} loadingText="刷新中...">
                  <RefreshCw className="h-4 w-4" />
                  刷新列表
                </Button>
              </div>
            </div>
          </Card>

          <div className="grid gap-3 sm:grid-cols-3 lg:col-span-12">
              <Card variant="bordered" padding="lg" className="rounded-[24px] border-border/60 bg-card/85">
                <p className="text-xs uppercase tracking-[0.16em] text-secondary-text">已完成扫描</p>
                <p className="mt-3 text-3xl font-semibold text-foreground">{stats.completed}</p>
                <p className="mt-2 text-sm text-secondary-text">
                  {reviewSummary ? `近 ${reviewSummary.days} 天事件转扫描 ${reviewSummary.scanConversionRate.toFixed(0)}%。` : '至少跑通过一次主题确认链路，不再只看原始新闻。'}
                </p>
              </Card>
              <Card variant="bordered" padding="lg" className="rounded-[24px] border-border/60 bg-card/85">
                <p className="text-xs uppercase tracking-[0.16em] text-secondary-text">高分主题</p>
                <p className="mt-3 text-3xl font-semibold text-foreground">{stats.highScore}</p>
                <p className="mt-2 text-sm text-secondary-text">
                  {reviewSummary ? `高分占比 ${reviewSummary.highScoreRate.toFixed(0)}%，更适合继续下钻个股和入场点。` : '主题因子分超过 75，适合继续下钻个股和入场点。'}
                </p>
              </Card>
              <Card variant="bordered" padding="lg" className="rounded-[24px] border-border/60 bg-card/85">
                <p className="text-xs uppercase tracking-[0.16em] text-secondary-text">ETF 已确认</p>
                <p className="mt-3 text-3xl font-semibold text-foreground">{stats.confirmedEtf}</p>
                <p className="mt-2 text-sm text-secondary-text">
                  {reviewSummary ? `确认率 ${reviewSummary.confirmedEtfRate.toFixed(0)}%，说明资金承认度在抬升。` : '说明市场资金已经开始认可这条主线，不只是信息面单独躁动。'}
                </p>
              </Card>
          </div>
        </div>
      </section>

      {error ? <ApiErrorAlert error={error} /> : null}
      {actionError ? <ApiErrorAlert error={actionError} /> : null}
      {runSummary ? (
        <InlineAlert
          variant="success"
          title="本轮主题因子扫描已完成"
          message={`本次消费 ${runSummary.scannedEvents} 条高质量事件，生成 ${runSummary.generatedScans} 条主题因子结果。`}
        />
      ) : null}

      <section className="grid gap-5 xl:grid-cols-12">
        <Card variant="bordered" padding="lg" className="rounded-[28px] xl:col-span-7 xl:min-h-[1040px]">
          <div className="flex items-center justify-between gap-3">
            <div>
              <span className="label-uppercase">Recent Scans</span>
              <h3 className="mt-1 text-2xl font-semibold text-foreground">
                {historyEvent ? '按事件回看的主题因子历史' : '最近主题因子结果'}
              </h3>
            </div>
            <div className="flex items-center gap-3">
              {historyEvent ? (
                <Button variant="secondary" size="sm" onClick={() => setHistoryEventId('')}>
                  查看全部历史
                </Button>
              ) : null}
              <Badge variant="default" className="border-border/60 px-3 py-1">{scans.length} 条</Badge>
            </div>
          </div>

          <div className={`mt-5 space-y-3 ${RECENT_SCAN_SCROLL_CLASS}`}>
            {!loading && scans.length === 0 ? (
              <EmptyState
                title="还没有主题因子扫描结果"
                description="先从高质量事件里跑一次扫描，系统会给出主题分、ETF 确认和候选股。"
                icon={<Orbit className="h-6 w-6" />}
                action={<Button onClick={() => void handleRunOnce()}>开始第一次扫描</Button>}
              />
            ) : null}

            {scans.map((scan) => {
              const event = scan.result?.event;
              const etf = scan.result?.etfConfirmation;
              const stocks = scan.result?.themeScan?.stocks ?? [];
              return (
                <div key={scan.scanId} className="rounded-[22px] border border-border/60 bg-background/72 px-4 py-4">
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant={scanStatusVariant(scan.status)} className="border-0 px-3 py-1">
                          {scan.status}
                        </Badge>
                        <Badge variant="info" className="border-0 px-3 py-1">
                          {scan.themeName}
                        </Badge>
                        {etf?.confirmed ? (
                          <Badge variant="success" className="border-0 px-3 py-1">ETF 已确认</Badge>
                        ) : null}
                      </div>
                      <h4 className="text-lg font-semibold text-foreground">{event?.title ?? '未回填事件标题'}</h4>
                      <p className="mt-2 text-sm leading-6 text-secondary-text">
                        事件源层级 {event?.sourceTier ?? '未知'} · 生成时间 {formatDateTime(scan.createdAt)}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">Theme Factor Score</p>
                      <p className={`mt-2 text-2xl font-semibold ${scoreTone(scan.themeFactorScore)}`}>
                        {Number(scan.themeFactorScore ?? 0).toFixed(0)}
                      </p>
                    </div>
                  </div>

                  <div className="mt-4 grid gap-3 sm:grid-cols-3">
                    <div className="rounded-[18px] border border-border/60 bg-card/70 px-4 py-3">
                      <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">事件分</p>
                      <p className={`mt-2 text-lg font-semibold ${scoreTone(scan.eventScore)}`}>{Number(scan.eventScore ?? 0).toFixed(0)}</p>
                    </div>
                    <div className="rounded-[18px] border border-border/60 bg-card/70 px-4 py-3">
                      <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">ETF 确认</p>
                      <p className={`mt-2 text-lg font-semibold ${scoreTone(scan.etfConfirmationScore)}`}>{Number(scan.etfConfirmationScore ?? 0).toFixed(0)}</p>
                      <p className="mt-1 text-xs text-secondary-text">
                        {etf?.etfName ?? etf?.etfCode ?? '暂无 ETF'}
                        {etf?.confirmedCount ? ` · ${etf.confirmedCount} 只确认` : ''}
                      </p>
                    </div>
                    <div className="rounded-[18px] border border-border/60 bg-card/70 px-4 py-3">
                      <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">龙头确认</p>
                      <p className={`mt-2 text-lg font-semibold ${scoreTone(scan.leaderConfirmationScore)}`}>{Number(scan.leaderConfirmationScore ?? 0).toFixed(0)}</p>
                    </div>
                  </div>

                  <div className="mt-4 grid gap-3 lg:grid-cols-[0.95fr_1.05fr]">
                    {scan.result?.leaderConfirmation?.stockName ? (
                      <div className="rounded-[18px] border border-border/60 bg-card/70 px-4 py-3">
                        <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">龙头确认</p>
                        <p className="mt-2 text-sm font-semibold text-foreground">
                          {scan.result.leaderConfirmation.stockName}
                          {scan.result.leaderConfirmation.stockCode ? ` · ${scan.result.leaderConfirmation.stockCode}` : ''}
                        </p>
                        <p className="mt-1 text-xs text-secondary-text">
                          {scan.result.leaderConfirmation.signalLevel ?? '待确认'} · 趋势 {Number(scan.result.leaderConfirmation.trendScore ?? 0).toFixed(0)}
                        </p>
                      </div>
                    ) : (
                      <div className="rounded-[18px] border border-dashed border-border/60 bg-card/60 px-4 py-3 text-sm text-secondary-text">
                        当前还没有明确龙头确认，说明这条主题更多处在信息先行阶段。
                      </div>
                    )}

                    {scan.result?.roleBreakdown ? (
                      <div className="rounded-[18px] border border-dashed border-border/60 bg-card/60 px-4 py-3">
                        <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">角色分层</p>
                        <div className="mt-2 flex flex-wrap gap-2 text-xs text-secondary-text">
                          <Badge variant="success" className="border-0 px-3 py-1">
                            龙头 {scan.result.roleBreakdown.leader?.stockName ?? '暂无'}
                          </Badge>
                          <Badge variant="info" className="border-0 px-3 py-1">
                            一阶 {scan.result.roleBreakdown.firstOrder?.length ?? 0}
                          </Badge>
                          <Badge variant="default" className="border-border/60 px-3 py-1">
                            二阶 {scan.result.roleBreakdown.secondOrder?.length ?? 0}
                          </Badge>
                          <Badge variant="default" className="border-border/60 px-3 py-1">
                            观察 {scan.result.roleBreakdown.observe?.length ?? 0}
                          </Badge>
                        </div>
                      </div>
                    ) : (
                      <div className="rounded-[18px] border border-dashed border-border/60 bg-card/60 px-4 py-3 text-sm text-secondary-text">
                        当前还没有角色分层结果，说明候选股还不足以区分一阶和二阶受益。
                      </div>
                    )}
                  </div>

                  {stocks.length > 0 ? (
                    <div className="mt-4 space-y-2">
                      {stocks.slice(0, 3).map((stock, index) => (
                        <div
                          key={`${scan.scanId}-${stock.stockCode ?? index}`}
                          className="grid gap-3 rounded-[18px] border border-border/60 bg-card/70 px-4 py-3 md:grid-cols-[1fr_120px_100px] md:items-center"
                        >
                          <div>
                            <p className="text-sm font-semibold text-foreground">
                              {stock.stockName ?? '--'} {stock.stockCode ? `· ${stock.stockCode}` : ''}
                            </p>
                            <p className="mt-1 text-xs text-secondary-text">{stock.selectionReason ?? '等待补充技术理由'}</p>
                          </div>
                          <Badge variant="default" className="w-fit border-border/60 px-3 py-1">
                            {stock.signalLevel ?? '待确认'}
                          </Badge>
                          <div className="text-sm text-secondary-text">
                            {stock.trendScore != null ? `趋势 ${stock.trendScore}` : '暂无趋势分'}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="mt-4 rounded-[18px] border border-dashed border-border/60 bg-card/60 px-4 py-3 text-sm text-secondary-text">
                      本次主题扫描还没有给出明确候选股，可能主题本身未触发或仍在等待更多市场确认。
                    </div>
                  )}

                  <div className="mt-4 flex flex-wrap justify-end gap-2">
                    <Button
                      variant="secondary"
                      size="sm"
                      disabled={scan.status !== 'completed'}
                      onClick={() => handleSyncToThemePicker(scan)}
                    >
                      同步到主题选股
                      <ArrowRight className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        </Card>

        <div className="grid gap-5 xl:col-span-5 xl:auto-rows-auto">
          {reviewSummary ? (
            <Card variant="bordered" padding="lg" className="rounded-[28px] xl:min-h-[360px]">
              <div className="flex items-center gap-3">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-success/10 text-success">
                  <Sparkles className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-secondary-text">Review</p>
                  <h3 className="mt-1 text-2xl font-semibold text-foreground">近 {reviewSummary.days} 天复盘统计</h3>
                </div>
              </div>
              <div className="mt-5 grid gap-3 sm:grid-cols-2">
                <div className="rounded-[18px] border border-border/60 bg-card/70 px-4 py-3">
                  <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">事件总数</p>
                  <p className="mt-2 text-lg font-semibold text-foreground">{reviewSummary.totalEvents}</p>
                  <p className="mt-1 text-xs text-secondary-text">高质量 {reviewSummary.promotedEvents} · promoted {reviewSummary.promotedRate.toFixed(0)}%</p>
                </div>
                <div className="rounded-[18px] border border-border/60 bg-card/70 px-4 py-3">
                  <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">开放发现</p>
                  <p className="mt-2 text-lg font-semibold text-foreground">{reviewSummary.discoveryEvents}</p>
                  <p className="mt-1 text-xs text-secondary-text">说明新主线探索已开始沉淀成结构化事件。</p>
                </div>
              </div>
              <div className={`mt-4 space-y-2 ${REVIEW_SCROLL_CLASS}`}>
                {reviewSummary.eventTypeBreakdown.slice(0, 4).map((item) => (
                  <div key={item.key} className="rounded-[18px] border border-border/60 bg-card/70 px-4 py-3">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm font-semibold text-foreground">{item.label}</p>
                      <p className="text-xs text-secondary-text">
                        事件 {item.eventCount} · 扫描 {item.scanCount} · 高分 {item.highScoreCount}
                      </p>
                    </div>
                    <p className="mt-1 text-xs text-secondary-text">
                      平均事件强度 {item.avgSignalStrength.toFixed(1)} · 平均主题因子分 {item.avgThemeFactorScore.toFixed(1)}
                    </p>
                  </div>
                ))}
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                {reviewSummary.topThemes.slice(0, 5).map((item) => (
                  <Badge key={`theme-${item.label}`} variant="info" className="border-0 px-3 py-1">
                    {item.label} · {item.count}
                  </Badge>
                ))}
                {reviewSummary.topSourceHosts.slice(0, 3).map((item) => (
                  <Badge key={`host-${item.label}`} variant="default" className="border-border/60 px-3 py-1">
                    {item.label} · {item.count}
                  </Badge>
                ))}
              </div>
            </Card>
          ) : null}

          <Card variant="bordered" padding="lg" className="rounded-[28px] xl:min-h-[460px]">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-cyan/10 text-cyan">
                <Radar className="h-5 w-5" />
              </div>
              <div>
                <span className="label-uppercase">Promoted Events</span>
                <h3 className="mt-1 text-2xl font-semibold text-foreground">高质量事件输入</h3>
              </div>
            </div>
            <div className={`mt-5 space-y-3 ${PROMOTED_EVENT_SCROLL_CLASS}`}>
              {events.length === 0 ? (
                <EmptyState
                  title="还没有 promoted 事件"
                  description="先去信息观察池跑一轮，把高价值产业事件筛出来。"
                  action={(
                    <Link to="/information-watch">
                      <Button>进入信息观察池</Button>
                    </Link>
                  )}
                />
              ) : (
                events.slice(0, 6).map((event) => (
                  <div key={event.eventId} className="rounded-[22px] border border-border/60 bg-background/72 px-4 py-4">
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-semibold text-foreground">{event.title}</p>
                        <p className="mt-1 text-xs text-secondary-text">
                          {event.themes.join(' / ') || '待归类'} · {formatDateTime(event.publishedAt)}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant="success" className="border-0 px-3 py-1">{event.signalStrength.toFixed(0)}</Badge>
                        <Button
                          variant={historyEventId === event.eventId ? 'secondary' : 'ghost'}
                          size="sm"
                          onClick={() => setHistoryEventId(event.eventId)}
                        >
                          回看历史
                        </Button>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </Card>

          <Card variant="bordered" padding="lg" className="rounded-[28px] xl:min-h-[200px]">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-purple/10 text-purple">
                <Sparkles className="h-5 w-5" />
              </div>
              <div>
                <span className="label-uppercase">Next Step</span>
                <h3 className="mt-1 text-2xl font-semibold text-foreground">继续下钻主题与个股</h3>
              </div>
            </div>
            <div className="mt-5 space-y-3 text-sm leading-7 text-secondary-text">
              <div className="rounded-[22px] border border-border/60 bg-background/72 px-4 py-4">
                主题因子分高，不代表立刻买入；下一步应该回到主题页和单股页，确认二阶标的位置、节奏和风险。
              </div>
              <div className="rounded-[22px] border border-border/60 bg-background/72 px-4 py-4">
                ETF 已确认时，更适合去看龙头和二阶票有没有“回踩不破”“趋势跟随”这类舒服入场点。
              </div>
              <Link to="/theme-picker" className="block">
                <Button variant="secondary" className="w-full rounded-2xl justify-between">
                  去主题选股继续看候选
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </Link>
            </div>
          </Card>
        </div>
      </section>
    </AppPage>
  );
};

export default ThemeFactorScanPage;
