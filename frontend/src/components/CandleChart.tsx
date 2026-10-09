import { useEffect, useRef } from "react";
import { ColorType, LineStyle, createChart } from "lightweight-charts";
import type { Time } from "lightweight-charts";
import type { Candle, FeedRow } from "../types";

export default function CandleChart({ candles, row }: { candles: Candle[]; row: FeedRow }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const chart = createChart(el, {
      width: el.clientWidth,
      height: 340,
      layout: { background: { type: ColorType.Solid, color: "#080c10" }, textColor: "#6b7e93" },
      grid: { vertLines: { color: "#1c2733" }, horzLines: { color: "#1c2733" } },
      rightPriceScale: { borderColor: "#243141" },
      timeScale: { borderColor: "#243141", timeVisible: true, secondsVisible: false },
    });
    const series = chart.addCandlestickSeries({
      upColor: "#22c55e", downColor: "#ef4444", wickUpColor: "#22c55e", wickDownColor: "#ef4444", borderVisible: false,
    });
    series.setData(candles.map((c) => ({ ...c, time: c.time as Time })));

    const line = (price: number | null, color: string, title: string, style: LineStyle, width: 1 | 2 = 1) => {
      if (price !== null && price > 0) series.createPriceLine({ price, color, title, lineStyle: style, lineWidth: width, axisLabelVisible: true });
    };
    line(row.entry,        "#60a5fa", "Entry",    LineStyle.Solid, 2);
    line(row.stop,         "#f87171", "Stop",     LineStyle.Solid, 2);
    line(row.target,       "#4ade80", "Target",   LineStyle.Solid, 2);
    line(row.htf_proximal, "#a78bfa", "HTF prox", LineStyle.Dashed);
    line(row.htf_distal,   "#a78bfa", "HTF dist", LineStyle.Dotted);
    line(row.ltf_proximal, "#f5a524", "LTF prox", LineStyle.Dashed);
    line(row.ltf_distal,   "#f5a524", "LTF dist", LineStyle.Dotted);
    chart.timeScale().fitContent();

    const ro = new ResizeObserver(() => chart.applyOptions({ width: el.clientWidth }));
    ro.observe(el);
    return () => { ro.disconnect(); chart.remove(); };
  }, [candles, row]);

  return <div ref={ref} className="chart" />;
}
