import type React from 'react';
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowRight,
  Bookmark,
  BrainCircuit,
  ChevronRight,
  Clock3,
  Flame,
  Layers3,
  Newspaper,
  Sparkles,
  Star,
  Target,
  TrendingUp,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import {
  themePickerApi,
  type ThemePickerTaskHistoryItem,
  type ThemePickerScanResponse,
  type ThemePickerSelectedStock,
  type ThemePickerStockItem,
  type ThemePickerStrategyMode,
  type ThemePickerTaskStatus,
  type ThemePickerThemeListItem,
} from '../api/themePicker';
import type { ParsedApiError } from '../api/error';
import { createParsedApiError, getParsedApiError } from '../api/error';
import { ApiErrorAlert, AppPage, Badge, Button, Card, Drawer, EmptyState, InlineAlert, Input, Select } from '../components/common';

const STRATEGY_OPTIONS: Array<{ value: ThemePickerStrategyMode; label: string }> = [
  { value: 'holding', label: '趋势持有' },
  { value: 'event', label: '短线异动' },
];

const DEFAULT_MAX_CANDIDATES = 8;
const MIN_MAX_CANDIDATES = 1;
const MAX_MAX_CANDIDATES = 50;

type QueryMode =
  | 'theme_id'
  | 'board_code'
  | 'board_name'
  | 'theme_name'
  | 'empty';

type ResolvedScanPayload = {
  themeId?: string;
  themeName?: string;
  boardCode?: string;
  boardName?: string;
  strategyMode: ThemePickerStrategyMode;
  maxCandidates: number;
};

type QueryIntent = {
  mode: QueryMode;
  title: string;
  description: string;
  detail: string;
  payload: ResolvedScanPayload;
  effectiveFields: string[];
};

function formatNumber(value?: number | null, digits = 2): string {
  if (value == null || Number.isNaN(value)) return '--';
  return value.toFixed(digits);
}

function formatPercent(value?: number | null, digits = 1): string {
  if (value == null || Number.isNaN(value)) return '--';
  return `${value.toFixed(digits)}%`;
}

function signalBadgeVariant(signalLevel: string): 'success' | 'info' | 'warning' | 'danger' | 'default' {
  if (signalLevel === '优先关注') return 'danger';
  if (signalLevel === '持有候选') return 'warning';
  if (signalLevel === '低吸观察') return 'info';
  if (signalLevel === '不宜追高') return 'default';
  if (signalLevel === '主题触发') return 'success';
  return 'default';
}

function themeRelevanceLabel(value?: string | null): string {
  if (!value) return '待判定';
  if (value === 'high') return '强相关';
  if (value === 'medium') return '中等相关';
  if (value === 'low') return '弱相关';
  return value;
}

function themeRelevanceScore(value?: string | null): number {
  if (value === 'high') return 92;
  if (value === 'medium') return 76;
  if (value === 'low') return 58;
  return 68;
}

function heatLevelLabel(value?: string | null): string {
  if (value === 'high') return '高';
  if (value === 'medium') return '中';
  if (value === 'low') return '低';
  return '待判定';
}

function dataCompletenessLabel(value?: string | null): string {
  if (value === 'full_realtime') return '实时完整';
  if (value === 'partial_realtime') return '实时部分';
  if (value === 'daily_only') return '仅日线';
  return '待补充';
}

function priceLabel(value?: string | null): string {
  if (value === 'daily_only') return '最新收盘';
  return '现价';
}

function trendBandLabel(score?: number | null): string {
  if (score == null || Number.isNaN(score)) return '待判定';
  if (score >= 75) return '较强';
  if (score >= 60) return '中上';
  if (score >= 50) return '中性';
  return '偏弱';
}

function sourceLabel(value?: string | null): string {
  if (value === 'tushare_dc') return 'Tushare 题材';
  if (value === 'eastmoney_board') return '东方财富板块';
  if (value === 'search_service') return '新闻检索';
  if (value === 'tencent') return '腾讯实时';
  if (value === 'mixed') return '混合实时';
  if (value === 'multi_source_daily') return '多源日线';
  return value || '--';
}

function boardSourceConfidenceLabel(value?: string | null): string {
  if (value === 'high') return '高可信';
  if (value === 'medium') return '中可信';
  if (value === 'low') return '低可信';
  return '待判定';
}

function pricingSourceLabel(value?: string | null): string {
  if (value === 'realtime_enhanced') return '实时增强';
  if (value === 'mixed') return '实时/日线混合';
  if (value === 'daily_only') return '仅日线补算';
  return '待判定';
}

function taskStatusLabel(status: string): string {
  if (status === 'completed') return '已完成';
  if (status === 'failed') return '失败';
  if (status === 'processing') return '进行中';
  return '排队中';
}

function clampMaxCandidates(value: number): number {
  if (Number.isNaN(value)) return DEFAULT_MAX_CANDIDATES;
  return Math.min(MAX_MAX_CANDIDATES, Math.max(MIN_MAX_CANDIDATES, value));
}

function buildQueryIntent(params: {
  themeId: string;
  themeName: string;
  boardCode: string;
  boardName: string;
  strategyMode: ThemePickerStrategyMode;
  maxCandidates: number;
}): QueryIntent {
  const themeId = params.themeId.trim();
  const themeName = params.themeName.trim();
  const boardCode = params.boardCode.trim().toUpperCase();
  const boardName = params.boardName.trim();

  const basePayload = {
    strategyMode: params.strategyMode,
    maxCandidates: params.maxCandidates,
  };

  if (themeId) {
    return {
      mode: 'theme_id',
      title: '已注册主题',
      description: `当前会按主题 ID 直连配置检索：${themeId}`,
      detail: '优先使用主题注册表中的板块、映射和策略配置；其余输入仅作展示，不参与本次提交。',
      effectiveFields: ['themeId'],
      payload: {
        ...basePayload,
        themeId,
      },
    };
  }

  if (boardCode) {
    return {
      mode: 'board_code',
      title: '板块代码直检',
      description: `当前会按板块代码检索：${boardCode}`,
      detail: boardName
        ? `板块名称“${boardName}”仅作辅助展示，不参与提交。`
        : '如果同时填写了主题名称，主题名称仅作页面展示，不参与提交。',
      effectiveFields: ['boardCode'],
      payload: {
        ...basePayload,
        boardCode,
      },
    };
  }

  if (boardName) {
    return {
      mode: 'board_name',
      title: '板块名称检索',
      description: `当前会按板块名称检索：${boardName}`,
      detail: themeName
        ? `主题名称“${themeName}”仅作页面展示，不参与提交。`
        : '系统会优先尝试结构化板块名称匹配，再决定是否降级。',
      effectiveFields: ['boardName'],
      payload: {
        ...basePayload,
        boardName,
      },
    };
  }

  if (themeName) {
    return {
      mode: 'theme_name',
      title: '主题名称检索',
      description: `当前会按主题名称检索：${themeName}`,
      detail: '系统会从主题名称出发匹配板块和新闻，不依赖已注册主题 ID。',
      effectiveFields: ['themeName'],
      payload: {
        ...basePayload,
        themeName,
      },
    };
  }

  return {
    mode: 'empty',
    title: '等待输入',
    description: '请输入主题名称、板块代码或板块名称。',
    detail: '支持三种入口：已注册主题、板块直检、主题名称检索。',
    effectiveFields: [],
    payload: {
      ...basePayload,
    },
  };
}

