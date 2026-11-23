import { CheckCircle2, KeyRound, Plug, Plus, RefreshCw, ShieldCheck, Trash2, X } from "lucide-react";
import { useState, type FormEvent } from "react";
import { api } from "../api/client";
import { ConnectionStatusBadge } from "../components/domain";
import { Badge, Button, Card, EmptyState, ErrorCallout, Field, PageHeader, Spinner } from "../components/ui";
import { useScope } from "../context/ScopeContext";
import { useAsync } from "../hooks/useAsync";
import { relativeTime } from "../lib/format";
import { AWS_REGIONS, looksLikeAccessKey, validateConnection, type ConnectionDraft, type ConnectionErrors } from "../lib/validation";
import type { AwsConnection } from "../types/domain";

export function ConnectionsPage() {
  const list = useAsync(() => api.listConnections());
  const { refreshConnections } = useScope();
  const [adding, setAdding] = useState(false);
  const [validating, setValidating] = useState<string>();

  async function validate(c: AwsConnection) {
    setValidating(c.id);
    try {
      await api.validateConnection(c.id);
      list.reload();
      await refreshConnections();
    } finally {
      setValidating(undefined);
    }
  }
  async function remove(c: AwsConnection) {
    if (!window.confirm(`Remove connection "${c.name}"? Past investigations stay in history.`)) return;
    await api.deleteConnection(c.id);
    list.reload();
    await refreshConnections();
  }

  return (
    <div className="page">
      <PageHeader
        title="AWS connections"
        subtitle="CloudSage reaches each AWS account by assuming a read-only IAM role with temporary credentials."
        actions={<Button variant="primary" onClick={() => setAdding(true)}><Plus size={14} /> Add connection</Button>}
      />
      <div className="callout info">
        <ShieldCheck size={16} style={{ flex: "none", marginTop: 2 }} />
        <div className="small">
          <strong>No access keys are ever stored.</strong> Each connection is an IAM role ARN (plus optional external ID) that the CloudSage
          backend assumes via STS for each investigation. The role and its trust policy are provisioned by your infrastructure team.
        </div>
      </div>

      {list.error && <ErrorCallout error={list.error} />}
      {!list.data ? (
        <Spinner />
      ) : list.data.length === 0 ? (
        <Card><EmptyState icon={<Plug size={28} />} title="No AWS connections yet">Add one to start investigating.</EmptyState></Card>
      ) : (
        <div className="grid grid-3">
          {list.data.map((c) => (
            <Card
              key={c.id}
              title={<div className="stack" style={{ gap: 2 }}><h2>{c.name}</h2><span className="mono small faint">{c.accountId}</span></div>}
              actions={<ConnectionStatusBadge status={c.status} />}
            >
              <div className="stack-lg">
                <dl className="kv">
                  <dt>Role</dt><dd className="mono small">{c.roleArn}</dd>
                  <dt>External ID</dt><dd className="small">{c.externalId ? <span className="mono">{c.externalId}</span> : <span className="faint">None</span>}</dd>
                  <dt>Default region</dt><dd className="small">{c.defaultRegion}</dd>
                  <dt>Allowed regions</dt><dd><div className="row wrap" style={{ gap: 4 }}>{c.allowedRegions.map((r) => <Badge key={r}>{r}</Badge>)}</div></dd>
                  <dt>Last validated</dt><dd className="small">{c.lastValidatedAt ? relativeTime(c.lastValidatedAt) : <span className="faint">Never</span>}</dd>
                </dl>
                {c.statusMessage && <div className="callout bad small">{c.statusMessage}</div>}
                <div className="row">
                  <Button size="sm" onClick={() => validate(c)} disabled={validating === c.id}>
                    {validating === c.id ? <span className="spinner" /> : <RefreshCw size={13} />} Validate
                  </Button>
                  <Button size="sm" variant="ghost" className="btn-danger" onClick={() => remove(c)} aria-label={`Remove ${c.name}`}><Trash2 size={13} /> Remove</Button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {adding && (
        <AddConnectionModal
          onClose={() => setAdding(false)}
          onCreated={async () => {
            setAdding(false);
            list.reload();
            await refreshConnections();
          }}
        />
      )}
    </div>
  );
}

const EMPTY: ConnectionDraft = { name: "", accountId: "", roleArn: "", externalId: "", defaultRegion: "us-east-1", allowedRegions: ["us-east-1"] };

export function AddConnectionModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [draft, setDraft] = useState<ConnectionDraft>(EMPTY);
  const [errors, setErrors] = useState<ConnectionErrors>({});
  const [saving, setSaving] = useState(false);
  const set = <K extends keyof ConnectionDraft>(k: K, v: ConnectionDraft[K]) => setDraft((d) => ({ ...d, [k]: v }));
  const keyPasted = Object.values(draft).some((v) => typeof v === "string" && looksLikeAccessKey(v));

  async function submit(e: FormEvent) {
    e.preventDefault();
    const errs = validateConnection(draft);
    setErrors(errs);
    if (Object.keys(errs).length || keyPasted) return;
    setSaving(true);
    try {
      await api.createConnection({ ...draft, roleArn: draft.roleArn.trim(), externalId: draft.externalId || undefined });
      onCreated();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Add AWS connection">
      <Card className="modal" title="Add AWS connection" actions={<Button variant="ghost" size="sm" onClick={onClose} aria-label="Close"><X size={14} /></Button>}>
        <form className="stack-lg" onSubmit={submit} noValidate>
          <Field label="Name" htmlFor="c-name" hint={errors.name}>
            <input id="c-name" className="input" value={draft.name} onChange={(e) => set("name", e.target.value)} placeholder="Production" />
          </Field>
          <Field label="AWS account ID" htmlFor="c-acct" hint={errors.accountId}>
            <input id="c-acct" className="input mono" inputMode="numeric" value={draft.accountId} onChange={(e) => set("accountId", e.target.value.trim())} placeholder="123456789012" />
          </Field>
          <Field label="Read-only IAM role ARN" htmlFor="c-role" hint={errors.roleArn ?? "Provided by your infrastructure engineer."}>
            <input id="c-role" className="input mono" value={draft.roleArn} onChange={(e) => set("roleArn", e.target.value)} placeholder="arn:aws:iam::123456789012:role/CloudSageReadOnly" />
          </Field>
          <Field label="External ID (optional)" htmlFor="c-ext" hint={errors.externalId}>
            <input id="c-ext" className="input mono" value={draft.externalId} onChange={(e) => set("externalId", e.target.value)} />
          </Field>
          <Field label="Allowed regions" hint={errors.allowedRegions ?? "Investigations can only run in these regions."}>
            <div className="chips">
              {AWS_REGIONS.map((r) => {
                const on = draft.allowedRegions.includes(r);
                return (
                  <button key={r} type="button" className="chip" aria-pressed={on} style={on ? { borderColor: "var(--accent)", color: "var(--accent)" } : undefined}
                    onClick={() => set("allowedRegions", on ? draft.allowedRegions.filter((x) => x !== r) : [...draft.allowedRegions, r])}>
                    {on && <CheckCircle2 size={12} style={{ marginRight: 4, verticalAlign: -2 }} />}{r}
                  </button>
                );
              })}
            </div>
          </Field>
          <Field label="Default region" htmlFor="c-def" hint={errors.defaultRegion}>
            <select id="c-def" className="select" value={draft.defaultRegion} onChange={(e) => set("defaultRegion", e.target.value)}>
              {AWS_REGIONS.map((r) => <option key={r}>{r}</option>)}
            </select>
          </Field>
          {keyPasted && (
            <div className="callout bad small" role="alert"><KeyRound size={14} /> This looks like an AWS access key. CloudSage never accepts long-lived keys; use an IAM role ARN instead.</div>
          )}
          <div className="row" style={{ justifyContent: "flex-end" }}>
            <Button variant="ghost" onClick={onClose}>Cancel</Button>
            <Button type="submit" variant="primary" disabled={saving}>{saving ? "Saving..." : "Add connection"}</Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
