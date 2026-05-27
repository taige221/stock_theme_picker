import { useEffect, useMemo, useRef } from 'react';
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  createChart,
  createSeriesMarkers,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type LineData,
  type SeriesMarker,
  type Time,
} from 'lightweight-charts';
import type { ParsedApiError } from '../api/error';
import type { BacktestStockChartBar, BacktestStockChartMarker, BacktestStockChartResponse } from '../api/backtests';

interface BacktestStockKlineChartProps {
  chart: BacktestStockChartResponse | null;
  loading: boolean;
  error?: ParsedApiError | null;
  stockCode: string;
  stockName?: string | null;
}

const EMPTY_BARS: BacktestStockChartBar[] = [];
const EMPTY_MARKERS: BacktestStockChartMarker[] = [];

function toTime(date?: string | null): Time {
  return (date ? date.slice(0, 10) : '') as Time;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function formatPct(value?: number | null): string {
  if (!isFiniteNumber(value)) return '';
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(1)}%`;
}

function toCandleData(bars: BacktestStockChartBar[]): CandlestickData[] {
  return bars.flatMap((bar) => {
    if (!bar.tradeDate || !isFiniteNumber(bar.open) || !isFiniteNumber(bar.high) || !isFiniteNumber(bar.low) || !isFiniteNumber(bar.close)) {
      return [];
    }
    return [{
      time: toTime(bar.tradeDate),
      open: bar.open,
      high: bar.high,
      low: bar.low,
      close: bar.close,
    }];
  });
}

function toVolumeData(bars: BacktestStockChartBar[]): HistogramData[] {
  return bars.flatMap((bar) => {
    if (!bar.tradeDate || !isFiniteNumber(bar.volume) || !isFiniteNumber(bar.open) || !isFiniteNumber(bar.close)) {
      return [];
    }
    return [{
      time: toTime(bar.tradeDate),
      value: bar.volume,
      color: bar.close >= bar.open ? 'rgba(196,34,28,0.30)' : 'rgba(19,122,61,0.30)',
    }];
  });
}

function toMaData(bars: BacktestStockChartBar[], key: 'ma5' | 'ma10' | 'ma20'): LineData[] {
  return bars.flatMap((bar) => {
    const value = bar[key];
    if (!bar.tradeDate || !isFiniteNumber(value)) return [];
    return [{ time: toTime(bar.tradeDate), value }];
  });
}

function toSeriesMarkers(markers: BacktestStockChartMarker[]): SeriesMarker<Time>[] {
  return markers.flatMap((marker) => {
    if (!marker.tradeDate) return [];
    const isBuy = marker.type === 'buy';
    const label = isBuy
      ? marker.score != null ? `B ${Number(marker.score).toFixed(0)}` : 'B'
      : marker.returnPct != null ? `S ${formatPct(marker.returnPct)}` : 'S';
    return [{
      time: toTime(marker.tradeDate),
      position: isBuy ? 'belowBar' : 'aboveBar',
      color: isBuy ? '#c4221c' : '#137a3d',
      shape: isBuy ? 'arrowUp' : 'arrowDown',
      text: label,
    }];
  });
}

function isDarkMode(): boolean {
  return document.documentElement.classList.contains('dark');
}

export const BacktestStockKlineChart: React.FC<BacktestStockKlineChartProps> = ({
  chart,
  loading,
  error,
  stockCode,
  stockName,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const ma5SeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const ma10SeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const ma20SeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const markerPluginRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);

  const bars = chart?.bars ?? EMPTY_BARS;
  const markers = chart?.markers ?? EMPTY_MARKERS;
  const title = chart?.stockName ?? stockName ?? '单股K线';
  const visibleCode = chart?.stockCode ?? stockCode;
  const markerSummary = useMemo(() => {
    const buys = markers.filter((marker) => marker.type === 'buy').length;
    const sells = markers.filter((marker) => marker.type === 'sell').length;
    return { buys, sells };
  }, [markers]);

  useEffect(() => {
    if (!containerRef.current) return;
    const dark = isDarkMode();
    const instance = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: dark ? '#0b111b' : '#ffffff' },
        textColor: dark ? '#a6adba' : '#847c70',
        fontFamily: 'Inter, "SF Pro Display", "PingFang SC", system-ui, sans-serif',
        fontSize: 12,
      },
      grid: {
        vertLines: { color: dark ? 'rgba(255,255,255,0.05)' : 'rgba(42,37,32,0.06)' },
        horzLines: { color: dark ? 'rgba(255,255,255,0.05)' : 'rgba(42,37,32,0.06)' },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: dark ? 'rgba(255,255,255,0.22)' : 'rgba(42,37,32,0.22)', width: 1, style: 2 },
        horzLine: { color: dark ? 'rgba(255,255,255,0.22)' : 'rgba(42,37,32,0.22)', width: 1, style: 2 },
      },
      rightPriceScale: {
        borderColor: dark ? 'rgba(255,255,255,0.10)' : 'rgba(42,37,32,0.12)',
      },
      timeScale: {
        borderColor: dark ? 'rgba(255,255,255,0.10)' : 'rgba(42,37,32,0.12)',
        timeVisible: false,
      },
      handleScroll: true,
      handleScale: true,
    });

    chartRef.current = instance;
    const candleSeries = instance.addSeries(CandlestickSeries, {
      upColor: '#c4221c',
      downColor: '#137a3d',
      borderUpColor: '#c4221c',
      borderDownColor: '#137a3d',
      wickUpColor: '#c4221c',
      wickDownColor: '#137a3d',
    });
    candleSeriesRef.current = candleSeries;
    markerPluginRef.current = createSeriesMarkers(candleSeries, []);

    const volumeSeries = instance.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    });
    volumeSeriesRef.current = volumeSeries;
    instance.priceScale('volume').applyOptions({ scaleMargins: { top: 0.83, bottom: 0 } });

    ma5SeriesRef.current = instance.addSeries(LineSeries, {
      color: '#d28a05',
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    ma10SeriesRef.current = instance.addSeries(LineSeries, {
      color: '#2364aa',
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    ma20SeriesRef.current = instance.addSeries(LineSeries, {
      color: '#6d4c41',
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
    });

    const handleResize = () => {
      if (containerRef.current) {
        instance.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    const observer = new ResizeObserver(handleResize);
    observer.observe(containerRef.current);
    handleResize();

    return () => {
      observer.disconnect();
      instance.remove();
      chartRef.current = null;
      markerPluginRef.current = null;
    };
  }, []);

  useEffect(() => {
    const candleData = toCandleData(bars);
    candleSeriesRef.current?.setData(candleData);
    volumeSeriesRef.current?.setData(toVolumeData(bars));
    ma5SeriesRef.current?.setData(toMaData(bars, 'ma5'));
    ma10SeriesRef.current?.setData(toMaData(bars, 'ma10'));
    ma20SeriesRef.current?.setData(toMaData(bars, 'ma20'));
    markerPluginRef.current?.setMarkers(toSeriesMarkers(markers));
    if (candleData.length > 0) {
      chartRef.current?.timeScale().fitContent();
    }
  }, [bars, markers]);

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="min-w-0">
          <h4 className="truncate text-base font-semibold text-foreground">{title}</h4>
          <p className="mt-1 font-mono text-xs text-secondary-text">
            {visibleCode || '--'} · {chart?.priceAdjustment ?? 'qfq'} · {bars.length} 根K线
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-xs text-secondary-text">
          <span className="inline-flex items-center gap-1"><span className="h-2 w-4 rounded-sm bg-[#d28a05]" />MA5</span>
          <span className="inline-flex items-center gap-1"><span className="h-2 w-4 rounded-sm bg-[#2364aa]" />MA10</span>
          <span className="inline-flex items-center gap-1"><span className="h-2 w-4 rounded-sm bg-[#6d4c41]" />MA20</span>
          <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-[#c4221c]" />买 {markerSummary.buys}</span>
          <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-[#137a3d]" />卖 {markerSummary.sells}</span>
        </div>
      </div>

      {error ? (
        <div className="rounded-xl border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-danger">
          {error.message || '加载单股K线失败'}
        </div>
      ) : null}

      <div className="relative overflow-hidden rounded-2xl border border-border/60 bg-card">
        {loading ? (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-card/84 backdrop-blur-sm">
            <div className="flex items-center gap-2 text-sm text-secondary-text">
              <span className="backtest-spinner sm" />
              加载K线
            </div>
          </div>
        ) : null}
        {!loading && !error && bars.length === 0 ? (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-card/84 text-sm text-secondary-text">
            暂无K线缓存
          </div>
        ) : null}
        <div ref={containerRef} className="h-[420px] w-full" />
      </div>

      <div className="flex flex-wrap gap-3 text-xs text-secondary-text">
        <span>数据源: {chart?.dataSource ?? '--'}</span>
        <span>{chart?.startDate ?? '--'} 至 {chart?.endDate ?? '--'}</span>
        <span>只读缓存: {chart?.readOnly ? '是' : '--'}</span>
      </div>
    </div>
  );
};
