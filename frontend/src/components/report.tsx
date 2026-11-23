// Investigation report sections, shared by the Investigation Details page and the AI Assistant.
// Observed facts (backed by tool evidence), AI hypotheses and recommendations are kept visually distinct.
import { Activity, AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, Circle, FileText, Info, Lightbulb, ListChecks, Loader2, Server, ShieldCheck, Terminal, Wrench, XCircle } from "lucide-react";
import { Fragment, useEffect, useState } from "react";
import type { InvestigationDetail, InvestigationEvent, InvestigationReport, ResourceRef, ToolExecution } from "../types/domain";
import { formatDuration, formatTime } from "../lib/format";
import { HealthBadge, MetricChart, SERVICE_LABEL } from "./domain";
import { Badge, Card } from "./ui";

export function EventIcon({ type }: { type: InvestigationEvent["type"] }) {
  if (type === "tool_completed" || type === "report_ready") return <span className="tl-icon ok"><CheckCircle2 size={13} /></span>;
  if (type === "tool_failed" || type === "failed") return <span className="tl-icon bad"><XCircle size={13} /></span>;
  if (type === "tool_started" || type === "analyzing" || type === "planning") return <span className="tl-icon accent"><Loader2 size={13} /></span>;
  return <span className="tl-icon"><Circle size={9} /></span>;
}

export function Timeline({ events, label }: { events: InvestigationEvent[]; label?: string }) {
  // A started tool stops spinning once its completion event has arrived.
  const finished = new Set(events.filter((e) => e.type === "tool_completed" || e.type === "tool_failed").map((e) => e.toolExecutionId));
  const lastType = events[events.length - 1]?.type;
  return (
    <ol className="timeline" aria-label={label} aria-live="polite">
      {events.map((e, i) => {
        const settled = (e.type === "tool_started" && finished.has(e.toolExecutionId)) || ((e.type === "planning" || e.type === "analyzing") && i < events.length - 1 && lastType !== e.type);
        return (
          <li key={e.id}>
            {settled ? <span className="tl-icon"><Circle size={9} /></span> : <EventIcon type={e.type} />}
            <span className={e.toolExecutionId ? "mono small" : ""}>{e.message}</span>
            <span className="tl-time">{formatTime(e.createdAt)}</span>
          </li>
        );
      })}
    </ol>
  );
}

function SectionTitle({ icon, children, tag }: { icon: React.ReactNode; children: React.ReactNode; tag?: React.ReactNode }) {
  return <div className="section-title">{icon}{children}{tag}</div>;
}

function EvidenceRefs({ ids, onEvidence }: { ids: string[]; onEvidence?: (id: string) => void }) {
  return (
    <span className="row wrap" style={{ gap: 4 }}>
      {ids.map((id) => (
        <button key={id} type="button" className="evidence-chip" onClick={() => onEvidence?.(id)} title="Show raw evidence">{id}</button>
      ))}
    </span>
  );
}

const CONF_PCT = { high: 0.85, medium: 0.6, low: 0.35 } as const;

