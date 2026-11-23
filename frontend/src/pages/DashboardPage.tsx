import { AlertTriangle, ArrowRight, Clock, Layers, Search } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { InvestigationStatusBadge, SERVICE_LABEL, ServiceTag } from "../components/domain";
import { Card, ErrorCallout, PageHeader, Spinner } from "../components/ui";
import { useScope } from "../context/ScopeContext";
import { useAsync } from "../hooks/useAsync";
import { formatDuration, relativeTime } from "../lib/format";

export function DashboardPage() {
  const navigate = useNavigate();
  const { connection, region } = useScope();
  const summary = useAsync(() => api.getDashboard());
  const recent = useAsync(() => api.listInvestigations());

  if (summary.error) return <ErrorCallout error={summary.error} />;
  const s = summary.data;
  const totalResources = s ? Object.values(s.resourcesMonitored).reduce((a, b) => a + b, 0) : 0;
  const maxDaily = s ? Math.max(...s.dailyInvestigations.map((d) => d.count), 1) : 1;
  const active = recent.data?.filter((i) => i.status === "running" || i.status === "queued") ?? [];

  return (
    <div className="page">
      <PageHeader
        title="Operations overview"
        subtitle={connection ? <>Scope: <strong>{connection.name}</strong> · <span className="mono">{connection.accountId}</span> · {region}</> : "Select an AWS connection"}
      />

      {!s ? (
        <Spinner />
      ) : (
        <>
          <div className="grid grid-4">
            <Card><div className="stat" style={{ padding: 0 }}>
              <span className="stat-label"><Search size={14} /> Investigations (7 days)</span>
              <span className="stat-value">{s.investigationsLast7d}</span>
              <span className="stat-foot">{active.length} in progress now</span>
            </div></Card>
            <Card><div className="stat" style={{ padding: 0 }}>
              <span className="stat-label"><AlertTriangle size={14} /> Open issues</span>
              <span className="stat-value" style={{ color: "var(--warn)" }}>{s.openIssues}</span>
              <span className="stat-foot">Unhealthy or degraded resources</span>
            </div></Card>
            <Card><div className="stat" style={{ padding: 0 }}>
              <span className="stat-label"><Clock size={14} /> Avg. time to report</span>
              <span className="stat-value">{formatDuration(s.avgTimeToReportSec * 1000)}</span>
              <span className="stat-foot">From request to evidence-backed report</span>
            </div></Card>
            <Card><div className="stat" style={{ padding: 0 }}>
              <span className="stat-label"><Layers size={14} /> Resources in scope</span>
              <span className="stat-value">{totalResources}</span>
              <span className="stat-foot">EC2 · ECS · RDS · Lambda</span>
            </div></Card>
          </div>

          <div className="grid grid-main-side">
            <Card title="Resource health by service">
              <div className="stack-lg">
                {s.healthByService.map((h) => {
                  const total = h.healthy + h.degraded + h.unhealthy;
                  return (
                    <div key={h.service} className="stack" style={{ gap: 6 }}>
                      <div className="row" style={{ justifyContent: "space-between" }}>
                        <ServiceTag service={h.service} />
                        <span className="small muted">
                          <span style={{ color: "var(--ok)" }}>{h.healthy} healthy</span>
                          {h.degraded > 0 && <> · <span style={{ color: "var(--warn)" }}>{h.degraded} degraded</span></>}
                          {h.unhealthy > 0 && <> · <span style={{ color: "var(--bad)" }}>{h.unhealthy} unhealthy</span></>}
                        </span>
                      </div>
                      <div className="health-bar" aria-label={`${SERVICE_LABEL[h.service]} health`}>
                        <span style={{ width: `${(h.healthy / total) * 100}%`, background: "var(--ok)" }} />
                        <span style={{ width: `${(h.degraded / total) * 100}%`, background: "var(--warn)" }} />
                        <span style={{ width: `${(h.unhealthy / total) * 100}%`, background: "var(--bad)" }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            </Card>
            <Card title="Investigations per day">
              <div className="bars">
                {s.dailyInvestigations.map((d) => (
                  <div className="bar-col" key={d.day} title={`${d.day}: ${d.count}`}>
                    <span className="small faint">{d.count}</span>
                    <div className="bar" style={{ height: `${(d.count / maxDaily) * 80}px` }} />
                    <span className="bar-label">{d.day.split(" ")[1]}</span>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        </>
      )}

      <Card title="Recent investigations" actions={<Link to="/investigations" className="row small">View all <ArrowRight size={14} /></Link>} flush>
        {!recent.data ? (
          <div className="card-body"><Spinner /></div>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Investigation</th><th>Services</th><th>Status</th><th>Started</th></tr></thead>
              <tbody>
                {recent.data.slice(0, 5).map((i) => (
                  <tr key={i.id} className="clickable" onClick={() => navigate(`/investigations/${i.id}`)}>
                    <td>
                      <div style={{ fontWeight: 500 }}>{i.title}</div>
                      <div className="small faint mono">{i.id} · {i.region}</div>
                    </td>
                    <td><div className="row wrap">{i.services.map((sv) => <ServiceTag key={sv} service={sv} />)}</div></td>
                    <td><InvestigationStatusBadge status={i.status} /></td>
                    <td className="muted small">{relativeTime(i.createdAt)}</td>
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
