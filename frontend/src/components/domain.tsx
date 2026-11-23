// Domain-aware presentational components shared by several pages.
import { Box, Cloud, Container, Database, Server, Zap } from "lucide-react";
import type { ReactNode } from "react";
import type { AwsService, Confidence, ConnectionStatus, InvestigationStatus, MetricSeries, ResourceHealth } from "../types/domain";
import { Badge, type Tone } from "./ui";

const STATUS: Record<InvestigationStatus, { tone: Tone; label: string }> = {
  queued: { tone: "neutral", label: "Queued" },
  running: { tone: "accent", label: "Running" },
  completed: { tone: "ok", label: "Completed" },
  failed: { tone: "bad", label: "Failed" },
  timed_out: { tone: "warn", label: "Timed out" },
};

export function InvestigationStatusBadge({ status }: { status: InvestigationStatus }) {
  const s = STATUS[status];
  return (
    <Badge tone={s.tone} dot pulse={status === "running" || status === "queued"}>
      {s.label}
    </Badge>
  );
}

const HEALTH: Record<ResourceHealth, Tone> = { healthy: "ok", degraded: "warn", unhealthy: "bad", unknown: "neutral" };
export function HealthBadge({ health }: { health: ResourceHealth }) {
  return (
    <Badge tone={HEALTH[health]} dot>
      {health[0].toUpperCase() + health.slice(1)}
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
    <Badge tone={CONN[status].tone} dot>
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

const SERVICE_ICON: Record<AwsService, ReactNode> = {
  ec2: <Server size={13} />,
  ecs: <Container size={13} />,
  rds: <Database size={13} />,
  lambda: <Zap size={13} />,
  cloudwatch: <Cloud size={13} />,
};
export const SERVICE_LABEL: Record<AwsService, string> = { ec2: "EC2", ecs: "ECS", rds: "RDS", lambda: "Lambda", cloudwatch: "CloudWatch" };

export function ServiceTag({ service }: { service: AwsService }) {
  return (
    <span className="badge svc" title={SERVICE_LABEL[service]}>
      {SERVICE_ICON[service] ?? <Box size={13} />}
      {SERVICE_LABEL[service]}
    </span>
  );
}

/** Lightweight SVG line chart for CloudWatch metric evidence (no chart library needed). */
export function Sparkline({ series, height = 120 }: { series: MetricSeries; height?: number }) {
  const w = 600;
  const pad = { t: 8, r: 8, b: 18, l: 32 };
  const vals = series.points.map((p) => p.v);
  const max = Math.max(...vals, series.threshold ?? 0) * 1.05 || 1;
  const min = 0;
  const x = (i: number) => pad.l + (i / Math.max(1, series.points.length - 1)) * (w - pad.l - pad.r);
  const y = (v: number) => pad.t + (1 - (v - min) / (max - min)) * (height - pad.t - pad.b);
  const d = series.points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.v).toFixed(1)}`).join(" ");
  const area = `${d} L${x(series.points.length - 1)},${y(0)} L${x(0)},${y(0)} Z`;
  const first = series.points[0];
  const last = series.points[series.points.length - 1];
  const fmt = (t: string) => new Date(t).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  return (
    <svg className="spark" viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none" role="img" aria-label={`${series.label} chart`}>
      <path className="area" d={area} />
      <path className="line" d={d} vectorEffect="non-scaling-stroke" />
      {series.threshold !== undefined && (
        <line className="threshold" x1={pad.l} x2={w - pad.r} y1={y(series.threshold)} y2={y(series.threshold)} vectorEffect="non-scaling-stroke" />
      )}
      <text className="axis" x={2} y={pad.t + 8}>{Math.round(max)}</text>
      <text className="axis" x={2} y={height - pad.b}>0</text>
      {first && <text className="axis" x={pad.l} y={height - 4}>{fmt(first.t)}</text>}
      {last && <text className="axis" x={w - pad.r} y={height - 4} textAnchor="end">{fmt(last.t)}</text>}
    </svg>
  );
}
