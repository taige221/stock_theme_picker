import apiClient from './index';
import { toCamelCase } from './utils';

export interface InformationWatchItem {
  itemId: string;
  name: string;
  enabled: boolean;
  isSystem: boolean;
  priority: number;
  eventType: string;
  seedTerms: string[];
  aliases: string[];
  themes: string[];
  chainTags: string[];
  sourceTiers: string[];
  freshnessDays: number;
  notes?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface OpenDiscoveryProfile {
  profileId: string;
  name: string;
  enabled: boolean;
  priority: number;
  eventType: string;
  queryTemplates: string[];
  themes: string[];
  chainTags: string[];
  sourceTiers: string[];
  freshnessDays: number;
  notes?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface InformationWatchEvent {
  eventId: string;
  watchItemId?: string | null;
  watchItemName?: string | null;
  title: string;
  summary?: string | null;
  eventType: string;
  impactDirection?: string | null;
  sourceMode: string;
  sourceTier: string;
  provider?: string | null;
  sourceHost?: string | null;
  clusterKey?: string | null;
  clusterLabel?: string | null;
  url?: string | null;
  publishedAt?: string | null;
  firstSeenAt?: string | null;
  lastSeenAt?: string | null;
  isNewEvent: boolean;
  duplicateKey?: string | null;
  themes: string[];
  chainTags: string[];
  entities: Record<string, unknown>;
  metadata: Record<string, unknown>;
  freshnessScore: number;
  credibilityScore: number;
  signalStrength: number;
  status: string;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface InformationWatchItemListResponse {
  items: InformationWatchItem[];
}

export interface OpenDiscoveryProfileListResponse {
  items: OpenDiscoveryProfile[];
}

export interface InformationEventListResponse {
  items: InformationWatchEvent[];
}

export interface InformationWatchRunOnceResponse {
  scannedItems: number;
  createdEvents: number;
  promotedEvents: number;
  items: InformationWatchEvent[];
}

export interface OpenDiscoveryRunOnceResponse {
  scannedProfiles: number;
  createdEvents: number;
  promotedEvents: number;
  items: InformationWatchEvent[];
}

export interface OpenDiscoveryCandidate {
  clusterKey: string;
  label: string;
  eventType: string;
  themes: string[];
  chainTags: string[];
  eventCount: number;
  promotedCount: number;
  sourceHosts: string[];
  sourceTiers: string[];
  hardSourceConfirmed: boolean;
  candidateScore: number;
  representativeEventId?: string | null;
  representativeTitle?: string | null;
  latestPublishedAt?: string | null;
  watchItemId?: string | null;
  watchItemName?: string | null;
  status: string;
}

export interface OpenDiscoveryCandidateListResponse {
  items: OpenDiscoveryCandidate[];
}

export interface InformationWatchItemUpsertPayload {
  itemId?: string;
  name: string;
  enabled?: boolean;
  priority?: number;
  eventType: string;
  seedTerms: string[];
  aliases?: string[];
  themes?: string[];
  chainTags?: string[];
  sourceTiers?: string[];
  freshnessDays?: number;
  notes?: string | null;
}

export interface ThemeFactorScanEventResult {
  eventId?: string;
  title?: string;
  eventType?: string;
  sourceTier?: string;
}

export interface ThemeFactorScanEtfConfirmation {
  etfCode?: string | null;
  etfName?: string | null;
  pctChg?: number | null;
  volumeRatio?: number | null;
  score?: number | null;
  confirmed?: boolean;
  confirmedCount?: number | null;
  items?: Array<{
    etfCode?: string | null;
    etfName?: string | null;
    pctChg?: number | null;
    volumeRatio?: number | null;
    score?: number | null;
    confirmed?: boolean;
  }>;
}

export interface ThemeFactorScanStockItem {
  rank?: number;
  stockCode?: string;
  stockName?: string;
  signalLevel?: string;
  selectionReason?: string;
  currentPrice?: number | null;
  trendScore?: number | null;
  pctChg?: number | null;
  volumeRatio?: number | null;
  turnoverRate?: number | null;
}

export interface ThemeFactorScanResultPayload {
  event?: ThemeFactorScanEventResult;
  etfConfirmation?: ThemeFactorScanEtfConfirmation;
  leaderConfirmation?: {
    score?: number | null;
    stockCode?: string | null;
    stockName?: string | null;
    signalLevel?: string | null;
    trendScore?: number | null;
    selectionReason?: string | null;
  };
  roleBreakdown?: {
    leader?: ThemeFactorScanStockItem | null;
    firstOrder?: ThemeFactorScanStockItem[];
    secondOrder?: ThemeFactorScanStockItem[];
    observe?: ThemeFactorScanStockItem[];
    breadthScore?: number | null;
  };
  themeScan?: {
    query?: {
      themeId?: string | null;
      themeName?: string | null;
      boardCode?: string | null;
      boardName?: string | null;
      strategyMode?: 'event' | 'holding' | null;
      maxCandidates?: number | null;
    };
    themeInsight?: Record<string, unknown>;
    stocks?: ThemeFactorScanStockItem[];
    selectedStock?: Record<string, unknown> | null;
    sourceInfo?: Record<string, unknown>;
    emptyReason?: string | null;
  };
}

export interface ThemeFactorScanItem {
  scanId: string;
  eventId: string;
  themeId?: string | null;
  themeName: string;
  status: string;
  eventScore?: number | null;
  etfConfirmationScore?: number | null;
  leaderConfirmationScore?: number | null;
  themeFactorScore?: number | null;
  result: ThemeFactorScanResultPayload;
  error?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface ThemeFactorScanListResponse {
  items: ThemeFactorScanItem[];
}

export interface ThemeFactorScanRunOnceResponse {
  scannedEvents: number;
  generatedScans: number;
  items: ThemeFactorScanItem[];
}

export interface InformationReviewBreakdownItem {
  key: string;
  label: string;
  eventCount: number;
  promotedCount: number;
  scanCount: number;
  highScoreCount: number;
  avgSignalStrength: number;
  avgThemeFactorScore: number;
}

export interface InformationReviewSummary {
  days: number;
  totalEvents: number;
  promotedEvents: number;
  discoveryEvents: number;
  scanCount: number;
  highScoreScanCount: number;
  confirmedEtfScanCount: number;
  promotedRate: number;
  scanConversionRate: number;
  highScoreRate: number;
  confirmedEtfRate: number;
  topThemes: Array<{ label: string; count: number }>;
  topSourceHosts: Array<{ label: string; count: number }>;
  eventTypeBreakdown: InformationReviewBreakdownItem[];
}

export const informationWatchApi = {
  async listItems(): Promise<InformationWatchItemListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/theme-picker/information-watch/items');
    return toCamelCase<InformationWatchItemListResponse>(response.data);
  },

  async listEvents(limit = 30, promotedOnly = false, status?: string): Promise<InformationEventListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/theme-picker/information-watch/events', {
      params: {
        limit,
        promoted_only: promotedOnly,
        status: status || undefined,
      },
    });
    return toCamelCase<InformationEventListResponse>(response.data);
  },

