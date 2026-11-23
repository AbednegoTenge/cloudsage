import type { ButtonHTMLAttributes, ReactNode } from "react";

export function Card({ title, actions, children, flush, className = "", id }: {
  title?: ReactNode;
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
          {typeof title === "string" ? <h2>{title}</h2> : title}
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
export function Badge({ tone = "neutral", dot, pulse, children, title }: { tone?: Tone; dot?: boolean; pulse?: boolean; children: ReactNode; title?: string }) {
  return (
    <span className={`badge ${tone === "neutral" ? "" : tone} ${pulse ? "pulse" : ""}`} title={title}>
      {dot && <span className="dot" />}
      {children}
    </span>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="page-header">
      <div>
        <h1>{title}</h1>
        {subtitle && <p className="sub">{subtitle}</p>}
      </div>
      {actions && <div className="row">{actions}</div>}
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
      <strong style={{ color: "var(--text-2)" }}>{title}</strong>
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

export function Field({ label, hint, htmlFor, children }: { label: string; hint?: ReactNode; htmlFor?: string; children: ReactNode }) {
  return (
    <div className="field">
      <label htmlFor={htmlFor}>{label}</label>
      {children}
      {hint && <span className="hint">{hint}</span>}
    </div>
  );
}
