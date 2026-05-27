import type React from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Activity,
  BarChart3,
  ChevronDown,
  Database,
  LineChart,
  Play,
  RefreshCw,
  Save,
  Settings2,
  Table2,
  Trash2,
} from 'lucide-react';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import {
  backtestsApi,
  type BacktestActionResponse,
  type BacktestEquityPoint,
  type BacktestKpis,
  type BacktestPreset,
  type BacktestRunDetailResponse,
  type BacktestRunListItem,
  type BacktestStockChartResponse,
  type BacktestStockDetail,
  type BacktestStockResult,
  type BacktestTrade,
  type BacktestEquityCurveResponse,
} from '../api/backtests';
import { BacktestStockKlineChart } from '../components/BacktestStockKlineChart';
import {
  BacktestParamEditor,
  type ParamDraft,
} from '../components/BacktestParamEditor';
import { buildBacktestMutationPayload } from '../components/backtestParamPayload';
import { ApiErrorAlert, AppPage, Badge, Button, Card, EmptyState, Select } from '../components/common';

const numberFormatter = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 });
const moneyFormatter = new Intl.NumberFormat('zh-CN', {
  maximumFractionDigits: 0,
  style: 'currency',
  currency: 'CNY',
});
function formatNumber(value?: number | null, fallback = '--'): string {
  return typeof value === 'number' && Number.isFinite(value) ? numberFormatter.format(value) : fallback;
}

function formatMoney(value?: number | null): string {
  return typeof value === 'number' && Number.isFinite(value) ? moneyFormatter.format(value) : '--';
}

function formatPct(value?: number | null, signed = false): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '--';
  const sign = signed && value > 0 ? '+' : '';
  return `${sign}${numberFormatter.format(value)}%`;
}

function formatDate(value?: string | null): string {
  if (!value) return '--';
  return value.slice(0, 10);
}

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

function pctTone(value?: number | null): string {
  const safe = Number(value ?? 0);
  if (safe > 0) return 'text-success';
  if (safe < 0) return 'text-danger';
  return 'text-secondary-text';
}

function statusVariant(status?: string): 'default' | 'success' | 'warning' | 'info' | 'danger' {
  if (status === 'finished') return 'success';
  if (status === 'failed') return 'danger';
  if (status === 'running') return 'warning';
  if (status === 'pending') return 'info';
  return 'default';
}

