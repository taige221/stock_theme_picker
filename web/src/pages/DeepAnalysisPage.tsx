import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  ArrowRight,
  BrainCircuit,
  Clock3,
  Database,
  History,
  Radar,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  Target,
} from 'lucide-react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { createParsedApiError, getParsedApiError, type ParsedApiError } from '../api/error';
import {
  stockQueryApi,
  type StockAlertRuleItem,
  type StockQueryContextSupplement,
  type StockDeepAnalysisItem,
  type StockDeepAnalysisMessage,
} from '../api/stockQuery';
import { ApiErrorAlert, AppPage, Badge, Button, Card, Drawer, EmptyState, InlineAlert, Input } from '../components/common';

const MIN_ALERT_SCAN_INTERVAL_MINUTES = 5;

function formatNumber(value?: number | null, digits = 2): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '--';
  return value.toFixed(digits);
}

function formatTime(value?: string | null): string {
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

function actionLabel(value?: string | null): string {
  if (value === 'wait_retest') return '等待回踩';
  if (value === 'trial_buy') return '可试仓';
  if (value === 'breakout_confirm') return '突破确认';
  if (value === 'avoid') return '放弃观察';
  if (value === 'observe') return '继续观察';
  return value || '待生成';
}

function actionVariant(value?: string | null): 'success' | 'warning' | 'danger' | 'info' | 'default' {
  if (value === 'trial_buy') return 'success';
  if (value === 'breakout_confirm') return 'warning';
  if (value === 'avoid') return 'danger';
  if (value === 'wait_retest' || value === 'observe') return 'info';
  return 'default';
}

function analysisStatusLabel(value?: string | null): string {
  if (value === 'pending') return '排队中';
  if (value === 'processing') return '生成中';
  if (value === 'completed') return '已完成';
  if (value === 'failed') return '失败';
  return value || '待生成';
}

function coverageVariant(value?: string): string {
  if (value === 'ok' || value === 'full') return 'border-success/20 bg-success/10 text-foreground';
  if (value === 'partial') return 'border-warning/20 bg-warning/10 text-foreground';
  if (value === 'failed') return 'border-danger/20 bg-danger/10 text-foreground';
  return 'border-border/60 bg-background/60 text-secondary-text';
}

function roleBubbleClass(role: string): string {
  if (role === 'assistant') {
    return 'border-cyan/20 bg-cyan/10 text-foreground';
  }
  return 'border-purple/20 bg-purple/10 text-foreground';
}

function supplementItems(value?: string[] | null, fallback?: string[] | null): string[] {
  const selected = (value?.length ? value : fallback) ?? [];
  return selected.filter((item): item is string => typeof item === 'string' && item.trim().length > 0).slice(0, 4);
}

function ruleTypeLabel(value: string): string {
  if (value === 'support_retest') return '回踩试仓';
  if (value === 'breakout_confirm') return '突破确认';
  if (value === 'risk_event') return '风险事件';
  return value;
}

const DeepAnalysisPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryId = searchParams.get('queryId')?.trim() || '';
  const analysisId = searchParams.get('analysisId')?.trim() || '';
  const stockCodeHint = searchParams.get('stock')?.trim() || '';
  const stockNameHint = searchParams.get('name')?.trim() || '';

  const [analysis, setAnalysis] = useState<StockDeepAnalysisItem | null>(null);
  const [historyItems, setHistoryItems] = useState<StockDeepAnalysisItem[]>([]);
  const [allHistoryItems, setAllHistoryItems] = useState<StockDeepAnalysisItem[]>([]);
  const [generatedRules, setGeneratedRules] = useState<StockAlertRuleItem[]>([]);
  const [scanInterval, setScanInterval] = useState(String(MIN_ALERT_SCAN_INTERVAL_MINUTES));
  const [followUp, setFollowUp] = useState('');
  const [historyDrawerOpen, setHistoryDrawerOpen] = useState(false);
  const [allHistoryLoading, setAllHistoryLoading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [chatLoading, setChatLoading] = useState(false);
  const [rulesLoading, setRulesLoading] = useState(false);
  const [regenerateLoading, setRegenerateLoading] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [allHistoryError, setAllHistoryError] = useState<ParsedApiError | null>(null);
  const [chatError, setChatError] = useState<ParsedApiError | null>(null);
  const [rulesError, setRulesError] = useState<ParsedApiError | null>(null);
  const activeLoadRequestIdRef = useRef(0);
  const pollTimeoutRef = useRef<number | null>(null);

  const tradePlan = analysis?.tradePlan;
  const levels = tradePlan?.levels;
  const stockResult = analysis?.contextSnapshot?.stockQueryResult;
  const contextSupplement = (analysis?.fundamental?.contextSupplement ?? stockResult?.stockContextSupplement ?? null) as StockQueryContextSupplement | null;
  const conceptAttribution = contextSupplement?.conceptAttribution ?? null;
  const profileHighlights = supplementItems(contextSupplement?.profile?.highlights, contextSupplement?.profile?.headlines);
  const announcementHighlights = supplementItems(contextSupplement?.announcements?.highlights, contextSupplement?.announcements?.headlines);
  const lockupHighlights = supplementItems(contextSupplement?.lockup?.highlights, contextSupplement?.lockup?.headlines);
  const generationMode = analysis?.contextSnapshot?.generationMode || 'deterministic';
  const generationModel = analysis?.contextSnapshot?.generationModel || '';
  const coverageEntries = useMemo(
    () => Object.entries(stockResult?.fundamentalCoverage ?? stockResult?.fundamentalContext?.coverage ?? {}),
    [stockResult?.fundamentalContext?.coverage, stockResult?.fundamentalCoverage],
  );
  const dataSourceEntries = useMemo(
    () => Object.entries(stockResult?.dataSources ?? {}).filter(([, value]) => Boolean(value)),
    [stockResult?.dataSources],
  );
  const analysisMessages = analysis?.messages ?? [];
  const recentHistoryItems = useMemo(() => historyItems.slice(0, 5), [historyItems]);

  const loadHistory = useCallback(async (stockCode?: string, currentAnalysisId?: string) => {
    try {
      const response = await stockQueryApi.getDeepAnalysisHistory(stockCode, stockCode ? 8 : 20);
      setHistoryItems(
        response.items.filter((item) => !currentAnalysisId || item.analysisId !== currentAnalysisId),
      );
    } catch {
      setHistoryItems([]);
    }
  }, []);

  const loadAllHistory = useCallback(async () => {
    setAllHistoryLoading(true);
    setAllHistoryError(null);
    try {
      const response = await stockQueryApi.getDeepAnalysisHistory(undefined, 50);
      setAllHistoryItems(response.items);
    } catch (requestError) {
      setAllHistoryError(getParsedApiError(requestError));
    } finally {
      setAllHistoryLoading(false);
    }
  }, []);

  const clearPollTimer = useCallback(() => {
    if (pollTimeoutRef.current !== null) {
      window.clearTimeout(pollTimeoutRef.current);
      pollTimeoutRef.current = null;
    }
  }, []);

  const applyAnalysisRecord = useCallback((nextAnalysis: StockDeepAnalysisItem) => {
    setAnalysis(nextAnalysis);
    if (nextAnalysis.stockCode) {
      void loadHistory(nextAnalysis.stockCode, nextAnalysis.analysisId);
    }
  }, [loadHistory]);

  const pollAnalysisUntilSettled = useCallback((targetAnalysisId: string) => {
    clearPollTimer();
    pollTimeoutRef.current = window.setTimeout(async () => {
      try {
        const nextAnalysis = await stockQueryApi.getDeepAnalysis(targetAnalysisId);
        applyAnalysisRecord(nextAnalysis);
        if (nextAnalysis.status === 'pending' || nextAnalysis.status === 'processing') {
          pollAnalysisUntilSettled(targetAnalysisId);
          return;
        }
        setLoading(false);
      } catch (requestError) {
        setError(getParsedApiError(requestError));
        setLoading(false);
      }
    }, 3000);
  }, [applyAnalysisRecord, clearPollTimer]);

  useEffect(() => () => {
    clearPollTimer();
  }, [clearPollTimer]);

  useEffect(() => {
    if (!analysisId && !queryId) {
      activeLoadRequestIdRef.current = 0;
      setAnalysis(null);
      void loadHistory();
      setGeneratedRules([]);
      setLoading(false);
      setError(null);
      clearPollTimer();
      return;
    }

    let cancelled = false;
    const requestId = activeLoadRequestIdRef.current + 1;
    activeLoadRequestIdRef.current = requestId;

    const run = async () => {
      setLoading(true);
      setError(null);
      setGeneratedRules([]);
      clearPollTimer();

      try {
        if (analysisId) {
          const nextAnalysis = await stockQueryApi.getDeepAnalysis(analysisId);
          if (cancelled || activeLoadRequestIdRef.current !== requestId) {
            return;
          }
          applyAnalysisRecord(nextAnalysis);
          setLoading(false);
          return;
        }

        const nextAnalysis = await stockQueryApi.createDeepAnalysis(queryId, false);
        if (cancelled || activeLoadRequestIdRef.current !== requestId) {
          return;
        }

        applyAnalysisRecord(nextAnalysis);
        const nextParams = new URLSearchParams();
        nextParams.set('analysisId', nextAnalysis.analysisId);
        if (nextAnalysis.sourceQueryId || queryId) {
          nextParams.set('queryId', nextAnalysis.sourceQueryId || queryId);
        }
        if (nextAnalysis.stockCode || stockCodeHint) {
          nextParams.set('stock', nextAnalysis.stockCode || stockCodeHint);
        }
        if (nextAnalysis.stockName || stockNameHint) {
          nextParams.set('name', nextAnalysis.stockName || stockNameHint);
        }
        setSearchParams(nextParams, { replace: true });

        if (nextAnalysis.status === 'pending' || nextAnalysis.status === 'processing') {
          pollAnalysisUntilSettled(nextAnalysis.analysisId);
          return;
        }

        setLoading(false);
      } catch (requestError) {
        if (cancelled || activeLoadRequestIdRef.current !== requestId) {
          return;
        }
        setAnalysis(null);
        setHistoryItems([]);
        setError(getParsedApiError(requestError));
        setLoading(false);
      }
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, [analysisId, applyAnalysisRecord, clearPollTimer, loadHistory, pollAnalysisUntilSettled, queryId, setSearchParams, stockCodeHint, stockNameHint]);

  const handleRegenerate = async (): Promise<void> => {
    const targetQueryId = queryId || analysis?.sourceQueryId || '';
    if (!targetQueryId) {
      setError(
        createParsedApiError({
          title: '无法重新生成',
          message: '当前深度分析缺少来源 queryId，请先从单股查询页重新发起。',
        }),
      );
      return;
    }

    setRegenerateLoading(true);
    setError(null);
    clearPollTimer();
    try {
      const nextAnalysis = await stockQueryApi.createDeepAnalysis(targetQueryId, true);
      applyAnalysisRecord(nextAnalysis);
      setGeneratedRules([]);
      const nextParams = new URLSearchParams(searchParams);
      nextParams.set('analysisId', nextAnalysis.analysisId);
      nextParams.set('queryId', targetQueryId);
      setSearchParams(nextParams, { replace: true });
      if (nextAnalysis.status === 'pending' || nextAnalysis.status === 'processing') {
        setLoading(true);
        pollAnalysisUntilSettled(nextAnalysis.analysisId);
      }
    } catch (requestError) {
      setError(getParsedApiError(requestError));
    } finally {
      setRegenerateLoading(false);
    }
  };

  const handleSendChat = async (event: React.FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    if (!analysis?.analysisId || !followUp.trim()) return;

    setChatLoading(true);
    setChatError(null);
    try {
      const response = await stockQueryApi.chatDeepAnalysis(analysis.analysisId, followUp.trim());
      setAnalysis((current) => {
        if (!current) return current;
        return {
          ...current,
          messages: [...current.messages, response.userMessage, response.assistantMessage],
        };
      });
      setFollowUp('');
    } catch (requestError) {
      setChatError(getParsedApiError(requestError));
    } finally {
      setChatLoading(false);
    }
  };

  const handleGenerateRules = async (): Promise<void> => {
    if (!analysis?.analysisId) return;
    const parsedInterval = Number.parseInt(scanInterval, 10);
    const normalizedInterval = Number.isFinite(parsedInterval)
      ? Math.max(MIN_ALERT_SCAN_INTERVAL_MINUTES, parsedInterval)
      : MIN_ALERT_SCAN_INTERVAL_MINUTES;

    setRulesLoading(true);
    setRulesError(null);
    try {
      const response = await stockQueryApi.createDeepAnalysisAlertRules(analysis.analysisId, normalizedInterval);
      setGeneratedRules(response.items);
      setScanInterval(String(normalizedInterval));
    } catch (requestError) {
      setRulesError(getParsedApiError(requestError));
    } finally {
      setRulesLoading(false);
    }
  };

  const handleHistoryOpen = async (item: StockDeepAnalysisItem): Promise<void> => {
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set('analysisId', item.analysisId);
    if (item.sourceQueryId) {
      nextParams.set('queryId', item.sourceQueryId);
    }
    setSearchParams(nextParams, { replace: false });
    navigate(`/deep-analysis?${nextParams.toString()}`);
  };

  const handleOpenHistoryDrawer = async (): Promise<void> => {
    setHistoryDrawerOpen(true);
    await loadAllHistory();
  };

  return (
    <AppPage className="max-w-[1680px] py-6">
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-6">
          <section className="rounded-[32px] border border-cyan/15 bg-[radial-gradient(circle_at_top_right,rgba(17,200,255,0.18),transparent_28%),linear-gradient(180deg,#0b1f35_0%,#081422_100%)] p-6 shadow-[0_24px_80px_rgba(3,10,24,0.42)]">
            <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
              <div className="max-w-3xl">
                <div className="flex flex-wrap items-center gap-3">
                  <Badge variant="info" className="border-cyan/20 bg-cyan/10 px-3 py-1 text-cyan">
                    <BrainCircuit className="h-3.5 w-3.5" />
                    Deep Analysis
                  </Badge>
                  {analysis?.action ? (
                    <Badge variant={actionVariant(analysis.action)} className="border-0 px-3 py-1">
                      {actionLabel(analysis.action)}
                    </Badge>
                  ) : null}
                  {analysis?.status ? (
                    <Badge variant="default" className="border-border/60 px-3 py-1">
                      {analysisStatusLabel(analysis.status)}
                    </Badge>
                  ) : null}
                  <Badge variant={generationMode === 'llm' ? 'success' : 'warning'} className="border-0 px-3 py-1">
                    {generationMode === 'llm' ? 'LLM 生成' : 'Fallback 生成'}
                  </Badge>
                </div>

                <div className="mt-4">
                  <p className="text-sm uppercase tracking-[0.18em] text-cyan/80">Single Stock Cockpit</p>
                  <h1 className="mt-3 text-3xl font-semibold tracking-tight text-white md:text-4xl">
                    {analysis?.stockName || stockNameHint || '单股深度分析'}
                    {analysis?.stockCode ? (
                      <span className="ml-3 text-lg font-medium text-slate-400">{analysis.stockCode}</span>
                    ) : null}
                  </h1>
                  <p className="mt-4 max-w-3xl text-sm leading-7 text-slate-300">
                    {analysis?.summary || '深度分析会围绕一次已完成的单股查询结果，生成结构化交易计划，并支持受控追问与告警规则生成。'}
                  </p>
                </div>
              </div>

              <div className="flex shrink-0 flex-wrap gap-3">
                <Button
                  variant="secondary"
                  size="lg"
                  isLoading={regenerateLoading}
                  loadingText="生成中..."
                  onClick={() => void handleRegenerate()}
                  disabled={!queryId && !analysis?.sourceQueryId}
                  className="rounded-2xl"
                >
                  <RefreshCw className="h-4 w-4" />
                  重新生成
                </Button>
                <Link to="/stock-query" className="inline-flex">
                  <Button variant="outline" size="lg" className="rounded-2xl">
                    <Radar className="h-4 w-4" />
                    返回单股查询
                  </Button>
                </Link>
              </div>
            </div>

            {error ? (
              <ApiErrorAlert
                error={error}
                className="mt-5"
                actionLabel={queryId || analysis?.sourceQueryId ? '重试' : undefined}
                onAction={queryId || analysis?.sourceQueryId ? () => void handleRegenerate() : undefined}
                onDismiss={() => setError(null)}
              />
            ) : null}
          </section>

          {!queryId && !analysisId ? (
            <EmptyState
              title="深度分析历史"
              description="这里可以直接查看已经生成过的深度分析历史。你也可以先在单股查询页发起新的深度分析，再回到这里持续跟踪。"
              icon={<BrainCircuit className="h-8 w-8" />}
              action={(
                <Link to="/stock-query">
                  <Button className="rounded-2xl">前往单股查询</Button>
                </Link>
              )}
            />
          ) : null}

          {loading && !analysis ? (
            <Card variant="bordered" padding="lg" className="rounded-[28px] border-border/60 bg-card/90">
              <div className="flex items-center gap-3 text-secondary-text">
                <RefreshCw className="h-4 w-4 animate-spin text-cyan" />
                <span>正在生成深度分析...</span>
              </div>
            </Card>
          ) : null}

          {analysis && analysis.status !== 'completed' ? (
            <Card variant="bordered" padding="lg" className="rounded-[28px] border-border/60 bg-card/95">
              <div className="flex items-center gap-3">
                {analysis.status === 'failed' ? (
                  <AlertTriangle className="h-5 w-5 text-danger" />
                ) : (
                  <RefreshCw className="h-5 w-5 animate-spin text-cyan" />
                )}
                <div>
                  <p className="text-base font-semibold text-foreground">
                    {analysis.status === 'failed' ? '深度分析生成失败' : '深度分析正在后台处理'}
                  </p>
                  <p className="mt-1 text-sm text-secondary-text">
                    {analysis.error || '已经切到后台任务模式，可以离开当前页面，稍后再回来查看结果。'}
                  </p>
                </div>
              </div>
            </Card>
          ) : null}

          {analysis?.status === 'completed' ? (
            <>
              <section className="grid gap-6 lg:grid-cols-[minmax(0,1.35fr)_360px]">
                <Card variant="bordered" padding="lg" className="rounded-[28px] border-border/60 bg-card/95">
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <p className="text-xs uppercase tracking-[0.18em] text-secondary-text">交易计划</p>
                      <h2 className="mt-2 text-2xl font-semibold text-foreground">{tradePlan?.actionLabel || actionLabel(analysis.action)}</h2>
                    </div>
                    <Badge variant="info" className="border-0 px-3 py-1">
                      置信度 {tradePlan?.confidence ?? '--'} / 100
                    </Badge>
                  </div>

                  <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                    <div className="rounded-2xl border border-success/15 bg-success/10 p-4">
                      <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">试仓位</p>
                      <p className="mt-3 text-2xl font-semibold text-success">{formatNumber(levels?.trialPrice)}</p>
                    </div>
                    <div className="rounded-2xl border border-cyan/15 bg-cyan/10 p-4">
                      <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">确认位</p>
                      <p className="mt-3 text-2xl font-semibold text-cyan">{formatNumber(levels?.confirmPrice)}</p>
                    </div>
                    <div className="rounded-2xl border border-danger/15 bg-danger/10 p-4">
                      <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">止损位</p>
                      <p className="mt-3 text-2xl font-semibold text-danger">{formatNumber(levels?.stopLoss)}</p>
                    </div>
                    <div className="rounded-2xl border border-warning/15 bg-warning/10 p-4">
                      <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">目标位</p>
                      <p className="mt-3 text-2xl font-semibold text-warning">{formatNumber(levels?.targetPrice)}</p>
                    </div>
                  </div>

                  <div className="mt-6 grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
                    <div className="rounded-3xl border border-border/60 bg-background/60 p-5">
                      <div className="flex items-center gap-2">
                        <Target className="h-4 w-4 text-cyan" />
                        <h3 className="text-lg font-semibold text-foreground">执行步骤</h3>
                      </div>
                      <div className="mt-4 space-y-3">
                        {(tradePlan?.triggers ?? []).map((item, index) => (
                          <div key={`${item}-${index}`} className="rounded-2xl border border-border/50 bg-card/80 px-4 py-3">
                            <p className="text-sm leading-6 text-foreground">{item}</p>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="rounded-3xl border border-border/60 bg-background/60 p-5">
                      <div className="flex items-center gap-2">
                        <ShieldAlert className="h-4 w-4 text-warning" />
                        <h3 className="text-lg font-semibold text-foreground">仓位建议</h3>
                      </div>
                      <div className="mt-4 space-y-3 text-sm text-secondary-text">
                        <div className="flex items-center justify-between rounded-2xl border border-border/50 bg-card/80 px-4 py-3">
                          <span>初始仓位</span>
                          <strong className="text-foreground">{tradePlan?.positionPlan?.initial ?? '--'}</strong>
                        </div>
                        <div className="flex items-center justify-between rounded-2xl border border-border/50 bg-card/80 px-4 py-3">
                          <span>加仓条件</span>
                          <strong className="text-right text-foreground">{tradePlan?.positionPlan?.add ?? '--'}</strong>
                        </div>
                        <div className="flex items-center justify-between rounded-2xl border border-border/50 bg-card/80 px-4 py-3">
                          <span>最大仓位</span>
                          <strong className="text-foreground">{tradePlan?.positionPlan?.max ?? '--'}</strong>
                        </div>
                      </div>
                    </div>
                  </div>
                </Card>

                <Card variant="bordered" padding="lg" className="rounded-[28px] border-border/60 bg-card/95">
                  <p className="text-xs uppercase tracking-[0.18em] text-secondary-text">上下文快照</p>
                  <div className="mt-4 space-y-4">
                    <div className="rounded-2xl border border-border/60 bg-background/60 px-4 py-4">
                      <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">当前价格</p>
                      <p className="mt-3 text-3xl font-semibold text-foreground">{formatNumber(stockResult?.currentPrice)}</p>
                      <p className="mt-2 text-sm text-secondary-text">涨跌幅 {formatNumber(stockResult?.pctChg, 2)}%</p>
                    </div>

                    <div className="grid gap-3 sm:grid-cols-2">
                      <div className="rounded-2xl border border-border/60 bg-background/60 p-4">
                        <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">趋势状态</p>
                        <p className="mt-2 text-base font-medium text-foreground">{stockResult?.trendStatus || '--'}</p>
                      </div>
                      <div className="rounded-2xl border border-border/60 bg-background/60 p-4">
                        <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">买点信号</p>
                        <p className="mt-2 text-base font-medium text-foreground">{stockResult?.buySignal || stockResult?.signal || '--'}</p>
                      </div>
                    </div>

                    {conceptAttribution?.conceptNames?.length ? (
                      <div className="rounded-2xl border border-border/60 bg-background/60 p-4">
                        <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">概念 / 题材归因</p>
                        <div className="mt-3 flex flex-wrap gap-2">
                          {conceptAttribution.conceptNames.slice(0, 5).map((item) => (
                            <Badge key={item} variant="default" className="border-border/60 bg-card/80 px-3 py-1">
                              {item}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    ) : null}

                    <InlineAlert
                      variant="info"
                      title="来源"
                      message={`基于 queryId ${analysis.sourceQueryId || '--'} 生成，可重复加载和追溯。${generationModel ? ` 当前模型：${generationModel}` : ''}`}
                    />
                  </div>
                </Card>
              </section>

              <section className="grid gap-6 xl:grid-cols-[minmax(0,1.3fr)_420px]">
                <div className="space-y-6">
                  <Card variant="bordered" padding="lg" className="rounded-[28px] border-border/60 bg-card/95">
                    <div className="flex items-center gap-2">
                      <Sparkles className="h-4 w-4 text-cyan" />
                      <h2 className="text-xl font-semibold text-foreground">分析拆解</h2>
                    </div>
                    <div className="mt-5 grid gap-4">
                      <div className="rounded-2xl border border-border/60 bg-background/60 p-4">
                        <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">技术确认</p>
                        <p className="mt-3 text-sm leading-7 text-foreground">{analysis.technical?.assessment || '--'}</p>
                      </div>
                      <div className="rounded-2xl border border-border/60 bg-background/60 p-4">
                        <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">基本面质量</p>
                        <p className="mt-3 text-sm leading-7 text-foreground">{analysis.fundamental?.assessment || '--'}</p>
                      </div>
                      <div className="rounded-2xl border border-border/60 bg-background/60 p-4">
                        <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">风险清单</p>
                        <div className="mt-3 space-y-2">
                          {(analysis.risk?.items ?? []).map((item, index) => (
                            <div key={`${item}-${index}`} className="flex gap-3 rounded-2xl border border-danger/10 bg-danger/5 px-4 py-3">
                              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-danger" />
                              <p className="text-sm leading-6 text-foreground">{item}</p>
                            </div>
                          ))}
                        </div>
                      </div>
                      {(conceptAttribution || contextSupplement?.profile || contextSupplement?.announcements || contextSupplement?.lockup) ? (
                        <div className="rounded-2xl border border-border/60 bg-background/60 p-4">
                          <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">补充上下文</p>
                          {conceptAttribution?.summary ? (
                            <p className="mt-3 text-sm leading-7 text-foreground">{conceptAttribution.summary}</p>
                          ) : null}
                          <div className="mt-3 space-y-3">
                            <DeepSupplementBlock
                              title="公司画像"
                              summary={contextSupplement?.profile?.summary}
                              items={profileHighlights}
                            />
                            <DeepSupplementBlock
                              title="近期公告"
                              summary={contextSupplement?.announcements?.summary}
                              items={announcementHighlights}
                            />
                            <DeepSupplementBlock
                              title="解禁 / 风险"
                              summary={contextSupplement?.lockup?.summary}
                              items={lockupHighlights}
                              danger
                            />
                          </div>
                        </div>
                      ) : null}
                    </div>
                  </Card>

                  <Card variant="bordered" padding="lg" className="rounded-[28px] border-border/60 bg-card/95">
                    <div className="flex items-center gap-2">
                      <Database className="h-4 w-4 text-cyan" />
                      <h2 className="text-xl font-semibold text-foreground">数据覆盖与来源</h2>
                    </div>
                    <div className="mt-5 grid gap-3 sm:grid-cols-2">
                      {coverageEntries.length > 0 ? coverageEntries.map(([key, value]) => (
                        <div key={key} className={`rounded-2xl border px-4 py-3 ${coverageVariant(value)}`}>
                          <p className="text-xs uppercase tracking-[0.14em]">{key}</p>
                          <p className="mt-2 text-sm font-medium">{value}</p>
                        </div>
                      )) : (
                        <p className="text-sm text-secondary-text">当前没有可展示的数据覆盖信息。</p>
                      )}
                    </div>
                    {dataSourceEntries.length > 0 ? (
                      <div className="mt-5 rounded-2xl border border-border/60 bg-background/60 p-4">
                        <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">数据源</p>
                        <div className="mt-3 flex flex-wrap gap-2">
                          {dataSourceEntries.map(([key, value]) => (
                            <Badge key={key} variant="default" className="border-border/60 bg-card/80 px-3 py-1">
                              {key}: {String(value)}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    ) : null}
                  </Card>
                </div>

                <div className="space-y-6">
                  <Card variant="bordered" padding="lg" className="rounded-[28px] border-border/60 bg-card/95">
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-2">
                        <BrainCircuit className="h-4 w-4 text-cyan" />
                        <h2 className="text-xl font-semibold text-foreground">受控追问</h2>
                      </div>
                      <Badge variant="info" className="border-0 px-3 py-1">不重新搜索</Badge>
                    </div>

                    <div className="mt-5 space-y-3">
                      {analysisMessages.length > 0 ? analysisMessages.map((message: StockDeepAnalysisMessage) => (
                        <div key={message.id} className={`rounded-2xl border px-4 py-3 ${roleBubbleClass(message.role)}`}>
                          <div className="flex items-center justify-between gap-3">
                            <p className="text-sm font-medium text-foreground">
                              {message.role === 'assistant' ? 'AI' : '用户'}
                            </p>
                            <span className="text-xs text-secondary-text">{formatTime(message.createdAt)}</span>
                          </div>
                          <p className="mt-2 text-sm leading-7 text-foreground">{message.content}</p>
                        </div>
                      )) : (
                        <p className="text-sm text-secondary-text">这次深度分析还没有追问记录。</p>
                      )}
                    </div>

                    <form className="mt-5 space-y-3" onSubmit={(event) => void handleSendChat(event)}>
                      <Input
                        label="继续追问"
                        value={followUp}
                        onChange={(event) => setFollowUp(event.target.value)}
                        placeholder="例如：为什么现在不适合买？"
                        className="min-h-[48px] rounded-2xl"
                      />
                      {chatError ? <ApiErrorAlert error={chatError} onDismiss={() => setChatError(null)} /> : null}
                      <div className="flex flex-wrap gap-3">
                        <Button
                          type="submit"
                          isLoading={chatLoading}
                          loadingText="追问中..."
                          disabled={!analysis.analysisId || !followUp.trim()}
                          className="rounded-2xl"
                        >
                          <ArrowRight className="h-4 w-4" />
                          提交追问
                        </Button>
                        <button
                          type="button"
                          onClick={() => setFollowUp('跌破哪里需要放弃？')}
                          className="inline-flex items-center rounded-2xl border border-border/60 bg-background/60 px-4 py-2 text-sm text-secondary-text transition hover:border-cyan/20 hover:text-foreground"
                        >
                          跌破哪里需要放弃？
                        </button>
                      </div>
                    </form>
                  </Card>

                  <Card variant="bordered" padding="lg" className="rounded-[28px] border-border/60 bg-card/95">
                    <div className="flex items-center gap-2">
                      <Radar className="h-4 w-4 text-cyan" />
                      <h2 className="text-xl font-semibold text-foreground">生成告警规则</h2>
                    </div>
                    <div className="mt-5 grid gap-4">
                      <Input
                        label="扫描间隔(分钟)"
                        value={scanInterval}
                        onChange={(event) => setScanInterval(event.target.value)}
                        placeholder={`最小 ${MIN_ALERT_SCAN_INTERVAL_MINUTES}`}
                        className="rounded-2xl"
                      />
                      {rulesError ? <ApiErrorAlert error={rulesError} onDismiss={() => setRulesError(null)} /> : null}
                      <Button
                        isLoading={rulesLoading}
                        loadingText="生成中..."
                        onClick={() => void handleGenerateRules()}
                        disabled={!analysis.analysisId}
                        className="rounded-2xl"
                      >
                        生成规则
                      </Button>
                      {generatedRules.length > 0 ? (
                        <div className="space-y-3 rounded-2xl border border-border/60 bg-background/60 p-4">
                          {generatedRules.map((rule) => (
                            <div key={rule.id} className="flex items-center justify-between gap-3 rounded-2xl border border-border/50 bg-card/80 px-4 py-3">
                              <div>
                                <p className="text-sm font-medium text-foreground">{ruleTypeLabel(rule.ruleType)}</p>
                                <p className="mt-1 text-xs text-secondary-text">{rule.note || '已接入观察池扫描器'}</p>
                              </div>
                              <div className="text-right">
                                <p className="text-sm font-medium text-foreground">{formatNumber(rule.thresholdValue)}</p>
                                <p className="mt-1 text-xs text-secondary-text">{rule.scanIntervalMinutes} 分钟</p>
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  </Card>
                </div>
              </section>
            </>
          ) : null}

          {!analysis && !loading && historyItems.length > 0 ? (
            <Card variant="bordered" padding="lg" className="rounded-[28px] border-border/60 bg-card/95">
              <div className="flex items-center gap-2">
                <History className="h-4 w-4 text-cyan" />
                <h2 className="text-xl font-semibold text-foreground">最近的深度分析</h2>
              </div>
              <div className="mt-4 flex justify-end">
                <Button variant="outline" size="sm" className="rounded-2xl" onClick={() => void handleOpenHistoryDrawer()}>
                  查看全部历史
                </Button>
              </div>
              <p className="mt-3 text-sm leading-7 text-secondary-text">
                点击任意一条历史记录，可以恢复查看当时的交易计划、追问记录和告警生成上下文。
              </p>
              <div className="mt-5 grid gap-3">
                {historyItems.map((item) => (
                  <button
                    key={item.analysisId}
                    type="button"
                    onClick={() => void handleHistoryOpen(item)}
                    className="block w-full rounded-2xl border border-border/60 bg-background/60 px-4 py-4 text-left transition hover:border-cyan/20 hover:bg-card"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex min-w-0 items-center gap-3">
                        <p className="truncate text-sm font-medium text-foreground">
                          {item.stockName} <span className="text-secondary-text">{item.stockCode}</span>
                        </p>
                        <Badge variant={item.status === 'completed' ? actionVariant(item.action) : 'default'} className="border-0 px-3 py-1">
                          {item.status === 'completed' ? actionLabel(item.action) : analysisStatusLabel(item.status)}
                        </Badge>
                      </div>
                      <span className="shrink-0 text-xs text-secondary-text">{formatTime(item.updatedAt || item.createdAt)}</span>
                    </div>
                    <p className="mt-2 text-sm leading-6 text-secondary-text">
                      {item.summary || item.error || '点击恢复查看这次深度分析。'}
                    </p>
                  </button>
                ))}
              </div>
            </Card>
          ) : null}
        </div>

        <aside className="space-y-6">
          <Card variant="bordered" padding="lg" className="rounded-[28px] border-border/60 bg-card/95">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <History className="h-4 w-4 text-cyan" />
                <h2 className="text-xl font-semibold text-foreground">历史分析</h2>
              </div>
              <Button variant="ghost" size="sm" className="rounded-2xl" onClick={() => void handleOpenHistoryDrawer()}>
                全部历史
              </Button>
            </div>
            <div className="mt-5 space-y-3">
              {recentHistoryItems.length > 0 ? recentHistoryItems.map((item) => (
                <button
                  key={item.analysisId}
                  type="button"
                  onClick={() => void handleHistoryOpen(item)}
                  className="block w-full rounded-2xl border border-border/60 bg-background/60 px-4 py-4 text-left transition hover:border-cyan/20 hover:bg-card"
                >
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-medium text-foreground">
                      {item.status === 'completed' ? actionLabel(item.action) : analysisStatusLabel(item.status)}
                    </p>
                    <span className="text-xs text-secondary-text">{formatTime(item.updatedAt || item.createdAt)}</span>
                  </div>
                  <p className="mt-2 text-xs leading-6 text-secondary-text">
                    {item.summary || item.error || (item.status === 'processing' ? '正在生成结构化交易计划…' : '无摘要')}
                  </p>
                </button>
              )) : (
                <p className="text-sm text-secondary-text">
                  {analysis?.stockCode ? '这只股票还没有更多深度分析历史。' : '这里会显示最近的深度分析历史，支持直接恢复查看。'}
                </p>
              )}
            </div>
          </Card>

          <Card variant="bordered" padding="lg" className="rounded-[28px] border-border/60 bg-card/95">
            <div className="flex items-center gap-2">
              <Clock3 className="h-4 w-4 text-cyan" />
              <h2 className="text-xl font-semibold text-foreground">最近更新</h2>
            </div>
            <div className="mt-5 space-y-3 text-sm text-secondary-text">
              <div className="flex items-center justify-between rounded-2xl border border-border/60 bg-background/60 px-4 py-3">
                <span>生成时间</span>
                <strong className="text-foreground">{formatTime(analysis?.createdAt)}</strong>
              </div>
              <div className="flex items-center justify-between rounded-2xl border border-border/60 bg-background/60 px-4 py-3">
                <span>更新时间</span>
                <strong className="text-foreground">{formatTime(analysis?.updatedAt)}</strong>
              </div>
              <div className="flex items-center justify-between rounded-2xl border border-border/60 bg-background/60 px-4 py-3">
                <span>来源 queryId</span>
                <strong className="max-w-[160px] truncate text-foreground">{analysis?.sourceQueryId || queryId || '--'}</strong>
              </div>
            </div>
          </Card>

          {!analysis && (stockCodeHint || stockNameHint) ? (
            <InlineAlert
              variant="info"
              title="入口兼容"
              message={`检测到旧入口参数 ${stockNameHint || stockCodeHint}。如果缺少 queryId，需要先回到单股查询页重新发起一次分析。`}
            />
          ) : null}
        </aside>
      </div>

      <Drawer
        isOpen={historyDrawerOpen}
        onClose={() => setHistoryDrawerOpen(false)}
        title="深度分析历史"
        width="max-w-xl"
        side="right"
      >
        <div className="space-y-4">
          {allHistoryError ? <ApiErrorAlert error={allHistoryError} /> : null}

          {allHistoryLoading ? (
            <InlineAlert
              variant="info"
              title="正在加载深度分析历史"
              message="正在从后端读取最近的深度分析记录。"
            />
          ) : null}

          {!allHistoryLoading && allHistoryItems.length === 0 ? (
            <EmptyState
              title="暂无深度分析历史"
              description="完成几次深度分析后，这里会显示完整历史，方便你恢复查看和横向对比。"
              icon={<Clock3 className="h-8 w-8" />}
            />
          ) : null}

          <div className="space-y-3">
            {allHistoryItems.map((item) => {
              const active = item.analysisId === analysis?.analysisId;
              return (
                <div
                  key={item.analysisId}
                  className={[
                    'rounded-2xl border px-4 py-4 transition-colors',
                    active ? 'border-cyan/40 bg-cyan/6' : 'border-border/60 bg-background/70',
                  ].join(' ')}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-base font-semibold text-foreground">
                        {item.stockName} <span className="text-secondary-text">{item.stockCode}</span>
                      </p>
                      <p className="mt-1 text-sm text-secondary-text">{formatTime(item.updatedAt || item.createdAt)}</p>
                    </div>
                    <Badge variant={item.status === 'completed' ? actionVariant(item.action) : 'default'} className="border-0">
                      {item.status === 'completed' ? actionLabel(item.action) : analysisStatusLabel(item.status)}
                    </Badge>
                  </div>

                  <div className="mt-3 space-y-2 text-sm">
                    <p className="text-secondary-text">{item.summary || item.error || '无摘要'}</p>
                    <p className="text-secondary-text">来源 queryId {item.sourceQueryId || '--'}</p>
                  </div>

                  <div className="mt-4 flex items-center justify-end gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        void handleHistoryOpen(item);
                        setHistoryDrawerOpen(false);
                      }}
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

type DeepSupplementBlockProps = {
  title: string;
  summary?: string | null;
  items?: string[];
  danger?: boolean;
};

const DeepSupplementBlock: React.FC<DeepSupplementBlockProps> = ({ title, summary, items = [], danger = false }) => {
  if (!summary && items.length === 0) return null;
  return (
    <div className={`rounded-2xl border px-4 py-3 ${danger ? 'border-danger/15 bg-danger/5' : 'border-border/60 bg-card/80'}`}>
      <p className="text-sm font-medium text-foreground">{title}</p>
      {summary ? (
        <p className="mt-2 text-sm leading-6 text-secondary-text">{summary}</p>
      ) : null}
      {items.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {items.map((item) => (
            <Badge
              key={item}
              variant="default"
              className={danger ? 'border-danger/20 bg-danger/10 px-3 py-1 text-foreground' : 'border-border/60 bg-background/60 px-3 py-1 text-foreground'}
            >
              {item}
            </Badge>
          ))}
        </div>
      ) : null}
    </div>
  );
};

export default DeepAnalysisPage;
