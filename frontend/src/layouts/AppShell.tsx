import { Activity, Bot, Cloud, History, LayoutDashboard, Plug, Settings, ShieldCheck } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { useScope } from "../context/ScopeContext";
import { ConnectionStatusBadge } from "../components/domain";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/assistant", label: "AI Assistant", icon: Bot },
  { to: "/investigations", label: "Investigations", icon: History },
];
const ADMIN = [
  { to: "/connections", label: "AWS Connections", icon: Plug },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function ScopeSelector() {
  const { connections, connection, region, setConnectionId, setRegion } = useScope();
  return (
    <div className="scope" aria-label="AWS scope">
      <span className="scope-label">Account</span>
      <select
        className="select compact"
        aria-label="AWS connection"
        value={connection?.id ?? ""}
        onChange={(e) => setConnectionId(e.target.value)}
      >
        {connections.map((c) => (
          <option key={c.id} value={c.id} disabled={c.status === "error"}>
            {c.name} ({c.accountId}){c.status === "error" ? " - unavailable" : ""}
          </option>
        ))}
      </select>
      <span className="scope-label">Region</span>
      <select className="select compact" aria-label="AWS region" value={region} onChange={(e) => setRegion(e.target.value)}>
        {(connection?.allowedRegions ?? []).map((r) => (
          <option key={r}>{r}</option>
        ))}
      </select>
    </div>
  );
}

export function AppShell() {
  const { connection } = useScope();
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><Cloud size={18} /></div>
          <div>
            <div className="brand-name">CloudSage</div>
            <div className="brand-sub">AWS Operations Agent</div>
          </div>
        </div>
        <div className="nav-label">Operate</div>
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end} className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
            <Icon size={16} /> {label}
          </NavLink>
        ))}
        <div className="nav-label">Configure</div>
        {ADMIN.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to} className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
            <Icon size={16} /> {label}
          </NavLink>
        ))}
        <div className="sidebar-foot">
          <span className="row"><ShieldCheck size={14} /> Read-only access</span>
          <span className="row"><Activity size={14} /> v0.1.0 · mock data</span>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <ScopeSelector />
          {connection && <ConnectionStatusBadge status={connection.status} />}
          <div className="spacer" />
          <NavLink to="/assistant" className="btn btn-primary btn-sm"><Bot size={14} /> New investigation</NavLink>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
