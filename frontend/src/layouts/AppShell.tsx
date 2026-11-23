import { Bell, ChevronDown, ChevronsUpDown, Cloud, CloudCog, Globe, HelpCircle, LayoutGrid, PanelLeft, Search, Server, Settings, Sparkles } from "lucide-react";
import { useState } from "react";
import { matchPath, NavLink, Outlet, useLocation } from "react-router-dom";
import { useScope } from "../context/ScopeContext";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutGrid, end: true },
  { to: "/assistant", label: "AI Assistant", icon: Sparkles },
  { to: "/investigations", label: "Investigations", icon: Search },
  { to: "/infrastructure", label: "Infrastructure", icon: Server },
];
const ADMIN = [
  { to: "/connections", label: "AWS Connections", icon: Cloud },
  { to: "/settings", label: "Settings", icon: Settings },
];

const TITLES: { path: string; crumb: string; title: string }[] = [
  { path: "/", crumb: "Overview", title: "Overview" },
  { path: "/assistant", crumb: "AI Assistant", title: "AI Assistant" },
  { path: "/investigations", crumb: "Investigations", title: "Investigations" },
  { path: "/investigations/:id", crumb: "Investigation Details", title: "Investigation Report" },
  { path: "/infrastructure", crumb: "Infrastructure", title: "Infrastructure" },
  { path: "/connections", crumb: "AWS Connections", title: "AWS Connections" },
  { path: "/settings", crumb: "Settings", title: "Settings" },
];

export function ScopeSelector() {
  const { connections, connection, region, setConnectionId, setRegion } = useScope();
  return (
    <div className="row" aria-label="AWS scope">
      <label className="scope-select">
        <span className="dot" style={{ color: connection?.status === "connected" ? "var(--healthy)" : "var(--warning)" }} />
        <span className="ellipsis" style={{ maxWidth: 110 }}>{connection?.name ?? "No account"}</span>
        <span className="mono hide-mobile">{connection?.accountId}</span>
        <ChevronDown size={14} className="faint" />
        <select aria-label="AWS connection" value={connection?.id ?? ""} onChange={(e) => setConnectionId(e.target.value)}>
          {connections.map((c) => (
            <option key={c.id} value={c.id} disabled={c.status === "error"}>
              {c.name} ({c.accountId}){c.status === "error" ? " - unavailable" : ""}
            </option>
          ))}
        </select>
      </label>
      <label className="scope-select">
        <Globe size={14} className="faint" />
        <span className="mono" style={{ color: "var(--foreground)" }}>{region}</span>
        <ChevronDown size={14} className="faint" />
        <select aria-label="AWS region" value={region} onChange={(e) => setRegion(e.target.value)}>
          {(connection?.allowedRegions ?? []).map((r) => (
            <option key={r}>{r}</option>
          ))}
        </select>
      </label>
    </div>
  );
}

export function AppShell() {
  const { connection } = useScope();
  const { pathname } = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const page = [...TITLES].reverse().find((t) => matchPath({ path: t.path, end: true }, pathname)) ?? TITLES[0];

  return (
    <div className="shell">
      <aside className={`sidebar ${collapsed ? "collapsed" : ""}`}>
        <div className="brand">
          <div className="brand-mark"><CloudCog size={18} /></div>
          <div className="hide-collapsed">
            <div className="brand-name">CloudSage</div>
            <div className="brand-sub">Cloud Operations Intelligence</div>
          </div>
        </div>
        <nav className="nav" aria-label="Primary">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} title={label} className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
              <Icon size={16} /> <span className="hide-collapsed">{label}</span>
            </NavLink>
          ))}
          <div className="nav-label hide-collapsed">Management</div>
          {ADMIN.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} title={label} className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
              <Icon size={16} /> <span className="hide-collapsed">{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="user-card">
            <span className="avatar">CE</span>
            <div className="hide-collapsed" style={{ minWidth: 0, flex: 1 }}>
              <div className="small" style={{ fontWeight: 500 }}>Cloud Engineer</div>
              <div className="xs muted ellipsis">engineer@example.com</div>
            </div>
            <ChevronsUpDown size={14} className="faint hide-collapsed" />
          </div>
          <button type="button" className="collapse-btn" onClick={() => setCollapsed((c) => !c)} aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
            <PanelLeft size={15} /> <span className="hide-collapsed">Collapse</span>
          </button>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <div className="crumbs">
            <div className="trail">CloudSage <span className="faint">›</span> <strong>{page.crumb}</strong></div>
            <div className="title-row">
              <span className="page-title">{page.title}</span>
              {connection && <span className="acct-pill"><span className="dot" />{connection.accountId}</span>}
            </div>
          </div>
          <div className="spacer" />
          <ScopeSelector />
          <button type="button" className="icon-btn hide-mobile" aria-label="Notifications"><Bell size={15} /><span className="notif" /></button>
          <button type="button" className="icon-btn hide-mobile" aria-label="Help"><HelpCircle size={15} /></button>
          <span className="avatar hide-mobile" aria-label="Account">CE</span>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