function selectedStockFromResult(result: ThemePickerScanResponse | null): ThemePickerSelectedStock | null {
  if (!result) return null;
  if (result.selectedStock) return result.selectedStock;
  const first = result.stocks[0];
  if (!first) return null;
    return {
      stockCode: first.stockCode,
      stockName: first.stockName,
      themeRelevance: 'medium',
      currentPrice: first.currentPrice ?? null,
      pctChg: first.pctChg ?? null,
      volumeRatio: first.volumeRatio ?? null,
      turnoverRate: first.turnoverRate ?? null,
      trendScore: first.trendScore ?? null,
      trendStatus: null,
      buySignal: first.buySignal ?? null,
      currentPattern: first.currentPattern ?? null,
      dataCompleteness: first.dataCompleteness ?? null,
      resonanceCount: null,
      ma5: null,
      ma10: null,
      ma20: null,
    biasMa5: null,
    biasMa10: null,
    biasMa20: null,
    recentStrongDays: null,
    supportLevel: first.supportLevel ?? null,
    pressureLevel: first.pressureLevel ?? null,
    newsSummary: [],
    selectedReasons: first.miniReasons.length > 0 ? first.miniReasons : [first.selectionReason],
    riskReasons: first.riskNote ? [first.riskNote] : [],
    dataSources: {},
  };
}

function deriveSelectedStock(stock: ThemePickerStockItem, result: ThemePickerScanResponse): ThemePickerSelectedStock {
  if (result.selectedStock?.stockCode === stock.stockCode) {
    return result.selectedStock;
  }

    return {
      stockCode: stock.stockCode,
      stockName: stock.stockName,
      themeRelevance: result.selectedStock?.themeRelevance ?? 'medium',
    currentPrice: stock.currentPrice ?? result.selectedStock?.currentPrice ?? null,
    pctChg: stock.pctChg ?? result.selectedStock?.pctChg ?? null,
    volumeRatio: stock.volumeRatio ?? result.selectedStock?.volumeRatio ?? null,
    turnoverRate: stock.turnoverRate ?? result.selectedStock?.turnoverRate ?? null,
    trendScore: stock.trendScore ?? null,
    trendStatus: result.selectedStock?.trendStatus ?? null,
    buySignal: stock.buySignal ?? null,
    currentPattern: stock.currentPattern ?? result.selectedStock?.currentPattern ?? null,
    dataCompleteness: stock.dataCompleteness ?? result.selectedStock?.dataCompleteness ?? null,
    resonanceCount: result.selectedStock?.resonanceCount ?? null,
    newsSummary: result.selectedStock?.newsSummary ?? [],
    selectedReasons: stock.miniReasons.length > 0 ? stock.miniReasons : [stock.selectionReason],
    riskReasons: stock.riskNote ? [stock.riskNote] : [],
    dataSources: result.selectedStock?.dataSources ?? {},
    ma5: result.selectedStock?.ma5 ?? null,
    ma10: result.selectedStock?.ma10 ?? null,
    ma20: result.selectedStock?.ma20 ?? null,
    biasMa5: result.selectedStock?.biasMa5 ?? null,
    biasMa10: result.selectedStock?.biasMa10 ?? null,
    biasMa20: result.selectedStock?.biasMa20 ?? null,
    recentStrongDays: result.selectedStock?.recentStrongDays ?? null,
    supportLevel: stock.supportLevel ?? result.selectedStock?.supportLevel ?? null,
    pressureLevel: stock.pressureLevel ?? result.selectedStock?.pressureLevel ?? null,
  };
}