  async runOnce(payload?: { limit?: number; itemIds?: string[] }): Promise<InformationWatchRunOnceResponse> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/theme-picker/information-watch/run-once', {
      limit: payload?.limit ?? 20,
      item_ids: payload?.itemIds ?? [],
    });
    return toCamelCase<InformationWatchRunOnceResponse>(response.data);
  },

  async upsertItem(payload: InformationWatchItemUpsertPayload): Promise<InformationWatchItem> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/theme-picker/information-watch/items', {
      item_id: payload.itemId,
      name: payload.name,
      enabled: payload.enabled ?? true,
      priority: payload.priority ?? 100,
      event_type: payload.eventType,
      seed_terms: payload.seedTerms,
      aliases: payload.aliases ?? [],
      themes: payload.themes ?? [],
      chain_tags: payload.chainTags ?? [],
      source_tiers: payload.sourceTiers ?? ['L1', 'L2'],
      freshness_days: payload.freshnessDays ?? 3,
      notes: payload.notes ?? null,
    });
    return toCamelCase<InformationWatchItem>(response.data);
  },

  async deleteItem(itemId: string): Promise<void> {
    await apiClient.delete(`/api/v1/theme-picker/information-watch/items/${encodeURIComponent(itemId)}`);
  },

  async listDiscoveryProfiles(): Promise<OpenDiscoveryProfileListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/theme-picker/information-discovery/profiles');
    return toCamelCase<OpenDiscoveryProfileListResponse>(response.data);
  },

  async listDiscoveryEvents(limit = 30, promotedOnly = false, status?: string): Promise<InformationEventListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/theme-picker/information-discovery/events', {
      params: {
        limit,
        promoted_only: promotedOnly,
        status: status || undefined,
      },
    });
    return toCamelCase<InformationEventListResponse>(response.data);
  },

  async runDiscoveryOnce(payload?: { limit?: number; profileIds?: string[] }): Promise<OpenDiscoveryRunOnceResponse> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/theme-picker/information-discovery/run-once', {
      limit: payload?.limit ?? 12,
      profile_ids: payload?.profileIds ?? [],
    });
    return toCamelCase<OpenDiscoveryRunOnceResponse>(response.data);
  },

  async promoteDiscoveryEventToWatchItem(eventId: string): Promise<InformationWatchItem> {
    const response = await apiClient.post<Record<string, unknown>>(
      `/api/v1/theme-picker/information-discovery/events/${encodeURIComponent(eventId)}/watch-item`,
    );
    return toCamelCase<InformationWatchItem>(response.data);
  },

  async listDiscoveryCandidates(limit = 20, promotedOnly = true): Promise<OpenDiscoveryCandidateListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/theme-picker/information-discovery/candidates', {
      params: {
        limit,
        promoted_only: promotedOnly,
      },
    });
    return toCamelCase<OpenDiscoveryCandidateListResponse>(response.data);
  },

  async promoteDiscoveryCandidateToWatchItem(clusterKey: string): Promise<InformationWatchItem> {
    const response = await apiClient.post<Record<string, unknown>>(
      `/api/v1/theme-picker/information-discovery/candidates/${encodeURIComponent(clusterKey)}/watch-item`,
    );
    return toCamelCase<InformationWatchItem>(response.data);
  },
};

export const themeFactorScanApi = {
  async listScans(limit = 20, eventId?: string): Promise<ThemeFactorScanListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/theme-picker/theme-factor-scans', {
      params: {
        limit,
        event_id: eventId,
      },
    });
    return toCamelCase<ThemeFactorScanListResponse>(response.data);
  },

  async runOnce(payload?: {
    limit?: number;
    eventIds?: string[];
    minSignalStrength?: number;
  }): Promise<ThemeFactorScanRunOnceResponse> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/theme-picker/theme-factor-scans/run-once', {
      limit: payload?.limit ?? 10,
      event_ids: payload?.eventIds ?? [],
      min_signal_strength: payload?.minSignalStrength ?? 70,
    });
    return toCamelCase<ThemeFactorScanRunOnceResponse>(response.data);
  },

  async getReviewSummary(days = 7): Promise<InformationReviewSummary> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/theme-picker/information-review/summary', {
      params: { days },
    });
    return toCamelCase<InformationReviewSummary>(response.data);
  },
};
