import { AlertCircle, ArrowRight, ArrowUpRight, CheckCircle2, FileSearch, RefreshCw, Server, Sparkles } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { HealthBadge, hhmm, InvestigationStatusBadge, LineChart, SERVICE_COLOR, SERVICE_LABEL, ServiceTag } from "../components/domain";
import { Button, Card, DemoNote, ErrorCallout, PageHeader, Segmented, Spinner } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import type { AwsService } from "../types/domain";

const RANGES = ["15m", "1h", "6h", "24h", "7d"] as const;

function StatCard({ label, value, icon, tone, foot }: { label: string; value: number | string; icon: React.ReactNode; tone?: "ok" | "bad"; foot: React.ReactNode }) {
  return (
    <section className="card stat-card">
      <span className="label-caps">{label}</span>
      <span className="stat-value">{value}</span>
      <span className={`icon-tile stat-icon ${tone ?? ""}`}>{icon}</span>
      <span className="stat-foot">{foot}</span>
    </section>
  );
}

export function DashboardPage() {
  const navigate = useNavigate();
  const [range, setRange] = useState<(typeof RANGES)[number]>("1h");
  const summary = useAsync(() => api.getDashboard());
  const recent = useAsync(() => api.listInvestigations());
  const resources = useAsync(() => api.listResources());

  if (summary.error) return <div className="page"><ErrorCallout error={summary.error} /></div>;
  const s = summary.data;
  const services: AwsService[] = ["ec2", "ecs", "rds", "lambda"];
  const total = s ? services.reduce((a, k) => a + s.resourcesMonitored[k], 0) : 0;
  const healthy = s ? s.healthByService.reduce((a, h) => a + h.healthy, 0) : 0;
  const unhealthy = s ? s.healthByService.reduce((a, h) => a + h.degraded + h.unhealthy, 0) : 0;
  const active = recent.data?.filter((i) => i.status === "running" || i.status === "queued").length ?? 0;
  const maxDist = s ? Math.max(...services.map((k) => s.resourcesMonitored[k])) : 1;

  return (
    <div className="page">
      <PageHeader
        title="Overview"
        subtitle="Monitor your AWS infrastructure and investigate operational issues."
        actions={
          <>
            <Segmented label="Time range" options={RANGES.map((r) => ({ value: r, label: r }))} value={range} onChange={setRange} />
            <Button onClick={() => { summary.reload(); recent.reload(); resources.reload(); }}><RefreshCw size={14} /> Refresh</Button>
            <Link to="/assistant" className="btn btn-primary"><Sparkles size={14} /> Start Investigation</Link>
          </>
        }
      />

      {!s ? (
        <Spinner />
      ) : (
        <>
          <div className="grid grid-4">
            <StatCard label="Total resources" value={total} icon={<Server size={16} />} foot={<><span className="trend-up"><ArrowUpRight size={13} />+2 this week</span> across EC2 · ECS · RDS · Lambda</>} />
            <StatCard label="Healthy resources" value={healthy} tone="ok" icon={<CheckCircle2 size={16} />} foot={`${Math.round((healthy / Math.max(1, healthy + unhealthy)) * 100)}% of fleet`} />
            <StatCard label="Unhealthy resources" value={unhealthy} tone="bad" icon={<AlertCircle size={16} />} foot={<><span className="trend-up"><ArrowUpRight size={13} />{s.openIssues} open</span> requires attention</>} />
            <StatCard label="Active investigations" value={active} icon={<FileSearch size={16} />} foot="AI agent in progress" />
          </div>

          <div className="grid grid-dash">
            <Card
              title="Infrastructure Health"
              subtitle={`Healthy vs unhealthy resources · last ${range}`}
              actions={<div className="legend"><span><span className="dot" style={{ color: "var(--healthy)" }} />Healthy</span><span><span className="dot" style={{ color: "var(--unhealthy)" }} />Unhealthy</span></div>}
            >
              <LineChart
                ariaLabel="Infrastructure health over time"
                labels={s.healthTimeline.map((p) => hhmm(p.t))}
                series={[
                  { label: "Healthy", color: "var(--healthy)", values: s.healthTimeline.map((p) => p.healthy) },
                  { label: "Unhealthy", color: "var(--unhealthy)", values: s.healthTimeline.map((p) => p.unhealthy) },
                ]}
              />
            </Card>
            <Card title="Resource Distribution" subtitle="Discovered resources by AWS service">
              <div className="stack-lg" style={{ paddingTop: 8 }}>
                {services.map((k) => (
                  <div key={k} className="dist-row">
                    <div className="row between small"><span style={{ fontWeight: 500 }}>{SERVICE_LABEL[k]}</span><span className="mono muted">{s.resourcesMonitored[k]}</span></div>
                    <div className="dist-bar"><span style={{ width: `${(s.resourcesMonitored[k] / maxDist) * 100}%`, background: SERVICE_COLOR[k] }} /></div>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        </>
      )}

      <div className="grid grid-dash">
        <Card title="Recent Investigations" actions={<Link to="/investigations" className="row small">View all <ArrowRight size={13} /></Link>} flush>
          {!recent.data ? (
            <div className="card-body"><Spinner /></div>
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Investigation</th><th>Service</th><th>Resource</th><th>Status</th><th>Summary</th></tr></thead>
                <tbody>
                  {recent.data.slice(0, 5).map((i) => (
                    <tr key={i.id} className="clickable" onClick={() => navigate(`/investigations/${i.id}`)}>
                      <td style={{ maxWidth: 260 }}>
                        <div className="ellipsis" style={{ fontWeight: 500 }}>{i.title}</div>
                        <div className="id">{i.id.toUpperCase()}</div>
                      </td>
                      <td>{i.resources[0] ? <ServiceTag service={i.resources[0].service} /> : <ServiceTag service={i.services[0]} />}</td>
                      <td className="mono small muted ellipsis" style={{ maxWidth: 140 }}>{i.resources[0]?.name ?? "discovery"}</td>
                      <td><InvestigationStatusBadge status={i.status} /></td>
                      <td className="small muted" style={{ maxWidth: 280 }}><div className="ellipsis">{i.summary}</div></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
        <Card title="Infrastructure Health" actions={<Link to="/infrastructure" className="row small">Explore <ArrowRight size={13} /></Link>} flush>
          {!resources.data ? (
            <div className="card-body"><Spinner /></div>
          ) : (
            <table className="table">
              <thead><tr><th>Resource</th><th>Status</th><th>Observed</th></tr></thead>
              <tbody>
                {resources.data.slice(0, 7).map((r) => (
                  <tr key={r.identifier}>
                    <td style={{ maxWidth: 160 }}>
                      <div className="ellipsis" style={{ fontWeight: 500 }}>{r.name}</div>
                      <div className="xs faint">{SERVICE_LABEL[r.service]} · {r.region}</div>
                    </td>
                    <td><HealthBadge health={r.health} /></td>
                    <td className="mono xs muted">{hhmm(r.observedAt)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>
      <DemoNote />
    </div>
  );
}
