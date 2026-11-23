import { ArrowRight, Bot, CheckCircle2, Circle, Loader2, Lock, Send, XCircle } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { InvestigationStatusBadge, ServiceTag } from "../components/domain";
import { Button, Card, Field, PageHeader } from "../components/ui";
import { useScope } from "../context/ScopeContext";
import { formatTime } from "../lib/format";
import type { Investigation, InvestigationEvent } from "../types/domain";

const EXAMPLES = [
  "Investigate why EC2 instance i-0a1b2c3d4e5f67890 is unhealthy.",
  "Find unhealthy EC2 instances in my AWS account.",
  "Why is the ECS service payments-api not finishing its deployment?",
  "The Lambda function order-processor is throwing errors. What changed?",
  "Is RDS instance orders-db under CPU or storage pressure?",
];

const TIME_RANGES = [1, 3, 6, 12, 24, 72, 168];

export function EventIcon({ type }: { type: InvestigationEvent["type"] }) {
  if (type === "tool_completed" || type === "report_ready") return <span className="tl-icon ok"><CheckCircle2 size={13} /></span>;
  if (type === "tool_failed" || type === "failed") return <span className="tl-icon bad"><XCircle size={13} /></span>;
  if (type === "tool_started" || type === "analyzing" || type === "planning") return <span className="tl-icon accent"><Loader2 size={13} /></span>;
  return <span className="tl-icon"><Circle size={10} /></span>;
}

export function AssistantPage() {
  const { connection, region, connections, setConnectionId, setRegion } = useScope();
  const [prompt, setPrompt] = useState("");
  const [hours, setHours] = useState(6);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string>();
  const [current, setCurrent] = useState<Investigation>();
  const [events, setEvents] = useState<InvestigationEvent[]>([]);

  useEffect(() => {
    if (!current) return;
    setEvents([]);
    return api.streamInvestigationEvents(current.id, (e) => setEvents((prev) => (prev.some((p) => p.id === e.id) ? prev : [...prev, e])));
  }, [current]);

  const done = events.some((e) => e.type === "report_ready");
  const failed = events.some((e) => e.type === "failed");
  const status: Investigation["status"] = done ? "completed" : failed ? "failed" : events.length > 1 ? "running" : "queued";

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!connection || !prompt.trim()) return;
    setSubmitting(true);
    setError(undefined);
    try {
      setCurrent(await api.createInvestigation({ prompt: prompt.trim(), connectionId: connection.id, region, timeRangeHours: hours }));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page">
      <PageHeader
        title="AI Assistant"
        subtitle="Describe an operational problem. CloudSage identifies the resources, gathers read-only evidence and reports what it found."
      />

      <div className="grid grid-main-side">
        <Card title={<div className="row"><Bot size={16} /><h2>New investigation</h2></div>}>
          <form className="composer" onSubmit={submit}>
            <textarea
              className="textarea"
              aria-label="Investigation request"
              placeholder='e.g. "Investigate why EC2 instance i-0123456789abcdef0 is unhealthy" or "Find unhealthy EC2 instances"'
              value={prompt}
              maxLength={2000}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void submit(e);
              }}
            />
            <div className="scope-row">
              <Field label="AWS account" htmlFor="as-conn">
                <select id="as-conn" className="select" value={connection?.id ?? ""} onChange={(e) => setConnectionId(e.target.value)}>
                  {connections.map((c) => (
                    <option key={c.id} value={c.id} disabled={c.status === "error"}>{c.name} ({c.accountId})</option>
                  ))}
                </select>
              </Field>
              <Field label="Region" htmlFor="as-region">
                <select id="as-region" className="select" value={region} onChange={(e) => setRegion(e.target.value)}>
                  {(connection?.allowedRegions ?? []).map((r) => <option key={r}>{r}</option>)}
                </select>
              </Field>
              <Field label="Time range" htmlFor="as-range">
                <select id="as-range" className="select" value={hours} onChange={(e) => setHours(Number(e.target.value))}>
                  {TIME_RANGES.map((h) => <option key={h} value={h}>{h < 48 ? `Last ${h} h` : `Last ${h / 24} days`}</option>)}
                </select>
              </Field>
              <Button type="submit" variant="primary" disabled={!prompt.trim() || !connection || submitting}>
                <Send size={14} /> {submitting ? "Starting..." : "Investigate"}
              </Button>
            </div>
            {error && <div className="callout bad" role="alert">{error}</div>}
            <div className="row small faint"><Lock size={12} /> Read-only. CloudSage never modifies AWS resources. Ctrl/⌘ + Enter to submit.</div>
          </form>
        </Card>

        <Card title="Try an example">
          <div className="chips" style={{ flexDirection: "column" }}>
            {EXAMPLES.map((ex) => (
              <button key={ex} type="button" className="chip" onClick={() => setPrompt(ex)}>{ex}</button>
            ))}
          </div>
        </Card>
      </div>

      {current && (
        <Card
          title={
            <div className="stack" style={{ gap: 2 }}>
              <div className="row"><h2>{current.title}</h2></div>
              <div className="row small faint">
                <span className="mono">{current.id}</span> · {current.accountId} · {current.region} ·
                {current.identificationMode === "explicit" ? " explicit resource" : " auto-discovery"}
                {current.services.map((s) => <ServiceTag key={s} service={s} />)}
              </div>
            </div>
          }
          actions={<InvestigationStatusBadge status={status} />}
        >
          <ol className="timeline" aria-label="Investigation progress" aria-live="polite">
            {events.map((e) => (
              <li key={e.id}>
                <EventIcon type={e.type} />
                <span className={e.toolExecutionId ? "mono" : ""}>{e.message}</span>
                <span className="tl-time">{formatTime(e.createdAt)}</span>
              </li>
            ))}
          </ol>
          {done && (
            <div className="row" style={{ marginTop: 12 }}>
              <Link to={`/investigations/${current.id}`} className="btn btn-primary">View report <ArrowRight size={14} /></Link>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
