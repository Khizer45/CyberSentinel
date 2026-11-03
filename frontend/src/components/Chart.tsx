/**
 * Plotly chart with a lazily loaded library (kept out of the main bundle) and an accessible data-table
 * alternative. Colours come from the CSS theme tokens so charts follow light/dark mode.
 */
import { useEffect, useRef, useState } from "react";
import type { Config, Data, Layout } from "plotly.js";
import { useTheme } from "../features/theme/ThemeProvider";
import { formatNumber, shiftTimeLabel } from "../utils/format";
import { EmptyState } from "./States";

export interface ChartSeries {
  name: string;
  x: (string | number)[];
  y: number[];
  /** CSS variable name, e.g. ``--chart-2``. */
  colorVar?: string;
}

export type ChartKind = "bar" | "hbar" | "stacked" | "line" | "donut";

interface ChartProps {
  title: string;
  kind: ChartKind;
  series: ChartSeries[];
  height?: number;
  xTitle?: string;
  yTitle?: string;
  /** Per-category colours (CSS variable names) for single-series bar and donut charts. */
  categoryColorVars?: string[];
  /** X values are time buckets (``YYYY-MM-DD`` or ``YYYY-MM-DD HH:mm``) of this granularity. */
  timeBucket?: "day" | "hour";
  emptyMessage?: string;
}

type PlotlyApi = typeof import("plotly.js");
let plotlyPromise: Promise<PlotlyApi> | null = null;

function loadPlotly(): Promise<PlotlyApi> {
  plotlyPromise ??= import("plotly.js-basic-dist-min").then((module) => module.default as PlotlyApi);
  return plotlyPromise;
}

const PALETTE = ["--chart-1", "--chart-2", "--chart-3", "--chart-4", "--chart-5", "--chart-6"];

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#7a869a";
}

function buildFigure(props: ChartProps): { data: Data[]; layout: Partial<Layout> } {
  const { kind, series, height = 280, xTitle, yTitle, categoryColorVars, timeBucket } = props;
  const text = cssVar("--text-muted");
  const grid = cssVar("--chart-grid");
  const seriesColor = (index: number, item: ChartSeries) => cssVar(item.colorVar ?? PALETTE[index % PALETTE.length] ?? "--chart-1");
  const categoryColors = categoryColorVars?.map(cssVar);

  let data: Data[];
  if (kind === "donut") {
    const first = series[0] ?? { name: "", x: [], y: [] };
    data = [
      {
        type: "pie",
        hole: 0.58,
        labels: first.x.map(String),
        values: first.y,
        sort: false,
        textinfo: "percent",
        hovertemplate: "%{label}: %{value:,} (%{percent})<extra></extra>",
        marker: { colors: categoryColors ?? first.x.map((_, index) => cssVar(PALETTE[index % PALETTE.length] ?? "--chart-1")) },
      },
    ];
  } else if (kind === "line") {
    data = series.map((item, index) => ({
      type: "scatter",
      mode: "lines+markers",
      name: item.name,
      x: item.x,
      y: item.y,
      line: { color: seriesColor(index, item), width: 2.5, shape: "spline", smoothing: 0.4 },
      marker: { size: 6 },
    }));
  } else {
    const horizontal = kind === "hbar";
    data = series.map((item, index) => ({
      type: "bar",
      name: item.name,
      orientation: horizontal ? "h" : "v",
      x: horizontal ? item.y : item.x,
      y: horizontal ? item.x : item.y,
      marker: { color: series.length === 1 && categoryColors ? categoryColors : seriesColor(index, item) },
      hovertemplate: horizontal ? "%{y}: %{x:,}<extra></extra>" : "%{x}: %{y:,}<extra></extra>",
    }));
  }

  const axis = { gridcolor: grid, zerolinecolor: grid, linecolor: grid, tickfont: { color: text }, automargin: true };
  let timeAxis: Partial<Layout["xaxis"]> = {};
  if (timeBucket) {
    const unit = timeBucket === "day" ? 86_400_000 : 3_600_000;
    const xs = Array.from(new Set(series.flatMap((item) => item.x.map(String)))).sort();
    timeAxis = {
      type: "date",
      tickformat: timeBucket === "day" ? "%b %d" : "%b %d %H:%M",
      hoverformat: timeBucket === "day" ? "%Y-%m-%d" : "%Y-%m-%d %H:%M",
      // A single bucket would otherwise be auto-ranged to a few milliseconds.
      ...(xs.length === 1 && xs[0] ? { range: [shiftTimeLabel(xs[0], -unit), shiftTimeLabel(xs[0], unit)] } : {}),
      ...(xs.length <= 14 ? { dtick: unit } : {}),
    };
  }
  const layout: Partial<Layout> = {
    height,
    margin: { l: 48, r: 16, t: 12, b: 40 },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: getComputedStyle(document.body).fontFamily, color: text, size: 12 },
    showlegend: kind === "donut" || series.length > 1,
    legend: { orientation: "h", y: kind === "donut" ? -0.05 : -0.2 },
    barmode: kind === "stacked" ? "stack" : "group",
    xaxis: { ...axis, ...timeAxis, title: xTitle ? { text: xTitle } : undefined },
    yaxis: { ...axis, title: yTitle ? { text: yTitle } : undefined, autorange: kind === "hbar" ? "reversed" : true },
    hoverlabel: { bgcolor: cssVar("--surface"), bordercolor: grid, font: { color: cssVar("--text") } },
  };
  return { data, layout };
}

