// Domain-aware presentational components shared by several pages.
import type { AwsService, Confidence, ConnectionStatus, InvestigationStatus, MetricSeries, ResourceHealth } from "../types/domain";
import { Badge, type Tone } from "./ui";

const STATUS: Record<InvestigationStatus, { tone: Tone; label: string }> = {
  queued: { tone: "neutral", label: "Queued" },
  running: { tone: "info", label: "Investigating" },
  completed: { tone: "ok", label: "Completed" },
  failed: { tone: "bad", label: "Failed" },
  timed_out: { tone: "warn", label: "Timed out" },
};

export function InvestigationStatusBadge({ status }: { status: InvestigationStatus }) {
  const s = STATUS[status];
  return (
    <Badge tone={s.tone} dot pill pulse={status === "running" || status === "queued"}>
      {s.label}
    </Badge>
  );
}

const HEALTH: Record<ResourceHealth, { tone: Tone; label: string }> = {
  healthy: { tone: "ok", label: "Healthy" },
  degraded: { tone: "warn", label: "Warning" },
  unhealthy: { tone: "bad", label: "Unhealthy" },
  unknown: { tone: "neutral", label: "Unknown" },
};
export function HealthBadge({ health }: { health: ResourceHealth }) {
  return (
    <Badge tone={HEALTH[health].tone} dot pill>
      {HEALTH[health].label}
    </Badge>
  );
}

const CONN: Record<ConnectionStatus, { tone: Tone; label: string }> = {
  connected: { tone: "ok", label: "Connected" },
  unvalidated: { tone: "warn", label: "Not validated" },
  error: { tone: "bad", label: "Error" },
};
export function ConnectionStatusBadge({ status }: { status: ConnectionStatus }) {
  return (
    <Badge tone={CONN[status].tone} dot pill>
      {CONN[status].label}
    </Badge>
  );
}

const CONF: Record<Confidence, Tone> = { high: "ok", medium: "warn", low: "bad" };
export function ConfidenceBadge({ confidence, prefix = "Confidence" }: { confidence: Confidence; prefix?: string }) {
  return (
    <Badge tone={CONF[confidence]}>
      {prefix}: {confidence}
    </Badge>
  );
}

export const SERVICE_LABEL: Record<AwsService, string> = { ec2: "EC2", ecs: "ECS", rds: "RDS", lambda: "Lambda", cloudwatch: "CloudWatch" };
export const SERVICE_COLOR: Record<AwsService, string> = {
  ec2: "var(--chart-1)",
  ecs: "var(--chart-2)",
  rds: "var(--chart-3)",
  lambda: "var(--chart-4)",
  cloudwatch: "var(--chart-5)",
};

export function ServiceTag({ service }: { service: AwsService }) {
  return <span className="svc-tag">{SERVICE_LABEL[service]}</span>;
}

// ---------- Charts (dependency-free SVG) ----------

export interface ChartSeries {
  label: string;
  color: string;
  values: number[];
}

function smoothPath(pts: [number, number][]): string {
  if (pts.length < 2) return "";
  let d = `M${pts[0][0]},${pts[0][1]}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i - 1] ?? pts[i];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[i + 2] ?? p2;
    const c1 = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6];
    const c2 = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
    d += ` C${c1[0].toFixed(1)},${c1[1].toFixed(1)} ${c2[0].toFixed(1)},${c2[1].toFixed(1)} ${p2[0].toFixed(1)},${p2[1].toFixed(1)}`;
  }
  return d;
}

let chartSeq = 0;

/** Smooth multi-series line chart with gradient fill, y-axis ticks and time labels. */
export function LineChart({ series, labels, height = 220, unit = "", max: maxIn, threshold, ariaLabel }: {
  series: ChartSeries[];
  labels: string[];
  height?: number;
  unit?: string;
  max?: number;
  threshold?: number;
  ariaLabel: string;
}) {
  const id = `g${++chartSeq}`;
  const w = 640;
  const pad = { t: 10, r: 8, b: 24, l: 40 };
  const all = series.flatMap((s) => s.values);
  const rawMax = Math.max(maxIn ?? 0, ...all, threshold ?? 0, 1);
  const step = niceStep(rawMax / 4);
  const max = maxIn ?? Math.ceil(rawMax / step) * step;
  const ticks = Array.from({ length: Math.round(max / step) + 1 }, (_, i) => i * step);
  const n = Math.max(1, (series[0]?.values.length ?? 1) - 1);
  const x = (i: number) => pad.l + (i / n) * (w - pad.l - pad.r);
  const y = (v: number) => pad.t + (1 - v / max) * (height - pad.t - pad.b);
  const labelEvery = Math.max(1, Math.ceil(labels.length / 8));
  return (
    <svg className="chart" viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none" role="img" aria-label={ariaLabel} style={{ height }}>
      <defs>
        {series.map((s, si) => (
          <linearGradient key={si} id={`${id}-${si}`} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={s.color} stopOpacity={series.length > 1 ? 0.14 : 0.24} />
            <stop offset="100%" stopColor={s.color} stopOpacity="0" />
          </linearGradient>
        ))}
      </defs>
      {ticks.map((t) => (
        <g key={t}>
          <line className="gridline" x1={pad.l} x2={w - pad.r} y1={y(t)} y2={y(t)} vectorEffect="non-scaling-stroke" />
          <text className="axis" x={pad.l - 8} y={y(t) + 3} textAnchor="end">{t}{unit}</text>
        </g>
      ))}
      {threshold !== undefined && <line className="threshold" x1={pad.l} x2={w - pad.r} y1={y(threshold)} y2={y(threshold)} vectorEffect="non-scaling-stroke" />}
      {series.map((s, si) => {
        const pts = s.values.map((v, i) => [x(i), y(v)] as [number, number]);
        const line = smoothPath(pts);
        return (
          <g key={s.label}>
            <path d={`${line} L${x(n)},${y(0)} L${x(0)},${y(0)} Z`} fill={`url(#${id}-${si})`} />
            <path d={line} fill="none" stroke={s.color} strokeWidth={2} vectorEffect="non-scaling-stroke" />
          </g>
        );
      })}
      {labels.map((l, i) => (i % labelEvery === 0 || i === labels.length - 1) && (
        <text key={i} className="axis" x={x(i)} y={height - 6} textAnchor={i === 0 ? "start" : i === labels.length - 1 ? "end" : "middle"}>{l}</text>
      ))}
    </svg>
  );
}

function niceStep(raw: number): number {
  const p = Math.pow(10, Math.floor(Math.log10(raw || 1)));
  const f = raw / p;
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * p;
}

export const hhmm = (t: string) => new Date(t).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false });

/** A CloudWatch metric series rendered as a chart (kept for evidence views). */
export function MetricChart({ series, color = "var(--chart-1)", height = 180 }: { series: MetricSeries; color?: string; height?: number }) {
  return (
    <LineChart
      ariaLabel={`${series.label} chart`}
      series={[{ label: series.label, color, values: series.points.map((p) => p.v) }]}
      labels={series.points.map((p) => hhmm(p.t))}
      unit={series.unit === "%" ? "%" : ""}
      max={series.unit === "%" ? 100 : undefined}
      threshold={series.threshold}
      height={height}
    />
  );
}
