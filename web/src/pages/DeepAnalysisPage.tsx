import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  ArrowRight,
  BrainCircuit,
  Clock3,
  RefreshCw,
  Search,
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

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const MIN_ALERT_SCAN_INTERVAL_MINUTES = 5;

const ANALYSIS_TABS = [
  { key: 'chat', label: 'AI 对话' },
  { key: 'finance', label: '财务' },
  { key: 'valuation', label: '估值带' },
  { key: 'peers', label: '同业对比' },
  { key: 'institution', label: '机构观点' },
  { key: 'technical', label: '技术面' },
] as const;

const QUESTION_TEMPLATES = [
  { category: '基本面', question: '这家公司未来两年的盈利增长可持续吗？' },
  { category: '估值', question: '当前估值是合理、偏贵还是便宜？给出理由。' },
  { category: '风险', question: '持有这只股票最大的 3 个风险是什么？' },
  { category: '同业', question: '和板块前 3 名比较，给出选股建议' },
  { category: '事件', question: '未来 2 周关键事件 + 对股价潜在影响' },
] as const;

/* ------------------------------------------------------------------ */
/*  Utility functions                                                  */
/* ------------------------------------------------------------------ */

function formatNumber(value?: number | null, digits = 2): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '--';
  return value.toFixed(digits);
}

function formatTime(value?: string | null): string {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(date);
}

function formatShortTime(value?: string | null): string {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false }).format(date);
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

function ruleTypeLabel(value: string): string {
  if (value === 'support_retest') return '回踩试仓';
  if (value === 'breakout_confirm') return '突破确认';
  if (value === 'risk_event') return '风险事件';
  return value;
}