const CONFIG: Partial<Config> = {
  responsive: true,
  displaylogo: false,
  modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d", "toggleSpikelines", "hoverCompareCartesian", "hoverClosestCartesian"],
};

export function Chart(props: ChartProps) {
  const { title, series, emptyMessage = "No data for this selection yet." } = props;
  const { resolved } = useTheme();
  const containerRef = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);
  const hasData = series.some((item) => item.y.some((value) => Number.isFinite(value) && value !== 0));
  // A stable serialization of the figure inputs, so parent re-renders with equal data do not redraw.
  const specKey = JSON.stringify({
    title,
    kind: props.kind,
    timeBucket: props.timeBucket,
    series,
    height: props.height,
    xTitle: props.xTitle,
    yTitle: props.yTitle,
    categoryColorVars: props.categoryColorVars,
  });

  useEffect(() => {
    const node = containerRef.current;
    if (!node || !hasData) return;
    let cancelled = false;
    let plotted: PlotlyApi | null = null;
    const spec = JSON.parse(specKey) as ChartProps;
    const { data, layout } = buildFigure(spec);
    loadPlotly()
      .then(async (Plotly) => {
        if (cancelled) return;
        plotted = Plotly;
        await Plotly.react(node, data, layout, { ...CONFIG, toImageButtonOptions: { filename: spec.title.replace(/\W+/g, "-") } });
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
      // purge() also removes Plotly's window resize listener (responsive mode).
      if (plotted) plotted.purge(node);
    };
    // ``resolved`` is a trigger only: colours are re-read from the CSS tokens when the theme changes.
  }, [specKey, resolved, hasData]);

  if (!hasData) return <EmptyState title="No data" message={emptyMessage} />;

  return (
    <figure style={{ margin: 0 }}>
      {failed ? (
        <p className="muted small">The chart library could not be loaded; the data is available in the table below.</p>
      ) : (
        <div ref={containerRef} className="chart" role="img" aria-label={title} />
      )}
      <details className="data-table-toggle" open={failed || undefined}>
        <summary>Show data table</summary>
        <ChartDataTable title={title} series={series} />
      </details>
    </figure>
  );
}

function ChartDataTable({ title, series }: { title: string; series: ChartSeries[] }) {
  const categories = Array.from(new Set(series.flatMap((item) => item.x.map(String))));
  return (
    <div className="table-wrap">
      <table className="table table-compact">
        <caption className="sr-only">{title}</caption>
        <thead>
          <tr>
            <th scope="col">Category</th>
            {series.map((item) => (
              <th key={item.name} scope="col" className="num">
                {item.name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {categories.map((category) => (
            <tr key={category}>
              <th scope="row">{category}</th>
              {series.map((item) => {
                const index = item.x.map(String).indexOf(category);
                return (
                  <td key={item.name} className="num">
                    {index >= 0 ? formatNumber(item.y[index], Number.isInteger(item.y[index]) ? 0 : 3) : "—"}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Convert a ``{label: count}`` mapping into a single chart series, largest first. */
export function countsToSeries(name: string, counts: Record<string, number> | null | undefined, order?: string[]): ChartSeries {
  const entries = Object.entries(counts ?? {});
  if (order) entries.sort((a, b) => order.indexOf(a[0]) - order.indexOf(b[0]));
  else entries.sort((a, b) => b[1] - a[1]);
  return { name, x: entries.map(([key]) => key), y: entries.map(([, value]) => value) };
}

export const RISK_BAND_ORDER = ["low", "medium", "high", "critical"];
export const RISK_BAND_COLORS = ["--risk-low", "--risk-medium", "--risk-high", "--risk-critical"];
