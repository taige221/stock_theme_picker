import apiClient from './index';
import { toCamelCase } from './utils';
import type { StockAlertRuleItem, StockAlertRuleListResponse } from './watchlist';

export type StockQueryThemeConfidence = 'high' | 'medium' | 'low';

export interface StockQueryAnalyzeRequest {
  query?: string;
  stockCode?: string;
  stockName?: string;
}

export interface StockQueryThemeAttribution {
  themeId: string;
  themeName: string;
  relationType: string;
  confidence: StockQueryThemeConfidence | string;
  reason: string;
}

export interface StockQueryNewsSummary {
  summary?: string;
  provider?: string;
  headlines?: string[];
  catalysts?: string[];
  riskEvents?: string[];
  sentiment?: string;
}

export interface StockQueryBoardItem {
  name: string;
  code?: string;
  type?: string;
}

export interface StockQueryValuationDetails {
  peRatio?: number | null;
  pbRatio?: number | null;
  totalMv?: number | null;
  circMv?: number | null;
}

export interface StockQueryCapitalFlowDetails {
  stockFlow?: {
    mainNetInflow?: number | null;
    inflow5d?: number | null;
    inflow10d?: number | null;
  };
  sectorRankings?: {
    top?: Array<{ name: string; netInflow?: number | null }>;
    bottom?: Array<{ name: string; netInflow?: number | null }>;
  };
}

export interface StockQueryDragonTigerDetails {
  isOnList?: boolean;
  recentCount?: number;
  latestDate?: string | null;
}

export interface StockQueryGrowthDetails {
  revenueYoy?: number | null;
  netProfitYoy?: number | null;
  roe?: number | null;
  grossMargin?: number | null;
}

export interface StockQueryEarningsDetails {
  financialReport?: {
    reportDate?: string | null;
    revenue?: number | null;
    netProfitParent?: number | null;
    operatingCashFlow?: number | null;
    roe?: number | null;
  };
  forecastSummary?: string;
  quickReportSummary?: string;
  dividend?: {
    ttmEventCount?: number | null;
    ttmCashDividendPerShare?: number | null;
    ttmDividendYieldPct?: number | null;
  };
  textSummary?: string;
  textProvider?: string;
  textHeadlines?: string[];
}

export interface StockQueryInstitutionDetails {
  institutionHoldingChange?: number | null;
  top10HolderChange?: number | null;
  textSummary?: string;
  textProvider?: string;
  textHeadlines?: string[];
}

export interface StockQueryFundamentalDetails {
  valuation?: StockQueryValuationDetails;
  growth?: StockQueryGrowthDetails;
  earnings?: StockQueryEarningsDetails;
  institution?: StockQueryInstitutionDetails;
  capitalFlow?: StockQueryCapitalFlowDetails;
  dragonTiger?: StockQueryDragonTigerDetails;
  boards?: {
    items?: StockQueryBoardItem[];
    source?: string;
    provider?: string;
  };
}

export interface StockQueryFundamentalBlock<T = Record<string, unknown>> {
  status?: string;
  data?: T;
  sourceChain?: Array<Record<string, unknown>>;
  errors?: string[];
}

export interface StockQueryFundamentalContext {
  market?: string;
  status?: string;
  coverage?: Record<string, string>;
  sourceChain?: Array<Record<string, unknown>>;
  errors?: string[];
  elapsedMs?: number;
  valuation?: StockQueryFundamentalBlock<StockQueryValuationDetails>;
  growth?: StockQueryFundamentalBlock<StockQueryGrowthDetails>;
  earnings?: StockQueryFundamentalBlock<StockQueryEarningsDetails>;
  institution?: StockQueryFundamentalBlock<StockQueryInstitutionDetails>;
  capitalFlow?: StockQueryFundamentalBlock<StockQueryCapitalFlowDetails>;
  dragonTiger?: StockQueryFundamentalBlock<StockQueryDragonTigerDetails>;
  boards?: StockQueryFundamentalBlock<{
    items?: StockQueryBoardItem[];
    source?: string;
    provider?: string;
  }>;
}

