import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowRight,
  ChevronRight,
  Eye,
  Plus,
  Search,
  TrendingUp,
} from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';
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
import { ApiErrorAlert, AppPage, Badge, Button, Card, EmptyState, InlineAlert, Input, Select } from '../components/common';

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const STRATEGY_OPTIONS: Array<{ value: ThemePickerStrategyMode; label: string }> = [
  { value: 'holding', label: '趋势持有' },
  { value: 'event', label: '短线异动' },
];

const DEFAULT_MAX_CANDIDATES = 8;
const MIN_MAX_CANDIDATES = 1;
const MAX_MAX_CANDIDATES = 50;

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

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

type ThemeFactorSyncContext = {
  fromThemeFactor: boolean;
  scanId: string;
  eventId: string;
  eventTitle: string;
  themeFactorScore: string;
};

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function isSyntheticThemeId(value?: string | null): boolean {
  const text = String(value || '').trim();
  return text.startsWith('theme_name_') || text.startsWith('board_') || text.startsWith('board_name_');
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

function normalizeSyncedBoardName(value?: string | null): string {
  const text = String(value || '').trim();
  if (!text) return '';
  if (text.startsWith('board_name_')) {
    return text.replace(/^board_name_/, '').trim();
  }
  const prefixedMatch = text.match(/^board_name\s*=\s*(.+)$/i);
  if (prefixedMatch) {
    return prefixedMatch[1]?.trim() ?? '';
  }
  return text;
}

function normalizeSyncedBoardCode(value?: string | null): string {
  const text = String(value || '').trim();
  if (!text) return '';
  const prefixedMatch = text.match(/^board_code\s*=\s*(.+)$/i);
  if (prefixedMatch) {
    return prefixedMatch[1]?.trim().toUpperCase() ?? '';
  }
  if (text.startsWith('board_')) {
    return text.replace(/^board_/, '').trim().toUpperCase();
  }
  return text.toUpperCase();
}

function formatNumber(value?: number | null, digits = 2): string {
  if (value == null || Number.isNaN(value)) return '--';
  return value.toFixed(digits);
}

function formatSignedPercent(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return '--';
  const prefix = value > 0 ? '+' : '';
  return `${prefix}${value.toFixed(2)}%`;
}

function signalBadgeVariant(signalLevel: string): 'success' | 'info' | 'warning' | 'danger' | 'default' {
  if (signalLevel === '优先关注') return 'danger';
  if (signalLevel === '持有候选') return 'warning';
  if (signalLevel === '低吸观察') return 'info';
  if (signalLevel === '不宜追高') return 'default';
  if (signalLevel === '主题触发') return 'success';
  return 'default';
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
      mode: 'theme_id', title: '已注册主题',
      description: `当前会按主题 ID 直连配置检索：${themeId}`,
      detail: '优先使用主题注册表中的板块、映射和策略配置；其余输入仅作展示，不参与本次提交。',
      effectiveFields: ['themeId'], payload: { ...basePayload, themeId },
    };
  }
  if (boardCode) {
    return {
      mode: 'board_code', title: '板块代码直检',
      description: `当前会按板块代码检索：${boardCode}`,
      detail: boardName ? `板块名称"${boardName}"仅作辅助展示，不参与提交。` : '如果同时填写了主题名称，主题名称仅作页面展示，不参与提交。',
      effectiveFields: ['boardCode'], payload: { ...basePayload, boardCode },
    };
  }
  if (boardName) {
    return {
      mode: 'board_name', title: '板块名称检索',
      description: `当前会按板块名称检索：${boardName}`,
      detail: themeName ? `主题名称"${themeName}"仅作页面展示，不参与提交。` : '系统会优先尝试结构化板块名称匹配，再决定是否降级。',
      effectiveFields: ['boardName'], payload: { ...basePayload, boardName },
    };
  }
  if (themeName) {
    return {
      mode: 'theme_name', title: '主题名称检索',
      description: `当前会按主题名称检索：${themeName}`,
      detail: '系统会从主题名称出发匹配板块和新闻，不依赖已注册主题 ID。',
      effectiveFields: ['themeName'], payload: { ...basePayload, themeName },
    };
  }
  return {
    mode: 'empty', title: '等待输入',
    description: '请输入主题名称、板块代码或板块名称。',
    detail: '支持三种入口：已注册主题、板块直检、主题名称检索。',
    effectiveFields: [], payload: { ...basePayload },
  };
}

