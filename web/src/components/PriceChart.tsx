import { useEffect, useRef } from "react";
import {
  CandlestickSeries,
  ColorType,
  HistogramSeries,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { api } from "../api";

interface Props {
  symbol: string;
}

export function PriceChart({ symbol }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeRef = useRef<ISeriesApi<"Histogram"> | null>(null);

  useEffect(() => {
    if (!container.current) return;
    const chart = createChart(container.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#8b97a8",
        fontFamily: "Inter, system-ui, sans-serif",
      },
      grid: {
        vertLines: { color: "#1c2533" },
        horzLines: { color: "#1c2533" },
      },
      timeScale: { timeVisible: true, secondsVisible: true, borderColor: "#263041" },
      rightPriceScale: { borderColor: "#263041" },
    });
    const candles = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderVisible: false,
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
    });
    const volume = chart.addSeries(HistogramSeries, {
      priceScaleId: "volume",
      priceFormat: { type: "volume" },
      color: "#334155",
    });
    chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    chartRef.current = chart;
    candleRef.current = candles;
    volumeRef.current = volume;
    return () => chart.remove();
  }, []);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const data = await api.candles(symbol);
        if (!active || !candleRef.current || !volumeRef.current) return;
        // The chart library draws times in UTC, so shift them to the viewer's clock.
        const offset = new Date().getTimezoneOffset() * 60;
        candleRef.current.setData(
          data.map((c) => ({
            time: (c.time - offset) as UTCTimestamp,
            open: c.open,
            high: c.high,
            low: c.low,
            close: c.close,
          })),
        );
        volumeRef.current.setData(
          data.map((c) => ({
            time: (c.time - offset) as UTCTimestamp,
            value: c.volume,
            color: c.close >= c.open ? "#14532d" : "#7f1d1d",
          })),
        );
      } catch {
        // The next poll will try again.
      }
    };
    load();
    const timer = window.setInterval(load, 2000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [symbol]);

  return (
    <div className="panel chart">
      <div className="panel-title">
        {symbol} <span className="muted">5 second candles</span>
      </div>
      <div className="chart-box" ref={container} />
    </div>
  );
}
