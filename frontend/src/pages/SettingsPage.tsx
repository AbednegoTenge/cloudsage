import { Check, Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { Button, Card, ErrorCallout, Field, PageHeader, Spinner, Switch } from "../components/ui";
import { useScope } from "../context/ScopeContext";
import { useAsync } from "../hooks/useAsync";
import { getStoredTheme, setTheme, type Theme } from "../lib/theme";
import type { UserSettings } from "../types/domain";

export function SettingsPage() {
  const loaded = useAsync(() => api.getSettings());
  const { connections } = useScope();
  const [s, setS] = useState<UserSettings>();
  const [theme, setThemeState] = useState<Theme>(getStoredTheme());
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (loaded.data) setS(loaded.data);
  }, [loaded.data]);

  if (loaded.error) return <ErrorCallout error={loaded.error} />;
  if (!s) return <Spinner />;
  const set = <K extends keyof UserSettings>(k: K, v: UserSettings[K]) => {
    setSaved(false);
    setS({ ...s, [k]: v });
  };

  return (
    <div className="page" style={{ maxWidth: 880 }}>
      <PageHeader
        title="Settings"
        actions={<Button variant="primary" onClick={async () => { await api.updateSettings(s); setSaved(true); }}>{saved ? <><Check size={14} /> Saved</> : "Save changes"}</Button>}
      />

      <Card title="Profile">
        <div className="grid grid-2">
          <Field label="Display name" htmlFor="s-name"><input id="s-name" className="input" value={s.displayName} onChange={(e) => set("displayName", e.target.value)} /></Field>
          <Field label="Email" htmlFor="s-email" hint="Managed by your identity provider."><input id="s-email" className="input" value={s.email} disabled /></Field>
        </div>
      </Card>

      <Card title="Investigation defaults">
        <div className="grid grid-2">
          <Field label="Default AWS connection" htmlFor="s-conn">
            <select id="s-conn" className="select" value={s.defaultConnectionId ?? ""} onChange={(e) => set("defaultConnectionId", e.target.value || null)}>
              <option value="">None</option>
              {connections.map((c) => <option key={c.id} value={c.id}>{c.name} ({c.accountId})</option>)}
            </select>
          </Field>
          <Field label="Default time range" htmlFor="s-range">
            <select id="s-range" className="select" value={s.defaultTimeRangeHours} onChange={(e) => set("defaultTimeRangeHours", Number(e.target.value))}>
              {[1, 3, 6, 12, 24, 72, 168].map((h) => <option key={h} value={h}>{h < 48 ? `${h} hours` : `${h / 24} days`}</option>)}
            </select>
          </Field>
          <Field label="Max tool calls per investigation" htmlFor="s-tools" hint="Capped by the server limit.">
            <input id="s-tools" type="number" min={1} max={50} className="input" value={s.maxToolCalls} onChange={(e) => set("maxToolCalls", Math.max(1, Math.min(50, Number(e.target.value))))} />
          </Field>
          <Field label="Investigation timeout (seconds)" htmlFor="s-timeout" hint="Capped by the server limit.">
            <input id="s-timeout" type="number" min={30} max={900} className="input" value={s.investigationTimeoutSec} onChange={(e) => set("investigationTimeoutSec", Math.max(30, Math.min(900, Number(e.target.value))))} />
          </Field>
        </div>
        <div className="row" style={{ justifyContent: "space-between", marginTop: 16 }}>
          <div><strong>Expand raw evidence by default</strong><div className="small faint">Open the Evidence tab first on investigation pages.</div></div>
          <Switch label="Expand raw evidence by default" checked={s.showRawEvidenceByDefault} onChange={(v) => set("showRawEvidenceByDefault", v)} />
        </div>
      </Card>

      <Card title="Appearance">
        <div className="row">
          {(["dark", "light"] as Theme[]).map((t) => (
            <Button key={t} variant={theme === t ? "primary" : "default"} onClick={() => { setTheme(t); setThemeState(t); }}>
              {t === "dark" ? <Moon size={14} /> : <Sun size={14} />} {t === "dark" ? "Dark" : "Light"}
            </Button>
          ))}
        </div>
      </Card>

      <Card title="Security posture">
        <ul className="stack" style={{ margin: 0, paddingLeft: 18 }}>
          <li>All AWS operations are read-only (<span className="mono">Describe*</span>, <span className="mono">List*</span>, <span className="mono">Get*</span>, CloudWatch queries).</li>
          <li>Access uses temporary STS credentials from an assumed IAM role; no long-lived keys are stored.</li>
          <li>Investigations are restricted to each connection's account and allowed regions.</li>
          <li>Retrieved logs and resource descriptions are treated as untrusted data by the agent.</li>
          <li>Credentials and secrets are redacted from logs and reports.</li>
        </ul>
      </Card>
    </div>
  );
}
