import apiClient from './index';
import { toCamelCase } from './utils';

function toSnakeKey(key: string): string {
  return key
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .replace(/[-\s]+/g, '_')
    .toLowerCase();
}

function toSnakeCaseDeep(value: unknown): unknown {
  if (Array.isArray(value)) return value.map((item) => toSnakeCaseDeep(item));
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([key, nestedValue]) => [
        toSnakeKey(key),
        toSnakeCaseDeep(nestedValue),
      ]),
    );
  }
  return value;
}

export type BacktestRunStatus = 'pending' | 'running' | 'finished' | 'failed' | 'unknown';

export interface BacktestRunListItem {
  runId: string;
  name: string;
  strategy: string;
  strategyVersion?: string | null;
  stockPoolName?: string | null;
  startDate?: string | null;
  endDate?: string | null;
  status: BacktestRunStatus | string;
  totalSymbols?: number | null;
  totalTradeCount?: number | null;
  aggregateReturnPct?: number | null;
  maxDrawdownPct?: number | null;
  winRatePct?: number | null;
  generatedAt?: string | null;
}

export interface BacktestRunListResponse {
  items: BacktestRunListItem[];
  nextCursor?: string | null;
}

export interface BacktestPreset {
  presetId: string;
  name: string;
  strategy: string;
  strategyVersion?: string | null;
  description?: string | null;
  isBuiltin?: boolean | null;
  isDefault?: boolean | null;
  params?: Record<string, unknown> | null;
  defaultParams?: Record<string, unknown> | null;
  constraints?: Record<string, unknown> | null;
  config?: Record<string, unknown> | null;
  capital?: Record<string, unknown> | null;
  stockPool?: BacktestStockPoolSummary | Record<string, unknown> | null;
  importedRunId?: string | null;
  importedVersions?: Array<{
    runId?: string | null;
    strategyVersion?: string | null;
    stockPoolName?: string | null;
    totalSymbols?: number | null;
    startDate?: string | null;
    endDate?: string | null;
    generatedAt?: string | null;
  }> | null;
  category?: string | null;
  stockPoolSummary?: string | null;
}

export interface BacktestStockPoolMemberPreview {
  stockCode?: string | null;
  stockName?: string | null;
}

export interface BacktestStockPoolSummary {
  poolId?: string | null;
  name?: string | null;
  sourcePath?: string | null;
  totalSymbols?: number | null;
  namedSymbols?: number | null;
  membersPreview?: BacktestStockPoolMemberPreview[] | null;
  description?: string | null;
  summary?: string | null;
}

export interface BacktestPresetListResponse {
  items: BacktestPreset[];
}

export interface BacktestRunDetail {
  runId: string;
  name: string;
  status: BacktestRunStatus | string;
  sourceType?: string | null;
  sourcePath?: string | null;
  strategy: string;
  strategyVersion?: string | null;
  startDate?: string | null;
  endDate?: string | null;
  sampleDays?: number | null;
  runtimeSeconds?: number | null;
  generatedAt?: string | null;
}

export interface BacktestStrategyCard {
  stockPool?: {
    poolId?: string | null;
    name?: string | null;
    sourcePath?: string | null;
    totalSymbols?: number | null;
    namedSymbols?: number | null;
    membersPreview?: BacktestStockPoolMemberPreview[] | null;
  } | null;
  capital?: {
    initialCash?: number | null;
    totalInitialCash?: number | null;
    positionPct?: number | null;
    maxPositions?: number | null;
  } | null;
  entrySummary?: string | null;
  exitSummary?: string | null;
  costSummary?: string | null;
  constraints?: {
    priceAdjustment?: string | null;
    tradingConstraints?: string | null;
  } | Record<string, unknown> | null;
  config?: Record<string, unknown> | null;
  params?: Record<string, unknown> | null;
}

export interface BacktestKpis {
  aggregateReturnPct?: number | null;
  annualizedReturnPct?: number | null;
  benchmarkReturnPct?: number | null;
  maxDrawdownPct?: number | null;
  sharpe?: number | null;
  sortino?: number | null;
  winRatePct?: number | null;
  profitableSymbols?: number | null;
  losingSymbols?: number | null;
  totalTradeCount?: number | null;
  averageHoldingDays?: number | null;
  profitFactor?: number | null;
  calmar?: number | null;
}

