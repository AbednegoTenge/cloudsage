import { ArrowLeft, Clock, FileText, FlaskConical, Lightbulb, ListChecks, ShieldAlert, Wrench } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { ConfidenceBadge, HealthBadge, InvestigationStatusBadge, ServiceTag, Sparkline } from "../components/domain";
import { Badge, Card, EmptyState, ErrorCallout, PageHeader, Spinner } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { formatDateTime, formatDuration, formatTime, timeRangeLabel } from "../lib/format";
import type { InvestigationDetail, InvestigationEvent, InvestigationReport, ToolExecution } from "../types/domain";
import { EventIcon } from "./AssistantPage";

type Tab = "report" | "evidence" | "timeline";

export function InvestigationDetailPage() {
  const { id = "" } = useParams();
  const detail = useAsync(() => api.getInvestigation(id), [id]);
  const [tab, setTab] = useState<Tab>("report");
  const [focusEvidence, setFocusEvidence] = useState<string>();
  const [liveEvents, setLiveEvents] = useState<InvestigationEvent[]>([]);

  const d = detail.data;
  const isLive = d?.investigation.status === "running" || d?.investigation.status === "queued";
  useEffect(() => {
    if (!isLive) return;
    setLiveEvents([]);
    return api.streamInvestigationEvents(id, (e) => {
      setLiveEvents((p) => (p.some((x) => x.id === e.id) ? p : [...p, e]));
      if (e.type === "report_ready" || e.type === "failed") detail.reload();
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, isLive]);

  useEffect(() => {
    if (!d) return;
    const failed = d.events.some((e) => e.type === "failed");
    setTab(d.report || failed ? "report" : "timeline");
  }, [d?.investigation.id, !!d?.report]); // eslint-disable-line react-hooks/exhaustive-deps

  if (detail.error) return <div className="page"><BackLink /><ErrorCallout error={detail.error} /></div>;
  if (!d) return <div className="page"><BackLink /><Spinner /></div>;

  const inv = d.investigation;
  const events = isLive && liveEvents.length ? liveEvents : d.events;
  const showEvidence = (evidenceId: string) => {
    setFocusEvidence(evidenceId);
    setTab("evidence");
  };

  return (
    <div className="page">
      <BackLink />
      <PageHeader
        title={inv.title}
        subtitle={<span className="row wrap"><InvestigationStatusBadge status={inv.status} /><span className="mono small faint">{inv.id}</span><span className="small faint">"{inv.prompt}"</span></span>}
      />

      <div className="grid grid-main-side" style={{ alignItems: "start" }}>
        <div className="stack-lg">
          <div className="tabs" role="tablist">
            <TabButton id="report" tab={tab} setTab={setTab} icon={<FileText size={14} />} label="Report" />
            <TabButton id="evidence" tab={tab} setTab={setTab} icon={<FlaskConical size={14} />} label="Evidence" count={d.toolExecutions.length} />
            <TabButton id="timeline" tab={tab} setTab={setTab} icon={<Clock size={14} />} label="Timeline" count={events.length} />
          </div>
          {tab === "report" && (d.report ? <ReportView report={d.report} onEvidence={showEvidence} /> : <NoReport detail={d} />)}
          {tab === "evidence" && <EvidenceView tools={d.toolExecutions} focus={focusEvidence} />}
          {tab === "timeline" && <TimelineView events={events} />}
        </div>

        <div className="stack-lg">
          <Card title="Scope">
            <dl className="kv">
              <dt>Account</dt><dd className="mono">{inv.accountId}</dd>
              <dt>Region</dt><dd>{inv.region}</dd>
              <dt>Time range</dt><dd>{timeRangeLabel(inv.timeRange.start, inv.timeRange.end)}<div className="small faint">{formatDateTime(inv.timeRange.start)} to {formatDateTime(inv.timeRange.end)}</div></dd>
              <dt>Identification</dt><dd><Badge tone={inv.identificationMode === "explicit" ? "neutral" : "info"}>{inv.identificationMode === "explicit" ? "Explicit resource ID" : "Auto-discovered"}</Badge></dd>
              <dt>Services</dt><dd><div className="row wrap">{inv.services.map((s) => <ServiceTag key={s} service={s} />)}</div></dd>
              <dt>Tool calls</dt><dd>{inv.toolCallCount}</dd>
              <dt>Started</dt><dd>{formatDateTime(inv.createdAt)}</dd>
              {inv.completedAt && <><dt>Finished</dt><dd>{formatDateTime(inv.completedAt)}</dd></>}
            </dl>
          </Card>
          <Card title="Identified resources" flush>
            {inv.resources.length === 0 ? (
              <EmptyState title="No resources identified yet" />
            ) : (
              <ul className="item-list">
                {inv.resources.map((r) => (
                  <li key={r.identifier}>
                    <div className="row" style={{ justifyContent: "space-between" }}>
                      <ServiceTag service={r.service} />
                      {r.health && <HealthBadge health={r.health} />}
                    </div>
                    <div style={{ fontWeight: 500 }}>{r.name ?? r.resourceType}</div>
                    <div className="mono small faint" style={{ overflowWrap: "anywhere" }}>{r.identifier}</div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

function BackLink() {
  return <Link to="/investigations" className="row small"><ArrowLeft size={14} /> All investigations</Link>;
}

function TabButton({ id, tab, setTab, icon, label, count }: { id: Tab; tab: Tab; setTab: (t: Tab) => void; icon: React.ReactNode; label: string; count?: number }) {
  return (
    <button type="button" role="tab" aria-selected={tab === id} className={`tab ${tab === id ? "active" : ""}`} onClick={() => setTab(id)}>
      {icon} {label} {count !== undefined && <span className="count">{count}</span>}
    </button>
  );
}

function NoReport({ detail }: { detail: InvestigationDetail }) {
  const failure = detail.events.find((e) => e.type === "failed");
  if (failure) return <div className="callout bad" role="alert"><ShieldAlert size={16} /><div><strong>Investigation failed.</strong> {failure.message}</div></div>;
  return <Card><Spinner label="Investigation in progress. The report appears when the agent finishes analyzing evidence." /></Card>;
}

function EvidenceRefs({ ids, onEvidence }: { ids: string[]; onEvidence: (id: string) => void }) {
  return (
    <span className="row wrap" style={{ gap: 4 }}>
      {ids.map((id) => (
        <button key={id} type="button" className="evidence-chip" onClick={() => onEvidence(id)} title="Show raw evidence">{id}</button>
      ))}
    </span>
  );
}

export function ReportView({ report, onEvidence }: { report: InvestigationReport; onEvidence: (id: string) => void }) {
  return (
    <div className="stack-lg">
      <Card title="Summary" actions={<ConfidenceBadge confidence={report.confidence} />}>
        <p style={{ fontSize: 14.5, lineHeight: 1.6 }}>{report.summary}</p>
        <p className="small faint" style={{ marginTop: 10 }}>AI-generated from the evidence below · {formatDateTime(report.generatedAt)}</p>
      </Card>

      <Card flush title={<span className="section-tag fact"><ListChecks size={14} /> Observed conditions (facts)</span>} actions={<span className="small faint">Each item is backed by retrieved evidence</span>}>
        <ul className="item-list">
          {report.observations.map((o, i) => (
            <li key={i}>
              <div className="row" style={{ alignItems: "flex-start", gap: 10 }}>
                <span className="faint mono small" style={{ minWidth: 20 }}>F{i + 1}</span>
                <div className="stack" style={{ gap: 6 }}>
                  <span>{o.statement}</span>
                  <EvidenceRefs ids={o.evidenceIds} onEvidence={onEvidence} />
                </div>
              </div>
            </li>
          ))}
        </ul>
      </Card>

      {(report.metrics.length > 0 || report.logExcerpts.length > 0) && (
        <Card title="Metrics and log evidence">
          <div className="stack-lg">
            {report.metrics.length > 0 && (
              <div className={`grid ${report.metrics.length > 1 ? "grid-2" : ""}`}>
                {report.metrics.map((m) => (
                  <div key={m.label} className="stack" style={{ gap: 6 }}>
                    <div className="row" style={{ justifyContent: "space-between" }}>
                      <strong className="small">{m.label}</strong>
                      <EvidenceRefs ids={[m.evidenceId]} onEvidence={onEvidence} />
                    </div>
                    <Sparkline series={m} />
                    {m.threshold !== undefined && <span className="small faint">Dashed line: {m.threshold}{m.unit} reference threshold</span>}
                  </div>
                ))}
              </div>
            )}
            {report.logExcerpts.map((l) => (
              <div key={l.evidenceId + l.logGroup} className="stack" style={{ gap: 6 }}>
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <strong className="small mono">{l.logGroup}</strong>
                  <EvidenceRefs ids={[l.evidenceId]} onEvidence={onEvidence} />
                </div>
                <pre className="log-lines">{l.lines.map((line, i) => <div key={i}>{line}</div>)}</pre>
              </div>
            ))}
          </div>
        </Card>
      )}

      <Card flush title={<span className="section-tag hypo"><Lightbulb size={14} /> Potential root causes (hypotheses)</span>}>
        <ul className="item-list">
          {report.hypotheses.map((h, i) => (
            <li key={i}>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
                <span>{h.statement}</span>
                <ConfidenceBadge confidence={h.confidence} prefix="Likelihood" />
              </div>
              <span className="small faint">Based on {h.supportingObservations.map((n) => `F${n + 1}`).join(", ")}</span>
            </li>
          ))}
        </ul>
      </Card>

      <Card flush title={<span className="section-tag rec"><Wrench size={14} /> Recommended troubleshooting steps</span>}>
        <ul className="item-list">
          {report.recommendations.map((r, i) => (
            <li key={i}>
              <div className="row" style={{ justifyContent: "space-between" }}>
                <strong>{r.title}</strong>
                <Badge tone={r.priority === "now" ? "bad" : r.priority === "next" ? "warn" : "neutral"}>{r.priority === "now" ? "Do now" : r.priority === "next" ? "Next" : "Later"}</Badge>
              </div>
              <span className="muted">{r.detail}</span>
            </li>
          ))}
        </ul>
      </Card>

      <Card title="Confidence and limitations" actions={<ConfidenceBadge confidence={report.confidence} />}>
        <ul style={{ margin: 0, paddingLeft: 18 }} className="stack">
          {report.limitations.map((l, i) => <li key={i} className="muted">{l}</li>)}
        </ul>
      </Card>
    </div>
  );
}

function EvidenceView({ tools, focus }: { tools: ToolExecution[]; focus?: string }) {
  useEffect(() => {
    if (focus) document.getElementById(`ev-${focus}`)?.scrollIntoView?.({ behavior: "smooth", block: "center" });
  }, [focus]);
  if (tools.length === 0) return <Card><EmptyState icon={<FlaskConical size={26} />} title="No evidence collected" /></Card>;
  return (
    <div className="stack-lg">
      <div className="callout info small">Raw tool outputs exactly as returned by AWS read-only APIs. Stored separately from the AI-generated report so every claim can be audited.</div>
      {tools.map((t) => (
        <Card
          key={t.id}
          id={`ev-${t.id}`}
          className={focus === t.id ? "highlight" : ""}
          title={<div className="row wrap"><span className="evidence-chip">{t.id}</span><strong className="mono">{t.toolName}</strong><ServiceTag service={t.service} /></div>}
          actions={<><Badge tone={t.status === "succeeded" ? "ok" : t.status === "failed" ? "bad" : "accent"} dot pulse={t.status === "running"}>{t.status}</Badge><span className="small faint">{t.status === "running" ? "..." : formatDuration(t.durationMs)}</span></>}
        >
          <div className="grid grid-2">
            <div className="stack"><h3>Input</h3><pre className="code">{JSON.stringify(t.input, null, 2)}</pre></div>
            <div className="stack"><h3>Output</h3><pre className="code">{t.error ?? JSON.stringify(t.output, null, 2)}</pre></div>
          </div>
        </Card>
      ))}
    </div>
  );
}

function TimelineView({ events }: { events: InvestigationEvent[] }) {
  return (
    <Card>
      <ol className="timeline">
        {events.map((e) => (
          <li key={e.id}>
            <EventIcon type={e.type} />
            <span>{e.message}</span>
            <span className="tl-time">{formatTime(e.createdAt)}</span>
          </li>
        ))}
      </ol>
    </Card>
  );
}
