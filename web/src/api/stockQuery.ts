import apiClient from './index';
import { toCamelCase } from './utils';

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
  fundamentalCoverage?: Record<string, string>;
  fundamentalErrors?: string[];
  fundamentalDetails?: StockQueryFundamentalDetails;
  dataSources: Record<string, string | null | undefined>;
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

export const stockQueryApi = {
  async analyze(payload: StockQueryAnalyzeRequest): Promise<StockQueryAnalyzeResponse> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/stock-query/analyze', {
      query: payload.query,
      stock_code: payload.stockCode,
      stock_name: payload.stockName,
    });
    return toCamelCase<StockQueryAnalyzeResponse>(response.data);
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
};
