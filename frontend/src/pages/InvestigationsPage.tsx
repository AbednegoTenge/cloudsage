import { History, Search } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { HealthBadge, InvestigationStatusBadge, ServiceTag } from "../components/domain";
import { Badge, Card, EmptyState, ErrorCallout, PageHeader, Spinner } from "../components/ui";
import { useScope } from "../context/ScopeContext";
import { useAsync } from "../hooks/useAsync";
import { formatDateTime, timeRangeLabel } from "../lib/format";
import type { InvestigationStatus } from "../types/domain";

const STATUSES: (InvestigationStatus | "")[] = ["", "running", "completed", "failed", "timed_out", "queued"];

export function InvestigationsPage() {
  const navigate = useNavigate();
  const { connections } = useScope();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<InvestigationStatus | "">("");
  const [connectionId, setConnectionId] = useState("");
  const list = useAsync(
    () => api.listInvestigations({ search: search || undefined, status: status || undefined, connectionId: connectionId || undefined }),
    [search, status, connectionId],
  );
  const connName = (id: string) => connections.find((c) => c.id === id)?.name ?? id;

  return (
    <div className="page">
      <PageHeader title="Investigation history" subtitle="Every investigation, its scope, and the evidence it collected." />
      <Card flush title={
        <div className="row wrap" style={{ flex: 1 }}>
          <div className="row" style={{ flex: "1 1 260px", position: "relative" }}>
            <Search size={14} style={{ position: "absolute", left: 10, color: "var(--text-3)" }} />
            <input className="input" style={{ paddingLeft: 30 }} placeholder="Search by title, prompt or resource ID" aria-label="Search investigations" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <select className="select compact" aria-label="Filter by status" value={status} onChange={(e) => setStatus(e.target.value as InvestigationStatus | "")}>
            {STATUSES.map((s) => <option key={s} value={s}>{s ? s.replace("_", " ") : "All statuses"}</option>)}
          </select>
          <select className="select compact" aria-label="Filter by account" value={connectionId} onChange={(e) => setConnectionId(e.target.value)}>
            <option value="">All accounts</option>
            {connections.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
      }>
        {list.error ? (
          <div className="card-body"><ErrorCallout error={list.error} /></div>
        ) : !list.data ? (
          <div className="card-body"><Spinner /></div>
        ) : list.data.length === 0 ? (
          <EmptyState icon={<History size={28} />} title="No investigations match these filters" />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Investigation</th><th>Resources</th><th>Scope</th><th>Window</th><th>Status</th><th>Started</th></tr>
              </thead>
              <tbody>
                {list.data.map((i) => (
                  <tr key={i.id} className="clickable" onClick={() => navigate(`/investigations/${i.id}`)}>
                    <td style={{ maxWidth: 380 }}>
                      <div style={{ fontWeight: 500 }} className="ellipsis">{i.title}</div>
                      <div className="row small faint">
                        <span className="mono">{i.id}</span>
                        <Badge tone={i.identificationMode === "explicit" ? "neutral" : "info"}>{i.identificationMode === "explicit" ? "Explicit ID" : "Auto-discovered"}</Badge>
                      </div>
                    </td>
                    <td>
                      <div className="stack" style={{ gap: 4 }}>
                        {i.resources.slice(0, 2).map((r) => (
                          <div key={r.identifier} className="row small">
                            <ServiceTag service={r.service} />
                            <span className="mono ellipsis" style={{ maxWidth: 160 }} title={r.identifier}>{r.name ?? r.identifier}</span>
                            {r.health && <HealthBadge health={r.health} />}
                          </div>
                        ))}
                        {i.resources.length === 0 && <span className="small faint">Discovering...</span>}
                      </div>
                    </td>
                    <td className="small"><div>{connName(i.connectionId)}</div><div className="faint">{i.region}</div></td>
                    <td className="small muted">{timeRangeLabel(i.timeRange.start, i.timeRange.end)}</td>
                    <td><InvestigationStatusBadge status={i.status} /></td>
                    <td className="small muted">{formatDateTime(i.createdAt)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
