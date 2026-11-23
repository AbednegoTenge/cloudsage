import { ArrowUpDown, Radar, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { HealthBadge, SERVICE_LABEL, ServiceTag } from "../components/domain";
import { Button, Card, DemoNote, EmptyState, ErrorCallout, PageHeader, Spinner } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import type { AwsService, DiscoveredResource } from "../types/domain";

const SERVICES: AwsService[] = ["ec2", "ecs", "rds", "lambda"];
type SortKey = "name" | "service" | "region" | "health";
const HEALTH_ORDER = { unhealthy: 0, degraded: 1, unknown: 2, healthy: 3 };
const PAGE_SIZE = 8;

export function promptFor(r: DiscoveredResource): string {
  return `Investigate the health of ${SERVICE_LABEL[r.service]} ${r.resourceType} ${r.identifier}.`;
}

export function InfrastructurePage() {
  const navigate = useNavigate();
  const list = useAsync(() => api.listResources());
  const [tab, setTab] = useState<AwsService | "all">("all");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "health", dir: 1 });
  const [page, setPage] = useState(0);

  const rows = useMemo(() => {
    const q = search.toLowerCase();
    return (list.data ?? [])
      .filter((r) => tab === "all" || r.service === tab)
      .filter((r) => !q || r.name.toLowerCase().includes(q) || r.identifier.toLowerCase().includes(q))
      .sort((a, b) => {
        const va = sort.key === "health" ? HEALTH_ORDER[a.health] : a[sort.key];
        const vb = sort.key === "health" ? HEALTH_ORDER[b.health] : b[sort.key];
        return (va < vb ? -1 : va > vb ? 1 : 0) * sort.dir;
      });
  }, [list.data, tab, search, sort]);
  const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const visible = rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const count = (s: AwsService | "all") => (list.data ?? []).filter((r) => s === "all" || r.service === s).length;

  const th = (key: SortKey, label: string) => (
    <th>
      <button type="button" className="row" style={{ background: "none", border: "none", color: "inherit", font: "inherit", letterSpacing: "inherit", textTransform: "inherit", cursor: "pointer", padding: 0, gap: 4 }}
        onClick={() => setSort((s) => ({ key, dir: s.key === key ? (s.dir === 1 ? -1 : 1) : 1 }))}>
        {label} <ArrowUpDown size={11} />
      </button>
    </th>
  );

  return (
    <div className="page">
      <PageHeader
        title="Infrastructure"
        subtitle="Browse discovered AWS resources. Investigate any resource to launch an AI-powered inquiry."
        actions={<Button onClick={list.reload}><Radar size={14} /> Discover resources</Button>}
      />
      <div className="tabs" role="tablist" aria-label="Service">
        {(["all", ...SERVICES] as const).map((s) => (
          <button key={s} type="button" role="tab" aria-selected={tab === s} className={`tab ${tab === s ? "active" : ""}`} onClick={() => { setTab(s); setPage(0); }}>
            {s === "all" ? "All Resources" : SERVICE_LABEL[s]} <span className="count">{count(s)}</span>
          </button>
        ))}
      </div>
      <Card>
        <div className="stack-lg">
          <div className="row between wrap">
            <label className="search"><Search size={14} /><input className="input" placeholder="Search resources..." aria-label="Search resources" value={search} onChange={(e) => { setSearch(e.target.value); setPage(0); }} /></label>
            <span className="xs faint mono">{rows.length} resources</span>
          </div>
          {list.error ? <ErrorCallout error={list.error} /> : !list.data ? <Spinner label="Discovering resources..." /> : rows.length === 0 ? (
            <EmptyState icon={<Radar size={26} />} title="No resources match" />
          ) : (
            <div className="table-card">
              <div className="table-wrap">
                <table className="table">
                  <thead><tr>{th("name", "Resource")}{th("service", "Service")}{th("region", "Region")}{th("health", "Status")}<th style={{ textAlign: "right" }}>Actions</th></tr></thead>
                  <tbody>
                    {visible.map((r) => (
                      <tr key={r.identifier}>
                        <td style={{ maxWidth: 380 }}>
                          <div style={{ fontWeight: 500 }}>{r.name}</div>
                          <div className="mono xs faint ellipsis" title={r.identifier}>{r.identifier}</div>
                        </td>
                        <td><ServiceTag service={r.service} /></td>
                        <td className="mono small muted">{r.region}</td>
                        <td><HealthBadge health={r.health} /></td>
                        <td style={{ textAlign: "right" }}>
                          <Button size="sm" onClick={() => navigate(`/assistant?prompt=${encodeURIComponent(promptFor(r))}`)} aria-label={`Investigate ${r.name}`}>Investigate</Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="table-foot">
                <span>Page {page + 1} of {pages}</span>
                <div className="row">
                  <Button size="sm" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>Previous</Button>
                  <Button size="sm" disabled={page >= pages - 1} onClick={() => setPage((p) => p + 1)}>Next</Button>
                </div>
              </div>
            </div>
          )}
        </div>
      </Card>
      <DemoNote>Discovery is read-only (Describe/List APIs) and limited to the selected account's allowed regions.</DemoNote>
    </div>
  );
}
