import apiClient from './index';
import { toCamelCase } from './utils';
import type { StockAlertRuleItem, StockAlertRuleListResponse } from './watchlist';

export type StockQueryThemeConfidence = 'high' | 'medium' | 'low';

export interface StockQueryAnalyzeRequest {
  query?: string;
  stockCode?: string;
  stockName?: string;
  strategy?: string;
}

export interface StockQueryStrategyDecision {
  key: string;
  label: string;
  matched: boolean;
  signal: string;
  pattern?: string | null;
  biasMa10?: number | null;
  selectedReasons?: string[];
  excludedReasons?: string[];
}

export interface StockQueryThemeAttribution {
  themeId: string;
  themeName: string;
  relationType: string;
  confidence: StockQueryThemeConfidence | string;
  reason: string;
  matchedBoards?: string[];
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
  asOf?: string | null;
  lookbackDays?: number | null;
  sampleCount?: number | null;
  pePercentile?: number | null;
  pbPercentile?: number | null;
  peLow?: number | null;
  peHigh?: number | null;
  pbLow?: number | null;
  pbHigh?: number | null;
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
    status?: string;
    reason?: string;
  };
}

export interface StockQueryDragonTigerDetails {
  isOnList?: boolean;
  recentCount?: number;
  latestDate?: string | null;
  reason?: string | null;
  netBuyAmount?: number | null;
  institutionNetBuy?: number | null;
  buySeats?: string[];
  sellSeats?: string[];
}

export interface StockQueryTextSupplement {
  summary?: string;
  provider?: string;
  headlines?: string[];
  highlights?: string[];
}

export interface StockQueryConceptAttribution {
  summary?: string;
  primaryConcept?: string | null;
  conceptNames?: string[];
  matchedBoardNames?: string[];
  matchedThemes?: StockQueryThemeAttribution[];
}

export interface StockQueryPeerItem {
  stockCode: string;
  stockName: string;
  industry?: string | null;
  price?: number | null;
  pctChg?: number | null;
  turnoverRate?: number | null;
  volumeRatio?: number | null;
  peRatio?: number | null;
  pbRatio?: number | null;
  totalMv?: number | null;
  circMv?: number | null;
  revenueYoy?: number | null;
  netProfitYoy?: number | null;
  roe?: number | null;
  grossMargin?: number | null;
  isTarget?: boolean;
}

export interface StockQueryPeerComparison {
  industry?: string | null;
  source?: string | null;
  provider?: string | null;
  items?: StockQueryPeerItem[];
}