export interface BacktestRunDetailResponse {
  run: BacktestRunDetail;
  strategyCard?: BacktestStrategyCard | null;
  kpis?: BacktestKpis | null;
  rawAvailable?: Record<string, boolean | null | undefined> | null;
}

export interface BacktestEquityPoint {
  tradeDate: string;
  cash?: number | null;
  marketValue?: number | null;
  equity: number;
  returnPct?: number | null;
  drawdownPct?: number | null;
  benchmarkReturnPct?: number | null;
}

export interface BacktestEquityCurveResponse {
  runId: string;
  scope: string;
  granularity: string;
  benchmark?: {
    code?: string | null;
    name?: string | null;
    available?: boolean | null;
  } | null;
  points: BacktestEquityPoint[];
  summary?: {
    longestDrawdownDays?: number | null;
    drawdownStartDate?: string | null;
    drawdownEndDate?: string | null;
  } | null;
}

export interface BacktestStockResult {
  stockCode: string;
  stockName?: string | null;
  status?: string | null;
  initialCash?: number | null;
  finalEquity?: number | null;
  totalReturnPct?: number | null;
  maxDrawdownPct?: number | null;
  tradeCount?: number | null;
  winRatePct?: number | null;
  avgWinPct?: number | null;
  avgLossPct?: number | null;
  profitFactor?: number | null;
  hasOpenPosition?: boolean | null;
  contributionPct?: number | null;
}

export interface BacktestHoldingRange {
  entryDate?: string | null;
  exitDate?: string | null;
  entryPrice?: number | null;
  exitPrice?: number | null;
  returnPct?: number | null;
}

export interface BacktestStockDetail extends BacktestStockResult {
  params?: Record<string, unknown> | null;
  config?: Record<string, unknown> | null;
  metrics?: Record<string, unknown> | null;
  dataContext?: Record<string, unknown> | null;
  latestSignalMetadata?: Record<string, unknown> | null;
  openPosition?: Record<string, unknown> | null;
  trades?: BacktestTrade[];
  equityCurve?: BacktestEquityPoint[];
  holdingRanges?: BacktestHoldingRange[];
}

export interface BacktestStockChartBar {
  tradeDate: string;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  close?: number | null;
  volume?: number | null;
  amount?: number | null;
  pctChg?: number | null;
  ma5?: number | null;
  ma10?: number | null;
  ma20?: number | null;
  dataSource?: string | null;
}

export interface BacktestStockChartMarker {
  type: 'buy' | 'sell' | string;
  tradeId?: string | null;
  tradeDate?: string | null;
  price?: number | null;
  shares?: number | null;
  reason?: string | null;
  score?: number | null;
  returnPct?: number | null;
  metadata?: Record<string, unknown> | null;
}

export interface BacktestStockChartResponse {
  runId: string;
  stockCode: string;
  stockName?: string | null;
  priceAdjustment?: string | null;
  startDate?: string | null;
  endDate?: string | null;
  dataSource?: string | null;
  bars: BacktestStockChartBar[];
  markers: BacktestStockChartMarker[];
  trades?: BacktestTrade[];
  latestSignalMetadata?: Record<string, unknown> | null;
  readOnly?: boolean | null;
}

export interface BacktestStockListResponse {
  items: BacktestStockResult[];
  counts?: {
    all?: number | null;
    profitable?: number | null;
    losing?: number | null;
    flat?: number | null;
    error?: number | null;
  } | null;
}

export interface BacktestTrade {
  tradeId: string;
  stockCode: string;
  stockName?: string | null;
  entryDate?: string | null;
  exitDate?: string | null;
  entryPrice?: number | null;
  exitPrice?: number | null;
  shares?: number | null;
  grossPnl?: number | null;
  netPnl?: number | null;
  returnPct?: number | null;
  holdingDays?: number | null;
  exitReason?: string | null;
  entrySignalReason?: string | null;
  entrySignalScore?: number | null;
  mfePct?: number | null;
  maePct?: number | null;
}

export interface BacktestTradeListResponse {
  items: BacktestTrade[];
  nextCursor?: string | null;
}