/* ------------------------------------------------------------------ */
/*  Main component                                                     */
/* ------------------------------------------------------------------ */

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
  const [activeTab, setActiveTab] = useState<string>('chat');
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
  const pollFnRef = useRef<(id: string) => void>(() => {});
  const chatEndRef = useRef<HTMLDivElement>(null);

  /* ---- derived data ---- */

  const tradePlan = analysis?.tradePlan;
  const levels = tradePlan?.levels;
  const stockResult = analysis?.contextSnapshot?.stockQueryResult;
  const contextSupplement = (analysis?.fundamental?.contextSupplement ?? stockResult?.stockContextSupplement ?? null) as StockQueryContextSupplement | null;
  const conceptAttribution = contextSupplement?.conceptAttribution ?? null;
  const generationMode = analysis?.contextSnapshot?.generationMode || 'deterministic';
  const generationModel = analysis?.contextSnapshot?.generationModel || '';
  const analysisMessages = analysis?.messages ?? [];
  const recentHistoryItems = useMemo(() => historyItems.slice(0, 5), [historyItems]);
  const confidence = tradePlan?.confidence ?? null;

  /* Build reference sources for sidebar */
  const referenceSources = useMemo(() => {
    const sources: Array<{ type: string; title: string; date: string }> = [];
    const newsHeadlines = stockResult?.stockNewsSummary?.headlines ?? [];
    const profileHeadlines = contextSupplement?.profile?.headlines ?? [];
    const announcementHeadlines = contextSupplement?.announcements?.headlines ?? [];

    for (const h of announcementHeadlines.slice(0, 2)) {
      sources.push({ type: '公司公告', title: h.slice(0, 30), date: '' });
    }
    for (const h of profileHeadlines.slice(0, 1)) {
      sources.push({ type: '研报', title: h.slice(0, 30), date: '' });
    }
    for (const h of newsHeadlines.slice(0, 3)) {
      sources.push({ type: '新闻', title: h.slice(0, 30), date: '' });
    }
    return sources;
  }, [stockResult?.stockNewsSummary?.headlines, contextSupplement?.profile?.headlines, contextSupplement?.announcements?.headlines]);

  /* Theme tags from stock result – let React Compiler handle memoization */
  const themeTags = (() => {
    const tags: string[] = [];
    const themes = stockResult?.themeAttributions ?? stockResult?.themes ?? [];
    for (const t of themes) { if (t.themeName) tags.push(t.themeName); }
    if (conceptAttribution?.conceptNames) {
      for (const c of conceptAttribution.conceptNames.slice(0, 3)) {
        if (!tags.includes(c)) tags.push(c);
      }
    }
    return tags.slice(0, 5);
  })();

  /* ---- data loaders ---- */

  const loadHistory = useCallback(async (stockCode?: string, currentAnalysisId?: string) => {
    try {
      const response = await stockQueryApi.getDeepAnalysisHistory(stockCode, stockCode ? 8 : 20);
      setHistoryItems(response.items.filter((item) => !currentAnalysisId || item.analysisId !== currentAnalysisId));
    } catch { setHistoryItems([]); }
  }, []);

  const loadAllHistory = useCallback(async () => {
    setAllHistoryLoading(true);
    setAllHistoryError(null);
    try {
      const response = await stockQueryApi.getDeepAnalysisHistory(undefined, 50);
      setAllHistoryItems(response.items);
    } catch (requestError) {
      setAllHistoryError(getParsedApiError(requestError));
    } finally { setAllHistoryLoading(false); }
  }, []);

  const clearPollTimer = useCallback(() => {
    if (pollTimeoutRef.current !== null) { window.clearTimeout(pollTimeoutRef.current); pollTimeoutRef.current = null; }
  }, []);

  const applyAnalysisRecord = useCallback((nextAnalysis: StockDeepAnalysisItem) => {
    setAnalysis(nextAnalysis);
    if (nextAnalysis.stockCode) { void loadHistory(nextAnalysis.stockCode, nextAnalysis.analysisId); }
  }, [loadHistory]);

  const pollAnalysisUntilSettled = useCallback((targetAnalysisId: string) => {
    clearPollTimer();
    pollTimeoutRef.current = window.setTimeout(async () => {
      try {
        const nextAnalysis = await stockQueryApi.getDeepAnalysis(targetAnalysisId);
        applyAnalysisRecord(nextAnalysis);
        if (nextAnalysis.status === 'pending' || nextAnalysis.status === 'processing') {
          pollFnRef.current(targetAnalysisId);
          return;
        }
        setLoading(false);
      } catch (requestError) { setError(getParsedApiError(requestError)); setLoading(false); }
    }, 3000);
  }, [applyAnalysisRecord, clearPollTimer]);

  useEffect(() => { pollFnRef.current = pollAnalysisUntilSettled; }, [pollAnalysisUntilSettled]);
  useEffect(() => () => { clearPollTimer(); }, [clearPollTimer]);

  useEffect(() => {
    if (!analysisId && !queryId) {
      activeLoadRequestIdRef.current = 0;
      clearPollTimer();
      const resetAndLoad = async () => {
        setAnalysis(null);
        setGeneratedRules([]);
        setLoading(false);
        setError(null);
        await loadHistory();
      };
      void resetAndLoad();
      return;
    }
    let cancelled = false;
    const requestId = activeLoadRequestIdRef.current + 1;
    activeLoadRequestIdRef.current = requestId;

    const run = async () => {
      setLoading(true); setError(null); setGeneratedRules([]); clearPollTimer();
      try {
        if (analysisId) {
          const nextAnalysis = await stockQueryApi.getDeepAnalysis(analysisId);
          if (cancelled || activeLoadRequestIdRef.current !== requestId) return;
          applyAnalysisRecord(nextAnalysis); setLoading(false); return;
        }
        const nextAnalysis = await stockQueryApi.createDeepAnalysis(queryId, false);
        if (cancelled || activeLoadRequestIdRef.current !== requestId) return;
        applyAnalysisRecord(nextAnalysis);
        const nextParams = new URLSearchParams();
        nextParams.set('analysisId', nextAnalysis.analysisId);
        if (nextAnalysis.sourceQueryId || queryId) nextParams.set('queryId', nextAnalysis.sourceQueryId || queryId);
        if (nextAnalysis.stockCode || stockCodeHint) nextParams.set('stock', nextAnalysis.stockCode || stockCodeHint);
        if (nextAnalysis.stockName || stockNameHint) nextParams.set('name', nextAnalysis.stockName || stockNameHint);
        setSearchParams(nextParams, { replace: true });
        if (nextAnalysis.status === 'pending' || nextAnalysis.status === 'processing') {
          pollAnalysisUntilSettled(nextAnalysis.analysisId); return;
        }
        setLoading(false);
      } catch (requestError) {
        if (cancelled || activeLoadRequestIdRef.current !== requestId) return;
        setAnalysis(null); setHistoryItems([]); setError(getParsedApiError(requestError)); setLoading(false);
      }
    };
    void run();
    return () => { cancelled = true; };
  }, [analysisId, applyAnalysisRecord, clearPollTimer, loadHistory, pollAnalysisUntilSettled, queryId, setSearchParams, stockCodeHint, stockNameHint]);

  /* ---- handlers ---- */

  const handleRegenerate = async (): Promise<void> => {
    const targetQueryId = queryId || analysis?.sourceQueryId || '';
    if (!targetQueryId) {
      setError(createParsedApiError({ title: '无法重新生成', message: '当前深度分析缺少来源 queryId，请先从单股查询页重新发起。' }));
      return;
    }
    setRegenerateLoading(true); setError(null); clearPollTimer();
    try {
      const nextAnalysis = await stockQueryApi.createDeepAnalysis(targetQueryId, true);
      applyAnalysisRecord(nextAnalysis); setGeneratedRules([]);
      const nextParams = new URLSearchParams(searchParams);
      nextParams.set('analysisId', nextAnalysis.analysisId);
      nextParams.set('queryId', targetQueryId);
      setSearchParams(nextParams, { replace: true });
      if (nextAnalysis.status === 'pending' || nextAnalysis.status === 'processing') {
        setLoading(true); pollAnalysisUntilSettled(nextAnalysis.analysisId);
      }
    } catch (requestError) { setError(getParsedApiError(requestError)); } finally { setRegenerateLoading(false); }
  };

  const handleSendChat = async (event: React.FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    if (!analysis?.analysisId || !followUp.trim()) return;
    setChatLoading(true); setChatError(null);
    try {
      const response = await stockQueryApi.chatDeepAnalysis(analysis.analysisId, followUp.trim());
      setAnalysis((current) => {
        if (!current) return current;
        return { ...current, messages: [...current.messages, response.userMessage, response.assistantMessage] };
      });
      setFollowUp('');
      setTimeout(() => chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
    } catch (requestError) { setChatError(getParsedApiError(requestError)); } finally { setChatLoading(false); }
  };

  const handleGenerateRules = async (): Promise<void> => {
    if (!analysis?.analysisId) return;
    const parsedInterval = Number.parseInt(scanInterval, 10);
    const normalizedInterval = Number.isFinite(parsedInterval) ? Math.max(MIN_ALERT_SCAN_INTERVAL_MINUTES, parsedInterval) : MIN_ALERT_SCAN_INTERVAL_MINUTES;
    setRulesLoading(true); setRulesError(null);
    try {
      const response = await stockQueryApi.createDeepAnalysisAlertRules(analysis.analysisId, normalizedInterval);
      setGeneratedRules(response.items); setScanInterval(String(normalizedInterval));
    } catch (requestError) { setRulesError(getParsedApiError(requestError)); } finally { setRulesLoading(false); }
  };

  const handleHistoryOpen = async (item: StockDeepAnalysisItem): Promise<void> => {
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set('analysisId', item.analysisId);
    if (item.sourceQueryId) nextParams.set('queryId', item.sourceQueryId);
    setSearchParams(nextParams, { replace: false });
    navigate(`/deep-analysis?${nextParams.toString()}`);
  };

  const handleOpenHistoryDrawer = async (): Promise<void> => {
    setHistoryDrawerOpen(true);
    await loadAllHistory();
  };

  /* ================================================================ */
  /*  RENDER                                                           */
  /* ================================================================ */

  return (
    <AppPage className="!max-w-none px-4 md:px-8 lg:px-12 xl:px-16">

      {/* ---- Breadcrumb + Search ---- */}
      <div className="search-bar-card flex flex-wrap items-center gap-3 lg:gap-4">
        <p className="shrink-0 text-sm text-secondary-text">
          深度分析
          {analysis ? (
            <> / <span className="font-semibold text-foreground">{analysis.stockName}</span>{' '}<span>{analysis.stockCode}</span>
              {analysisMessages.length > 0 ? <span className="ml-1">· 对话 #{analysisMessages.length}</span> : null}
            </>
          ) : stockNameHint ? (
            <> / <span className="font-semibold text-foreground">{stockNameHint}</span></>
          ) : null}
        </p>

        <div className="relative min-w-0 flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-secondary-text" />
          <input
            placeholder="搜索过往对话..."
            className="h-10 w-full rounded-xl border border-border bg-card pl-9 pr-3 text-sm text-foreground placeholder:text-secondary-text/60 focus:border-foreground/30 focus:outline-none"
            onFocus={() => void handleOpenHistoryDrawer()}
            readOnly
          />
        </div>

        <p className="shrink-0 text-sm text-secondary-text">
          {analysis?.status === 'completed' && generationModel ? (
            <>{generationMode === 'llm' ? `模型 ${generationModel}` : 'Fallback 生成'}</>
          ) : null}
          {analysis?.status === 'completed' && referenceSources.length > 0 ? (
            <> · 引用 {referenceSources.length} 条</>
          ) : null}
        </p>
      </div>

      {/* ---- Analysis Tabs ---- */}
      {(analysis || analysisId || queryId) ? (
        <div className="mt-4 flex items-center gap-1.5">
          {ANALYSIS_TABS.map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => setActiveTab(tab.key)}
              className={`rounded-lg px-4 py-1.5 text-sm font-medium transition-colors ${
                activeTab === tab.key
                  ? 'bg-foreground text-background'
                  : 'text-secondary-text hover:bg-elevated hover:text-foreground'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      ) : null}

      {/* ---- Error alerts ---- */}
      {error ? <div className="mt-4"><ApiErrorAlert error={error} onDismiss={() => setError(null)} /></div> : null}

      {/* ---- Main two-column grid ---- */}
      <div className="mt-5 grid min-w-0 gap-5 xl:grid-cols-[1fr_340px]">

        {/* ======================== LEFT COLUMN ======================== */}
        <div className="min-w-0 space-y-5">

          {/* ---- Stock header card ---- */}
          {analysis ? (
            <Card padding="lg" className="!rounded-2xl">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <div className="flex items-center gap-3">
                    <h2 className="text-3xl font-bold text-foreground">{analysis.stockName}</h2>
                    <span className="rounded-md border border-border px-2 py-0.5 text-sm text-secondary-text">{analysis.stockCode}</span>
                    {analysis.action ? (
                      <Badge variant={actionVariant(analysis.action)} size="sm" className="border-danger/30 bg-danger/90 text-white">
                        {actionLabel(analysis.action)}
                      </Badge>
                    ) : null}
                  </div>
                  {/* Tags */}
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    {themeTags.map((tag) => (
                      <span key={tag} className="rounded-full border border-border bg-elevated/60 px-3 py-1 text-xs font-medium text-foreground">
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="flex items-center gap-6">
                  {/* Price */}
                  {stockResult?.currentPrice ? (
                    <div className="text-right">
                      <p className="text-3xl font-bold text-foreground">{formatNumber(stockResult.currentPrice)}</p>
                      <p className={`mt-0.5 text-lg font-semibold ${(stockResult.pctChg ?? 0) >= 0 ? 'text-success' : 'text-danger'}`}>
                        {(stockResult.pctChg ?? 0) > 0 ? '+' : ''}{formatNumber(stockResult.pctChg)}%
                      </p>
                    </div>
                  ) : null}
                  {/* Score circle */}
                  {confidence != null ? (
                    <div className="flex flex-col items-center">
                      <div className="flex h-16 w-16 items-center justify-center rounded-full border-4 border-foreground/15">
                        <span className="text-xl font-bold text-foreground">{confidence}</span>
                      </div>
                      <p className="mt-1 text-xs text-secondary-text">
                        {tradePlan?.actionLabel || actionLabel(analysis.action)}
                      </p>
                    </div>
                  ) : null}
                </div>
              </div>
            </Card>
          ) : null}

          {/* ---- Tab: AI 对话 ---- */}
          {activeTab === 'chat' ? (<>

          {/* ---- Empty state ---- */}
          {!queryId && !analysisId ? (
            <Card padding="lg" className="!rounded-2xl">
              <EmptyState
                title="深度分析历史"
                description="这里可以直接查看已经生成过的深度分析历史。你也可以先在单股查询页发起新的深度分析，再回到这里持续跟踪。"
                icon={<BrainCircuit className="h-8 w-8" />}
                action={<Link to="/stock-query"><Button className="rounded-xl">前往单股查询</Button></Link>}
              />
            </Card>
          ) : null}

          {/* ---- Loading state ---- */}
          {loading && !analysis ? (
            <Card padding="lg" className="!rounded-2xl">
              <div className="flex items-center gap-4">
                <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-foreground/5">
                  <RefreshCw className="h-5 w-5 animate-spin text-foreground" />
                </div>
                <div>
                  <p className="text-lg font-semibold text-foreground">正在生成深度分析...</p>
                  <p className="mt-1 text-sm text-secondary-text">已切到后台任务模式，可以等待或稍后再回来。</p>
                </div>
              </div>
            </Card>
          ) : null}

          {/* ---- Processing / Failed state ---- */}
          {analysis && analysis.status !== 'completed' ? (
            <Card padding="lg" className="!rounded-2xl">
              <div className="flex items-center gap-3">
                {analysis.status === 'failed' ? (
                  <AlertTriangle className="h-5 w-5 text-danger" />
                ) : (
                  <RefreshCw className="h-5 w-5 animate-spin text-foreground" />
                )}
                <div>
                  <p className="text-base font-semibold text-foreground">
                    {analysis.status === 'failed' ? '深度分析生成失败' : '深度分析正在后台处理'}
                  </p>
                  <p className="mt-1 text-sm text-secondary-text">
                    {analysis.error || '可以离开当前页面，稍后再回来查看结果。'}
                  </p>
                </div>
              </div>
            </Card>
          ) : null}

          {/* ---- Chat / Analysis Content ---- */}
          {analysis?.status === 'completed' ? (
            <Card padding="lg" className="!rounded-2xl">
              {/* Chat header */}
              <div className="flex items-center justify-between gap-3 border-b border-border pb-4">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-foreground/5 text-sm font-bold text-foreground">AI</div>
                  <div>
                    <p className="font-semibold text-foreground">深度分析 · 对话模式</p>
                    <p className="text-xs text-secondary-text">
                      {generationMode === 'llm' ? `${generationModel || 'LLM'}` : 'Fallback'}
                      {referenceSources.length > 0 ? ` · ${referenceSources.length} 条引用` : ''}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    className="rounded-xl"
                    isLoading={regenerateLoading}
                    loadingText="生成中..."
                    onClick={() => void handleRegenerate()}
                    disabled={!queryId && !analysis.sourceQueryId}
                  >
                    <RefreshCw className="h-3.5 w-3.5" />
                    重新生成
                  </Button>
                </div>
              </div>

              {/* Initial AI response: summary + trade plan */}
              <div className="mt-5 space-y-5">
                {/* Summary text */}
                {analysis.summary ? (
                  <p className="text-sm leading-7 text-foreground">{analysis.summary}</p>
                ) : null}

                {/* Multi-dimensional score card */}
                {(analysis.technical || analysis.fundamental || tradePlan) ? (
                  <div className="rounded-xl border border-border bg-elevated/20 px-5 py-4">
                    <div className="flex items-center justify-between">
                      <p className="text-xs uppercase tracking-widest text-secondary-text">五 维 评 分 · Multi-Dimensional Score</p>
                      {confidence != null ? <p className="text-sm text-secondary-text">综合 {confidence} / 100</p> : null}
                    </div>
                    <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
                      <ScoreDimension label="基本面" value={analysis.fundamental?.assessment ? 'A' : '--'} sub={analysis.fundamental?.assessment?.slice(0, 8) || '--'} />
                      <ScoreDimension label="估值面" value={stockResult?.peRatio ? formatNumber(stockResult.peRatio, 0) : '--'} sub={stockResult?.peRatio ? 'PE(TTM)' : '--'} />
                      <ScoreDimension label="技术面" value={analysis.technical?.trendScore ? String(Math.round(analysis.technical.trendScore)) : '--'} sub={analysis.technical?.trendStatus || '--'} />
                      <ScoreDimension label="主题热度" value={themeTags.length > 0 ? String(themeTags.length) : '--'} sub={themeTags[0] || '--'} />
                      <ScoreDimension label="资金流向" value={stockResult?.buySignal || '--'} sub={analysis.technical?.buySignal || '--'} />
                    </div>
                  </div>
                ) : null}

                {/* Trade plan levels */}
                {levels ? (
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                    <LevelCard label="试仓位" value={formatNumber(levels.trialPrice)} />
                    <LevelCard label="确认位" value={formatNumber(levels.confirmPrice)} />
                    <LevelCard label="止损位" value={formatNumber(levels.stopLoss)} />
                    <LevelCard label="目标位" value={formatNumber(levels.targetPrice)} />
                  </div>
                ) : null}

                {/* Technical + fundamental assessment */}
                {analysis.technical?.assessment ? (
                  <div className="text-sm leading-7 text-foreground">
                    <p className="font-semibold">技术确认：</p>
                    <p className="mt-1 text-secondary-text">{analysis.technical.assessment}</p>
                  </div>
                ) : null}
                {analysis.fundamental?.assessment ? (
                  <div className="text-sm leading-7 text-foreground">
                    <p className="font-semibold">基本面质量：</p>
                    <p className="mt-1 text-secondary-text">{analysis.fundamental.assessment}</p>
                  </div>
                ) : null}

                {/* Risk items */}
                {(analysis.risk?.items ?? []).length > 0 ? (
                  <div className="text-sm leading-7 text-foreground">
                    <p className="font-semibold">风险清单：</p>
                    <div className="mt-2 space-y-1">
                      {(analysis.risk?.items ?? []).map((item, i) => (
                        <div key={`risk-${i}`} className="flex items-start gap-2 text-secondary-text">
                          <AlertTriangle className="mt-1 h-3.5 w-3.5 shrink-0 text-warning" />
                          <span>{item}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}

                {/* Execution steps */}
                {(tradePlan?.triggers ?? []).length > 0 ? (
                  <div className="text-sm leading-7 text-foreground">
                    <p className="font-semibold">执行步骤：</p>
                    <div className="mt-2 space-y-1">
                      {(tradePlan?.triggers ?? []).map((step, i) => (
                        <p key={`step-${i}`} className="text-secondary-text">
                          <span className="mr-2 inline-flex h-5 w-5 items-center justify-center rounded-full border border-border text-xs">{i + 1}</span>
                          {step}
                        </p>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>

              {/* ---- Chat messages ---- */}
              {analysisMessages.length > 0 ? (
                <div className="mt-6 space-y-4 border-t border-border pt-5">
                  {analysisMessages.map((msg: StockDeepAnalysisMessage) => (
                    <div key={msg.id} className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
                      <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-bold ${msg.role === 'user' ? 'bg-foreground text-background' : 'bg-foreground/10 text-foreground'}`}>
                        {msg.role === 'user' ? '我' : 'TP'}
                      </div>
                      <div className={`max-w-[80%] rounded-2xl px-4 py-3 ${msg.role === 'user' ? 'bg-foreground text-background' : 'border border-border bg-elevated/30 text-foreground'}`}>
                        <p className="text-xs text-current/60">{msg.role === 'user' ? 'YOU' : 'THEME PICKER AI'} · {formatShortTime(msg.createdAt)}</p>
                        <p className="mt-1 text-sm leading-7">{msg.content}</p>
                      </div>
                    </div>
                  ))}
                  <div ref={chatEndRef} />
                </div>
              ) : null}

              {/* ---- Chat input ---- */}
              <form className="mt-5 border-t border-border pt-4" onSubmit={(event) => void handleSendChat(event)}>
                {chatError ? <div className="mb-3"><ApiErrorAlert error={chatError} onDismiss={() => setChatError(null)} /></div> : null}
                <div className="flex items-center gap-2">
                  <input
                    value={followUp}
                    onChange={(e) => setFollowUp(e.target.value)}
                    placeholder="继续追问，例如：为什么现在不适合买？"
                    className="h-10 min-w-0 flex-1 rounded-xl border border-border bg-card px-4 text-sm text-foreground placeholder:text-secondary-text/60 focus:border-foreground/30 focus:outline-none"
                  />
                  <Button
                    type="submit"
                    size="sm"
                    isLoading={chatLoading}
                    loadingText="追问中..."
                    disabled={!analysis.analysisId || !followUp.trim()}
                    className="h-10 rounded-xl px-4"
                  >
                    <ArrowRight className="h-3.5 w-3.5" />
                    发送
                  </Button>
                </div>
              </form>

              {/* ---- Alert rules generation ---- */}
              <div className="mt-5 border-t border-border pt-4">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm font-semibold text-foreground">生成告警规则</p>
                  <div className="flex items-center gap-2">
                    <Input
                      label=""
                      value={scanInterval}
                      onChange={(e) => setScanInterval(e.target.value)}
                      placeholder="间隔(分钟)"
                      className="h-8 w-20 rounded-lg text-xs"
                    />
                    <Button
                      size="sm"
                      className="rounded-lg"
                      isLoading={rulesLoading}
                      loadingText="生成中..."
                      onClick={() => void handleGenerateRules()}
                      disabled={!analysis.analysisId}
                    >
                      生成规则
                    </Button>
                  </div>
                </div>
                {rulesError ? <div className="mt-2"><ApiErrorAlert error={rulesError} onDismiss={() => setRulesError(null)} /></div> : null}
                {generatedRules.length > 0 ? (
                  <div className="mt-3 grid gap-2 sm:grid-cols-3">
                    {generatedRules.map((rule) => (
                      <div key={rule.id} className="rounded-xl border border-border bg-elevated/20 px-3 py-2.5">
                        <p className="text-sm font-medium text-foreground">{ruleTypeLabel(rule.ruleType)}</p>
                        <p className="mt-0.5 text-xs text-secondary-text">阈值 {formatNumber(rule.thresholdValue)} · {rule.scanIntervalMinutes}分钟</p>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            </Card>
          ) : null}

          {/* ---- History list when no analysis loaded ---- */}
          {!analysis && !loading && historyItems.length > 0 ? (
            <Card padding="lg" className="!rounded-2xl">
              <h3 className="text-lg font-semibold text-foreground">最近的深度分析</h3>
              <div className="mt-4 space-y-2">
                {historyItems.map((item) => (
                  <button
                    key={item.analysisId}
                    type="button"
                    onClick={() => void handleHistoryOpen(item)}
                    className="flex w-full items-start justify-between gap-3 rounded-xl px-3 py-3 text-left transition-colors hover:bg-elevated/30"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-foreground">
                        {item.stockName} <span className="text-secondary-text">{item.stockCode}</span>
                      </p>
                      <p className="mt-0.5 truncate text-xs text-secondary-text">
                        {item.summary || item.error || '点击查看'}
                      </p>
                    </div>
                    <div className="shrink-0 text-right">
                      <Badge variant={item.status === 'completed' ? actionVariant(item.action) : 'default'} size="sm">
                        {item.status === 'completed' ? actionLabel(item.action) : analysisStatusLabel(item.status)}
                      </Badge>
                      <p className="mt-1 text-xs text-secondary-text">{formatTime(item.updatedAt || item.createdAt)}</p>
                    </div>
                  </button>
                ))}
              </div>
            </Card>
          ) : null}

          </>) : null}

          {/* ---- Tab: placeholder tabs ---- */}
          {activeTab !== 'chat' ? (
            <Card padding="lg" className="!rounded-2xl">
              <EmptyState
                title={ANALYSIS_TABS.find((t) => t.key === activeTab)?.label ?? ''}
                description="该模块正在开发中，敬请期待。"
                icon={<BrainCircuit className="h-8 w-8" />}
              />
            </Card>
          ) : null}
        </div>

        {/* ======================== RIGHT COLUMN ======================== */}
        <div className="min-w-0 space-y-5">

          {/* ---- 本次对话引用 ---- */}
          {referenceSources.length > 0 ? (
            <Card padding="lg" className="!rounded-2xl">
              <h3 className="text-lg font-semibold text-foreground">本次对话引用 · {referenceSources.length} 条</h3>
              <div className="mt-4 space-y-3">
                {referenceSources.map((src, i) => (
                  <div key={`ref-${i}`} className="flex items-start gap-3">
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-border text-xs text-foreground">{i + 1}</span>
                    <div className="min-w-0">
                      <p className="text-xs text-secondary-text">{src.type}</p>
                      <p className="mt-0.5 text-sm text-foreground">{src.title}</p>
                      {src.date ? <p className="mt-0.5 text-xs text-secondary-text">{src.date}</p> : null}
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          ) : null}

          {/* ---- 常用问题模板 ---- */}
          {analysis?.status === 'completed' ? (
            <Card padding="lg" className="!rounded-2xl">
              <h3 className="text-lg font-semibold text-foreground">常用问题模板</h3>
              <div className="mt-4 space-y-2">
                {QUESTION_TEMPLATES.map((tmpl) => (
                  <button
                    key={tmpl.question}
                    type="button"
                    onClick={() => setFollowUp(tmpl.question)}
                    className="w-full rounded-xl border border-border px-3 py-2.5 text-left transition-colors hover:bg-elevated/30"
                  >
                    <p className="text-xs font-medium text-secondary-text">{tmpl.category}</p>
                    <p className="mt-0.5 text-sm text-foreground">{tmpl.question}</p>
                  </button>
                ))}
              </div>
            </Card>
          ) : null}

          {/* ---- 对话历史 ---- */}
          <Card padding="lg" className="!rounded-2xl">
            <h3 className="text-lg font-semibold text-foreground">
              对话历史{analysis ? ` · ${analysis.stockName}` : ''}
            </h3>
            <div className="mt-4 space-y-2">
              {recentHistoryItems.length > 0 ? recentHistoryItems.map((item) => (
                <button
                  key={item.analysisId}
                  type="button"
                  onClick={() => void handleHistoryOpen(item)}
                  className="w-full rounded-xl px-2 py-2.5 text-left transition-colors hover:bg-elevated/30"
                >
                  <p className="truncate text-sm font-medium text-foreground">
                    {item.summary?.slice(0, 25) || actionLabel(item.action)}
                  </p>
                  <p className="mt-0.5 truncate text-xs text-secondary-text">
                    {formatTime(item.updatedAt || item.createdAt)} · {item.messages.length} 轮 · {referenceSources.length} 引用
                  </p>
                </button>
              )) : (
                <p className="text-sm text-secondary-text">
                  {analysis?.stockCode ? '这只股票还没有更多深度分析历史。' : '这里会显示最近的深度分析历史。'}
                </p>
              )}
              {recentHistoryItems.length > 0 ? (
                <button
                  type="button"
                  onClick={() => void handleOpenHistoryDrawer()}
                  className="mt-2 w-full rounded-xl border border-dashed border-border py-2.5 text-sm text-secondary-text transition-colors hover:border-foreground/30 hover:text-foreground"
                >
                  查看全部对话 →
                </button>
              ) : null}
            </div>
          </Card>

          {/* ---- Quick actions ---- */}
          {analysis ? (
            <div className="flex gap-2">
              <Link
                to={`/stock-query?stock=${encodeURIComponent(analysis.stockCode)}`}
                className="flex-1 rounded-xl border border-border bg-card py-2.5 text-center text-sm text-foreground transition-colors hover:bg-elevated"
              >
                返回单股查询
              </Link>
              <Link
                to="/watchlist"
                className="flex-1 rounded-xl border border-border bg-card py-2.5 text-center text-sm text-foreground transition-colors hover:bg-elevated"
              >
                观察池
              </Link>
            </div>
          ) : null}
        </div>
      </div>

      {/* ---- History Drawer ---- */}
      <Drawer isOpen={historyDrawerOpen} onClose={() => setHistoryDrawerOpen(false)} title="深度分析历史" width="max-w-xl" side="right">
        <div className="space-y-4">
          {allHistoryError ? <ApiErrorAlert error={allHistoryError} /> : null}
          {allHistoryLoading ? <InlineAlert variant="info" title="正在加载" message="正在读取最近的深度分析记录。" /> : null}
          {!allHistoryLoading && allHistoryItems.length === 0 ? (
            <EmptyState title="暂无深度分析历史" description="完成几次深度分析后，这里会显示完整历史。" icon={<Clock3 className="h-8 w-8" />} />
          ) : null}
          <div className="space-y-3">
            {allHistoryItems.map((item) => {
              const active = item.analysisId === analysis?.analysisId;
              return (
                <div key={item.analysisId} className={`rounded-2xl border px-4 py-4 transition-colors ${active ? 'border-foreground/20 bg-foreground/5' : 'border-border/60 bg-background/70'}`}>
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
                  <p className="mt-2 text-sm text-secondary-text">{item.summary || item.error || '无摘要'}</p>
                  <div className="mt-3 flex justify-end">
                    <Button variant="outline" size="sm" onClick={() => { void handleHistoryOpen(item); setHistoryDrawerOpen(false); }}>
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

const ScoreDimension: React.FC<{ label: string; value: string; sub: string }> = ({ label, value, sub }) => (
  <div>
    <p className="text-xs text-secondary-text">{label}</p>
    <p className="mt-1 text-2xl font-bold text-foreground">{value}</p>
    <div className="mt-1.5 h-1 w-full rounded-full bg-foreground/15" />
    <p className="mt-1 text-xs text-secondary-text">{sub}</p>
  </div>
);

const LevelCard: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="rounded-xl border border-border bg-elevated/20 px-3 py-3">
    <p className="text-xs text-secondary-text">{label}</p>
    <p className="mt-1 text-xl font-bold text-foreground">{value}</p>
  </div>
);

export default DeepAnalysisPage;