export function Findings({ report, onEvidence }: { report: InvestigationReport; onEvidence?: (id: string) => void }) {
  return (
    <div className="stack-lg">
      <SectionTitle icon={<ShieldCheck size={15} />} tag={<Badge tone="info">verified</Badge>}>Observed Facts</SectionTitle>
      <div className="stack">
        {report.observations.map((o, i) => (
          <div key={i} className="finding fact">
            <span className="finding-icon"><ShieldCheck size={15} /></span>
            <div className="stack" style={{ gap: 6 }}>
              <div className="row wrap"><span className="kind-tag fact">Observed Fact</span><span className="xs faint mono">F{i + 1}</span></div>
              <div className="finding-title">{o.statement}</div>
              <EvidenceRefs ids={o.evidenceIds} onEvidence={onEvidence} />
            </div>
          </div>
        ))}
      </div>

      <SectionTitle icon={<AlertTriangle size={15} />} tag={<Badge tone="warn">AI hypothesis</Badge>}>Potential Root Causes</SectionTitle>
      <div className="stack">
        {report.hypotheses.map((h, i) => {
          const pct = Math.round((h.score ?? CONF_PCT[h.confidence]) * 100);
          return (
            <div key={i} className="finding hypo">
              <span className="finding-icon"><Lightbulb size={15} /></span>
              <div className="stack" style={{ gap: 6 }}>
                <div className="row wrap">
                  <span className="kind-tag hypo">Potential Root Cause</span>
                  <span className="score"><span className="score-bar"><span style={{ width: `${pct}%` }} /></span>{pct}% confidence</span>
                </div>
                {h.title && <div className="finding-title">{h.title}</div>}
                <div className="finding-body">{h.statement}</div>
                <div className="xs faint">Based on {h.supportingObservations.map((n) => `F${n + 1}`).join(", ")}</div>
              </div>
            </div>
          );
        })}
      </div>

      <SectionTitle icon={<Info size={15} />} tag={<Badge tone="accent">actionable</Badge>}>Recommendations</SectionTitle>
      <div className="stack">
        {report.recommendations.map((r, i) => (
          <div key={i} className="finding rec">
            <span className="finding-icon"><Wrench size={15} /></span>
            <div className="stack" style={{ gap: 6 }}>
              <div className="row wrap">
                <span className="kind-tag rec">Recommendation</span>
                <Badge tone={r.priority === "now" ? "bad" : r.priority === "next" ? "warn" : "neutral"}>{r.priority === "now" ? "Do now" : r.priority === "next" ? "Next" : "Later"}</Badge>
              </div>
              <div className="finding-title">{r.title}</div>
              <div className="finding-body">{r.detail}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

const METRIC_COLORS = ["var(--unhealthy)", "var(--warning)", "var(--chart-1)", "var(--chart-2)"];

export function MetricEvidence({ report, onEvidence }: { report: InvestigationReport; onEvidence?: (id: string) => void }) {
  if (report.metrics.length === 0) return null;
  return (
    <div className={`grid ${report.metrics.length > 1 ? "grid-2" : ""}`}>
      {report.metrics.map((m, i) => {
        const vals = m.points.map((p) => p.v);
        const peak = Math.max(...vals);
        const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
        const unit = m.unit === "%" ? "%" : ` ${m.unit}`;
        return (
          <Card key={m.label} title={<h2 className="card-title"><Activity size={15} />{m.label}</h2>} subtitle={`CloudWatch · ${m.points.length} datapoints`} actions={<EvidenceRefs ids={[m.evidenceId]} onEvidence={onEvidence} />}>
            <MetricChart series={m} color={METRIC_COLORS[i % METRIC_COLORS.length]} />
            <dl className="metric-stats">
              <div><dt>Peak</dt><dd style={{ color: m.threshold !== undefined && peak >= m.threshold ? "var(--unhealthy)" : undefined }}>{peak}{unit}</dd></div>
              <div><dt>Average</dt><dd>{avg.toFixed(1)}{unit}</dd></div>
              {m.threshold !== undefined && <div><dt>Reference threshold</dt><dd>{m.threshold}{unit}</dd></div>}
            </dl>
          </Card>
        );
      })}
    </div>
  );
}

function parseLog(line: string): { ts: string; level: string; msg: string } {
  const m = /^(\S+)\s+(INFO|WARN|WARNING|ERROR|DEBUG)\s+(.*)$/.exec(line);
  if (!m) return { ts: "", level: "", msg: line };
  const t = m[1].includes("T") ? m[1].split("T")[1].replace("Z", "") : m[1];
  return { ts: t, level: m[2] === "WARNING" ? "WARN" : m[2], msg: m[3] };
}

export function LogEvidence({ report, onEvidence }: { report: InvestigationReport; onEvidence?: (id: string) => void }) {
  return (
    <>
      {report.logExcerpts.map((l) => (
        <Card key={l.evidenceId + l.logGroup} title={<h2 className="card-title"><FileText size={15} style={{ color: "var(--unhealthy)" }} />Log Events</h2>} subtitle={<span className="mono">{l.logGroup}</span>} actions={<><span className="tag-chip">CloudWatch Logs</span><EvidenceRefs ids={[l.evidenceId]} onEvidence={onEvidence} /></>}>
          <div className="log-list">
            {l.lines.map((line, i) => {
              const p = parseLog(line);
              return (
                <div key={i} className="log">
                  <span className="ts">{p.ts}</span>
                  <span className={`lvl-${p.level}`}>{p.level}</span>
                  <span style={{ overflowWrap: "anywhere" }}>{p.msg}</span>
                </div>
              );
            })}
          </div>
          <p className="xs faint" style={{ marginTop: 10 }}>Log content is untrusted data: it is shown verbatim and never treated as instructions by the agent.</p>
        </Card>
      ))}
    </>
  );
}

export function AffectedResources({ resources }: { resources: ResourceRef[] }) {
  return (
    <Card title={<h2 className="card-title"><Server size={15} />Affected Resources</h2>} actions={<span className="tag-chip">{resources.length} resource{resources.length === 1 ? "" : "s"}</span>} flush>
      {resources.length === 0 ? (
        <p className="small muted" style={{ padding: "4px 20px 18px" }}>No resources identified yet.</p>
      ) : (
        <table className="table">
          <tbody>
            {resources.map((r) => (
              <tr key={r.identifier}>
                <td style={{ maxWidth: 240 }}>
                  <div style={{ fontWeight: 500 }}>{r.name ?? r.identifier}</div>
                  <div className="mono xs faint ellipsis" title={r.identifier}>{SERVICE_LABEL[r.service]} · {r.identifier}</div>
                </td>
                <td style={{ textAlign: "right" }}>{r.health && <HealthBadge health={r.health} />}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}

function describeTool(t: ToolExecution): string {
  const inp = t.input as Record<string, unknown>;
  const target = inp.instance_id ?? inp.identifier ?? inp.log_group ?? inp.metric ?? inp.resource_id;
  return target ? String(target) : Object.keys(inp).join(", ");
}

/** Raw tool evidence: exactly what AWS returned, stored separately from the AI report. */
export function ToolExecutions({ tools, focus }: { tools: ToolExecution[]; focus?: string }) {
  const [open, setOpen] = useState<string | undefined>(focus);
  useEffect(() => {
    if (!focus) return;
    setOpen(focus);
    document.getElementById(`ev-${focus}`)?.scrollIntoView?.({ behavior: "smooth", block: "center" });
  }, [focus]);
  return (
    <Card title={<h2 className="card-title"><Terminal size={15} />Tool Execution History</h2>} subtitle="Raw evidence exactly as returned by read-only AWS APIs. Click a row to inspect input and output." flush>
      {tools.length === 0 ? (
        <p className="small muted" style={{ padding: "4px 20px 18px" }}>No tools executed.</p>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th style={{ width: 28 }} /><th>Evidence</th><th>Tool</th><th>Target</th><th>Status</th><th>Started</th><th>Duration</th></tr></thead>
            <tbody>
              {tools.map((t) => {
                const isOpen = open === t.id;
                return (
                  <Fragment key={t.id}>
                    <tr id={`ev-${t.id}`} className={`clickable ${focus === t.id ? "highlight" : ""}`} onClick={() => setOpen(isOpen ? undefined : t.id)} aria-expanded={isOpen}>
                      <td className="faint">{isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}</td>
                      <td><span className="evidence-chip">{t.id}</span></td>
                      <td className="mono small" style={{ whiteSpace: "nowrap" }}>{t.toolName}</td>
                      <td className="mono xs muted ellipsis" style={{ maxWidth: 220 }}>{describeTool(t)}</td>
                      <td><Badge tone={t.status === "succeeded" ? "ok" : t.status === "failed" ? "bad" : "info"} dot pill pulse={t.status === "running"}>{t.status === "succeeded" ? "Completed" : t.status === "failed" ? "Failed" : "Running"}</Badge></td>
                      <td className="mono xs muted">{formatTime(t.startedAt)}</td>
                      <td className="mono xs muted">{t.status === "running" ? "…" : formatDuration(t.durationMs)}</td>
                    </tr>
                    {isOpen && (
                      <tr>
                        <td colSpan={7} style={{ background: "transparent" }}>
                          <div className="grid grid-2">
                            <div className="stack"><span className="label-caps">Input</span><pre className="code">{JSON.stringify(t.input, null, 2)}</pre></div>
                            <div className="stack"><span className="label-caps">Output</span><pre className="code">{t.error ?? JSON.stringify(t.output, null, 2)}</pre></div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

export function Limitations({ report }: { report: InvestigationReport }) {
  return (
    <Card title={<h2 className="card-title"><ListChecks size={15} />Confidence and limitations</h2>} actions={<Badge tone={report.confidence === "high" ? "ok" : report.confidence === "medium" ? "warn" : "bad"}>Overall confidence: {report.confidence}</Badge>}>
      <ul className="stack small muted" style={{ margin: 0, paddingLeft: 18 }}>
        {report.limitations.map((l, i) => <li key={i}>{l}</li>)}
      </ul>
    </Card>
  );
}

/** Compact inline report for the assistant conversation. */
export function InlineReport({ detail }: { detail: InvestigationDetail }) {
  const r = detail.report;
  if (!r) return null;
  return (
    <div className="stack-lg">
      <Card title={<h2 className="card-title"><FileText size={15} />Investigation Summary</h2>} actions={<Badge tone="ok"><CheckCircle2 size={12} />Complete</Badge>}>
        <p style={{ lineHeight: 1.65, fontSize: 13.5 }}>{r.summary}</p>
      </Card>
      <AffectedResources resources={detail.investigation.resources} />
      <MetricEvidence report={r} />
      <Card><Findings report={r} /></Card>
    </div>
  );
}
