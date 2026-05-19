import apiClient from './index';
import { toCamelCase } from './utils';

export interface DailyBar {
  date: string | null;
  datetime: string | null;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
  amount: number | null;
  pctChg: number | null;
  ma5: number | null;
  ma10: number | null;
  ma20: number | null;
  volumeRatio: number | null;
}

export interface MarketDailyBarsResponse {
  stockCode: string;
  baseCode: string;
  instrumentType: string;
  instrumentLabel: string;
  requestedBars: number;
  returnedBars: number;
  latestTradeDate: string | null;
  dataSource: string;
  cacheStatus: string;
  dailyBars: DailyBar[];
  errors: string[];
}

export const marketApi = {
  async getDailyBars(stockCode: string, bars = 120): Promise<MarketDailyBarsResponse> {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/market/daily-bars/${encodeURIComponent(stockCode)}`,
      { params: { bars } },
    );
    return toCamelCase<MarketDailyBarsResponse>(response.data);
  },
};