export interface StockQueryAnalyzeResponse {
  queryId?: string | null;
  stockCode: string;
  stockName: string;
  currentPrice?: number | null;
  pctChg?: number | null;
  turnoverRate?: number | null;
  volumeRatio?: number | null;
  peRatio?: number | null;
  pbRatio?: number | null;
  totalMv?: number | null;
  circMv?: number | null;
  trendScore?: number | null;
  signal: string;
  pattern?: string | null;
  support?: number | null;
  pressure?: number | null;
  ma10?: number | null;
  ma20?: number | null;
  biasMa10?: number | null;
  trendStatus?: string | null;
  buySignal?: string | null;
  selectedReasons: string[];
  excludedReasons: string[];
  themeAttributions?: StockQueryThemeAttribution[];
  themes?: StockQueryThemeAttribution[];
  stockNewsSummary?: StockQueryNewsSummary | null;
  fundamentalContext?: StockQueryFundamentalContext | null;
  fundamentalCoverage?: Record<string, string>;
  fundamentalErrors?: string[];
  fundamentalDetails?: StockQueryFundamentalDetails;
  dataSources: Record<string, string | null | undefined>;
}

export interface StockQueryTaskAccepted {
  taskId: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  message: string;
}

export interface StockQueryTaskStatus {
  taskId: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress: number;
  message?: string | null;
  result?: StockQueryAnalyzeResponse | null;
  error?: string | null;
  createdAt: string;
  startedAt?: string | null;
  completedAt?: string | null;
}

export interface StockQueryHistoryItem {
  queryId: string;
  status: string;
  queryText?: string | null;
  stockCode?: string | null;
  stockName?: string | null;
  signal?: string | null;
  error?: string | null;
  createdAt: string;
  completedAt?: string | null;
  result?: StockQueryAnalyzeResponse | null;
}

export interface StockQueryHistoryListResponse {
  items: StockQueryHistoryItem[];
}

export interface StockDeepAnalysisMessage {
  id: number;
  analysisId: string;
  role: string;
  content: string;
  createdAt: string;
}

export interface StockDeepAnalysisTradePlan {
  action?: string;
  actionLabel?: string;
  confidence?: number;
  levels?: {
    currentPrice?: number | null;
    trialPrice?: number | null;
    confirmPrice?: number | null;
    stopLoss?: number | null;
    targetPrice?: number | null;
  };
  positionPlan?: {
    initial?: string;
    add?: string;
    max?: string;
  };
  triggers?: string[];
}

export interface StockDeepAnalysisTechnical {
  trendScore?: number | null;
  trendStatus?: string | null;
  buySignal?: string | null;
  pattern?: string | null;
  support?: number | null;
  pressure?: number | null;
  ma10?: number | null;
  ma20?: number | null;
  biasMa10?: number | null;
  assessment?: string;
}

export interface StockDeepAnalysisFundamental {
  coverage?: Record<string, string>;
  details?: StockQueryFundamentalDetails;
  errors?: string[];
  assessment?: string;
}

export interface StockDeepAnalysisRisk {
  items?: string[];
  newsSummary?: StockQueryNewsSummary | null;
  riskLevel?: string;
}

export interface StockDeepAnalysisContextSnapshot {
  source?: string;
  queryId?: string;
  generationMode?: string;
  generationModel?: string | null;
  stockQueryResult?: StockQueryAnalyzeResponse;
}

export interface StockDeepAnalysisItem {
  analysisId: string;
  stockCode: string;
  stockName: string;
  sourceQueryId?: string | null;
  status: string;
  action?: string | null;
  summary?: string | null;
  tradePlan?: StockDeepAnalysisTradePlan;
  technical?: StockDeepAnalysisTechnical;
  fundamental?: StockDeepAnalysisFundamental;
  risk?: StockDeepAnalysisRisk;
  contextSnapshot?: StockDeepAnalysisContextSnapshot | null;
  error?: string | null;
  createdAt: string;
  updatedAt: string;
  messages: StockDeepAnalysisMessage[];
}

