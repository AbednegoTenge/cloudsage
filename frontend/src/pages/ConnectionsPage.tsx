import { CheckCircle2, Clock, KeyRound, Lock, Plug, Plus, RefreshCw, ShieldCheck, Trash2, X } from "lucide-react";
import { useState, type FormEvent } from "react";
import { api } from "../api/client";
import { ConnectionStatusBadge } from "../components/domain";
import { Button, Card, DemoNote, EmptyState, ErrorCallout, Field, PageHeader, Spinner } from "../components/ui";
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
        subtitle="Manage the cross-account IAM role connections CloudSage uses to investigate your AWS infrastructure."
        actions={<Button variant="primary" onClick={() => setAdding(true)}><Plus size={14} /> Add connection</Button>}
      />
      <section className="callout info" style={{ padding: 18 }}>
        <span className="icon-tile" style={{ flex: "none" }}><ShieldCheck size={16} /></span>
        <div className="stack" style={{ gap: 6 }}>
          <strong style={{ fontSize: 14 }}>CloudSage uses temporary credentials. No long-lived AWS access keys.</strong>
          <span className="small muted">
            Each connection is an IAM role ARN (plus optional external ID). For every investigation the backend calls STS <span className="mono">AssumeRole</span> and
            receives a short-lived credential scoped to that role's read-only permissions. The role and its trust policy are provisioned by your infrastructure team.
          </span>
          <div className="row wrap" style={{ marginTop: 4 }}>
            <span className="tag-chip"><KeyRound size={11} /> STS AssumeRole</span>
            <span className="tag-chip"><Clock size={11} /> 15-60 min credentials</span>
            <span className="tag-chip"><Lock size={11} /> Read-only, least privilege</span>
          </div>
        </div>
      </section>

      {list.error && <ErrorCallout error={list.error} />}
      {list.data?.filter((c) => c.statusMessage).map((c) => (
        <div key={c.id} className="callout bad small" role="status">
          <strong style={{ color: "var(--unhealthy)" }}>{c.name}:</strong> {c.statusMessage}
        </div>
      ))}
      {!list.data ? (
        <Spinner />
      ) : list.data.length === 0 ? (
        <Card><EmptyState icon={<Plug size={28} />} title="No AWS connections yet">Add one to start investigating.</EmptyState></Card>
      ) : (
        <section className="card">
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Account</th><th>AWS account ID</th><th>Method</th><th>IAM role ARN</th><th>Regions</th><th>Status</th><th>Last validated</th><th style={{ textAlign: "right" }}>Actions</th></tr></thead>
              <tbody>
                {list.data.map((c) => (
                  <tr key={c.id}>
                    <td style={{ fontWeight: 500, whiteSpace: "nowrap" }}>{c.name}</td>
                    <td className="mono small muted">{c.accountId}</td>
                    <td className="small muted" style={{ whiteSpace: "nowrap" }}>IAM cross-account role</td>
                    <td className="mono xs muted ellipsis" style={{ maxWidth: 220 }} title={c.roleArn}>{c.roleArn}</td>
                    <td className="mono xs muted" style={{ whiteSpace: "nowrap" }}><span style={{ color: "var(--foreground)" }}>{c.defaultRegion}</span>{c.allowedRegions.length > 1 && ` +${c.allowedRegions.length - 1}`}</td>
                    <td><span title={c.statusMessage}><ConnectionStatusBadge status={c.status} /></span></td>
                    <td className="mono xs muted" style={{ whiteSpace: "nowrap" }}>{c.lastValidatedAt ? relativeTime(c.lastValidatedAt) : "never"}</td>
                    <td>
                      <div className="row" style={{ justifyContent: "flex-end" }}>
                        <Button size="sm" onClick={() => validate(c)} disabled={validating === c.id}>
                          {validating === c.id ? <span className="spinner" /> : <RefreshCw size={12} />} Re-validate
                        </Button>
                        <Button size="sm" variant="ghost" className="btn-danger" onClick={() => remove(c)} aria-label={`Remove ${c.name}`}><Trash2 size={13} /></Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      <DemoNote>In local development, validation is simulated. No IAM roles, trust policies or STS calls are touched.</DemoNote>

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
          <Field label="Name" htmlFor="c-name" error={errors.name}>
            <input id="c-name" className="input" value={draft.name} onChange={(e) => set("name", e.target.value)} placeholder="Production" />
          </Field>
          <Field label="AWS account ID" htmlFor="c-acct" error={errors.accountId}>
            <input id="c-acct" className="input mono" inputMode="numeric" value={draft.accountId} onChange={(e) => set("accountId", e.target.value.trim())} placeholder="123456789012" />
          </Field>
          <Field label="Read-only IAM role ARN" htmlFor="c-role" error={errors.roleArn} hint="Provided by your infrastructure engineer.">
            <input id="c-role" className="input mono" value={draft.roleArn} onChange={(e) => set("roleArn", e.target.value)} placeholder="arn:aws:iam::123456789012:role/CloudSageReadOnly" />
          </Field>
          <Field label="External ID (optional)" htmlFor="c-ext" error={errors.externalId}>
            <input id="c-ext" className="input mono" value={draft.externalId} onChange={(e) => set("externalId", e.target.value)} />
          </Field>
          <Field label="Allowed regions" error={errors.allowedRegions} hint="Investigations can only run in these regions.">
            <div className="chips">
              {AWS_REGIONS.map((r) => {
                const on = draft.allowedRegions.includes(r);
                return (
                  <button key={r} type="button" className="chip" aria-pressed={on} style={on ? { borderColor: "var(--primary)", color: "var(--primary)" } : undefined}
                    onClick={() => set("allowedRegions", on ? draft.allowedRegions.filter((x) => x !== r) : [...draft.allowedRegions, r])}>
                    {on && <CheckCircle2 size={12} style={{ marginRight: 4, verticalAlign: -2 }} />}{r}
                  </button>
                );
              })}
            </div>
          </Field>
          <Field label="Default region" htmlFor="c-def" error={errors.defaultRegion}>
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