const ThemeStockPickerPage: React.FC = () => {
  const navigate = useNavigate();
  const [themeId, setThemeId] = useState('');
  const [themeName, setThemeName] = useState('');
  const [boardCode, setBoardCode] = useState('');
  const [boardName, setBoardName] = useState('');
  const [strategyMode, setStrategyMode] = useState<ThemePickerStrategyMode>('holding');
  const [maxCandidates, setMaxCandidates] = useState<string>(String(DEFAULT_MAX_CANDIDATES));
  const [themes, setThemes] = useState<ThemePickerThemeListItem[]>([]);
  const [themesLoading, setThemesLoading] = useState(true);
  const [themesError, setThemesError] = useState<ParsedApiError | null>(null);
  const [scanLoading, setScanLoading] = useState(false);
  const [scanError, setScanError] = useState<ParsedApiError | null>(null);
  const [scanResult, setScanResult] = useState<ThemePickerScanResponse | null>(null);
  const [scanTask, setScanTask] = useState<ThemePickerTaskStatus | null>(null);
  const [selectedStock, setSelectedStock] = useState<ThemePickerSelectedStock | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyItems, setHistoryItems] = useState<ThemePickerTaskHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState<ParsedApiError | null>(null);
  const [historyActionTaskId, setHistoryActionTaskId] = useState<string | null>(null);
  const pollTimeoutRef = useRef<number | null>(null);
  const initialHistoryAppliedRef = useRef(false);
  const scanLoadingRef = useRef(false);
  const scanResultRef = useRef<ThemePickerScanResponse | null>(null);
  const scanTaskRef = useRef<ThemePickerTaskStatus | null>(null);

  useEffect(() => {
    document.title = '主题选股 - DSA';
  }, []);

  useEffect(() => {
    scanLoadingRef.current = scanLoading;
  }, [scanLoading]);

  useEffect(() => {
    scanResultRef.current = scanResult;
  }, [scanResult]);

  useEffect(() => {
    scanTaskRef.current = scanTask;
  }, [scanTask]);

  useEffect(() => () => {
    if (pollTimeoutRef.current != null) {
      window.clearTimeout(pollTimeoutRef.current);
    }
  }, []);

  useEffect(() => {
    let active = true;
    const loadThemes = async () => {
      setThemesLoading(true);
      try {
        const response = await themePickerApi.getThemes();
        if (!active) return;
        setThemes(response.items);
        setThemesError(null);
      } catch (error) {
        if (!active) return;
        setThemesError(getParsedApiError(error));
      } finally {
        if (active) setThemesLoading(false);
      }
    };
    void loadThemes();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    const loadHistory = async () => {
      setHistoryLoading(true);
      try {
        const response = await themePickerApi.getHistory(20);
        if (!active) return;
        setHistoryItems(response.items);
        setHistoryError(null);

        if (
          !initialHistoryAppliedRef.current
          && !scanLoadingRef.current
          && !scanResultRef.current
          && !scanTaskRef.current
        ) {
          const latestCompleted = response.items.find((item) => item.status === 'completed' && item.result);
          if (latestCompleted?.result) {
            initialHistoryAppliedRef.current = true;
            setScanTask({
              taskId: latestCompleted.taskId,
              status: latestCompleted.status,
              progress: latestCompleted.progress,
              message: latestCompleted.message,
              createdAt: latestCompleted.createdAt,
              startedAt: latestCompleted.startedAt,
              completedAt: latestCompleted.completedAt,
              result: latestCompleted.result,
              error: latestCompleted.error,
            });
            applyResultToPage(latestCompleted.result);
          }
        }
      } catch (error) {
        if (!active) return;
        setHistoryError(getParsedApiError(error));
      } finally {
        if (active) setHistoryLoading(false);
      }
    };
    void loadHistory();
    return () => {
      active = false;
    };
  }, []);

  const hasQuery = Boolean(themeId || themeName.trim() || boardCode.trim() || boardName.trim());
  const normalizedMaxCandidates = clampMaxCandidates(Number.parseInt(maxCandidates, 10));
  const queryIntent = useMemo(
    () => buildQueryIntent({
      themeId,
      themeName,
      boardCode,
      boardName,
      strategyMode,
      maxCandidates: normalizedMaxCandidates,
    }),
    [themeId, themeName, boardCode, boardName, strategyMode, normalizedMaxCandidates],
  );

  const quickThemes = useMemo(() => themes.slice(0, 6), [themes]);

  const handleQuickTheme = (item: ThemePickerThemeListItem) => {
    setThemeId(item.id);
    setThemeName(item.name);
    setBoardCode(item.boardCodes[0] ?? '');
    setBoardName(item.boardNames[0] ?? '');
    setStrategyMode(item.strategyMode ?? 'holding');
  };

  const handleThemeNameChange = (value: string) => {
    const hadThemeBinding = Boolean(themeId);
    setThemeId('');
    setThemeName(value);
    if (hadThemeBinding) {
      setBoardCode('');
      setBoardName('');
    }
  };

  const handleBoardCodeChange = (value: string) => {
    setThemeId('');
    setBoardCode(value.toUpperCase());
  };

  const handleBoardNameChange = (value: string) => {
    setThemeId('');
    setBoardName(value);
  };

  const handleDeepAnalyze = (stockCode: string, stockName: string) => {
    navigate(`/chat?stock=${encodeURIComponent(stockCode)}&name=${encodeURIComponent(stockName)}`);
  };

  const handleSingleStockAnalyze = (stockCode: string, stockName: string) => {
    navigate(`/stock-query?stock=${encodeURIComponent(stockCode)}&name=${encodeURIComponent(stockName)}`);
  };

  const applyResultToPage = (result: ThemePickerScanResponse) => {
    setScanResult(result);
    setSelectedStock(selectedStockFromResult(result));
    setThemeId(result.query.themeId ?? '');
    setThemeName(result.query.themeName ?? '');
    setBoardCode(result.query.boardCode ?? '');
    setBoardName(result.query.boardName ?? '');
    setStrategyMode(result.query.strategyMode);
    setMaxCandidates(String(result.query.maxCandidates ?? DEFAULT_MAX_CANDIDATES));
  };

  const refreshHistory = async () => {
    try {
      const response = await themePickerApi.getHistory(20);
      setHistoryItems(response.items);
      setHistoryError(null);
    } catch (error) {
      setHistoryError(getParsedApiError(error));
    } finally {
      setHistoryLoading(false);
    }
  };

  const handleHistorySelect = (item: ThemePickerTaskHistoryItem) => {
    if (!item.result) return;
    setScanTask({
      taskId: item.taskId,
      status: item.status,
      progress: item.progress,
      message: item.message,
      createdAt: item.createdAt,
      startedAt: item.startedAt,
      completedAt: item.completedAt,
      result: item.result,
      error: item.error,
    });
    setScanError(null);
    setScanLoading(false);
    applyResultToPage(item.result);
    setHistoryOpen(false);
  };

  const handleHistoryRetry = async (item: ThemePickerTaskHistoryItem) => {
    if (pollTimeoutRef.current != null) {
      window.clearTimeout(pollTimeoutRef.current);
      pollTimeoutRef.current = null;
    }
    setHistoryActionTaskId(item.taskId);
    setScanError(null);
    try {
      const accepted = await themePickerApi.retry(item.taskId);
      setHistoryOpen(false);
      setScanResult(null);
      setSelectedStock(null);
      setScanLoading(true);
      setScanTask({
        taskId: accepted.taskId,
        status: accepted.status,
        progress: 0,
        message: accepted.message,
        createdAt: new Date().toISOString(),
      });
      await pollScanStatus(accepted.taskId);
    } catch (error) {
      setHistoryError(getParsedApiError(error));
      setScanLoading(false);
    } finally {
      setHistoryActionTaskId(null);
    }
  };

  const handleScan = async () => {
    if (!hasQuery) return;
    if (pollTimeoutRef.current != null) {
      window.clearTimeout(pollTimeoutRef.current);
      pollTimeoutRef.current = null;
    }

    setScanLoading(true);
    setScanError(null);
    setScanResult(null);
    setSelectedStock(null);

    setMaxCandidates(String(normalizedMaxCandidates));

    try {
      const accepted = await themePickerApi.scan(queryIntent.payload);

      setScanTask({
        taskId: accepted.taskId,
        status: accepted.status,
        progress: 0,
        message: accepted.message,
        createdAt: new Date().toISOString(),
      });

      await pollScanStatus(accepted.taskId);
    } catch (error) {
      setScanError(getParsedApiError(error));
      setScanTask(null);
      setScanLoading(false);
    }
  };

  const pollScanStatus = async (taskId: string) => {
    try {
      const status = await themePickerApi.getScanStatus(taskId);
      setScanTask(status);

      if (status.status === 'completed' && status.result) {
        applyResultToPage(status.result);
        setScanLoading(false);
        pollTimeoutRef.current = null;
        void refreshHistory();
        return;
      }

      if (status.status === 'failed') {
        setScanError(createParsedApiError({
          title: '主题选股失败',
          message: status.error || status.message || '主题选股失败',
          status: 500,
        }));
        setScanLoading(false);
        pollTimeoutRef.current = null;
        void refreshHistory();
        return;
      }

      pollTimeoutRef.current = window.setTimeout(() => {
        void pollScanStatus(taskId);
      }, 5000);
    } catch (error) {
      setScanError(getParsedApiError(error));
      setScanLoading(false);
      pollTimeoutRef.current = null;
    }
  };

  const activeStockItem = useMemo(() => {
    if (!scanResult) return null;
    if (selectedStock) {
      return scanResult.stocks.find((item) => item.stockCode === selectedStock.stockCode) ?? scanResult.stocks[0] ?? null;
    }
    return scanResult.stocks[0] ?? null;
  }, [scanResult, selectedStock]);

  return (
    <AppPage className="space-y-6 !max-w-[1640px] px-3 md:px-5 lg:px-6">
      <section className="overflow-hidden rounded-[32px] border border-border/60 bg-[radial-gradient(circle_at_top_left,_rgba(6,182,212,0.14),_transparent_32%),linear-gradient(180deg,rgba(255,255,255,0.98),rgba(248,250,252,0.95))] shadow-soft-card dark:bg-[radial-gradient(circle_at_top_left,_rgba(34,211,238,0.18),_transparent_28%),radial-gradient(circle_at_top_right,_rgba(129,140,248,0.12),_transparent_30%),linear-gradient(180deg,rgba(10,15,26,0.98),rgba(14,20,32,0.95))]">
        <div className="grid gap-6 px-5 py-5 lg:grid-cols-[1.15fr_0.85fr] lg:px-7 lg:py-7">
          <div className="space-y-5">
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-center gap-4">
                <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-cyan/10 text-cyan shadow-soft-card">
                  <Target className="h-7 w-7" />
                </div>
                <div>
                  <h1 className="text-3xl font-semibold tracking-tight text-foreground">主题选股</h1>
                  <p className="mt-1 text-sm text-secondary-text">围绕主题、板块与新闻热度，收敛出更值得继续看的优质股票。</p>
                </div>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-2xl border border-border/50 bg-card/80 px-4 py-4">
                <p className="text-xs uppercase tracking-[0.16em] text-secondary-text">最近主题</p>
                <p className="mt-3 text-lg font-semibold text-foreground">{scanResult?.themeInsight.themeName || themeName || '等待输入'}</p>
                <p className="mt-1 text-sm text-secondary-text">{scanResult?.themeInsight.matchedKeywords.slice(0, 2).join(' / ') || '自动识别主题主线与催化词'}</p>
              </div>
              <div className="rounded-2xl border border-border/50 bg-card/80 px-4 py-4">
                <p className="text-xs uppercase tracking-[0.16em] text-secondary-text">板块路径</p>
                <p className="mt-3 text-lg font-semibold text-foreground">{scanResult?.themeInsight.boardMappingPath || boardCode || boardName || '--'}</p>
                <p className="mt-1 text-sm text-secondary-text">优先结构化板块，异常时自动回退备用源</p>
              </div>
              <div className="rounded-2xl border border-border/50 bg-card/80 px-4 py-4">
                <p className="text-xs uppercase tracking-[0.16em] text-secondary-text">结果状态</p>
                <p className="mt-3 text-lg font-semibold text-foreground">
                  {scanTask ? taskStatusLabel(scanTask.status) : scanResult ? `${scanResult.stocks.length} 只股票` : '等待筛选'}
                </p>
                <p className="mt-1 text-sm text-secondary-text">
                  {scanTask?.message || '进入页面后会自动恢复最近一次已完成结果'}
                </p>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => setHistoryOpen(true)}
                className="inline-flex items-center gap-2 rounded-full border border-border/60 bg-background/80 px-4 py-2 text-sm text-foreground transition-colors hover:bg-hover/40 dark:bg-background/60"
              >
                <Clock3 className="h-4 w-4 text-cyan" />
                <span>历史记录</span>
              </button>
              <div className="inline-flex items-center gap-2 rounded-full border border-border/60 bg-background/80 px-4 py-2 text-sm text-secondary-text dark:bg-background/60">
                <Newspaper className="h-4 w-4" />
                <span>交易日 04-29</span>
              </div>
              <button
                type="button"
                className="inline-flex items-center gap-2 rounded-full border border-border/60 bg-background/80 px-4 py-2 text-sm text-secondary-text transition-colors hover:text-foreground dark:bg-background/60"
                aria-label="收藏主题选股"
              >
                <Bookmark className="h-4 w-4" />
                <span>收藏页面</span>
              </button>
            </div>
          </div>

          <Card variant="bordered" padding="lg" className="rounded-[28px] border-border/60 bg-card/90 shadow-soft-card">
            <div className="grid gap-4 md:grid-cols-2">
              <Input
                label="主题名称"
                name="theme-name"
                placeholder="例如 DeepSeek"
                value={themeName}
                onChange={(e) => handleThemeNameChange(e.target.value)}
              />
              <Input
                label="板块代码（可选）"
                name="board-code"
                placeholder="例如 BK1188 / 000858.DC"
                value={boardCode}
                onChange={(e) => handleBoardCodeChange(e.target.value)}
              />
              <Input
                label="板块名称（可选）"
                name="board-name"
                placeholder="例如 DeepSeek概念"
                value={boardName}
                onChange={(e) => handleBoardNameChange(e.target.value)}
              />
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">策略</label>
                <Select
                  value={strategyMode}
                  onChange={(value) => setStrategyMode(value as ThemePickerStrategyMode)}
                  options={STRATEGY_OPTIONS}
                />
              </div>
              <Input
                label="最大股票数量"
                name="max-candidates"
                type="number"
                min={MIN_MAX_CANDIDATES}
                max={MAX_MAX_CANDIDATES}
                step={1}
                placeholder={String(DEFAULT_MAX_CANDIDATES)}
                value={maxCandidates}
                onChange={(e) => setMaxCandidates(e.target.value)}
              />
              <div className="flex items-end">
                <Button
                  variant="primary"
                  size="xl"
                  className="h-11 w-full rounded-2xl"
                  onClick={() => void handleScan()}
                  isLoading={scanLoading}
                  loadingText="筛选中..."
                  disabled={!hasQuery}
                >
                  开始筛选
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>

            {themesError ? (
              <div className="mt-4">
                <ApiErrorAlert error={themesError} />
              </div>
            ) : null}

            <div className="mt-5 space-y-3">
              <p className="text-sm text-secondary-text">热门主题推荐</p>
              <div className="flex flex-wrap gap-2">
                {quickThemes.map((item) => {
                  const active = item.id === themeId;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => handleQuickTheme(item)}
                      className={[
                        'inline-flex items-center rounded-full border px-4 py-2 text-sm transition-all',
                        active
                          ? 'border-cyan/30 bg-primary-gradient text-primary-foreground shadow-lg shadow-cyan/20'
                          : 'border-border/60 bg-background/80 text-secondary-text hover:text-foreground',
                      ].join(' ')}
                    >
                      {item.name}
                    </button>
                  );
                })}
                {themesLoading ? <span className="text-sm text-secondary-text">主题加载中...</span> : null}
              </div>
            </div>

            <div className="mt-5 rounded-2xl border border-border/60 bg-background/70 px-4 py-4">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="default" className="border-border/60 bg-card px-3 py-1.5 text-xs text-foreground">
                  当前检索方式
                </Badge>
                <Badge
                  variant={queryIntent.mode === 'theme_id' ? 'info' : queryIntent.mode === 'empty' ? 'default' : 'success'}
                  className="border-0 px-3 py-1.5 text-xs"
                >
                  {queryIntent.title}
                </Badge>
                {queryIntent.effectiveFields.map((field) => (
                  <Badge key={field} variant="default" className="border-border/60 bg-card px-3 py-1.5 text-xs text-secondary-text">
                    提交字段 {field}
                  </Badge>
                ))}
              </div>
              <p className="mt-3 text-sm font-medium text-foreground">{queryIntent.description}</p>
              <p className="mt-2 text-sm leading-6 text-secondary-text">{queryIntent.detail}</p>
            </div>
          </Card>
        </div>
      </section>

      {scanError ? <ApiErrorAlert error={scanError} /> : null}

      {scanTask && scanLoading ? (
        <InlineAlert
          variant="info"
          title="主题选股任务进行中"
          message={`${scanTask.message || '正在执行主题选股'}（${scanTask.progress}%）`}
        />
      ) : null}

      {scanResult ? (
        <>
          <section className="grid gap-4 lg:grid-cols-4">
            <Card variant="bordered" padding="lg" className="rounded-[24px]">
              <div className="flex items-start gap-4">
                <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-500/10 text-blue-500">
                  <BrainCircuit className="h-7 w-7" />
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.16em] text-secondary-text">主题识别</p>
                  <p className="mt-3 text-2xl font-semibold text-foreground">{scanResult.themeInsight.themeName}</p>
                  <p className="mt-2 text-sm leading-6 text-secondary-text">{scanResult.themeInsight.matchedKeywords.join(' / ') || '--'}</p>
                </div>
              </div>
            </Card>

            <Card variant="bordered" padding="lg" className="rounded-[24px]">
              <div className="flex items-start gap-4">
                <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-500/10 text-emerald-500">
                  <Layers3 className="h-7 w-7" />
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.16em] text-secondary-text">板块映射</p>
                  <p className="mt-3 text-lg font-semibold text-foreground">{scanResult.themeInsight.boardMappingPath || '--'}</p>
                  <p className="mt-2 text-sm text-secondary-text">成分股 {scanResult.themeInsight.boardCandidateCount ?? '--'} 只</p>
                </div>
              </div>
            </Card>

            <Card variant="bordered" padding="lg" className="rounded-[24px]">
              <div className="flex items-start gap-4">
                <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-orange-500/10 text-orange-500">
                  <Flame className="h-7 w-7" />
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.16em] text-secondary-text">新闻热度</p>
                  <p className="mt-3 text-2xl font-semibold text-foreground">{scanResult.themeInsight.newsCount} 条</p>
                  <p className="mt-2 text-sm text-secondary-text">热度 {heatLevelLabel(scanResult.themeInsight.heatLevel)} · {scanResult.themeInsight.primaryCatalyst || '等待催化摘要'}</p>
                </div>
              </div>
            </Card>

            <Card variant="bordered" padding="lg" className="rounded-[24px]">
              <div className="flex items-start gap-4">
                <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-cyan/10 text-cyan">
                  <Sparkles className="h-7 w-7" />
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.16em] text-secondary-text">当前输出</p>
                  <p className="mt-3 text-2xl font-semibold text-foreground">{scanResult.stocks.length} 只优先股票</p>
                  <p className="mt-2 text-sm text-secondary-text">{scanResult.sourceInfo.note || '已按主题、板块和新闻热度完成筛选'}</p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Badge variant="default" className="border-border/60 bg-background/70 px-3 py-1 text-xs text-secondary-text">
                      结果 v{scanResult.sourceInfo.responseSchemaVersion ?? 1}
                    </Badge>
                    {scanResult.sourceInfo.historyRepaired ? (
                      <Badge variant="warning" className="border-0 px-3 py-1 text-xs">
                        历史已修复
                      </Badge>
                    ) : null}
                    {scanResult.sourceInfo.keyLevelsBackfilled ? (
                      <Badge variant="info" className="border-0 px-3 py-1 text-xs">
                        关键位置已补算
                      </Badge>
                    ) : null}
                  </div>
                </div>
              </div>
            </Card>
          </section>

          {scanResult.emptyReason ? (
            <InlineAlert
              variant="warning"
              title="当前没有筛出优质股票"
              message={scanResult.emptyReason}
            />
          ) : null}

          <section className="grid gap-5 xl:grid-cols-[1.15fr_0.85fr]">
            <div className="space-y-4">
              <div className="flex items-center justify-between px-1">
                <div>
                  <h2 className="text-3xl font-semibold tracking-tight text-foreground">优质股票</h2>
                  <p className="mt-1 text-sm text-secondary-text">优先保留主题关联清晰、结构未破坏、并且仍有后续空间的股票。</p>
                </div>
                <Badge variant="default" className="border-border/60 bg-card/70 px-4 py-2 text-sm text-foreground">
                  共 {scanResult.stocks.length} 只
                </Badge>
              </div>

              {scanResult.stocks.length === 0 ? (
                <Card variant="bordered" padding="lg" className="rounded-[26px]">
                  <EmptyState
                    title="暂无可展示股票"
                    description="当前主题已完成筛选，但没有股票通过现有评分口径。"
                    icon={<Sparkles className="h-8 w-8" />}
                  />
                </Card>
              ) : (
                scanResult.stocks.map((stock) => {
                  const active = selectedStock?.stockCode === stock.stockCode;
                  return (
                    <button
                      key={stock.stockCode}
                      type="button"
                      onClick={() => setSelectedStock(deriveSelectedStock(stock, scanResult))}
                      className="block w-full text-left"
                    >
                      <Card
                        variant="bordered"
                        padding="lg"
                        className={[
                          'rounded-[26px] border-border/60 transition-all',
                          active ? 'border-cyan/40 bg-cyan/5 shadow-soft-card' : 'bg-card/90 hover:border-cyan/20 hover:bg-card',
                        ].join(' ')}
                      >
                        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
                          <div className="flex min-w-0 flex-1 items-start gap-4">
                            <div className={[
                              'flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl text-base font-semibold',
                              stock.rank === 1 ? 'bg-orange-400 text-white' : 'bg-muted text-secondary-text',
                            ].join(' ')}
                            >
                              {stock.rank}
                            </div>
                            <div className="min-w-0 flex-1">
                              <div className="flex flex-wrap items-center gap-3">
                                <h3 className="truncate text-2xl font-semibold text-foreground">{stock.stockName}</h3>
                                <span className="text-sm text-secondary-text">{stock.stockCode}</span>
                                <Badge
                                  variant={signalBadgeVariant(stock.signalLevel)}
                                  size="md"
                                  className="border-0 px-3 py-1.5 text-sm"
                                >
                                  {stock.signalLevel}
                                </Badge>
                              </div>
                              <p className="mt-3 text-sm leading-7 text-foreground">{stock.selectionReason}</p>
                              <div className="mt-4 flex flex-wrap gap-2">
                                {(stock.miniReasons.length > 0 ? stock.miniReasons : [stock.currentPattern || '等待补充形态']).slice(0, 3).map((reason) => (
                                  <span key={reason} className="rounded-full bg-background px-3 py-1.5 text-xs text-secondary-text">
                                    {reason}
                                  </span>
                                ))}
                              </div>
                            </div>
                          </div>

                          <div className="grid grid-cols-2 gap-3 lg:w-[320px]">
                            <div className="rounded-2xl bg-background px-4 py-3">
                              <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">趋势分</p>
                              <p className="mt-2 text-2xl font-semibold text-foreground">{formatNumber(stock.trendScore, 0)}</p>
                            </div>
                            <div className="rounded-2xl bg-background px-4 py-3">
                              <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">涨跌幅</p>
                              <p className="mt-2 text-2xl font-semibold text-foreground">{formatPercent(stock.pctChg, 1)}</p>
                            </div>
                            <div className="rounded-2xl bg-background px-4 py-3">
                              <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">量比</p>
                              <p className="mt-2 text-2xl font-semibold text-foreground">{formatNumber(stock.volumeRatio, 2)}</p>
                            </div>
                            <div className="rounded-2xl bg-background px-4 py-3">
                              <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">风险提示</p>
                              <p className="mt-2 text-sm leading-6 text-secondary-text">{stock.riskNote || '风险可控'}</p>
                            </div>
                          </div>
                        </div>

                        <div className="mt-4 grid gap-3 sm:grid-cols-3">
                          <div className="rounded-2xl border border-border/60 bg-background/70 px-4 py-3">
                            <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">{priceLabel(stock.dataCompleteness)}</p>
                            <p className="mt-2 font-mono text-lg font-semibold text-foreground">{formatNumber(stock.currentPrice)}</p>
                          </div>
                          <div className="rounded-2xl border border-border/60 bg-background/70 px-4 py-3">
                            <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">支撑位</p>
                            <p className="mt-2 font-mono text-lg font-semibold text-foreground">{formatNumber(stock.supportLevel)}</p>
                          </div>
                          <div className="rounded-2xl border border-border/60 bg-background/70 px-4 py-3">
                            <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">压力位</p>
                            <p className="mt-2 font-mono text-lg font-semibold text-foreground">{formatNumber(stock.pressureLevel)}</p>
                          </div>
                        </div>
                      </Card>
                    </button>
                  );
                })
              )}
            </div>

            <Card variant="bordered" padding="lg" className="sticky top-4 h-fit rounded-[28px] border-border/60 bg-card/90">
              {selectedStock ? (
                <div className="space-y-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="flex flex-wrap items-end gap-3">
                        <h2 className="text-[36px] font-semibold leading-none text-foreground">{selectedStock.stockName}</h2>
                        <span className="pb-1 text-lg text-secondary-text">{selectedStock.stockCode}</span>
                      </div>
                      <p className="mt-3 text-sm text-secondary-text">{activeStockItem?.selectionReason || '查看这只股票为什么被保留在当前结果里。'}</p>
                    </div>
                    <button
                      type="button"
                      className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-border/60 text-secondary-text transition-colors hover:text-foreground"
                      aria-label="收藏股票"
                    >
                      <Star className="h-5 w-5" />
                    </button>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div className="rounded-2xl border border-border/60 bg-background/80 px-4 py-4 text-center">
                      <p className="text-sm text-secondary-text">题材关联度</p>
                      <p className="mt-2 text-4xl font-semibold text-blue-600">{themeRelevanceScore(selectedStock.themeRelevance)}<span className="text-lg">分</span></p>
                      <p className="mt-1 text-sm font-medium text-blue-600">{themeRelevanceLabel(selectedStock.themeRelevance)}</p>
                    </div>
                    <div className="rounded-2xl border border-border/60 bg-background/80 px-4 py-4 text-center">
                      <p className="text-sm text-secondary-text">趋势分</p>
                      <p className="mt-2 text-4xl font-semibold text-emerald-600">{formatNumber(selectedStock.trendScore, 0)}<span className="text-lg">分</span></p>
                      <p className="mt-1 text-sm font-medium text-emerald-600">{trendBandLabel(selectedStock.trendScore)}</p>
                    </div>
                    <div className="rounded-2xl border border-border/60 bg-background/80 px-4 py-4 text-center">
                      <p className="text-sm text-secondary-text">技术信号</p>
                      <p className="mt-2 text-3xl font-semibold text-danger">{selectedStock.buySignal || '--'}</p>
                      <p className="mt-1 text-sm font-medium text-secondary-text">{selectedStock.currentPattern || activeStockItem?.currentPattern || '关注均线与支撑结构'}</p>
                    </div>
                    <div className="rounded-2xl border border-border/60 bg-background/80 px-4 py-4 text-center">
                      <p className="text-sm text-secondary-text">偏离 MA10</p>
                      <p className="mt-2 text-4xl font-semibold text-emerald-600">{formatPercent(selectedStock.biasMa10, 1)}</p>
                      <p className="mt-1 text-sm font-medium text-secondary-text">{selectedStock.trendStatus || '运行健康'}</p>
                    </div>
                  </div>

                  <Card variant="bordered" padding="md" className="rounded-2xl">
                    <div className="flex items-start justify-between gap-3">
                      <h3 className="text-xl font-semibold text-foreground">新闻摘要</h3>
                      <button type="button" className="text-sm font-medium text-blue-600">更多新闻</button>
                    </div>
                    <ul className="mt-3 space-y-3">
                      {(selectedStock.newsSummary.length > 0 ? selectedStock.newsSummary : ['当前没有返回新闻摘要。']).map((item) => (
                        <li key={item} className="flex items-start gap-2 text-sm text-foreground">
                          <span className="mt-1 h-2 w-2 rounded-full bg-blue-500" />
                          <span>{item}</span>
                        </li>
                      ))}
                    </ul>
                  </Card>

                  <div className="grid gap-3 md:grid-cols-[1.1fr_0.95fr]">
                    <Card variant="bordered" padding="md" className="rounded-2xl">
                      <h3 className="text-xl font-semibold text-foreground">技术结构</h3>
                      <ul className="mt-3 space-y-3 text-sm text-foreground">
                        {(selectedStock.selectedReasons.length > 0 ? selectedStock.selectedReasons : ['当前未返回更细的结构说明。']).slice(0, 4).map((reason) => (
                          <li key={reason} className="flex items-start gap-2">
                            <TrendingUp className="mt-0.5 h-4 w-4 text-emerald-500" />
                            <span>{reason}</span>
                          </li>
                        ))}
                      </ul>
                    </Card>

                    <Card variant="bordered" padding="md" className="rounded-2xl">
                      <h3 className="text-xl font-semibold text-foreground">关键位置</h3>
                      <div className="mt-3 space-y-3 text-sm">
                        <div className="flex items-center justify-between gap-3">
                          <Badge variant="default" className="border-0 px-3 py-1.5 text-sm">{priceLabel(selectedStock.dataCompleteness)}</Badge>
                          <span className="font-mono text-lg text-foreground">{formatNumber(selectedStock.currentPrice)}</span>
                        </div>
                        <div className="flex items-center justify-between gap-3">
                          <Badge variant="danger" className="border-0 bg-danger/12 px-3 py-1.5 text-sm">压力位</Badge>
                          <span className="font-mono text-lg text-foreground">{formatNumber(selectedStock.pressureLevel)}</span>
                        </div>
                        <div className="flex items-center justify-between gap-3">
                          <Badge variant="success" className="border-0 bg-success/12 px-3 py-1.5 text-sm">支撑位</Badge>
                          <span className="font-mono text-lg text-foreground">{formatNumber(selectedStock.supportLevel)}</span>
                        </div>
                        <div className="flex items-center justify-between gap-3">
                          <Badge variant="info" className="border-0 px-3 py-1.5 text-sm">MA10</Badge>
                          <span className="font-mono text-lg text-foreground">{formatNumber(selectedStock.ma10)}</span>
                        </div>
                        <div className="flex items-center justify-between gap-3">
                          <Badge variant="history" className="border-0 px-3 py-1.5 text-sm">MA20</Badge>
                          <span className="font-mono text-lg text-foreground">{formatNumber(selectedStock.ma20)}</span>
                        </div>
                      </div>
                    </Card>
                  </div>

                  <Card variant="bordered" padding="md" className="rounded-2xl">
                    <h3 className="text-xl font-semibold text-foreground">为什么入选</h3>
                    <ul className="mt-3 space-y-2 text-sm text-foreground">
                      {(selectedStock.selectedReasons.length > 0 ? selectedStock.selectedReasons : ['当前未返回更细的入选理由。']).map((reason) => (
                        <li key={reason} className="flex items-start gap-2">
                          <ArrowRight className="mt-0.5 h-4 w-4 text-cyan" />
                          <span>{reason}</span>
                        </li>
                      ))}
                    </ul>
                  </Card>

                  <Card variant="bordered" padding="md" className="rounded-2xl border-danger/30">
                    <h3 className="text-xl font-semibold text-foreground">风险提示</h3>
                    <ul className="mt-3 space-y-2 text-sm leading-7 text-secondary-text">
                      {(selectedStock.riskReasons.length > 0
                        ? selectedStock.riskReasons
                        : ['短期涨幅较大时，优先观察回踩承接和量能延续。']).slice(0, 3).map((reason) => (
                        <li key={reason} className="flex items-start gap-2">
                          <span className="mt-2 h-1.5 w-1.5 rounded-full bg-danger" />
                          <span>{reason}</span>
                        </li>
                      ))}
                    </ul>
                  </Card>

                  <Card variant="bordered" padding="md" className="rounded-2xl">
                    <h3 className="text-xl font-semibold text-foreground">数据口径</h3>
                    <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    <div className="rounded-2xl bg-background px-4 py-3">
                      <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">实时完整度</p>
                      <p className="mt-2 text-sm font-medium text-foreground">{dataCompletenessLabel(selectedStock.dataCompleteness)}</p>
                    </div>
                    <div className="rounded-2xl bg-background px-4 py-3">
                        <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">板块来源</p>
                        <p className="mt-2 text-sm font-medium text-foreground">{sourceLabel(selectedStock.dataSources.board ?? scanResult.sourceInfo.boardSource)}</p>
                      </div>
                      <div className="rounded-2xl bg-background px-4 py-3">
                        <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">板块可信度</p>
                        <p className="mt-2 text-sm font-medium text-foreground">{boardSourceConfidenceLabel(scanResult.sourceInfo.boardSourceConfidence)}</p>
                      </div>
                      <div className="rounded-2xl bg-background px-4 py-3">
                        <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">价格口径</p>
                        <p className="mt-2 text-sm font-medium text-foreground">{pricingSourceLabel(scanResult.sourceInfo.pricingSource)}</p>
                      </div>
                    </div>
                    {scanResult.sourceInfo.historyRepaired || scanResult.sourceInfo.keyLevelsBackfilled ? (
                      <div className="mt-3 rounded-2xl border border-border/60 bg-background px-4 py-3 text-sm text-secondary-text">
                        {scanResult.sourceInfo.historyRepaired ? '当前结果来自历史恢复，并已按最新兼容逻辑修复。' : '当前结果来自最新扫描。'}
                        {scanResult.sourceInfo.keyLevelsBackfilled ? ' 现价、支撑位、压力位已基于本地日线补算。' : ''}
                      </div>
                    ) : null}
                  </Card>

                  <div className="flex flex-wrap gap-3">
                    <Button
                      variant="outline"
                      className="rounded-2xl"
                      onClick={() => handleSingleStockAnalyze(selectedStock.stockCode, selectedStock.stockName)}
                    >
                      前往单股分析
                    </Button>
                    <Button
                      variant="primary"
                      className="rounded-2xl"
                      onClick={() => handleDeepAnalyze(selectedStock.stockCode, selectedStock.stockName)}
                    >
                      发起深度分析
                    </Button>
                  </div>
                </div>
              ) : (
                <EmptyState
                  title="选择左侧股票查看详情"
                  description="这里会展示题材关联、技术结构、关键位置和新闻摘要。"
                  icon={<Target className="h-8 w-8" />}
                />
              )}
            </Card>
          </section>

          <Card variant="bordered" padding="lg" className="rounded-[24px]">
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <h2 className="text-[32px] font-semibold tracking-tight text-foreground">数据来源与说明</h2>
                <span className="inline-flex h-6 w-6 items-center justify-center rounded-full border border-border/60 text-xs text-secondary-text">i</span>
              </div>
              <span className="text-sm text-secondary-text">{scanResult.sourceInfo.boardSource || 'mixed'}</span>
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-3">
              {scanResult.sourceInfo.sourcePills.map((item) => (
                <Badge key={item} variant="default" size="md" className="border-0 bg-muted/70 px-4 py-2 text-sm text-foreground">
                  {item}
                </Badge>
              ))}
              <Badge variant="default" size="md" className="border-border/60 bg-background/70 px-4 py-2 text-sm text-foreground">
                {boardSourceConfidenceLabel(scanResult.sourceInfo.boardSourceConfidence)}
              </Badge>
              <Badge variant="default" size="md" className="border-border/60 bg-background/70 px-4 py-2 text-sm text-foreground">
                {pricingSourceLabel(scanResult.sourceInfo.pricingSource)}
              </Badge>
              <span className="text-sm text-secondary-text">{scanResult.sourceInfo.note || '当前无需额外说明'}</span>
            </div>
          </Card>
        </>
      ) : (
        <section className="grid gap-5 xl:grid-cols-[1.1fr_0.9fr]">
          <Card variant="bordered" padding="lg" className="rounded-[28px] border-border/60 bg-card/90">
            <EmptyState
              title="输入主题后开始筛选"
              description="页面会直接输出候选股票和右侧详情，不再停留在回放型工作流。"
              icon={<Sparkles className="h-10 w-10" />}
            />
          </Card>
          <Card variant="bordered" padding="lg" className="rounded-[28px] border-border/60 bg-card/90">
            <div className="space-y-4">
              <div>
                <p className="text-xs uppercase tracking-[0.16em] text-secondary-text">使用建议</p>
                <h2 className="mt-3 text-2xl font-semibold text-foreground">先定主题，再看结构和风险</h2>
              </div>
              <div className="grid gap-3">
                {[
                  '先输入主题名称，系统会优先走结构化板块映射而不是模糊文本匹配。',
                  '趋势持有更适合找可继续观察的票，短线异动更适合找当天强催化。',
                  '最大股票数量建议控制在 5-12 只，便于结果更聚焦。',
                ].map((item) => (
                  <div key={item} className="rounded-2xl border border-border/60 bg-background/70 px-4 py-4 text-sm leading-7 text-foreground">
                    {item}
                  </div>
                ))}
              </div>
            </div>
          </Card>
        </section>
      )}

      <Drawer
        isOpen={historyOpen}
        onClose={() => setHistoryOpen(false)}
        title="主题选股历史"
        width="max-w-xl"
        side="right"
      >
        <div className="space-y-4">
          {historyError ? <ApiErrorAlert error={historyError} /> : null}

          {historyLoading ? (
            <InlineAlert variant="info" title="正在加载历史记录" message="正在读取最近的主题选股结果。" />
          ) : null}

          {!historyLoading && historyItems.length === 0 ? (
            <EmptyState
              title="暂无历史选股记录"
              description="执行过主题选股后，最近结果会出现在这里。"
              icon={<Clock3 className="h-8 w-8" />}
            />
          ) : null}

          <div className="space-y-3">
            {historyItems.map((item) => {
              const canRestore = Boolean(item.result);
              const active = scanTask?.taskId === item.taskId;
              const retrying = historyActionTaskId === item.taskId;
              return (
                <div
                  key={item.taskId}
                  className={[
                    'w-full rounded-2xl border px-4 py-4 text-left transition-colors',
                    active ? 'border-cyan/40 bg-cyan/6' : 'border-border/60 bg-background/70 hover:bg-hover/30',
                  ].join(' ')}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-base font-semibold text-foreground">
                        {item.themeName || item.query?.themeName || item.query?.boardName || item.query?.boardCode || '主题选股'}
                      </p>
                      <p className="mt-1 text-sm text-secondary-text">
                        {item.completedAt ? item.completedAt.replace('T', ' ').slice(0, 16) : item.createdAt.replace('T', ' ').slice(0, 16)}
                      </p>
                    </div>
                    <Badge variant={item.status === 'completed' ? 'success' : item.status === 'failed' ? 'danger' : 'info'} className="border-0">
                      {taskStatusLabel(item.status)}
                    </Badge>
                  </div>
                  <div className="mt-3 space-y-2 text-sm">
                    <p className="text-secondary-text">
                      {item.boardMappingPath || item.query?.boardCode || item.query?.boardName || '未记录板块路径'}
                    </p>
                    <p className="text-foreground">
                      {item.stockCount > 0 ? `结果 ${item.stockCount} 只：${item.topStockNames.join(' / ')}` : item.message || '暂无结果摘要'}
                    </p>
                  </div>
                  <div className="mt-4 flex items-center justify-end gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={!canRestore}
                      onClick={() => handleHistorySelect(item)}
                    >
                      恢复查看
                    </Button>
                    {item.canRetry ? (
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={retrying}
                        onClick={() => void handleHistoryRetry(item)}
                      >
                        {retrying ? '重试中...' : '重新筛选'}
                      </Button>
                    ) : null}
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

export default ThemeStockPickerPage;
