import { useEffect, useRef, useState } from 'react';
import { createChart, ColorType, CrosshairMode, CandlestickSeries, LineSeries, HistogramSeries, type IChartApi, type ISeriesApi, type CandlestickData, type LineData, type Time, type HistogramData } from 'lightweight-charts';
import { marketApi, type DailyBar } from '../api/market';
import { getParsedApiError, type ParsedApiError } from '../api/error';

interface CandlestickChartProps {
  stockCode: string;
  stockName: string;
  bars?: number;
}

function toTimestamp(dateStr: string | null): Time {
  if (!dateStr) return '' as Time;
  return dateStr.substring(0, 10) as Time;
}

function isDarkMode(): boolean {
  return document.documentElement.classList.contains('dark');
}

export const CandlestickChart: React.FC<CandlestickChartProps> = ({ stockCode, stockName, bars = 120 }) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const ma5SeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const ma10SeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const ma20SeriesRef = useRef<ISeriesApi<'Line'> | null>(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [info, setInfo] = useState<{ returnedBars: number; dataSource: string; cacheStatus: string } | null>(null);

  useEffect(() => {
    if (!chartContainerRef.current) return;

    const dark = isDarkMode();
    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: dark ? '#0a0f1a' : '#ffffff' },
        textColor: dark ? '#9ca3af' : '#6b7280',
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        fontSize: 12,
      },
      grid: {
        vertLines: { color: dark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.04)' },
        horzLines: { color: dark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.04)' },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: dark ? 'rgba(255,255,255,0.2)' : 'rgba(0,0,0,0.2)', width: 1, style: 2 },
        horzLine: { color: dark ? 'rgba(255,255,255,0.2)' : 'rgba(0,0,0,0.2)', width: 1, style: 2 },
      },
      rightPriceScale: {
        borderColor: dark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)',
      },
      timeScale: {
        borderColor: dark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)',
        timeVisible: false,
      },
      handleScroll: true,
      handleScale: true,
    });

    chartRef.current = chart;

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#ef4444',
      downColor: '#22c55e',
      borderUpColor: '#ef4444',
      borderDownColor: '#22c55e',
      wickUpColor: '#ef4444',
      wickDownColor: '#22c55e',
    });
    candleSeriesRef.current = candleSeries;

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    });
    volumeSeriesRef.current = volumeSeries;

    chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.85, bottom: 0 },
    });

    const ma5Series = chart.addSeries(LineSeries, {
      color: '#f59e0b',
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    ma5SeriesRef.current = ma5Series;

    const ma10Series = chart.addSeries(LineSeries, {
      color: '#06b6d4',
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    ma10SeriesRef.current = ma10Series;

    const ma20Series = chart.addSeries(LineSeries, {
      color: '#a855f7',
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    ma20SeriesRef.current = ma20Series;

    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };
    const observer = new ResizeObserver(handleResize);
    observer.observe(chartContainerRef.current);

    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    const fetchData = async () => {
      setLoading(true);
      setError(null);
      setInfo(null);
      try {
        const response = await marketApi.getDailyBars(stockCode, bars);
        if (cancelled) return;

        const dailyBars = response.dailyBars;
        setInfo({
          returnedBars: response.returnedBars,
          dataSource: response.dataSource,
          cacheStatus: response.cacheStatus,
        });

        const candleData: CandlestickData[] = [];
        const volumeData: HistogramData[] = [];
        const ma5Data: LineData[] = [];
        const ma10Data: LineData[] = [];
        const ma20Data: LineData[] = [];

        dailyBars.forEach((bar: DailyBar) => {
          if (!bar.date || bar.open === null || bar.high === null || bar.low === null || bar.close === null) return;

          const time = toTimestamp(bar.date);
          candleData.push({ time, open: bar.open, high: bar.high, low: bar.low, close: bar.close });

          if (bar.volume !== null) {
            const isUp = bar.close >= bar.open;
            volumeData.push({
              time,
              value: bar.volume,
              color: isUp ? 'rgba(239,68,68,0.3)' : 'rgba(34,197,94,0.3)',
            });
          }

          if (bar.ma5 !== null) ma5Data.push({ time, value: bar.ma5 });
          if (bar.ma10 !== null) ma10Data.push({ time, value: bar.ma10 });
          if (bar.ma20 !== null) ma20Data.push({ time, value: bar.ma20 });
        });

        candleSeriesRef.current?.setData(candleData);
        volumeSeriesRef.current?.setData(volumeData);
        ma5SeriesRef.current?.setData(ma5Data);
        ma10SeriesRef.current?.setData(ma10Data);
        ma20SeriesRef.current?.setData(ma20Data);

        chartRef.current?.timeScale().fitContent();
      } catch (requestError) {
        if (!cancelled) {
          setError(getParsedApiError(requestError));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void fetchData();
    return () => { cancelled = true; };
  }, [stockCode, bars]);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h3 className="text-lg font-semibold text-foreground">{stockName}</h3>
          <span className="text-sm text-secondary-text">{stockCode}</span>
        </div>
        <div className="flex items-center gap-3 text-xs text-secondary-text">
          <span className="inline-flex items-center gap-1">
            <span className="inline-block h-2 w-4 rounded-sm" style={{ backgroundColor: '#f59e0b' }} />
            MA5
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="inline-block h-2 w-4 rounded-sm" style={{ backgroundColor: '#06b6d4' }} />
            MA10
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="inline-block h-2 w-4 rounded-sm" style={{ backgroundColor: '#a855f7' }} />
            MA20
          </span>
        </div>
      </div>

      {error ? (
        <div className="rounded-2xl border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-danger">
          {error.message || '加载K线数据失败'}
        </div>
      ) : null}

      <div className="relative overflow-hidden rounded-2xl border border-border/60 bg-background">
        {loading ? (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-background/80">
            <div className="flex items-center gap-2 text-sm text-secondary-text">
              <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              加载K线数据...
            </div>
          </div>
        ) : null}
        <div ref={chartContainerRef} style={{ width: '100%', height: 420 }} />
      </div>

      {info ? (
        <div className="flex flex-wrap gap-3 text-xs text-secondary-text">
          <span>{info.returnedBars} 根K线</span>
          <span>数据源: {info.dataSource}</span>
          <span>缓存: {info.cacheStatus}</span>
        </div>
      ) : null}
    </div>
  );
};
