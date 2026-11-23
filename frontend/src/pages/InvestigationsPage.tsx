import { FileSearch, History, Sparkles } from "lucide-react";
import { Search } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { InvestigationStatusBadge, SERVICE_LABEL, ServiceTag } from "../components/domain";
import { Button, Card, DemoNote, EmptyState, ErrorCallout, PageHeader, Spinner } from "../components/ui";
import { useScope } from "../context/ScopeContext";
import { useAsync } from "../hooks/useAsync";
import { formatDuration } from "../lib/format";
import type { AwsService, Investigation, InvestigationStatus } from "../types/domain";

const STATUSES: { value: InvestigationStatus | ""; label: string }[] = [
  { value: "", label: "All statuses" },
  { value: "running", label: "Investigating" },
  { value: "completed", label: "Completed" },
  { value: "failed", label: "Failed" },
  { value: "timed_out", label: "Timed out" },
  { value: "queued", label: "Queued" },
];
const PAGE_SIZE = 8;

export function stamp(isoDate: string): string {
  const d = new Date(isoDate);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

export function investigationDuration(i: Investigation): string {
  if (!i.completedAt) return "in progress";
  return formatDuration(new Date(i.completedAt).getTime() - new Date(i.createdAt).getTime());
}

export function InvestigationsPage() {
  const navigate = useNavigate();
  const { connections } = useScope();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<InvestigationStatus | "">("");
  const [service, setService] = useState<AwsService | "">("");
  const [connectionId, setConnectionId] = useState("");
  const [page, setPage] = useState(0);
  const list = useAsync(
    () => api.listInvestigations({ search: search || undefined, status: status || undefined, connectionId: connectionId || undefined }),
    [search, status, connectionId],
  );
  const rows = (list.data ?? []).filter((i) => !service || i.services.includes(service));
  const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const visible = rows.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE);

  return (
    <div className="page">
      <PageHeader
        title="Investigation history"
        subtitle="Review previous AI-powered investigations. Click any row to open the detailed report."
        actions={<Link to="/assistant" className="btn btn-primary"><Sparkles size={14} /> New Investigation</Link>}
      />
      <Card
        title={<h2 className="card-title"><History size={15} />Investigations</h2>}
        actions={<span className="xs faint mono">sample data · not live AWS</span>}
      >
        <div className="stack-lg">
          <div className="row wrap between">
            <label className="search">
              <Search size={14} />
              <input className="input" placeholder="Search investigations..." aria-label="Search investigations" value={search} onChange={(e) => { setSearch(e.target.value); setPage(0); }} />
            </label>
            <div className="row wrap">
              <select className="select compact" aria-label="Filter by account" value={connectionId} onChange={(e) => { setConnectionId(e.target.value); setPage(0); }}>
                <option value="">All accounts</option>
                {connections.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
              <select className="select compact" aria-label="Filter by service" value={service} onChange={(e) => { setService(e.target.value as AwsService | ""); setPage(0); }}>
                <option value="">All services</option>
                {(["ec2", "ecs", "rds", "lambda"] as AwsService[]).map((s) => <option key={s} value={s}>{SERVICE_LABEL[s]}</option>)}
              </select>
              <select className="select compact" aria-label="Filter by status" value={status} onChange={(e) => { setStatus(e.target.value as InvestigationStatus | ""); setPage(0); }}>
                {STATUSES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
              </select>
            </div>
          </div>

          {list.error ? (
            <ErrorCallout error={list.error} />
          ) : !list.data ? (
            <Spinner />
          ) : rows.length === 0 ? (
            <EmptyState icon={<FileSearch size={26} />} title="No investigations match these filters" />
          ) : (
            <div className="table-card">
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr><th>ID</th><th>Title</th><th>Service</th><th>Resource</th><th>Status</th><th>Started</th><th>Duration</th></tr>
                  </thead>
                  <tbody>
                    {visible.map((i) => (
                      <tr key={i.id} className="clickable" onClick={() => navigate(`/investigations/${i.id}`)}>
                        <td className="id">{i.id.toUpperCase()}</td>
                        <td style={{ fontWeight: 500, maxWidth: 360 }}><div className="ellipsis">{i.title}</div></td>
                        <td><ServiceTag service={i.resources[0]?.service ?? i.services[0]} /></td>
                        <td className="mono small muted ellipsis" style={{ maxWidth: 170 }} title={i.resources[0]?.identifier}>{i.resources[0]?.name ?? i.resources[0]?.identifier ?? "auto-discovery"}</td>
                        <td><InvestigationStatusBadge status={i.status} /></td>
                        <td className="mono small muted" style={{ whiteSpace: "nowrap" }}>{stamp(i.createdAt)}</td>
                        <td className="mono small muted">{investigationDuration(i)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="table-foot">
                <span>Page {page + 1} of {pages} · {rows.length} investigations</span>
                <div className="row">
                  <Button size="sm" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>Previous</Button>
                  <Button size="sm" disabled={page >= pages - 1} onClick={() => setPage((p) => p + 1)}>Next</Button>
                </div>
              </div>
            </div>
          )}
        </div>
      </Card>
      <DemoNote>All investigations shown are sample records. Open any investigation to see its full report, evidence and tool executions.</DemoNote>
    </div>
  );
}
