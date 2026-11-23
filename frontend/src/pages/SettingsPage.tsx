import { Bell, Check, Globe, Monitor, Moon, Palette, SlidersHorizontal, Sun, User } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { Button, Card, ErrorCallout, Field, PageHeader, Segmented, Spinner, Switch } from "../components/ui";
import { useScope } from "../context/ScopeContext";
import { useAsync } from "../hooks/useAsync";
import { getStoredTheme, setTheme, type Theme } from "../lib/theme";
import { AWS_REGIONS } from "../lib/validation";
import type { UserSettings } from "../types/domain";

function Pref({ title, desc, checked, onChange }: { title: string; desc: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="pref-row">
      <div><div className="t">{title}</div><div className="d">{desc}</div></div>
      <Switch label={title} checked={checked} onChange={onChange} />
    </div>
  );
}

export function SettingsPage() {
  const loaded = useAsync(() => api.getSettings());
  const { connections } = useScope();
  const [s, setS] = useState<UserSettings>();
  const [theme, setThemeState] = useState<Theme | "system">(getStoredTheme());
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (loaded.data) setS(loaded.data);
  }, [loaded.data]);

  if (loaded.error) return <div className="page"><ErrorCallout error={loaded.error} /></div>;
  if (!s) return <div className="page"><Spinner /></div>;
  const set = <K extends keyof UserSettings>(k: K, v: UserSettings[K]) => {
    setSaved(false);
    setS({ ...s, [k]: v });
  };
  const pickTheme = (t: Theme | "system") => {
    setThemeState(t);
    const resolved: Theme = t === "system" ? (window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark") : t;
    setTheme(resolved);
  };
  const initials = s.displayName.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();

  return (
    <div className="page" style={{ maxWidth: 1000 }}>
      <PageHeader title="Settings" subtitle="Manage your CloudSage profile, preferences, and notification settings." />

      <Card title="Profile" icon={<User size={15} />}>
        <div className="stack-lg">
          <div className="row" style={{ gap: 14 }}>
            <span className="avatar lg">{initials}</span>
            <div>
              <div style={{ fontWeight: 500 }}>{s.displayName}</div>
              <div className="small muted">{s.email}</div>
              <div className="xs faint">Cloud Operations Engineer</div>
            </div>
          </div>
          <div className="grid grid-2">
            <Field label="Display name" htmlFor="s-name"><input id="s-name" className="input" value={s.displayName} onChange={(e) => set("displayName", e.target.value)} /></Field>
            <Field label="Email" htmlFor="s-email" hint="Managed by your identity provider."><input id="s-email" className="input" value={s.email} disabled /></Field>
          </div>
        </div>
      </Card>

      <Card title="Theme preference" icon={<Palette size={15} />}>
        <div className="choice-tiles" role="radiogroup" aria-label="Theme">
          {([["dark", "Dark", Moon], ["light", "Light", Sun], ["system", "System", Monitor]] as const).map(([v, label, Icon]) => (
            <button key={v} type="button" role="radio" aria-checked={theme === v} className={`choice-tile ${theme === v ? "on" : ""}`} onClick={() => pickTheme(v)}>
              <Icon size={16} />{label}
            </button>
          ))}
        </div>
        <p className="xs faint" style={{ marginTop: 12 }}>Dark is the recommended CloudSage experience. Light is available for accessibility and bright environments.</p>
      </Card>

      <Card title="Defaults" icon={<Globe size={15} />}>
        <div className="grid grid-2">
          <Field label="Default AWS connection" htmlFor="s-conn">
            <select id="s-conn" className="select" value={s.defaultConnectionId ?? ""} onChange={(e) => set("defaultConnectionId", e.target.value || null)}>
              <option value="">None</option>
              {connections.map((c) => <option key={c.id} value={c.id}>{c.name} ({c.accountId})</option>)}
            </select>
          </Field>
          <Field label="Default AWS region" htmlFor="s-region" hint="Used when launching new investigations, if the connection allows it.">
            <select id="s-region" className="select mono" value={s.defaultRegion} onChange={(e) => set("defaultRegion", e.target.value)}>
              {AWS_REGIONS.map((r) => <option key={r}>{r}</option>)}
            </select>
          </Field>
          <Field label="Default time range" htmlFor="s-range">
            <select id="s-range" className="select" value={s.defaultTimeRangeHours} onChange={(e) => set("defaultTimeRangeHours", Number(e.target.value))}>
              {[1, 3, 6, 12, 24, 72, 168].map((h) => <option key={h} value={h}>{h < 48 ? `${h} hours` : `${h / 24} days`}</option>)}
            </select>
          </Field>
        </div>
      </Card>

      <Card title="Investigation preferences" icon={<SlidersHorizontal size={15} />}>
        <div className="stack-lg">
          <div className="grid grid-2" style={{ alignItems: "end" }}>
            <div className="field">
              <label>Default investigation depth</label>
              <Segmented label="Investigation depth" value={s.investigationDepth} onChange={(v) => set("investigationDepth", v)}
                options={[{ value: "fast", label: "Fast" }, { value: "balanced", label: "Balanced" }, { value: "thorough", label: "Thorough" }]} />
            </div>
            <div className="grid grid-2">
              <Field label="Max tool calls" htmlFor="s-tools" hint="Capped by the server.">
                <input id="s-tools" type="number" min={1} max={50} className="input" value={s.maxToolCalls} onChange={(e) => set("maxToolCalls", Math.max(1, Math.min(50, Number(e.target.value))))} />
              </Field>
              <Field label="Timeout (seconds)" htmlFor="s-timeout" hint="Capped by the server.">
                <input id="s-timeout" type="number" min={30} max={900} className="input" value={s.investigationTimeoutSec} onChange={(e) => set("investigationTimeoutSec", Math.max(30, Math.min(900, Number(e.target.value))))} />
              </Field>
            </div>
          </div>
          <div>
            <Pref title="Auto-open investigation report on completion" desc="Open the investigation details page when the AI agent finishes." checked={s.autoOpenReport} onChange={(v) => set("autoOpenReport", v)} />
            <Pref title="Include CloudWatch Logs in evidence" desc="Query relevant log groups during investigations." checked={s.includeLogs} onChange={(v) => set("includeLogs", v)} />
            <Pref title="Include deployment history" desc="Cross-reference recent ECS deployments and Lambda versions with metric anomalies." checked={s.includeDeployments} onChange={(v) => set("includeDeployments", v)} />
          </div>
        </div>
      </Card>

      <Card title="Notification preferences" icon={<Bell size={15} />}>
        <Pref title="Notify on failed investigations" desc="Receive a notification when an investigation cannot complete." checked={s.notifyOnFailed} onChange={(v) => set("notifyOnFailed", v)} />
        <Pref title="Notify on completed investigations" desc="Receive a notification when each investigation completes." checked={s.notifyOnCompleted} onChange={(v) => set("notifyOnCompleted", v)} />
        <Pref title="Weekly operations digest" desc="Summary of investigations, unhealthy resources and recommendations every Monday." checked={s.weeklyDigest} onChange={(v) => set("weeklyDigest", v)} />
      </Card>

      <div className="row" style={{ justifyContent: "flex-end" }}>
        <Button variant="ghost" onClick={() => { if (loaded.data) setS(loaded.data); setSaved(false); }}>Cancel</Button>
        <Button variant="primary" onClick={async () => { await api.updateSettings(s); setSaved(true); }}>{saved ? <><Check size={14} /> Saved</> : "Save changes"}</Button>
      </div>
    </div>
  );
}