export interface BacktestPresetSaveRequest {
  presetId?: string | null;
  name?: string | null;
  strategy: string;
  strategyVersion?: string | null;
  sourceRunId?: string | null;
  stockPool?: Record<string, unknown> | null;
  capital?: Record<string, unknown> | null;
  constraints?: Record<string, unknown> | null;
  config?: Record<string, unknown> | null;
  params?: Record<string, unknown> | null;
}

export interface BacktestRunExecuteRequest extends BacktestPresetSaveRequest {
  startDate: string;
  endDate: string;
  priceAdjustment?: string | null;
  tradingConstraints?: string | null;
  stockPoolPath?: string | null;
  stockCodes?: string[] | null;
  baseRunId?: string | null;
  importDb?: boolean | null;
  equityMode?: 'portfolio_only' | 'traded_daily' | 'all_daily' | null;
}

export interface BacktestActionResponse {
  accepted?: boolean | null;
  status?: string | null;
  message?: string | null;
  taskId?: string | null;
  jobId?: string | null;
  runId?: string | null;
  presetId?: string | null;
  item?: {
    presetId?: string | null;
    name?: string | null;
  } | null;
}

export const backtestsApi = {
  async listPresets(): Promise<BacktestPresetListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/backtests/presets');
    return toCamelCase<BacktestPresetListResponse>(response.data);
  },

  async savePreset(payload: BacktestPresetSaveRequest): Promise<BacktestActionResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/backtests/presets',
      toSnakeCaseDeep(payload),
    );
    return toCamelCase<BacktestActionResponse>(response.data);
  },

  async deletePreset(presetId: string): Promise<BacktestActionResponse> {
    const response = await apiClient.delete<Record<string, unknown>>(
      `/api/v1/backtests/presets/${encodeURIComponent(presetId)}`,
    );
    return toCamelCase<BacktestActionResponse>(response.data);
  },

  async executeRun(payload: BacktestRunExecuteRequest): Promise<BacktestActionResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/backtests/runs/execute',
      toSnakeCaseDeep(payload),
    );
    return toCamelCase<BacktestActionResponse>(response.data);
  },

  async listRuns(limit = 20): Promise<BacktestRunListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/backtests/runs', {
      params: { limit },
    });
    return toCamelCase<BacktestRunListResponse>(response.data);
  },

  async getRun(runId: string): Promise<BacktestRunDetailResponse> {
    const response = await apiClient.get<Record<string, unknown>>(`/api/v1/backtests/runs/${runId}`);
    return toCamelCase<BacktestRunDetailResponse>(response.data);
  },

  async deleteRun(runId: string): Promise<BacktestActionResponse> {
    const response = await apiClient.delete<Record<string, unknown>>(
      `/api/v1/backtests/runs/${encodeURIComponent(runId)}`,
    );
    return toCamelCase<BacktestActionResponse>(response.data);
  },

  async getEquityCurve(runId: string): Promise<BacktestEquityCurveResponse> {
    const response = await apiClient.get<Record<string, unknown>>(`/api/v1/backtests/runs/${runId}/equity-curve`, {
      params: { scope: 'portfolio', granularity: 'daily' },
    });
    return toCamelCase<BacktestEquityCurveResponse>(response.data);
  },

  async listStocks(runId: string, limit = 50): Promise<BacktestStockListResponse> {
    const response = await apiClient.get<Record<string, unknown>>(`/api/v1/backtests/runs/${runId}/stocks`, {
      params: { limit, sort: 'total_return_pct', order: 'desc' },
    });
    return toCamelCase<BacktestStockListResponse>(response.data);
  },

  async getStockDetail(runId: string, stockCode: string): Promise<BacktestStockDetail> {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/backtests/runs/${runId}/stocks/${encodeURIComponent(stockCode)}`,
    );
    return toCamelCase<BacktestStockDetail>(response.data);
  },

  async getStockChart(runId: string, stockCode: string): Promise<BacktestStockChartResponse> {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/backtests/runs/${runId}/stocks/${encodeURIComponent(stockCode)}/chart`,
    );
    return toCamelCase<BacktestStockChartResponse>(response.data);
  },

  async listTrades(runId: string, limit = 100): Promise<BacktestTradeListResponse> {
    const response = await apiClient.get<Record<string, unknown>>(`/api/v1/backtests/runs/${runId}/trades`, {
      params: { limit },
    });
    return toCamelCase<BacktestTradeListResponse>(response.data);
  },
};