function selectedStockFromResult(result: ThemePickerScanResponse | null): ThemePickerSelectedStock | null {
  if (!result) return null;
  if (result.selectedStock) return result.selectedStock;
  const first = result.stocks[0];
  if (!first) return null;
  return {
    stockCode: first.stockCode, stockName: first.stockName,
    themeRelevance: 'medium', currentPrice: first.currentPrice ?? null,
    pctChg: first.pctChg ?? null, volumeRatio: first.volumeRatio ?? null,
    turnoverRate: first.turnoverRate ?? null, trendScore: first.trendScore ?? null,
    trendStatus: null, buySignal: first.buySignal ?? null,
    currentPattern: first.currentPattern ?? null, dataCompleteness: first.dataCompleteness ?? null,
    resonanceCount: null, ma5: null, ma10: null, ma20: null,
    biasMa5: null, biasMa10: null, biasMa20: null,
    recentStrongDays: null, supportLevel: first.supportLevel ?? null,
    pressureLevel: first.pressureLevel ?? null, newsSummary: [],
    selectedReasons: first.miniReasons.length > 0 ? first.miniReasons : [first.selectionReason],
    riskReasons: first.riskNote ? [first.riskNote] : [],
    dataSources: {},
  };
}

function deriveSelectedStock(stock: ThemePickerStockItem, result: ThemePickerScanResponse): ThemePickerSelectedStock {
  if (result.selectedStock?.stockCode === stock.stockCode) return result.selectedStock;
  return {
    stockCode: stock.stockCode, stockName: stock.stockName,
    themeRelevance: result.selectedStock?.themeRelevance ?? 'medium',
    currentPrice: stock.currentPrice ?? result.selectedStock?.currentPrice ?? null,
    pctChg: stock.pctChg ?? result.selectedStock?.pctChg ?? null,
    volumeRatio: stock.volumeRatio ?? result.selectedStock?.volumeRatio ?? null,
    turnoverRate: stock.turnoverRate ?? result.selectedStock?.turnoverRate ?? null,
    trendScore: stock.trendScore ?? null, trendStatus: result.selectedStock?.trendStatus ?? null,
    buySignal: stock.buySignal ?? null,
    currentPattern: stock.currentPattern ?? result.selectedStock?.currentPattern ?? null,
    dataCompleteness: stock.dataCompleteness ?? result.selectedStock?.dataCompleteness ?? null,
    resonanceCount: result.selectedStock?.resonanceCount ?? null,
    newsSummary: result.selectedStock?.newsSummary ?? [],
    selectedReasons: stock.miniReasons.length > 0 ? stock.miniReasons : [stock.selectionReason],
    riskReasons: stock.riskNote ? [stock.riskNote] : [],
    dataSources: result.selectedStock?.dataSources ?? {},
    ma5: result.selectedStock?.ma5 ?? null, ma10: result.selectedStock?.ma10 ?? null,
    ma20: result.selectedStock?.ma20 ?? null, biasMa5: result.selectedStock?.biasMa5 ?? null,
    biasMa10: result.selectedStock?.biasMa10 ?? null, biasMa20: result.selectedStock?.biasMa20 ?? null,
    recentStrongDays: result.selectedStock?.recentStrongDays ?? null,
    supportLevel: stock.supportLevel ?? result.selectedStock?.supportLevel ?? null,
    pressureLevel: stock.pressureLevel ?? result.selectedStock?.pressureLevel ?? null,
  };
}

/* ------------------------------------------------------------------ */
/*  Sub-components                                                     */
/* ------------------------------------------------------------------ */

