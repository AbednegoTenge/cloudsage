import { ArrowLeft, Clock, Copy, Download, FileText, Lightbulb, ShieldAlert, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, usingMockApi } from "../api/client";
import { InvestigationStatusBadge, SERVICE_LABEL } from "../components/domain";
import { AffectedResources, Findings, Limitations, LogEvidence, MetricEvidence, Timeline, ToolExecutions } from "../components/report";
import { Button, Card, DemoNote, ErrorCallout, Spinner } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { timeRangeLabel } from "../lib/format";
import type { InvestigationDetail, InvestigationEvent } from "../types/domain";
import { investigationDuration, stamp } from "./InvestigationsPage";

export function InvestigationDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const detail = useAsync(() => api.getInvestigation(id), [id]);
  const [focusEvidence, setFocusEvidence] = useState<string>();
  const [liveEvents, setLiveEvents] = useState<InvestigationEvent[]>([]);
  const [copied, setCopied] = useState(false);

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

  if (detail.error) return <div className="page"><BackLink /><ErrorCallout error={detail.error} /></div>;
  if (!d) return <div className="page"><BackLink /><Spinner /></div>;

  const inv = d.investigation;
  const r = d.report;
  const events = isLive && liveEvents.length ? liveEvents : d.events;
  const failure = d.events.find((e) => e.type === "failed");
  const primary = inv.resources[0];

  return (
    <div className="page">
      <div className="row between wrap">
        <BackLink />
        <div className="row">
          <Button onClick={async () => { try { await navigator.clipboard.writeText(window.location.href); setCopied(true); } catch { /* clipboard blocked */ } }}><Copy size={14} /> {copied ? "Copied" : "Copy link"}</Button>
          <Button onClick={() => exportJson(d)}><Download size={14} /> Export</Button>
          <Button variant="primary" onClick={() => navigate(`/assistant?prompt=${encodeURIComponent(`Follow up on ${inv.id}: ${inv.prompt}`)}`)}><Sparkles size={14} /> Start related investigation</Button>
        </div>
      </div>

      <section className="card" style={{ padding: 20 }}>
        <div className="stack" style={{ gap: 10 }}>
          <div className="row"><span className="mono xs muted">{inv.id.toUpperCase()}</span><InvestigationStatusBadge status={inv.status} /></div>
          <h1 style={{ fontSize: 19 }}>{inv.title}</h1>
          <div className="meta-row">
            <span><b>Service:</b>{inv.services.filter((s) => s !== "cloudwatch").map((s) => SERVICE_LABEL[s]).join(", ") || "CloudWatch"}</span>
            <span><b>Resource:</b>{primary?.name ?? primary?.identifier ?? "auto-discovery"}</span>
            <span><b>Account:</b>{inv.accountId}</span>
            <span><b>Region:</b>{inv.region}</span>
            <span><b>Window:</b>{timeRangeLabel(inv.timeRange.start, inv.timeRange.end)}</span>
            <span><b>Started:</b>{stamp(inv.createdAt)}</span>
            <span><b>Duration:</b>{investigationDuration(inv)}</span>
          </div>
          <p className="small muted">“{inv.prompt}” · {inv.identificationMode === "explicit" ? "resource ID supplied" : "resources auto-discovered"}</p>
        </div>
      </section>

      {failure && (
        <div className="callout bad" role="alert"><ShieldAlert size={16} style={{ flex: "none", color: "var(--unhealthy)" }} /><div><strong>Investigation failed.</strong> {failure.message}</div></div>
      )}

      {!r && !failure && (
        <Card title={<h2 className="card-title"><Clock size={15} />Live progress</h2>} subtitle="The report appears when the agent finishes analyzing evidence.">
          <Timeline events={events} label="Investigation progress" />
        </Card>
      )}

      {r && (
        <>
          <Card title={<h2 className="card-title"><FileText size={15} />Summary</h2>} subtitle="AI-generated from the evidence below">
            <p style={{ lineHeight: 1.65, fontSize: 13.5 }}>{r.summary}</p>
          </Card>

          <div className="stack-lg">
            <div className="section-title"><Lightbulb size={15} />Findings</div>
            <Findings report={r} onEvidence={setFocusEvidence} />
          </div>

          <div className="section-title" style={{ marginTop: 8 }}>Evidence</div>
          <MetricEvidence report={r} onEvidence={setFocusEvidence} />
          <LogEvidence report={r} onEvidence={setFocusEvidence} />
        </>
      )}

      <div className="grid grid-2" style={{ alignItems: "start" }}>
        <AffectedResources resources={inv.resources} />
        <Card title={<h2 className="card-title"><Clock size={15} />Investigation Timeline</h2>} actions={<span className="tag-chip">{events.length} events</span>}>
          <Timeline events={events} />
        </Card>
      </div>

      <ToolExecutions tools={d.toolExecutions} focus={focusEvidence} />
      {r && <Limitations report={r} />}
      <DemoNote>{usingMockApi ? "Sample data for local development. " : ""}Treat AI-generated root causes and recommendations as hypotheses to validate against your environment.</DemoNote>
    </div>
  );
}

function BackLink() {
  return <Link to="/investigations" className="row small muted"><ArrowLeft size={14} /> Back to investigations</Link>;
}

function exportJson(d: InvestigationDetail) {
  const blob = new Blob([JSON.stringify(d, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${d.investigation.id}.json`;
  a.click();
  URL.revokeObjectURL(url);
}
