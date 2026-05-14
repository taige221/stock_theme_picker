import apiClient from './index';
import { toCamelCase } from './utils';

export interface StockWatchlistItem {
  stockCode: string;
  stockName: string;
  groupName?: string | null;
  note?: string | null;
  latestSignal?: string | null;
  latestTheme?: string | null;
  alertEnabled: boolean;
  sourceQueryId?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface StockWatchlistListResponse {
  items: StockWatchlistItem[];
}

export interface StockAlertRuleItem {
  id: number;
  stockCode: string;
  stockName: string;
  ruleType: string;
  thresholdValue?: number | null;
  scanIntervalMinutes: number;
  enabled: boolean;
  note?: string | null;
  sourceQueryId?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface StockAlertRuleListResponse {
  items: StockAlertRuleItem[];
}

export interface StockAlertEventItem {
  id: number;
  stockCode: string;
  stockName: string;
  ruleId: number;
  ruleType: string;
  eventType: string;
  title: string;
  message: string;
  dedupeKey?: string | null;
  payload?: Record<string, unknown> | null;
  sourceQueryId?: string | null;
  linkedAnalysisId?: string | null;
  createdAt: string;
  readAt?: string | null;
}

export interface StockAlertEventListResponse {
  items: StockAlertEventItem[];
}

export interface StockAlertScanSummary {
  scannedRules: number;
  dueRules: number;
  triggeredEvents: number;
  skippedRules: number;
}

export interface StockAlertLoopStatus {
  enabled: boolean;
  running: boolean;
  baseTickSeconds: number;
  lastStartedAt?: string | null;
  lastFinishedAt?: string | null;
  lastError?: string | null;
  lastSummary?: StockAlertScanSummary | null;
}

export interface UpsertStockWatchlistPayload {
  stockCode: string;
  stockName: string;
  groupName?: string;
  note?: string;
  latestSignal?: string;
  latestTheme?: string;
  alertEnabled?: boolean;
  sourceQueryId?: string;
}

export const watchlistApi = {
  async listStocks(): Promise<StockWatchlistListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/watchlist/stocks');
    return toCamelCase<StockWatchlistListResponse>(response.data);
  },

  async upsertStock(payload: UpsertStockWatchlistPayload): Promise<StockWatchlistItem> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/watchlist/stocks', {
      stock_code: payload.stockCode,
      stock_name: payload.stockName,
      group_name: payload.groupName,
      note: payload.note,
      latest_signal: payload.latestSignal,
      latest_theme: payload.latestTheme,
      alert_enabled: payload.alertEnabled ?? false,
      source_query_id: payload.sourceQueryId,
    });
    return toCamelCase<StockWatchlistItem>(response.data);
  },

  async deleteStock(stockCode: string): Promise<void> {
    await apiClient.delete(`/api/v1/watchlist/stocks/${encodeURIComponent(stockCode)}`);
  },

  async listStockAlertRules(stockCode?: string): Promise<StockAlertRuleListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/watchlist/stock-alert-rules', {
      params: stockCode ? { stock_code: stockCode } : undefined,
    });
    return toCamelCase<StockAlertRuleListResponse>(response.data);
  },

  async createDefaultStockAlertRules(payload: {
    stockCode: string;
    stockName: string;
    supportPrice?: number | null;
    breakoutPrice?: number | null;
    scanIntervalMinutes?: number;
    sourceQueryId?: string;
  }): Promise<StockAlertRuleListResponse> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/watchlist/stock-alert-rules/defaults', {
      stock_code: payload.stockCode,
      stock_name: payload.stockName,
      support_price: payload.supportPrice,
      breakout_price: payload.breakoutPrice,
      scan_interval_minutes: payload.scanIntervalMinutes ?? 5,
      source_query_id: payload.sourceQueryId,
    });
    return toCamelCase<StockAlertRuleListResponse>(response.data);
  },

  async deleteStockAlertRule(ruleId: number): Promise<void> {
    await apiClient.delete(`/api/v1/watchlist/stock-alert-rules/${ruleId}`);
  },

  async updateStockAlertRule(payload: {
    ruleId: number;
    thresholdValue?: number | null;
    scanIntervalMinutes?: number;
    enabled?: boolean;
    note?: string;
  }): Promise<StockAlertRuleItem> {
    const response = await apiClient.patch<Record<string, unknown>>(`/api/v1/watchlist/stock-alert-rules/${payload.ruleId}`, {
      threshold_value: payload.thresholdValue,
      scan_interval_minutes: payload.scanIntervalMinutes,
      enabled: payload.enabled,
      note: payload.note,
    });
    return toCamelCase<StockAlertRuleItem>(response.data);
  },

  async listStockAlertEvents(params?: {
    limit?: number;
    stockCode?: string;
    unreadOnly?: boolean;
  }): Promise<StockAlertEventListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/watchlist/stock-alert-events', {
      params: {
        limit: params?.limit ?? 30,
        stock_code: params?.stockCode,
        unread_only: params?.unreadOnly,
      },
    });
    return toCamelCase<StockAlertEventListResponse>(response.data);
  },

  async markStockAlertEventRead(eventId: number): Promise<StockAlertEventItem> {
    const response = await apiClient.patch<Record<string, unknown>>(`/api/v1/watchlist/stock-alert-events/${eventId}/read`);
    return toCamelCase<StockAlertEventItem>(response.data);
  },

  async markAllStockAlertEventsRead(stockCode?: string): Promise<{ updated: number }> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/watchlist/stock-alert-events/read-all', {
      stock_code: stockCode,
    });
    return toCamelCase<{ updated: number }>(response.data);
  },

  async getStockAlertLoopStatus(): Promise<StockAlertLoopStatus> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/watchlist/stock-alert-loop/status');
    return toCamelCase<StockAlertLoopStatus>(response.data);
  },

  async runStockAlertLoopOnce(stockCode?: string): Promise<StockAlertScanSummary> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/watchlist/stock-alert-loop/run-once', null, {
      params: stockCode ? { stock_code: stockCode } : undefined,
    });
    return toCamelCase<StockAlertScanSummary>(response.data);
  },
};