export interface StockQueryContextSupplement {
  profile?: StockQueryTextSupplement | null;
  announcements?: StockQueryTextSupplement | null;
  lockup?: StockQueryTextSupplement | null;
  conceptAttribution?: StockQueryConceptAttribution | null;
  peers?: StockQueryPeerComparison | null;
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
  balanceSheet?: {
    reportDate?: string | null;
    totalAssets?: number | null;
    totalLiabilities?: number | null;
    shareholderEquity?: number | null;
    cashAndEquivalents?: number | null;
    shortDebt?: number | null;
    debtToAsset?: number | null;
    cashToShortDebt?: number | null;
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
  instrumentType?: string | null;
  instrumentLabel?: string | null;
  strategy?: string;
  strategyLabel?: string | null;
  currentPrice?: number | null;
  pctChg?: number | null;
  turnoverRate?: number | null;
  volumeRatio?: number | null;
  peRatio?: number | null;
  pbRatio?: number | null;
  totalMv?: number | null;
  circMv?: number | null;
  change60d?: number | null;
  high52w?: number | null;
  low52w?: number | null;
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
  strategyDecisions?: StockQueryStrategyDecision[];
  themeAttributions?: StockQueryThemeAttribution[];
  themes?: StockQueryThemeAttribution[];
  stockNewsSummary?: StockQueryNewsSummary | null;
  stockContextSupplement?: StockQueryContextSupplement | null;
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
  instrumentType?: string | null;
  instrumentLabel?: string | null;
  signal?: string | null;
  error?: string | null;
  createdAt: string;
  completedAt?: string | null;
  result?: StockQueryAnalyzeResponse | null;
}

export interface StockQueryHistoryListResponse {
  items: StockQueryHistoryItem[];
}

export interface EtfMarketBar {
  datetime: string;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  close?: number | null;
  volume?: number | null;
  amount?: number | null;
}

export interface EtfMarketQuote {
  name?: string | null;
  price?: number | null;
  lastClose?: number | null;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  changeAmount?: number | null;
  changePct?: number | null;
  amountWan?: number | null;
  turnoverRate?: number | null;
  peTtm?: number | null;
  amplitudePct?: number | null;
  totalMarketValueYi?: number | null;
  floatMarketValueYi?: number | null;
  pb?: number | null;
  limitUp?: number | null;
  limitDown?: number | null;
  volumeRatio?: number | null;
  peStatic?: number | null;
  tradeTime?: string | null;
  volume?: number | null;
  amount?: number | null;
  serverTime?: string | null;
  bid1?: number | null;
  ask1?: number | null;
  bidVol1?: number | null;
  askVol1?: number | null;
  rawSource?: string | null;
}

export interface EtfMarketProfile {
  fundFullName?: string | null;
  fundType?: string | null;
  trackingTarget?: string | null;
  performanceBenchmark?: string | null;
  investmentObjective?: string | null;
}

export interface EtfMarketHolding {
  rank?: number | null;
  stockCode?: string | null;
  stockName?: string | null;
  weightPct?: number | null;
  sharesWan?: number | null;
  marketValueWan?: number | null;
  reportPeriod?: string | null;
}

export interface EtfMarketAnalysis {
  signal: string;
  pattern?: string | null;
  summary?: string | null;
  support?: number | null;
  pressure?: number | null;
  ma5?: number | null;
  ma10?: number | null;
  ma20?: number | null;
  biasMa10?: number | null;
  selectedReasons: string[];
  riskReasons: string[];
}

export interface EtfEstimatedIopv {
  value?: number | null;
  premiumDiscountPct?: number | null;
  coverageWeightPct?: number | null;
  matchedHoldingsCount: number;
  totalHoldingsCount: number;
  reportPeriod?: string | null;
  basis?: string | null;
  note?: string | null;
}

export interface EtfDailyMetrics {
  tradeDate?: string | null;
  fundShares?: number | null;
  nav?: number | null;
  derivedFundSizeYi?: number | null;
  exchange?: string | null;
  dataSource?: string | null;
  updatedAt?: string | null;
  cacheStatus?: string | null;
}

export interface EtfDailyMetricsRefreshResponse {
  stockCode: string;
  baseCode: string;
  instrumentType: string;
  instrumentLabel: string;
  refreshed: boolean;
  cacheStatus: string;
  dailyMetrics: EtfDailyMetrics;
  errors: string[];
}

export interface EtfMarketSnapshotResponse {
  queryId?: string | null;
  stockCode: string;
  baseCode: string;
  stockName: string;
  instrumentType: string;
  instrumentLabel: string;
  quote: EtfMarketQuote;
  dailyBars: EtfMarketBar[];
  orderBook: EtfMarketQuote;
  profile: EtfMarketProfile;
  topHoldings: EtfMarketHolding[];
  analysis: EtfMarketAnalysis;
  estimatedIopv: EtfEstimatedIopv;
  dailyMetrics: EtfDailyMetrics;
  dataSources: Record<string, string | null | undefined>;
  errors: string[];
}

export interface EtfQueryHistoryItem {
  queryId: string;
  status: string;
  queryText?: string | null;
  stockCode?: string | null;
  stockName?: string | null;
  error?: string | null;
  createdAt: string;
  completedAt?: string | null;
  result?: EtfMarketSnapshotResponse | null;
}

export interface EtfQueryHistoryListResponse {
  items: EtfQueryHistoryItem[];
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
  contextSupplement?: StockQueryContextSupplement | null;
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
      strategy: payload.strategy,
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

  async getEtfMarketSnapshot(stockCode: string, bars = 60): Promise<EtfMarketSnapshotResponse> {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/stock-query/etf-market/${encodeURIComponent(stockCode)}`,
      {
        params: { bars },
      },
    );
    return toCamelCase<EtfMarketSnapshotResponse>(response.data);
  },

  async refreshEtfDailyMetrics(stockCode: string): Promise<EtfDailyMetricsRefreshResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      `/api/v1/stock-query/etf-daily-metrics/${encodeURIComponent(stockCode)}/refresh`,
    );
    return toCamelCase<EtfDailyMetricsRefreshResponse>(response.data);
  },

  async getEtfHistory(limit = 20, stockCode?: string): Promise<EtfQueryHistoryListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/stock-query/etf-history', {
      params: {
        limit,
        stock_code: stockCode,
      },
    });
    return toCamelCase<EtfQueryHistoryListResponse>(response.data);
  },

  async getEtfHistoryItem(queryId: string): Promise<EtfQueryHistoryItem> {
    const response = await apiClient.get<Record<string, unknown>>(`/api/v1/stock-query/etf-history/${queryId}`);
    return toCamelCase<EtfQueryHistoryItem>(response.data);
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

  async getDeepAnalysisHistory(stockCode?: string, limit = 20): Promise<StockDeepAnalysisListResponse> {
    const response = await apiClient.get<Record<string, unknown>>(
      stockCode
        ? `/api/v1/stock-query/${encodeURIComponent(stockCode)}/deep-analysis-history`
        : '/api/v1/stock-query/deep-analysis-history',
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