export function buildFundamentalDetails(
  context?: StockQueryFundamentalContext | null,
): StockQueryFundamentalDetails | undefined {
  if (!context) return undefined;
  const details: StockQueryFundamentalDetails = {};
  if (context.valuation?.data) details.valuation = context.valuation.data;
  if (context.growth?.data) details.growth = context.growth.data;
  if (context.earnings?.data) details.earnings = context.earnings.data;
  if (context.institution?.data) details.institution = context.institution.data;
  if (context.capitalFlow?.data) details.capitalFlow = context.capitalFlow.data;
  if (context.dragonTiger?.data) details.dragonTiger = context.dragonTiger.data;
  if (context.boards?.data) details.boards = context.boards.data;
  return Object.keys(details).length > 0 ? details : undefined;
}

export interface StockDeepAnalysisListResponse {
  items: StockDeepAnalysisItem[];
}

export interface StockDeepAnalysisChatResponse {
  analysisId: string;
  userMessage: StockDeepAnalysisMessage;
  assistantMessage: StockDeepAnalysisMessage;
}

export const stockQueryApi = {
  async analyze(payload: StockQueryAnalyzeRequest): Promise<StockQueryTaskAccepted> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/stock-query/analyze', {
      query: payload.query,
      stock_code: payload.stockCode,
      stock_name: payload.stockName,
    });
    return toCamelCase<StockQueryTaskAccepted>(response.data);
  },

  async getAnalyzeStatus(taskId: string): Promise<StockQueryTaskStatus> {
    const response = await apiClient.get<Record<string, unknown>>(`/api/v1/stock-query/status/${encodeURIComponent(taskId)}`);
    return toCamelCase<StockQueryTaskStatus>(response.data);
  },

  async getHistory(limit = 20, stockCode?: string): Promise<StockQueryHistoryListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/stock-query/history', {
      params: {
        limit,
        stock_code: stockCode,
      },
    });
    return toCamelCase<StockQueryHistoryListResponse>(response.data);
  },

  async getHistoryItem(queryId: string): Promise<StockQueryHistoryItem> {
    const response = await apiClient.get<Record<string, unknown>>(`/api/v1/stock-query/history/${queryId}`);
    return toCamelCase<StockQueryHistoryItem>(response.data);
  },

  async createDeepAnalysis(queryId: string, forceRefresh = false): Promise<StockDeepAnalysisItem> {
    const response = await apiClient.post<Record<string, unknown>>(
      `/api/v1/stock-query/${encodeURIComponent(queryId)}/deep-analysis`,
      { force_refresh: forceRefresh },
    );
    return toCamelCase<StockDeepAnalysisItem>(response.data);
  },

  async getDeepAnalysis(analysisId: string): Promise<StockDeepAnalysisItem> {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/stock-query/deep-analysis/${encodeURIComponent(analysisId)}`,
    );
    return toCamelCase<StockDeepAnalysisItem>(response.data);
  },

  async getDeepAnalysisHistory(stockCode: string, limit = 20): Promise<StockDeepAnalysisListResponse> {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/stock-query/${encodeURIComponent(stockCode)}/deep-analysis-history`,
      {
        params: { limit },
      },
    );
    return toCamelCase<StockDeepAnalysisListResponse>(response.data);
  },

  async chatDeepAnalysis(analysisId: string, message: string): Promise<StockDeepAnalysisChatResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      `/api/v1/stock-query/deep-analysis/${encodeURIComponent(analysisId)}/chat`,
      { message },
    );
    return toCamelCase<StockDeepAnalysisChatResponse>(response.data);
  },

  async createDeepAnalysisAlertRules(
    analysisId: string,
    scanIntervalMinutes = 5,
  ): Promise<StockAlertRuleListResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      `/api/v1/stock-query/deep-analysis/${encodeURIComponent(analysisId)}/alert-rules`,
      { scan_interval_minutes: scanIntervalMinutes },
    );
    return toCamelCase<StockAlertRuleListResponse>(response.data);
  },
};

export type { StockAlertRuleItem };
