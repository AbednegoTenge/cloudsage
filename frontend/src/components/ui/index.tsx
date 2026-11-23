import type { ButtonHTMLAttributes, ReactNode } from "react";

export function Card({ title, subtitle, icon, actions, children, flush, className = "", id }: {
  title?: ReactNode;
  subtitle?: ReactNode;
  icon?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  flush?: boolean;
  className?: string;
  id?: string;
}) {
  return (
    <section className={`card ${className}`} id={id}>
      {(title || actions) && (
        <div className="card-header">
          <div style={{ minWidth: 0 }}>
            {typeof title === "string" ? <h2 className="card-title">{icon}{title}</h2> : title}
            {subtitle && <div className="card-sub">{subtitle}</div>}
          </div>
          {actions && <div className="row">{actions}</div>}
        </div>
      )}
      <div className={`card-body ${flush ? "flush" : ""}`}>{children}</div>
    </section>
  );
}

type Variant = "default" | "primary" | "ghost" | "danger";
export function Button({ variant = "default", size, className = "", ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" }) {
  const v = variant === "default" ? "" : `btn-${variant}`;
  return <button type="button" className={`btn ${v} ${size === "sm" ? "btn-sm" : ""} ${className}`} {...rest} />;
}

export type Tone = "ok" | "warn" | "bad" | "info" | "accent" | "neutral";
export function Badge({ tone = "neutral", dot, pulse, pill, children, title }: { tone?: Tone; dot?: boolean; pulse?: boolean; pill?: boolean; children: ReactNode; title?: string }) {
  return (
    <span className={`badge ${tone === "neutral" ? "" : tone} ${pulse ? "pulse" : ""} ${pill ? "pill" : ""}`} title={title}>
      {dot && <span className="dot" />}
      {children}
    </span>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="page-header">
      <div>
        <h1>{title}</h1>
        {subtitle && <p className="sub">{subtitle}</p>}
      </div>
      {actions && <div className="row wrap">{actions}</div>}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="row muted small" role="status">
      <span className="spinner" aria-hidden />
      {label ?? "Loading..."}
    </span>
  );
}

export function EmptyState({ icon, title, children }: { icon?: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      {icon}
      <strong style={{ color: "var(--text-2)", fontWeight: 500 }}>{title}</strong>
      {children && <div className="small">{children}</div>}
    </div>
  );
}

export function ErrorCallout({ error }: { error: Error }) {
  return (
    <div className="callout bad" role="alert">
      <strong>Something went wrong.</strong> {error.message}
    </div>
  );
}

export function Switch({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className="switch" title={label}>
      <input type="checkbox" aria-label={label} checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span />
    </label>
  );
}

export function Field({ label, hint, error, htmlFor, children }: { label: string; hint?: ReactNode; error?: string; htmlFor?: string; children: ReactNode }) {
  return (
    <div className="field">
      <label htmlFor={htmlFor}>{label}</label>
      {children}
      {(error || hint) && <span className={`hint ${error ? "err" : ""}`}>{error ?? hint}</span>}
    </div>
  );
}

export function Segmented<T extends string | number>({ options, value, onChange, label }: { options: { value: T; label: string }[]; value: T; onChange: (v: T) => void; label: string }) {
  return (
    <div className="segmented" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button key={String(o.value)} type="button" role="radio" aria-checked={o.value === value} className={o.value === value ? "on" : ""} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** Footnote shown while the UI runs on canned data, so nobody mistakes it for live telemetry. */
export function DemoNote({ children }: { children?: ReactNode }) {
  return <p className="demo-note">{children ?? "Sample data for local development. Not connected to a live AWS account."}</p>;
}
