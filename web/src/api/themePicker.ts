import apiClient from './index';
import { toCamelCase } from './utils';

export type ThemePickerStrategyMode = 'event' | 'holding';

export interface ThemePickerScanRequest {
  themeId?: string;
  themeName?: string;
  boardCode?: string;
  boardName?: string;
  strategyMode: ThemePickerStrategyMode;
  maxCandidates: number;
  includeUntriggered?: boolean;
}

export interface ThemePickerQuery {
  themeId?: string | null;
  themeName?: string | null;
  boardCode?: string | null;
  boardName?: string | null;
  strategyMode: ThemePickerStrategyMode;
  maxCandidates: number;
}

export interface ThemePickerThemeInsight {
  themeName: string;
  eventStatus: string;
  eventScore?: number | null;
  matchedKeywords: string[];
  newsCount: number;
  heatLevel?: string | null;
  boardMappingPath?: string | null;
  boardCandidateCount?: number | null;
  primaryCatalyst?: string | null;
}

export interface ThemePickerStockItem {
  rank: number;
  stockCode: string;
  stockName: string;
  signalLevel: string;
  currentPattern?: string | null;
  selectionReason: string;
  riskNote?: string | null;
  currentPrice?: number | null;
  supportLevel?: number | null;
  pressureLevel?: number | null;
  trendScore?: number | null;
  pctChg?: number | null;
  volumeRatio?: number | null;
  turnoverRate?: number | null;
  buySignal?: string | null;
  dataCompleteness?: string | null;
  miniReasons: string[];
}

export interface ThemePickerSelectedStock {
  stockCode: string;
  stockName: string;
  themeRelevance?: string | null;
  currentPrice?: number | null;
  pctChg?: number | null;
  volumeRatio?: number | null;
  turnoverRate?: number | null;
  trendScore?: number | null;
  trendStatus?: string | null;
  buySignal?: string | null;
  currentPattern?: string | null;
  dataCompleteness?: string | null;
  resonanceCount?: number | null;
  ma5?: number | null;
  ma10?: number | null;
  ma20?: number | null;
  biasMa5?: number | null;
  biasMa10?: number | null;
  biasMa20?: number | null;
  recentStrongDays?: number | null;
  supportLevel?: number | null;
  pressureLevel?: number | null;
  newsSummary: string[];
  selectedReasons: string[];
  riskReasons: string[];
  dataSources: Record<string, string | null | undefined>;
}

export interface ThemePickerSourceInfo {
  boardSource?: string | null;
  boardFallbackUsed?: boolean | null;
  cacheHit?: boolean | null;
  sourcePills: string[];
  note?: string | null;
  responseSchemaVersion?: number | null;
  historyRepaired?: boolean | null;
  keyLevelsBackfilled?: boolean | null;
  boardSourceConfidence?: string | null;
  pricingSource?: string | null;
}

export interface ThemePickerScanResponse {
  query: ThemePickerQuery;
  themeInsight: ThemePickerThemeInsight;
  stocks: ThemePickerStockItem[];
  selectedStock?: ThemePickerSelectedStock | null;
  sourceInfo: ThemePickerSourceInfo;
  emptyReason?: string | null;
}

export interface ThemePickerTaskAccepted {
  taskId: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  message: string;
}

export interface ThemePickerTaskStatus {
  taskId: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress: number;
  message?: string | null;
  result?: ThemePickerScanResponse | null;
  error?: string | null;
  createdAt: string;
  startedAt?: string | null;
  completedAt?: string | null;
}

export interface ThemePickerTaskHistoryItem {
  taskId: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress: number;
  message?: string | null;
  createdAt: string;
  startedAt?: string | null;
  completedAt?: string | null;
  query?: ThemePickerQuery | null;
  themeName?: string | null;
  boardMappingPath?: string | null;
  stockCount: number;
  topStockNames: string[];
  canRetry: boolean;
  result?: ThemePickerScanResponse | null;
  error?: string | null;
}

export interface ThemePickerTaskHistoryListResponse {
  items: ThemePickerTaskHistoryItem[];
}

export interface ThemePickerThemeListItem {
  id: string;
  name: string;
  boardCodes: string[];
  boardNames: string[];
  strategyMode: ThemePickerStrategyMode;
  enabled: boolean;
}

export interface ThemePickerThemeListResponse {
  items: ThemePickerThemeListItem[];
}

export const themePickerApi = {
  async getThemes(): Promise<ThemePickerThemeListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/theme-picker/themes');
    return toCamelCase<ThemePickerThemeListResponse>(response.data);
  },

  async scan(payload: ThemePickerScanRequest): Promise<ThemePickerTaskAccepted> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/theme-picker/scan', {
      theme_id: payload.themeId,
      theme_name: payload.themeName,
      board_code: payload.boardCode,
      board_name: payload.boardName,
      strategy_mode: payload.strategyMode,
      max_candidates: payload.maxCandidates,
      include_untriggered: payload.includeUntriggered ?? false,
    });
    return toCamelCase<ThemePickerTaskAccepted>(response.data);
  },

  async getScanStatus(taskId: string): Promise<ThemePickerTaskStatus> {
    const response = await apiClient.get<Record<string, unknown>>(`/api/v1/theme-picker/status/${taskId}`);
    return toCamelCase<ThemePickerTaskStatus>(response.data);
  },

  async getHistory(limit = 20): Promise<ThemePickerTaskHistoryListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/theme-picker/history', {
      params: { limit },
    });
    return toCamelCase<ThemePickerTaskHistoryListResponse>(response.data);
  },

  async retry(taskId: string): Promise<ThemePickerTaskAccepted> {
    const response = await apiClient.post<Record<string, unknown>>(`/api/v1/theme-picker/retry/${taskId}`);
    return toCamelCase<ThemePickerTaskAccepted>(response.data);
  },
};