function buildCurvePath(points: BacktestEquityPoint[], width: number, height: number): string {
  const values = points
    .map((point) => point.equity)
    .filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
  if (values.length < 2) return '';

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const lastIndex = values.length - 1;

  return values
    .map((value, index) => {
      const x = (index / lastIndex) * width;
      const y = height - ((value - min) / range) * height;
      return `${index === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(' ');
}

function formatActionMessage(response: BacktestActionResponse, fallback: string): string {
  const token = response.taskId
    ?? response.jobId
    ?? response.runId
    ?? response.presetId
    ?? response.item?.presetId
    ?? response.status;
  if (response.message && token) return `${response.message} · ${token}`;
  if (response.message) return response.message;
  return token ? `${fallback} · ${token}` : fallback;
}

interface KpiCardProps {
  label: string;
  value: string;
  detail?: string;
  tone?: string;
}

const KpiCard: React.FC<KpiCardProps> = ({ label, value, detail, tone = 'text-foreground' }) => (
  <Card variant="bordered" padding="md" className="rounded-2xl border-border/60 bg-card/82">
    <p className="text-xs text-secondary-text">{label}</p>
    <p className={`mt-2 font-mono text-2xl font-semibold ${tone}`}>{value}</p>
    {detail ? <p className="mt-2 text-xs text-muted-text">{detail}</p> : null}
  </Card>
);

const StrategyBacktestPage: React.FC = () => {
  const [presets, setPresets] = useState<BacktestPreset[]>([]);
  const [runs, setRuns] = useState<BacktestRunListItem[]>([]);
  const [selectedRunId, setSelectedRunId] = useState('');
  const [selectedPresetKey, setSelectedPresetKey] = useState('');
  const [detail, setDetail] = useState<BacktestRunDetailResponse | null>(null);
  const [equityPoints, setEquityPoints] = useState<BacktestEquityPoint[]>([]);
  const [stocks, setStocks] = useState<BacktestStockResult[]>([]);
  const [trades, setTrades] = useState<BacktestTrade[]>([]);
  const [selectedStockCode, setSelectedStockCode] = useState('');
  const [stockDetail, setStockDetail] = useState<BacktestStockDetail | null>(null);
  const [stockChart, setStockChart] = useState<BacktestStockChartResponse | null>(null);
  const [paramPanelOpen, setParamPanelOpen] = useState(true);
  const [paramDraft, setParamDraft] = useState<ParamDraft>({});
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [savingPreset, setSavingPreset] = useState(false);
  const [executingBacktest, setExecutingBacktest] = useState(false);
  const [deletingPreset, setDeletingPreset] = useState(false);
  const [deletingRun, setDeletingRun] = useState(false);
  const [loadingRuns, setLoadingRuns] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [loadingStockDetail, setLoadingStockDetail] = useState(false);
  const [runsTableOpen, setRunsTableOpen] = useState(true);
  const [stockFilter, setStockFilter] = useState<'all' | 'profitable' | 'losing'>('all');
  const [equityCurveSummary, setEquityCurveSummary] = useState<BacktestEquityCurveResponse['summary']>(null);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [stockError, setStockError] = useState<ParsedApiError | null>(null);

  const loadRuns = useCallback(async (): Promise<void> => {
    try {
      setError(null);
      setLoadingRuns(true);
      const [presetResponse, runResponse] = await Promise.all([
        backtestsApi.listPresets(),
        backtestsApi.listRuns(100),
      ]);
      setPresets(presetResponse.items);
      setRuns(runResponse.items);
      setSelectedRunId((current) => current || runResponse.items[0]?.runId || '');
    } catch (requestError) {
      setError(getParsedApiError(requestError));
    } finally {
      setLoadingRuns(false);
    }
  }, []);

  const loadRunDetail = useCallback(async (runId: string): Promise<void> => {
    if (!runId) {
      setDetail(null);
      setEquityPoints([]);
      setEquityCurveSummary(null);
      setStocks([]);
      setTrades([]);
      setSelectedStockCode('');
      return;
    }

    try {
      setError(null);
      setLoadingDetail(true);
      const [runResponse, equityResponse, stockResponse, tradeResponse] = await Promise.all([
        backtestsApi.getRun(runId),
        backtestsApi.getEquityCurve(runId),
        backtestsApi.listStocks(runId, 80),
        backtestsApi.listTrades(runId, 160),
      ]);
      setDetail(runResponse);
      setEquityPoints(equityResponse.points);
      setEquityCurveSummary(equityResponse.summary ?? null);
      setStocks(stockResponse.items);
      setTrades(tradeResponse.items);
      setSelectedStockCode((current) => (
        current && stockResponse.items.some((item) => item.stockCode === current)
          ? current
          : stockResponse.items[0]?.stockCode ?? ''
      ));
    } catch (requestError) {
      setError(getParsedApiError(requestError));
      setDetail(null);
      setEquityPoints([]);
      setEquityCurveSummary(null);
      setStocks([]);
      setTrades([]);
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  const loadStockDetail = useCallback(async (runId: string, stockCode: string): Promise<void> => {
    if (!runId || !stockCode) {
      setStockDetail(null);
      setStockChart(null);
      return;
    }
    try {
      setStockError(null);
      setLoadingStockDetail(true);
      const [detailResponse, chartResponse] = await Promise.all([
        backtestsApi.getStockDetail(runId, stockCode),
        backtestsApi.getStockChart(runId, stockCode),
      ]);
      setStockDetail(detailResponse);
      setStockChart(chartResponse);
    } catch (requestError) {
      setStockError(getParsedApiError(requestError));
      setStockDetail(null);
      setStockChart(null);
    } finally {
      setLoadingStockDetail(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadRuns();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadRuns]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadRunDetail(selectedRunId);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadRunDetail, selectedRunId]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadStockDetail(selectedRunId, selectedStockCode);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadStockDetail, selectedRunId, selectedStockCode]);

  const runOptions = useMemo(
    () =>
      runs
        .filter((run) => {
          const preset = presets.find((item) => `preset:${item.presetId}` === selectedPresetKey);
          return preset ? run.strategy === preset.strategy : true;
        })
        .map((run) => ({
          value: run.runId,
          label: `${run.name || run.runId} · ${formatPct(run.aggregateReturnPct, true)} · ${formatDate(run.generatedAt)}`,
        })),
    [presets, runs, selectedPresetKey],
  );

  const selectedRunSummary = runs.find((run) => run.runId === selectedRunId) ?? null;
  const selectedRun = detail?.run ?? selectedRunSummary;
  const selectedPreset = presets.find((preset) => `preset:${preset.presetId}` === selectedPresetKey) ?? null;
  const visibleRuns = useMemo(
    () => (selectedPreset ? runs.filter((run) => run.strategy === selectedPreset.strategy) : runs),
    [runs, selectedPreset],
  );
  const activePreset = selectedPreset
    ?? presets.find((preset) => preset.strategy === selectedRun?.strategy)
    ?? presets[0]
    ?? null;
  const kpis: BacktestKpis = detail?.kpis ?? {};
  const strategyCard = detail?.strategyCard;
  const curvePath = useMemo(() => buildCurvePath(equityPoints, 720, 220), [equityPoints]);
  const firstPoint = equityPoints[0];
  const lastPoint = equityPoints[equityPoints.length - 1];
  const stockCounts = useMemo(() => {
    let profitable = 0;
    let losing = 0;
    for (const s of stocks) {
      if (typeof s.totalReturnPct === 'number' && s.totalReturnPct > 0) profitable++;
      else if (typeof s.totalReturnPct === 'number' && s.totalReturnPct < 0) losing++;
    }
    return { all: stocks.length, profitable, losing };
  }, [stocks]);
  const filteredStocks = useMemo(() => {
    const list = stockFilter === 'profitable'
      ? stocks.filter((s) => typeof s.totalReturnPct === 'number' && s.totalReturnPct > 0)
      : stockFilter === 'losing'
        ? stocks.filter((s) => typeof s.totalReturnPct === 'number' && s.totalReturnPct < 0)
        : stocks;
    return list.slice(0, 30);
  }, [stocks, stockFilter]);
  const selectedStockTrades = (
    stockChart?.trades?.length
      ? stockChart.trades
      : stockDetail?.trades?.length
        ? stockDetail.trades
        : trades.filter((trade) => trade.stockCode === selectedStockCode)
  ).slice(0, 18);

  const handleRefresh = useCallback(() => {
    if (selectedRunId) {
      void loadRunDetail(selectedRunId);
      if (selectedStockCode) void loadStockDetail(selectedRunId, selectedStockCode);
      return;
    }
    void loadRuns();
  }, [loadRunDetail, loadRuns, loadStockDetail, selectedRunId, selectedStockCode]);

  const handleRunSelect = useCallback((runId: string) => {
    setSelectedRunId(runId);
    setParamDraft({});
    setActionMessage(null);
  }, []);

  const handlePresetSelect = useCallback((preset: BacktestPreset) => {
    setSelectedPresetKey(`preset:${preset.presetId}`);
    setParamDraft({});
    setActionMessage(null);
    if (selectedRunId && runs.some((run) => run.runId === selectedRunId && run.strategy === preset.strategy)) return;
    const matchedRun = runs.find((run) => run.strategy === preset.strategy);
    if (matchedRun) {
      setSelectedRunId(matchedRun.runId);
      return;
    }
    setSelectedRunId('');
    setDetail(null);
    setEquityPoints([]);
    setEquityCurveSummary(null);
    setStocks([]);
    setTrades([]);
    setSelectedStockCode('');
    setStockDetail(null);
    setStockChart(null);
  }, [runs, selectedRunId]);

  const handleSavePreset = useCallback(async (): Promise<void> => {
    if (!detail && !activePreset) return;
    try {
      setError(null);
      setActionMessage(null);
      setSavingPreset(true);
      const payload = buildBacktestMutationPayload(detail, activePreset, paramDraft);
      const response = await backtestsApi.savePreset(payload);
      setActionMessage(formatActionMessage(response, '策略已保存'));
      setParamDraft({});
      await loadRuns();
    } catch (requestError) {
      setError(getParsedApiError(requestError));
    } finally {
      setSavingPreset(false);
    }
  }, [activePreset, detail, loadRuns, paramDraft]);

  const handleExecuteBacktest = useCallback(async (): Promise<void> => {
    if (!detail && !activePreset) return;
    try {
      setError(null);
      setActionMessage(null);
      setExecutingBacktest(true);
      const payload = buildBacktestMutationPayload(detail, activePreset, paramDraft);
      const response = await backtestsApi.executeRun(payload);
      setActionMessage(formatActionMessage(response, '回测任务已提交'));
      if (response.runId) setSelectedRunId(response.runId);
      await loadRuns();
    } catch (requestError) {
      setError(getParsedApiError(requestError));
    } finally {
      setExecutingBacktest(false);
    }
  }, [activePreset, detail, loadRuns, paramDraft]);

  const handleDeletePreset = useCallback(async (): Promise<void> => {
    if (!selectedPreset || selectedPreset.isBuiltin) return;
    const confirmed = window.confirm(`删除策略预设「${selectedPreset.name}」？此操作不会删除历史回测 run。`);
    if (!confirmed) return;
    try {
      setError(null);
      setActionMessage(null);
      setDeletingPreset(true);
      const response = await backtestsApi.deletePreset(selectedPreset.presetId);
      setActionMessage(formatActionMessage(response, '策略预设已删除'));
      setSelectedPresetKey('');
      setParamDraft({});
      await loadRuns();
    } catch (requestError) {
      setError(getParsedApiError(requestError));
    } finally {
      setDeletingPreset(false);
    }
  }, [loadRuns, selectedPreset]);

  const handleDeleteRun = useCallback(async (): Promise<void> => {
    if (!selectedRunId) return;
    const label = selectedRun?.name ?? selectedRunId;
    const confirmed = window.confirm(`删除回测数据「${label}」？相关个股结果、交易流水和资金曲线也会删除。`);
    if (!confirmed) return;
    try {
      setError(null);
      setActionMessage(null);
      setDeletingRun(true);
      const response = await backtestsApi.deleteRun(selectedRunId);
      setActionMessage(formatActionMessage(response, '回测数据已删除'));
      setSelectedRunId('');
      setSelectedPresetKey('');
      setDetail(null);
      setEquityPoints([]);
      setStocks([]);
      setTrades([]);
      setSelectedStockCode('');
      setStockDetail(null);
      setStockChart(null);
      await loadRuns();
    } catch (requestError) {
      setError(getParsedApiError(requestError));
    } finally {
      setDeletingRun(false);
    }
  }, [loadRuns, selectedRun?.name, selectedRunId]);

  return (
    <AppPage className="!max-w-none space-y-5">
      {/* ─── Compact Breadcrumb Bar ─── */}
      <section className="search-bar-card flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="flex items-center gap-2 min-w-0">
          <LineChart className="h-4 w-4 shrink-0 text-cyan" />
          <span className="text-sm font-medium text-foreground">策略回测</span>
          {selectedRun ? (
            <>
              <span className="text-secondary-text">/</span>
              <span className="text-sm font-medium text-foreground truncate">
                {activePreset?.name ?? selectedRun.strategy}
                {selectedRun.strategyVersion ? ` ${selectedRun.strategyVersion}` : ''}
              </span>
              <span className="text-secondary-text">·</span>
              <span className="text-sm text-secondary-text truncate">
                {strategyCard?.stockPool?.name ?? selectedRunSummary?.stockPoolName ?? ''}
              </span>
            </>
          ) : null}
        </div>
        {selectedRun ? (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 ml-auto text-xs text-secondary-text">
            <span className="font-mono">{formatDate(selectedRun.startDate)} → {formatDate(selectedRun.endDate)}</span>
            <span>样本 <strong className="text-foreground">{formatNumber(detail?.run.sampleDays)}</strong> 个交易日</span>
            <span>初始 <strong className="text-foreground">{formatMoney(strategyCard?.capital?.totalInitialCash ?? strategyCard?.capital?.initialCash)}</strong></span>
            <span>最终 <strong className={pctTone(kpis.aggregateReturnPct)}>{formatMoney(lastPoint?.equity)}</strong></span>
            <span>上次回测 {formatDateTime(selectedRun.generatedAt)}</span>
          </div>
        ) : (
          <span className="ml-auto text-xs text-secondary-text">选择策略预设或历史回测查看详情</span>
        )}
      </section>

      {/* ─── Preset Tabs ─── */}
      <section className="backtest-preset-rail">
        <div className="flex items-center gap-3">
          <div className="backtest-preset-label shrink-0">策略预设</div>
          <div className="backtest-preset-scroll flex-1">
            {presets.map((preset) => (
              <button
                key={preset.presetId}
                type="button"
                className={`backtest-preset-chip ${selectedPresetKey === `preset:${preset.presetId}` ? 'active' : ''}`}
                onClick={() => handlePresetSelect(preset)}
              >
                <span className="name">{preset.name}</span>
                <span className="meta">
                  {preset.strategy}
                  {preset.importedVersions?.length ? ` · ${preset.importedVersions.length} runs` : ''}
                </span>
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {selectedPreset ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => { setSelectedPresetKey(''); setParamDraft({}); setActionMessage(null); }}
              >
                查看全部回测
              </Button>
            ) : null}
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={handleSavePreset}
              isLoading={savingPreset}
              disabled={loadingRuns || loadingDetail || executingBacktest || deletingPreset || deletingRun || (!detail && !activePreset)}
            >
              <Save className="h-3.5 w-3.5" />
              保存当前参数
            </Button>
          </div>
        </div>
      </section>

      {/* ─── Strategy Info Bar ─── */}
      <Card variant="bordered" padding="md" className="rounded-2xl border-border/60 bg-card/88">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
          <div className="flex items-center gap-3 shrink-0">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-cyan/10 text-cyan">
              <Activity className="h-4 w-4" />
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-[0.16em] text-muted-text">Strategy</p>
              <p className="text-sm font-semibold text-foreground">{activePreset?.name ?? selectedRun?.strategy ?? '--'}</p>
            </div>
          </div>
          <div className="hidden lg:block h-8 w-px bg-border/60" />
          <div>
            <p className="text-[10px] uppercase tracking-[0.14em] text-muted-text">股票池</p>
            <p className="text-xs text-foreground">{strategyCard?.stockPool?.name ?? selectedRunSummary?.stockPoolName ?? '--'}</p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-[0.14em] text-muted-text">资金</p>
            <p className="text-xs text-foreground">{formatMoney(strategyCard?.capital?.totalInitialCash ?? strategyCard?.capital?.initialCash)}</p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-[0.14em] text-muted-text">入场</p>
            <p className="text-xs text-foreground">{strategyCard?.entrySummary ?? '--'}</p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-[0.14em] text-muted-text">出场</p>
            <p className="text-xs text-foreground">{strategyCard?.exitSummary ?? '--'}</p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-[0.14em] text-muted-text">成本</p>
            <p className="text-xs text-foreground">{strategyCard?.costSummary ?? '--'}</p>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-border/40 pt-3">
          <div className="w-[240px]">
            <Select
              label=""
              value={selectedRunId}
              onChange={handleRunSelect}
              options={runOptions}
              placeholder={loadingRuns ? '加载中' : '暂无回测记录'}
              disabled={loadingRuns || runOptions.length === 0}
            />
          </div>
          <Button type="button" variant="secondary" size="sm" onClick={() => setParamPanelOpen((o) => !o)} disabled={!selectedRun && !activePreset}>
            <Settings2 className="h-3.5 w-3.5" />
            调整参数
          </Button>
          <Button
            type="button"
            variant="primary"
            size="sm"
            onClick={handleExecuteBacktest}
            isLoading={executingBacktest}
            disabled={loadingRuns || loadingDetail || savingPreset || deletingPreset || deletingRun || (!detail && !activePreset)}
          >
            <Play className="h-3.5 w-3.5" />
            {selectedRun ? '重新回测' : '执行回测'}
          </Button>
          <Button type="button" variant="ghost" size="sm" onClick={handleRefresh} disabled={loadingRuns || loadingDetail}>
            <RefreshCw className={`h-3.5 w-3.5 ${loadingRuns || loadingDetail ? 'animate-spin' : ''}`} />
            刷新
          </Button>
          <Button
            type="button"
            variant="danger-subtle"
            size="sm"
            onClick={handleDeletePreset}
            isLoading={deletingPreset}
            disabled={!selectedPreset || Boolean(selectedPreset?.isBuiltin) || loadingRuns || loadingDetail || savingPreset || executingBacktest || deletingRun}
          >
            <Trash2 className="h-3.5 w-3.5" />
            删除策略
          </Button>
          <Button
            type="button"
            variant="danger-subtle"
            size="sm"
            onClick={handleDeleteRun}
            isLoading={deletingRun}
            disabled={!selectedRunId || loadingRuns || loadingDetail || savingPreset || executingBacktest || deletingPreset}
          >
            <Trash2 className="h-3.5 w-3.5" />
            删除回测数据
          </Button>
        </div>
      </Card>

      {/* ─── Param Editor (collapsible, outside selectedRun) ─── */}
      {paramPanelOpen ? (
        <Card variant="bordered" padding="lg" className="rounded-2xl border-border/60 bg-card/86">
          <button
            type="button"
            className="backtest-param-toggle"
            onClick={() => setParamPanelOpen(false)}
          >
            <span className="flex items-center gap-3">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan/10 text-cyan">
                <Settings2 className="h-5 w-5" />
              </span>
              <span>
                <span className="block text-xs uppercase tracking-[0.16em] text-secondary-text">Parameters</span>
                <span className="block text-lg font-semibold text-foreground">调整参数</span>
              </span>
            </span>
            <ChevronDown className="h-5 w-5 text-secondary-text transition-transform rotate-180" />
          </button>
          <BacktestParamEditor
            detail={detail}
            preset={activePreset}
            values={paramDraft}
            onChange={(key, value) => setParamDraft((draft) => ({ ...draft, [key]: value }))}
            onExecute={handleExecuteBacktest}
            onSave={handleSavePreset}
            executing={executingBacktest}
            saving={savingPreset}
            actionMessage={actionMessage}
          />
        </Card>
      ) : null}

      {error ? <ApiErrorAlert error={error} actionLabel="重试" onAction={handleRefresh} /> : null}

      {!loadingRuns && runs.length === 0 ? (
        <EmptyState
          icon={<Database className="h-7 w-7" />}
          title="暂无可展示的回测记录"
          description="后端导入历史 JSON 后，这里会自动读取 /api/v1/backtests/runs 的结果。"
        />
      ) : null}

      {loadingRuns && runs.length === 0 ? (
        <Card variant="bordered" padding="md" className="rounded-2xl border-border/60 bg-card/86">
          <div className="flex items-center gap-3 text-sm text-secondary-text">
            <span className="backtest-spinner sm" />
            正在读取策略预设与历史回测数据
          </div>
        </Card>
      ) : null}

      {/* ─── Runs Table (collapsible) ─── */}
      {visibleRuns.length > 0 ? (
        <Card variant="bordered" padding="lg" className="rounded-2xl border-border/60 bg-card/86">
          <button
            type="button"
            className="backtest-param-toggle"
            onClick={() => setRunsTableOpen((o) => !o)}
          >
            <span>
              <span className="block text-xs uppercase tracking-[0.16em] text-secondary-text">Backtest Runs</span>
              <span className="flex items-center gap-2">
                <span className="text-lg font-semibold text-foreground">回测数据列表</span>
                {selectedPreset ? <span className="text-sm font-normal text-secondary-text">{selectedPreset.name}</span> : null}
                <span className="text-xs text-muted-text">
                  {selectedPreset ? `${selectedPreset.strategy} · ` : '全部策略 · '}{visibleRuns.length} 条
                </span>
              </span>
            </span>
            <ChevronDown className={`h-5 w-5 text-secondary-text transition-transform ${runsTableOpen ? 'rotate-180' : ''}`} />
          </button>
          {runsTableOpen ? (
            <div className="backtest-table-wrapper max-h-[360px] mt-4">
              <table className="backtest-table w-full min-w-[1080px]">
                <thead className="backtest-table-head">
                  <tr>
                    <th className="backtest-table-head-cell text-left">策略</th>
                    <th className="backtest-table-head-cell text-left">回测名称</th>
                    <th className="backtest-table-head-cell text-left">股票池</th>
                    <th className="backtest-table-head-cell text-left">区间</th>
                    <th className="backtest-table-head-cell text-right">收益</th>
                    <th className="backtest-table-head-cell text-right">回撤</th>
                    <th className="backtest-table-head-cell text-right">交易</th>
                    <th className="backtest-table-head-cell text-left">生成时间</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleRuns.map((run) => (
                    <tr
                      key={run.runId}
                      className={`backtest-table-row cursor-pointer ${run.runId === selectedRunId ? 'selected' : ''}`}
                      onClick={() => handleRunSelect(run.runId)}
                    >
                      <td className="backtest-table-cell">
                        <span className="backtest-table-code">{run.strategy}</span>
                        {run.strategyVersion ? <span className="ml-2 text-secondary-text">{run.strategyVersion}</span> : null}
                      </td>
                      <td className="backtest-table-cell font-medium text-foreground">{run.name || run.runId}</td>
                      <td className="backtest-table-cell text-secondary-text">{run.stockPoolName ?? '--'}</td>
                      <td className="backtest-table-cell font-mono text-secondary-text">
                        {formatDate(run.startDate)} - {formatDate(run.endDate)}
                      </td>
                      <td className={`backtest-table-cell text-right font-mono ${pctTone(run.aggregateReturnPct)}`}>
                        {formatPct(run.aggregateReturnPct, true)}
                      </td>
                      <td className="backtest-table-cell text-right font-mono text-warning">{formatPct(run.maxDrawdownPct)}</td>
                      <td className="backtest-table-cell text-right font-mono">{formatNumber(run.totalTradeCount)}</td>
                      <td className="backtest-table-cell font-mono text-secondary-text">{formatDateTime(run.generatedAt)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </Card>
      ) : null}

      {selectedRun ? (
        <>
          {/* ─── Backtest Result Hero Card ─── */}
          <Card variant="bordered" padding="lg" className="rounded-2xl border-border/60 bg-card/88">
            <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
              <div className="min-w-0">
                <p className="text-xs uppercase tracking-[0.16em] text-secondary-text">
                  Backtest · {selectedRun.strategy} {selectedRun.strategyVersion ?? ''}
                </p>
                <div className="mt-1 flex flex-wrap items-center gap-3">
                  <h2 className="text-2xl font-semibold text-foreground">{selectedRun.name}</h2>
                  <Badge variant={statusVariant(selectedRun.status)} size="md">
                    {selectedRun.status?.toUpperCase()}
                    {detail?.run.sampleDays ? ` · ${detail.run.sampleDays}D` : ''}
                  </Badge>
                </div>
                <p className="mt-3 max-w-3xl text-sm leading-relaxed text-secondary-text">
                  在 {formatNumber(detail?.run.sampleDays)} 个交易日内对{' '}
                  {formatNumber(strategyCard?.stockPool?.totalSymbols ?? selectedRunSummary?.totalSymbols)} 只候选股完成{' '}
                  {formatNumber(kpis.totalTradeCount ?? selectedRunSummary?.totalTradeCount)} 次完整交易
                  {typeof kpis.aggregateReturnPct === 'number' && typeof kpis.benchmarkReturnPct === 'number'
                    ? `；策略累计${kpis.aggregateReturnPct >= kpis.benchmarkReturnPct ? '跑赢' : '跑输'}基准 ${formatNumber(Math.abs(kpis.aggregateReturnPct - kpis.benchmarkReturnPct))} 个百分点`
                    : ''}
                  。胜率 {formatPct(kpis.winRatePct ?? selectedRunSummary?.winRatePct)}，最大回撤 {formatPct(kpis.maxDrawdownPct ?? selectedRunSummary?.maxDrawdownPct)}。
                </p>
              </div>
              <div className="shrink-0 text-right text-xs text-secondary-text space-y-1">
                {detail?.run.runtimeSeconds != null ? (
                  <p>运行时长 <strong className="text-foreground">{formatNumber(detail.run.runtimeSeconds)}s</strong></p>
                ) : null}
                <p>完成 <strong className="text-foreground">{formatDateTime(selectedRun.generatedAt)}</strong></p>
              </div>
            </div>
          </Card>

          {/* ─── KPI Cards (6 columns) ─── */}
          <section className="grid gap-4 grid-cols-2 md:grid-cols-3 xl:grid-cols-6">
            <KpiCard
              label="累计收益"
              value={formatPct(kpis.aggregateReturnPct ?? selectedRunSummary?.aggregateReturnPct, true)}
              detail={formatMoney(lastPoint?.equity)}
              tone={pctTone(kpis.aggregateReturnPct ?? selectedRunSummary?.aggregateReturnPct)}
            />
            <KpiCard
              label="年化收益"
              value={formatPct(kpis.annualizedReturnPct, true)}
              detail={kpis.benchmarkReturnPct != null ? `基准 ${formatPct(kpis.benchmarkReturnPct, true)}` : `样本 ${formatNumber(detail?.run.sampleDays)} 天`}
              tone={pctTone(kpis.annualizedReturnPct)}
            />
            <KpiCard
              label="最大回撤"
              value={formatPct(kpis.maxDrawdownPct ?? selectedRunSummary?.maxDrawdownPct)}
              detail={equityCurveSummary?.longestDrawdownDays != null ? `恢复 ${equityCurveSummary.longestDrawdownDays} 日` : undefined}
              tone="text-warning"
            />
            <KpiCard
              label="夏普比率"
              value={formatNumber(kpis.sharpe)}
              detail={kpis.sortino != null ? `索提诺 ${formatNumber(kpis.sortino)}` : undefined}
              tone="text-foreground"
            />
            <KpiCard
              label="胜率"
              value={formatPct(kpis.winRatePct ?? selectedRunSummary?.winRatePct)}
              detail={`${formatNumber(kpis.profitableSymbols)} 胜 / ${formatNumber(kpis.losingSymbols)} 负`}
              tone="text-cyan"
            />
            <KpiCard
              label="交易次数"
              value={formatNumber(kpis.totalTradeCount ?? selectedRunSummary?.totalTradeCount)}
              detail={`平均持仓 ${formatNumber(kpis.averageHoldingDays)} 日`}
              tone="text-foreground"
            />
          </section>

          <Card variant="bordered" padding="lg" className="rounded-2xl border-border/60 bg-card/86">
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div>
                <p className="text-xs uppercase tracking-[0.16em] text-secondary-text">Equity Curve</p>
                <h3 className="mt-1 text-lg font-semibold text-foreground">净值曲线</h3>
              </div>
              <div className="backtest-summary">
                <span className="label">首日</span>
                <span className="value">{formatMoney(firstPoint?.equity)}</span>
                <span className="label">末日</span>
                <span className={`value ${Number(lastPoint?.equity ?? 0) >= Number(firstPoint?.equity ?? 0) ? 'success' : 'danger'}`}>
                  {formatMoney(lastPoint?.equity)}
                </span>
              </div>
            </div>

            <div className="mt-5 h-[280px] rounded-2xl border border-border/50 bg-background/70 p-4">
              {curvePath ? (
                <svg viewBox="0 0 720 220" className="h-full w-full overflow-visible" role="img" aria-label="组合资金曲线">
                  <defs>
                    <linearGradient id="equityGradient" x1="0" x2="0" y1="0" y2="1">
                      <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity="0.28" />
                      <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity="0" />
                    </linearGradient>
                  </defs>
                  <path d={`${curvePath} L 720 220 L 0 220 Z`} fill="url(#equityGradient)" />
                  <path d={curvePath} fill="none" stroke="hsl(var(--primary))" strokeLinecap="round" strokeWidth="3" />
                </svg>
              ) : (
                <div className="backtest-empty-state h-full">
                  <div className="icon-wrap">
                    <BarChart3 className="h-5 w-5 text-cyan" />
                  </div>
                  <p className="title">资金曲线暂无足够点位</p>
                  <p className="desc">接口返回至少 2 个 equity point 后会绘制简易曲线。</p>
                </div>
              )}
            </div>
          </Card>

          {/* ─── Additional Stats Row ─── */}
          <section className="grid gap-4 grid-cols-2 md:grid-cols-4">
            <Card variant="bordered" padding="md" className="rounded-2xl border-border/60 bg-card/82">
              <p className="text-xs text-secondary-text">最长回撤期</p>
              <p className="mt-1 font-mono text-lg font-semibold text-foreground">
                {equityCurveSummary?.longestDrawdownDays != null ? `${equityCurveSummary.longestDrawdownDays} 个交易日` : '--'}
              </p>
              {equityCurveSummary?.drawdownStartDate ? (
                <p className="mt-1 text-xs text-muted-text">{formatDate(equityCurveSummary.drawdownStartDate)} — {formatDate(equityCurveSummary.drawdownEndDate)}</p>
              ) : null}
            </Card>
            <Card variant="bordered" padding="md" className="rounded-2xl border-border/60 bg-card/82">
              <p className="text-xs text-secondary-text">盈亏比</p>
              <p className="mt-1 font-mono text-lg font-semibold text-foreground">{formatNumber(kpis.profitFactor)}</p>
              <p className="mt-1 text-xs text-muted-text">盈利因子 (Profit Factor)</p>
            </Card>
            <Card variant="bordered" padding="md" className="rounded-2xl border-border/60 bg-card/82">
              <p className="text-xs text-secondary-text">卡玛比率</p>
              <p className="mt-1 font-mono text-lg font-semibold text-foreground">{formatNumber(kpis.calmar)}</p>
              <p className="mt-1 text-xs text-muted-text">优化 / 最大回撤</p>
            </Card>
            <Card variant="bordered" padding="md" className="rounded-2xl border-border/60 bg-card/82">
              <p className="text-xs text-secondary-text">索提诺比率</p>
              <p className="mt-1 font-mono text-lg font-semibold text-foreground">{formatNumber(kpis.sortino)}</p>
              <p className="mt-1 text-xs text-muted-text">下行风险调整收益</p>
            </Card>
          </section>

          <section className="grid gap-5 xl:grid-cols-[320px_minmax(0,1fr)]">
            <Card variant="bordered" padding="md" className="rounded-2xl border-border/60 bg-card/86">
              <div className="flex items-center justify-between gap-2 px-1">
                <div>
                  <p className="text-xs uppercase tracking-[0.16em] text-secondary-text">个股表现 · Per-Stock</p>
                </div>
                <span className="text-xs text-muted-text">{stockCounts.all} 只 · {formatNumber(kpis.totalTradeCount)} 笔交易</span>
              </div>
              <div className="mt-2 flex items-center gap-1 px-1">
                {([
                  ['all', `全部 ${stockCounts.all}`],
                  ['profitable', `盈利 ${stockCounts.profitable}`],
                  ['losing', `亏损 ${stockCounts.losing}`],
                ] as const).map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                      stockFilter === key
                        ? 'bg-foreground text-background'
                        : 'text-secondary-text hover:bg-border/40'
                    }`}
                    onClick={() => setStockFilter(key)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <div className="mt-3 max-h-[600px] overflow-y-auto">
                {filteredStocks.length > 0 ? (
                  <div className="space-y-0.5">
                    {filteredStocks.map((stock, index) => (
                      <button
                        key={stock.stockCode}
                        type="button"
                        className={`flex w-full items-center gap-3 rounded-lg px-2 py-2.5 text-left transition-colors ${
                          stock.stockCode === selectedStockCode
                            ? 'bg-cyan/8 border-l-2 border-cyan'
                            : 'hover:bg-border/30 border-l-2 border-transparent'
                        }`}
                        onClick={() => setSelectedStockCode(stock.stockCode)}
                      >
                        <span className="w-5 shrink-0 text-center text-xs font-mono text-muted-text">
                          {String(index + 1).padStart(2, '0')}
                        </span>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-semibold text-foreground truncate">
                            {stock.stockName || stock.stockCode}
                          </p>
                          <p className="mt-0.5 text-[11px] text-secondary-text truncate">
                            {stock.stockCode} · {formatNumber(stock.tradeCount)} 笔 · 胜 {formatPct(stock.winRatePct)}
                          </p>
                        </div>
                        <span className={`shrink-0 font-mono text-sm font-semibold ${pctTone(stock.totalReturnPct)}`}>
                          {formatPct(stock.totalReturnPct, true)}
                        </span>
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="backtest-empty-state">
                    <div className="icon-wrap">
                      <Table2 className="h-5 w-5 text-cyan" />
                    </div>
                    <p className="title">暂无个股结果</p>
                    <p className="desc">等待 /stocks 接口返回单股汇总。</p>
                  </div>
                )}
              </div>
            </Card>

            <Card variant="bordered" padding="lg" className="rounded-2xl border-border/60 bg-card/86">
              <div className="backtest-table-toolbar">
                <div className="backtest-table-toolbar-meta">
                  <p className="text-xs uppercase tracking-[0.16em] text-secondary-text">Stock Detail</p>
                  <h3 className="text-lg font-semibold text-foreground">
                    {stockDetail?.stockName ?? stocks.find((stock) => stock.stockCode === selectedStockCode)?.stockName ?? '单股详情'}
                    {selectedStockCode ? <span className="ml-2 font-mono text-sm text-secondary-text">{selectedStockCode}</span> : null}
                  </h3>
                </div>
                <span className="backtest-table-scroll-hint">买点 B / 卖点 S</span>
              </div>
              <BacktestStockKlineChart
                chart={stockChart}
                loading={loadingStockDetail}
                error={stockError}
                stockCode={selectedStockCode}
                stockName={stockDetail?.stockName ?? stocks.find((stock) => stock.stockCode === selectedStockCode)?.stockName}
              />
            </Card>
          </section>

          <Card variant="bordered" padding="lg" className="rounded-2xl border-border/60 bg-card/86">
            <div className="backtest-table-toolbar">
              <div className="backtest-table-toolbar-meta">
                <p className="text-xs uppercase tracking-[0.16em] text-secondary-text">Trade Log</p>
                <h3 className="text-lg font-semibold text-foreground">交易流水</h3>
              </div>
              <span className="backtest-table-scroll-hint">
                {selectedStockCode ? `${selectedStockCode} · ` : ''}最近 {selectedStockTrades.length} 笔
              </span>
            </div>
            <div className="backtest-table-wrapper max-h-[520px]">
              {selectedStockTrades.length > 0 ? (
                <table className="backtest-table w-full min-w-[980px]">
                  <thead className="backtest-table-head">
                    <tr>
                      <th className="backtest-table-head-cell text-left">股票</th>
                      <th className="backtest-table-head-cell text-left">区间</th>
                      <th className="backtest-table-head-cell text-right">买入</th>
                      <th className="backtest-table-head-cell text-right">卖出</th>
                      <th className="backtest-table-head-cell text-right">收益</th>
                      <th className="backtest-table-head-cell text-right">持仓</th>
                      <th className="backtest-table-head-cell text-left">退出原因</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedStockTrades.map((trade) => (
                      <tr key={trade.tradeId} className="backtest-table-row">
                        <td className="backtest-table-cell">
                          <span className="backtest-table-code">{trade.stockCode}</span>
                          <span className="ml-2 text-foreground">{trade.stockName ?? ''}</span>
                        </td>
                        <td className="backtest-table-cell font-mono text-secondary-text">
                          {formatDate(trade.entryDate)} - {formatDate(trade.exitDate)}
                        </td>
                        <td className="backtest-table-cell text-right font-mono">{formatNumber(trade.entryPrice)}</td>
                        <td className="backtest-table-cell text-right font-mono">{formatNumber(trade.exitPrice)}</td>
                        <td className={`backtest-table-cell text-right font-mono ${pctTone(trade.returnPct)}`}>{formatPct(trade.returnPct, true)}</td>
                        <td className="backtest-table-cell text-right font-mono">{formatNumber(trade.holdingDays)}</td>
                        <td className="backtest-table-cell text-secondary-text">{trade.exitReason ?? '--'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="backtest-empty-state">
                  <div className="icon-wrap">
                    <Table2 className="h-5 w-5 text-cyan" />
                  </div>
                  <p className="title">暂无交易流水</p>
                  <p className="desc">等待 /trades 或单股详情接口返回明细。</p>
                </div>
              )}
            </div>
          </Card>
        </>
      ) : null}

      {loadingDetail ? (
        <div className="fixed bottom-5 right-5 flex items-center gap-3 rounded-full border border-border/60 bg-card/95 px-4 py-3 text-sm text-secondary-text shadow-soft-card">
          <span className="backtest-spinner sm" />
          加载回测数据
        </div>
      ) : null}
    </AppPage>
  );
};

export default StrategyBacktestPage;