function StatCell({ label, value, detail, color }: { label: string; value: string; detail?: string; color?: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wider text-secondary-text">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${color ?? 'text-foreground'}`}>{value}</p>
      {detail ? <p className={`mt-0.5 text-xs ${color ?? 'text-secondary-text'}`}>{detail}</p> : null}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Page component                                                     */
/* ------------------------------------------------------------------ */

const ThemeStockPickerPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
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
  const [historyItems, setHistoryItems] = useState<ThemePickerTaskHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState<ParsedApiError | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [showNewScanForm, setShowNewScanForm] = useState(false);
  const pollTimeoutRef = useRef<number | null>(null);
  const initialHistoryAppliedRef = useRef(false);
  const scanLoadingRef = useRef(false);
  const scanResultRef = useRef<ThemePickerScanResponse | null>(null);
  const scanTaskRef = useRef<ThemePickerTaskStatus | null>(null);

  const themeFactorSyncContext = useMemo<ThemeFactorSyncContext>(() => ({
    fromThemeFactor: searchParams.get('from') === 'theme-factor',
    scanId: searchParams.get('scanId') ?? '',
    eventId: searchParams.get('eventId') ?? '',
    eventTitle: searchParams.get('eventTitle') ?? '',
    themeFactorScore: searchParams.get('themeFactorScore') ?? '',
  }), [searchParams]);

  const hasThemeFactorSyncContext = themeFactorSyncContext.fromThemeFactor
    && Boolean(searchParams.get('themeName') || searchParams.get('themeId'));

  useEffect(() => {
    document.title = '主题选股 - DSA';
  }, []);

  useEffect(() => { scanLoadingRef.current = scanLoading; }, [scanLoading]);
  useEffect(() => { scanResultRef.current = scanResult; }, [scanResult]);
  useEffect(() => { scanTaskRef.current = scanTask; }, [scanTask]);

  useEffect(() => () => {
    if (pollTimeoutRef.current != null) window.clearTimeout(pollTimeoutRef.current);
  }, []);

  /* Load themes */
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
    return () => { active = false; };
  }, []);

  const applyResultToPage = useCallback((result: ThemePickerScanResponse) => {
    setScanResult(result);
    setSelectedStock(selectedStockFromResult(result));
    setThemeId(isSyntheticThemeId(result.query.themeId) ? '' : (result.query.themeId ?? ''));
    setThemeName(normalizeSyncedThemeName(result.query.themeName ?? ''));
    setBoardCode(normalizeSyncedBoardCode(result.query.boardCode ?? ''));
    setBoardName(normalizeSyncedBoardName(result.query.boardName ?? ''));
    setStrategyMode(result.query.strategyMode);
    setMaxCandidates(String(result.query.maxCandidates ?? DEFAULT_MAX_CANDIDATES));
  }, []);

  const refreshHistory = useCallback(async () => {
    try {
      const response = await themePickerApi.getHistory(30);
      setHistoryItems(response.items);
      setHistoryError(null);
    } catch (error) {
      setHistoryError(getParsedApiError(error));
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  /* pollScanStatus uses a ref for self-reference to avoid immutability issues */
  const pollFnRef = useRef<(id: string) => void>(() => {});

  const pollScanStatus = useCallback(async (taskId: string) => {
    try {
      const status = await themePickerApi.getScanStatus(taskId);
      setScanTask(status);
      if (status.status === 'completed' && status.result) {
        applyResultToPage(status.result);
        setScanLoading(false); pollTimeoutRef.current = null;
        void refreshHistory();
        return;
      }
      if (status.status === 'failed') {
        setScanError(createParsedApiError({
          title: '主题选股失败', message: status.error || status.message || '主题选股失败', status: 500,
        }));
        setScanLoading(false); pollTimeoutRef.current = null;
        void refreshHistory();
        return;
      }
      pollTimeoutRef.current = window.setTimeout(() => { pollFnRef.current(taskId); }, 5000);
    } catch (error) {
      setScanError(getParsedApiError(error));
      setScanLoading(false); pollTimeoutRef.current = null;
    }
  }, [applyResultToPage, refreshHistory]);

  useEffect(() => { pollFnRef.current = pollScanStatus; }, [pollScanStatus]);

  /* Load history */
  useEffect(() => {
    let active = true;
    const loadHistory = async () => {
      setHistoryLoading(true);
      try {
        const response = await themePickerApi.getHistory(30);
        if (!active) return;
        setHistoryItems(response.items);
        setHistoryError(null);
        if (
          !initialHistoryAppliedRef.current
          && !hasThemeFactorSyncContext
          && !scanLoadingRef.current
          && !scanResultRef.current
          && !scanTaskRef.current
        ) {
          const latestCompleted = response.items.find((item) => item.status === 'completed' && item.result);
          if (latestCompleted?.result) {
            initialHistoryAppliedRef.current = true;
            setScanTask({
              taskId: latestCompleted.taskId, status: latestCompleted.status,
              progress: latestCompleted.progress, message: latestCompleted.message,
              createdAt: latestCompleted.createdAt, startedAt: latestCompleted.startedAt,
              completedAt: latestCompleted.completedAt, result: latestCompleted.result,
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
    return () => { active = false; };
  }, [hasThemeFactorSyncContext, applyResultToPage]);

  const hasQuery = Boolean(themeId || themeName.trim() || boardCode.trim() || boardName.trim());
  const normalizedMaxCandidates = clampMaxCandidates(Number.parseInt(maxCandidates, 10));
  const queryIntent = useMemo(
    () => buildQueryIntent({ themeId, themeName, boardCode, boardName, strategyMode, maxCandidates: normalizedMaxCandidates }),
    [themeId, themeName, boardCode, boardName, strategyMode, normalizedMaxCandidates],
  );

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
    if (hadThemeBinding) { setBoardCode(''); setBoardName(''); }
  };

  const handleBoardCodeChange = (value: string) => {
    setThemeId('');
    setBoardCode(normalizeSyncedBoardCode(value));
  };

  const handleBoardNameChange = (value: string) => {
    const hadThemeBinding = Boolean(themeId);
    setThemeId('');
    if (hadThemeBinding) setBoardCode('');
    setBoardName(normalizeSyncedBoardName(value));
  };

  const handleDeepAnalyze = (stockCode: string, stockName: string) => {
    navigate(`/stock-query?stock=${encodeURIComponent(stockCode)}&name=${encodeURIComponent(stockName)}&intent=deep-analysis`);
  };

  const handleSingleStockAnalyze = (stockCode: string, stockName: string) => {
    navigate(`/stock-query?stock=${encodeURIComponent(stockCode)}&name=${encodeURIComponent(stockName)}`);
  };

  const submitScan = useCallback(async (payload: ResolvedScanPayload) => {
    if (pollTimeoutRef.current != null) {
      window.clearTimeout(pollTimeoutRef.current);
      pollTimeoutRef.current = null;
    }
    setScanLoading(true); setScanError(null); setScanResult(null); setSelectedStock(null);
    setMaxCandidates(String(clampMaxCandidates(payload.maxCandidates)));
    try {
      const accepted = await themePickerApi.scan(payload);
      setScanTask({
        taskId: accepted.taskId, status: accepted.status, progress: 0,
        message: accepted.message, createdAt: new Date().toISOString(),
      });
      await pollScanStatus(accepted.taskId);
    } catch (error) {
      setScanError(getParsedApiError(error));
      setScanTask(null); setScanLoading(false);
    }
  }, [pollScanStatus]);

  const handleHistorySelect = (item: ThemePickerTaskHistoryItem) => {
    if (!item.result) return;
    setScanTask({
      taskId: item.taskId, status: item.status, progress: item.progress,
      message: item.message, createdAt: item.createdAt, startedAt: item.startedAt,
      completedAt: item.completedAt, result: item.result, error: item.error,
    });
    setScanError(null); setScanLoading(false);
    applyResultToPage(item.result);
    setShowNewScanForm(false);
  };

  const handleScan = async () => {
    if (!hasQuery) return;
    await submitScan(queryIntent.payload);
    setShowNewScanForm(false);
  };

  /* Theme factor sync */
  useEffect(() => {
    if (!hasThemeFactorSyncContext) return;
    const syncParams = async () => {
      const themeNameFromParams = normalizeSyncedThemeName(searchParams.get('themeName'));
      const rawThemeIdFromParams = (searchParams.get('themeId') ?? '').trim();
      const themeIdFromParams = isSyntheticThemeId(rawThemeIdFromParams) ? '' : rawThemeIdFromParams;
      const boardCodeFromParams = normalizeSyncedBoardCode(searchParams.get('boardCode'));
      const boardNameFromParams = normalizeSyncedBoardName(searchParams.get('boardName'));
      const strategyModeFromParams = (searchParams.get('strategyMode') ?? '').trim();
      const maxCandidatesFromParams = clampMaxCandidates(
        Number.parseInt(searchParams.get('maxCandidates') ?? String(DEFAULT_MAX_CANDIDATES), 10),
      );
      setThemeId(themeIdFromParams); setThemeName(themeNameFromParams);
      setBoardCode(boardCodeFromParams); setBoardName(boardNameFromParams);
      setStrategyMode(strategyModeFromParams === 'event' ? 'event' : 'holding');
      setMaxCandidates(String(maxCandidatesFromParams));
    };
    void syncParams();
  }, [hasThemeFactorSyncContext, searchParams]);

  /* Derived data */
  const filteredHistory = useMemo(() => {
    if (!searchQuery.trim()) return historyItems;
    const q = searchQuery.trim().toLowerCase();
    return historyItems.filter((item) => {
      const name = item.themeName || item.query?.themeName || item.query?.boardName || '';
      return name.toLowerCase().includes(q);
    });
  }, [historyItems, searchQuery]);

  const avgPctChg = useMemo(() => {
    if (!scanResult?.stocks.length) return null;
    const values = scanResult.stocks.map((s) => s.pctChg).filter((v): v is number => v != null);
    if (!values.length) return null;
    return values.reduce((a, b) => a + b, 0) / values.length;
  }, [scanResult]);

  const medianVolumeRatio = useMemo(() => {
    if (!scanResult?.stocks.length) return null;
    const values = scanResult.stocks.map((s) => s.volumeRatio).filter((v): v is number => v != null).sort((a, b) => a - b);
    if (!values.length) return null;
    const mid = Math.floor(values.length / 2);
    return values.length % 2 !== 0 ? values[mid] : ((values[mid - 1] ?? 0) + (values[mid] ?? 0)) / 2;
  }, [scanResult]);

  const pctChgRange = useMemo(() => {
    if (!scanResult?.stocks.length) return null;
    const values = scanResult.stocks.map((s) => s.pctChg).filter((v): v is number => v != null);
    if (!values.length) return null;
    return { min: Math.min(...values), max: Math.max(...values) };
  }, [scanResult]);

  const statusDotColor = (status: string) => {
    if (status === 'completed') return 'bg-green-500';
    if (status === 'failed') return 'bg-red-500';
    if (status === 'processing') return 'bg-yellow-500';
    return 'bg-secondary-text';
  };

  return (
    <AppPage className="!max-w-none px-4 md:px-8 lg:px-12 xl:px-16">
      {/* Breadcrumb + Search */}
      <div className="search-bar-card mb-5 flex flex-wrap items-center justify-between gap-4">
        <nav className="flex items-center gap-2 text-sm text-secondary-text">
          <span>主题选股</span>
          {scanResult ? (
            <>
              <ChevronRight className="h-3.5 w-3.5" />
              <span>最近扫描</span>
              <ChevronRight className="h-3.5 w-3.5" />
              <span className="text-foreground">{scanResult.themeInsight.themeName}</span>
            </>
          ) : null}
        </nav>
        <div className="relative w-full max-w-md">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-secondary-text" />
          <input
            type="text"
            placeholder="搜索主题、代码、关键词..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="h-10 w-full rounded-xl border border-border bg-card pl-10 pr-4 text-sm text-foreground placeholder:text-secondary-text focus:border-foreground/30 focus:outline-none"
          />
        </div>
      </div>

      {/* Theme factor sync context */}
      {hasThemeFactorSyncContext ? (
        <div className="mb-4">
          <InlineAlert
            variant="info"
            title="已接收主题因子同步上下文"
            message={[
              themeName ? `当前主题：${themeName}` : null,
              themeFactorSyncContext.eventTitle ? `来源事件：${themeFactorSyncContext.eventTitle}` : null,
              themeFactorSyncContext.themeFactorScore ? `主题因子分：${themeFactorSyncContext.themeFactorScore}` : null,
              '你可以基于这条主题因子继续筛选候选股。',
            ].filter(Boolean).join(' · ')}
          />
        </div>
      ) : null}

      {/* Main two-column layout */}
      <div className="grid gap-6 xl:grid-cols-[320px_1fr]">
        {/* Left sidebar - scan history */}
        <div className="min-w-0 space-y-3">
          <Card variant="bordered" padding="md" className="rounded-2xl">
            <div className="flex items-center justify-between px-1 pb-3">
              <h2 className="text-lg font-semibold text-foreground">最近扫描</h2>
              <Badge variant="default" className="border-border/60 px-2 py-0.5 text-xs">
                {historyItems.length} 个
              </Badge>
            </div>

            <button
              type="button"
              onClick={() => setShowNewScanForm(true)}
              className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-border/80 bg-background/50 px-4 py-3 text-sm font-medium text-foreground transition-colors hover:bg-hover/30"
            >
              <Plus className="h-4 w-4" />
              新建主题扫描
            </button>

            {historyError ? <div className="mt-3"><ApiErrorAlert error={historyError} /></div> : null}

            <div className="mt-3 max-h-[calc(100vh-300px)] space-y-1 overflow-y-auto">
              {historyLoading ? (
                <p className="py-4 text-center text-sm text-secondary-text">加载中...</p>
              ) : null}
              {!historyLoading && filteredHistory.length === 0 ? (
                <p className="py-4 text-center text-sm text-secondary-text">暂无扫描记录</p>
              ) : null}
              {filteredHistory.map((item) => {
                const active = scanTask?.taskId === item.taskId;
                const name = item.themeName || item.query?.themeName || item.query?.boardName || item.query?.boardCode || '主题选股';
                const time = (item.completedAt || item.createdAt).replace('T', ' ').slice(5, 16);
                return (
                  <button
                    key={item.taskId}
                    type="button"
                    onClick={() => handleHistorySelect(item)}
                    disabled={!item.result}
                    className={`w-full rounded-xl px-3 py-3 text-left transition-colors ${
                      active
                        ? 'bg-foreground/[0.06]'
                        : 'hover:bg-hover/30'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-semibold text-foreground">{name}</p>
                        <p className="mt-0.5 text-xs text-secondary-text">
                          {time} · {item.stockCount} 候选
                        </p>
                      </div>
                      <span className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${statusDotColor(item.status)}`} />
                    </div>
                    {item.message ? (
                      <p className="mt-1 truncate text-xs text-secondary-text">{item.message}</p>
                    ) : null}
                  </button>
                );
              })}
            </div>
          </Card>
        </div>

        {/* Right main area */}
        <div className="min-w-0 space-y-5">
          {/* New scan form (collapsible) */}
          {showNewScanForm ? (
            <Card variant="bordered" padding="lg" className="rounded-2xl">
              <div className="flex items-center justify-between pb-4">
                <h3 className="text-lg font-semibold text-foreground">新建主题扫描</h3>
                <button type="button" onClick={() => setShowNewScanForm(false)} className="text-sm text-secondary-text hover:text-foreground">
                  收起
                </button>
              </div>
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                <Input label="主题名称" name="theme-name" placeholder="例如 DeepSeek" value={themeName} onChange={(e) => handleThemeNameChange(e.target.value)} />
                <Input label="板块代码（可选）" name="board-code" placeholder="例如 BK1188" value={boardCode} onChange={(e) => handleBoardCodeChange(e.target.value)} />
                <Input label="板块名称（可选）" name="board-name" placeholder="例如 DeepSeek概念" value={boardName} onChange={(e) => handleBoardNameChange(e.target.value)} />
                <div className="space-y-2">
                  <label className="text-sm font-medium text-foreground">策略</label>
                  <Select value={strategyMode} onChange={(value) => setStrategyMode(value as ThemePickerStrategyMode)} options={STRATEGY_OPTIONS} />
                </div>
                <Input label="最大股票数量" name="max-candidates" type="number" min={MIN_MAX_CANDIDATES} max={MAX_MAX_CANDIDATES} step={1} placeholder={String(DEFAULT_MAX_CANDIDATES)} value={maxCandidates} onChange={(e) => setMaxCandidates(e.target.value)} />
                <div className="flex items-end">
                  <Button variant="primary" size="xl" className="h-11 w-full rounded-2xl" onClick={() => void handleScan()} isLoading={scanLoading} loadingText="筛选中..." disabled={!hasQuery}>
                    开始筛选
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
              {themesError ? <div className="mt-4"><ApiErrorAlert error={themesError} /></div> : null}
              {/* Quick theme chips */}
              <div className="mt-4">
                <p className="mb-2 text-xs text-secondary-text">热门主题</p>
                <div className="flex flex-wrap gap-2">
                  {themes.slice(0, 8).map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => handleQuickTheme(item)}
                      className={`rounded-lg border px-3 py-1.5 text-xs transition-colors ${
                        item.id === themeId
                          ? 'border-foreground/30 bg-foreground/[0.06] text-foreground'
                          : 'border-border/60 text-secondary-text hover:text-foreground'
                      }`}
                    >
                      {item.name}
                    </button>
                  ))}
                  {themesLoading ? <span className="text-xs text-secondary-text">加载中...</span> : null}
                </div>
              </div>
              {/* Query intent info */}
              <div className="mt-4 rounded-xl bg-muted/30 px-4 py-3 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={queryIntent.mode === 'theme_id' ? 'info' : queryIntent.mode === 'empty' ? 'default' : 'success'} className="border-0 px-2 py-0.5 text-xs">
                    {queryIntent.title}
                  </Badge>
                  {queryIntent.effectiveFields.map((field) => (
                    <Badge key={field} variant="default" className="border-border/60 px-2 py-0.5 text-xs text-secondary-text">
                      {field}
                    </Badge>
                  ))}
                </div>
                <p className="mt-2 text-secondary-text">{queryIntent.description}</p>
              </div>
            </Card>
          ) : null}

          {/* Errors */}
          {scanError ? <ApiErrorAlert error={scanError} /> : null}

          {/* Loading state */}
          {scanTask && scanLoading ? (
            <InlineAlert variant="info" title="主题选股任务进行中" message={`${scanTask.message || '正在执行主题选股'}（${scanTask.progress}%）`} />
          ) : null}

          {/* Results */}
          {scanResult ? (
            <>
              {/* Task header */}
              <Card variant="bordered" padding="lg" className="rounded-2xl">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <p className="text-xs uppercase tracking-wider text-secondary-text">
                      THEME TASK · {scanTask?.taskId ? scanTask.taskId.slice(-4) : '--'}
                    </p>
                    <div className="mt-2 flex flex-wrap items-center gap-3">
                      <h1 className="text-3xl font-bold tracking-tight text-foreground">{scanResult.themeInsight.themeName}</h1>
                      <Badge variant="danger" className="border-0 px-3 py-1 text-sm">
                        {scanResult.themeInsight.eventStatus || 'TRIGGERED'}
                      </Badge>
                    </div>
                    <p className="mt-3 text-sm leading-relaxed text-secondary-text">
                      {scanResult.emptyReason
                        || `本次扫描使用「${strategyMode === 'event' ? '催化敏感' : '趋势持有'}」策略，${
                          scanResult.themeInsight.boardMappingPath
                            ? `板块路径 ${scanResult.themeInsight.boardMappingPath}，`
                            : ''
                        }共筛选出 ${scanResult.stocks.length} 只候选股票。`}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" className="rounded-xl" onClick={() => setShowNewScanForm(true)}>
                      编辑参数
                    </Button>
                    <Button variant="outline" size="sm" className="rounded-xl" onClick={() => void submitScan(queryIntent.payload)} disabled={!hasQuery || scanLoading}>
                      重新筛选
                    </Button>
                  </div>
                </div>

                {/* Stats row */}
                <div className="mt-6 grid grid-cols-2 gap-6 md:grid-cols-4">
                  <StatCell label="候选股票" value={String(scanResult.stocks.length)} detail={`策略：${strategyMode === 'event' ? '短线异动' : '趋势持有'}`} />
                  <StatCell
                    label="平均涨幅"
                    value={formatSignedPercent(avgPctChg)}
                    detail={pctChgRange ? `区间 ${formatSignedPercent(pctChgRange.min)} — ${formatSignedPercent(pctChgRange.max)}` : undefined}
                    color={avgPctChg != null && avgPctChg > 0 ? 'text-red-600' : avgPctChg != null && avgPctChg < 0 ? 'text-green-600' : undefined}
                  />
                  <StatCell
                    label="量比中位数"
                    value={medianVolumeRatio != null ? `${medianVolumeRatio.toFixed(1)}×` : '--'}
                    detail={medianVolumeRatio != null && medianVolumeRatio > 1.5 ? '高于 5 日均值' : '正常水平'}
                  />
                  <StatCell
                    label="数据来源"
                    value={`${scanResult.sourceInfo.sourcePills.length} 个`}
                    detail={scanResult.sourceInfo.note || '多源交叉验证'}
                  />
                </div>
              </Card>

              {/* Candidate table */}
              <Card variant="bordered" padding="lg" className="rounded-2xl">
                <div className="flex items-center justify-between pb-4">
                  <h2 className="text-lg font-semibold text-foreground">
                    本次候选池 · 全部 {scanResult.stocks.length} 只
                  </h2>
                  <span className="text-xs text-secondary-text">按 RS 评分排序</span>
                </div>

                {scanResult.stocks.length === 0 ? (
                  <EmptyState
                    title="暂无可展示股票"
                    description="当前主题已完成筛选，但没有股票通过现有评分口径。"
                  />
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-border/60 text-left text-xs uppercase tracking-wider text-secondary-text">
                          <th className="pb-3 pr-4">#</th>
                          <th className="pb-3 pr-4">名称</th>
                          <th className="pb-3 pr-4">主题词命中</th>
                          <th className="pb-3 pr-4">趋势</th>
                          <th className="pb-3 pr-4 text-right">涨幅</th>
                          <th className="pb-3 pr-4 text-right">量比</th>
                          <th className="pb-3 pr-4 text-right">RS</th>
                          <th className="pb-3 text-right">操作</th>
                        </tr>
                      </thead>
                      <tbody>
                        {scanResult.stocks.map((stock) => {
                          const active = selectedStock?.stockCode === stock.stockCode;
                          return (
                            <tr
                              key={stock.stockCode}
                              onClick={() => setSelectedStock(deriveSelectedStock(stock, scanResult))}
                              className={`cursor-pointer border-b border-border/30 transition-colors ${
                                active ? 'bg-foreground/[0.04]' : 'hover:bg-hover/20'
                              }`}
                            >
                              <td className="py-4 pr-4 text-base font-semibold text-foreground">{stock.rank}</td>
                              <td className="py-4 pr-4">
                                <div>
                                  <span className="font-semibold text-foreground">{stock.stockName}</span>
                                  <span className="ml-2 text-xs text-secondary-text">{stock.stockCode}</span>
                                </div>
                                <div className="mt-1 flex flex-wrap gap-1">
                                  {stock.miniReasons.length > 0 ? (
                                    stock.miniReasons.slice(0, 2).map((r) => (
                                      <Badge key={r} variant="info" className="border-0 px-1.5 py-0.5 text-[10px]">{r}</Badge>
                                    ))
                                  ) : (
                                    <Badge variant="default" className="border-border/60 px-1.5 py-0.5 text-[10px]">
                                      {stock.signalLevel}
                                    </Badge>
                                  )}
                                </div>
                              </td>
                              <td className="py-4 pr-4 text-xs text-secondary-text">
                                {stock.currentPattern || stock.selectionReason.slice(0, 20)}
                              </td>
                              <td className="py-4 pr-4">
                                {/* Mini sparkline placeholder */}
                                <div className="h-6 w-16">
                                  <TrendingUp className={`h-4 w-4 ${(stock.trendScore ?? 0) >= 60 ? 'text-red-500' : 'text-secondary-text'}`} />
                                </div>
                              </td>
                              <td className={`py-4 pr-4 text-right font-mono text-sm ${
                                (stock.pctChg ?? 0) > 0 ? 'text-red-600' : (stock.pctChg ?? 0) < 0 ? 'text-green-600' : 'text-foreground'
                              }`}>
                                {formatSignedPercent(stock.pctChg)}
                              </td>
                              <td className="py-4 pr-4 text-right font-mono text-sm text-foreground">
                                {stock.volumeRatio != null ? `${stock.volumeRatio.toFixed(1)}×` : '--'}
                              </td>
                              <td className="py-4 pr-4 text-right font-mono text-sm font-semibold text-foreground">
                                {formatNumber(stock.trendScore, 0)}
                              </td>
                              <td className="py-4 text-right">
                                <button
                                  type="button"
                                  onClick={(e) => { e.stopPropagation(); handleSingleStockAnalyze(stock.stockCode, stock.stockName); }}
                                  className="inline-flex items-center gap-1 rounded-lg border border-border/60 px-2 py-1 text-xs text-secondary-text transition-colors hover:text-foreground"
                                >
                                  <Eye className="h-3 w-3" />
                                  查看
                                </button>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card>

              {/* Selected stock detail */}
              {selectedStock ? (
                <Card variant="bordered" padding="lg" className="rounded-2xl">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="flex items-end gap-3">
                        <h2 className="text-2xl font-bold text-foreground">{selectedStock.stockName}</h2>
                        <span className="pb-0.5 text-sm text-secondary-text">{selectedStock.stockCode}</span>
                        <Badge variant={signalBadgeVariant(scanResult.stocks.find((s) => s.stockCode === selectedStock.stockCode)?.signalLevel ?? '')} className="border-0 px-2 py-0.5 text-xs">
                          {scanResult.stocks.find((s) => s.stockCode === selectedStock.stockCode)?.signalLevel ?? '--'}
                        </Badge>
                      </div>
                      <p className="mt-2 text-sm text-secondary-text">
                        {scanResult.stocks.find((s) => s.stockCode === selectedStock.stockCode)?.selectionReason ?? ''}
                      </p>
                    </div>
                    <div className="flex gap-2">
                      <Button variant="outline" size="sm" className="rounded-xl" onClick={() => handleSingleStockAnalyze(selectedStock.stockCode, selectedStock.stockName)}>
                        单股分析
                      </Button>
                      <Button variant="primary" size="sm" className="rounded-xl" onClick={() => handleDeepAnalyze(selectedStock.stockCode, selectedStock.stockName)}>
                        深度分析
                        <ArrowRight className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>

                  <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                    <div className="rounded-xl bg-muted/30 px-4 py-3">
                      <p className="text-xs text-secondary-text">现价</p>
                      <p className="mt-1 font-mono text-lg font-semibold text-foreground">{formatNumber(selectedStock.currentPrice)}</p>
                    </div>
                    <div className="rounded-xl bg-muted/30 px-4 py-3">
                      <p className="text-xs text-secondary-text">涨跌幅</p>
                      <p className={`mt-1 font-mono text-lg font-semibold ${
                        (selectedStock.pctChg ?? 0) > 0 ? 'text-red-600' : (selectedStock.pctChg ?? 0) < 0 ? 'text-green-600' : 'text-foreground'
                      }`}>{formatSignedPercent(selectedStock.pctChg)}</p>
                    </div>
                    <div className="rounded-xl bg-muted/30 px-4 py-3">
                      <p className="text-xs text-secondary-text">量比</p>
                      <p className="mt-1 font-mono text-lg font-semibold text-foreground">
                        {selectedStock.volumeRatio != null ? `${selectedStock.volumeRatio.toFixed(1)}×` : '--'}
                      </p>
                    </div>
                    <div className="rounded-xl bg-muted/30 px-4 py-3">
                      <p className="text-xs text-secondary-text">趋势分</p>
                      <p className="mt-1 font-mono text-lg font-semibold text-foreground">{formatNumber(selectedStock.trendScore, 0)}</p>
                    </div>
                  </div>

                  <div className="mt-4 grid gap-4 md:grid-cols-2">
                    {/* Key levels */}
                    <div className="rounded-xl border border-border/40 px-4 py-3">
                      <h4 className="text-xs font-medium uppercase tracking-wider text-secondary-text">关键位置</h4>
                      <div className="mt-3 space-y-2 text-sm">
                        <div className="flex justify-between"><span className="text-secondary-text">支撑位</span><span className="font-mono text-foreground">{formatNumber(selectedStock.supportLevel)}</span></div>
                        <div className="flex justify-between"><span className="text-secondary-text">压力位</span><span className="font-mono text-foreground">{formatNumber(selectedStock.pressureLevel)}</span></div>
                        <div className="flex justify-between"><span className="text-secondary-text">MA10</span><span className="font-mono text-foreground">{formatNumber(selectedStock.ma10)}</span></div>
                        <div className="flex justify-between"><span className="text-secondary-text">MA20</span><span className="font-mono text-foreground">{formatNumber(selectedStock.ma20)}</span></div>
                      </div>
                    </div>

                    {/* Selection reasons */}
                    <div className="rounded-xl border border-border/40 px-4 py-3">
                      <h4 className="text-xs font-medium uppercase tracking-wider text-secondary-text">入选理由</h4>
                      <ul className="mt-3 space-y-2 text-sm text-foreground">
                        {(selectedStock.selectedReasons.length > 0 ? selectedStock.selectedReasons : ['当前未返回更细的入选理由。']).slice(0, 4).map((reason) => (
                          <li key={reason} className="flex items-start gap-2">
                            <ArrowRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-secondary-text" />
                            <span>{reason}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>

                  {/* Risk */}
                  {selectedStock.riskReasons.length > 0 ? (
                    <div className="mt-4 rounded-xl bg-muted/30 px-4 py-3">
                      <h4 className="text-xs font-medium uppercase tracking-wider text-secondary-text">风险提示</h4>
                      <ul className="mt-2 space-y-1 text-sm text-secondary-text">
                        {selectedStock.riskReasons.slice(0, 3).map((reason) => (
                          <li key={reason} className="flex items-start gap-2">
                            <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-foreground/40" />
                            <span>{reason}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </Card>
              ) : null}
            </>
          ) : (
            /* Empty state */
            <Card variant="bordered" padding="lg" className="rounded-2xl">
              <EmptyState
                title="选择左侧扫描记录或新建主题扫描"
                description="这里会展示主题任务详情、候选池和个股分析。"
              />
              <div className="mt-6 grid gap-3 text-sm text-secondary-text">
                {[
                  '先输入主题名称，系统会优先走结构化板块映射而不是模糊文本匹配。',
                  '趋势持有更适合找可继续观察的票，短线异动更适合找当天强催化。',
                  '最大股票数量建议控制在 5-12 只，便于结果更聚焦。',
                ].map((item) => (
                  <div key={item} className="flex items-start gap-2 rounded-xl border border-border/40 px-4 py-3">
                    <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-foreground/40" />
                    <span>{item}</span>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      </div>
    </AppPage>
  );
};

export default ThemeStockPickerPage;
