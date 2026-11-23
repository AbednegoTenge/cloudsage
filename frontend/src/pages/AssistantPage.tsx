import { ArrowRight, Clock, CloudCog, FlaskConical, Globe, History, Lightbulb, Lock, Paperclip, Send, Server, Sparkles, User } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { InvestigationStatusBadge, ServiceTag } from "../components/domain";
import { InlineReport, Timeline } from "../components/report";
import { Badge } from "../components/ui";
import { useScope } from "../context/ScopeContext";
import { formatTime } from "../lib/format";
import type { Investigation, InvestigationDetail, InvestigationEvent } from "../types/domain";

const EXAMPLES = [
  "Find unhealthy EC2 instances in my AWS account.",
  "Investigate why EC2 instance i-0a1b2c3d4e5f67890 is unhealthy.",
  "Why is the ECS service payments-api not finishing its deployment?",
  "The Lambda function order-processor is throwing errors. What changed?",
];
const TIME_RANGES = [1, 3, 6, 12, 24, 72, 168];

interface Turn {
  investigation: Investigation;
  events: InvestigationEvent[];
  detail?: InvestigationDetail;
}

function greeting(): string {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

function AgentTurn({ turn, onUpdate }: { turn: Turn; onUpdate: (t: Turn) => void }) {
  const turnRef = useRef(turn);
  turnRef.current = turn;
  useEffect(() => {
    const seen = new Set<string>();
    return api.streamInvestigationEvents(turn.investigation.id, (e) => {
      if (seen.has(e.id)) return;
      seen.add(e.id);
      const cur = turnRef.current;
      const next = { ...cur, events: [...cur.events, e] };
      turnRef.current = next;
      onUpdate(next);
      if (e.type === "report_ready") {
        void api.getInvestigation(turn.investigation.id).then((detail) => {
          const withDetail = { ...turnRef.current, detail };
          turnRef.current = withDetail;
          onUpdate(withDetail);
        });
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [turn.investigation.id]);

  const inv = turn.investigation;
  const done = turn.events.some((e) => e.type === "report_ready");
  const failed = turn.events.some((e) => e.type === "failed");
  const status: Investigation["status"] = done ? "completed" : failed ? "failed" : turn.events.length > 1 ? "running" : "queued";

  return (
    <div className="msg">
      <span className="msg-avatar agent"><CloudCog size={16} /></span>
      <div className="stack-lg" style={{ minWidth: 0 }}>
        <div>
          <div className="msg-head">CloudSage <span className="xs faint">AI Agent</span><span className="xs faint mono">{formatTime(inv.createdAt)}</span></div>
          <div className="row wrap small muted">
            <span className="mono">{inv.id.toUpperCase()}</span>·<span className="mono">{inv.accountId}</span>·<span className="mono">{inv.region}</span>·
            <span>{inv.identificationMode === "explicit" ? "explicit resource" : "auto-discovery"}</span>
            {inv.services.map((s) => <ServiceTag key={s} service={s} />)}
            <InvestigationStatusBadge status={status} />
          </div>
        </div>
        <section className="card" style={{ padding: "14px 18px" }}>
          <Timeline events={turn.events} label="Investigation progress" />
        </section>
        {turn.detail && (
          <>
            <p className="small muted">Investigation complete. Observed evidence below comes from read-only AWS tool calls; root causes and recommendations are AI-generated hypotheses and labelled as such.</p>
            <InlineReport detail={turn.detail} />
          </>
        )}
        {done && (
          <div><Link to={`/investigations/${inv.id}`} className="btn btn-primary">Open full report <ArrowRight size={14} /></Link></div>
        )}
      </div>
    </div>
  );
}

export function AssistantPage() {
  const { connection, region, setRegion } = useScope();
  const [params] = useSearchParams();
  const [prompt, setPrompt] = useState(params.get("prompt") ?? "");
  const [resource, setResource] = useState("");
  const [hours, setHours] = useState(6);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string>();
  const [turns, setTurns] = useState<Turn[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo?.({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [turns]);

  async function submit(e?: FormEvent, text = prompt) {
    e?.preventDefault();
    const body = text.trim();
    if (!connection || !body) return;
    const full = resource.trim() ? `${body} (resource: ${resource.trim()})` : body;
    setSubmitting(true);
    setError(undefined);
    try {
      const investigation = await api.createInvestigation({ prompt: full, connectionId: connection.id, region, timeRangeHours: hours });
      setTurns((t) => [...t, { investigation, events: [] }]);
      setPrompt("");
      setResource("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="workspace">
      <div className="workspace-head">
        <div>
          <div className="row"><Sparkles size={15} style={{ color: "var(--primary)" }} /><h1 style={{ fontSize: 15 }}>AI Assistant</h1><Badge tone="info">Investigation workspace</Badge></div>
          <p className="small muted" style={{ marginTop: 4 }}>Investigate AWS infrastructure, analyze metrics, and identify operational issues.</p>
        </div>
        <Link to="/investigations" className="btn"><History size={14} /> Investigation history</Link>
      </div>

      <div className="workspace-scroll" ref={scrollRef}>
        <div className="workspace-inner">
          {turns.length === 0 ? (
            <>
              <div className="hero">
                <div className="brand-mark"><Sparkles size={20} /></div>
                <h2>{greeting()}. What would you like to investigate today?</h2>
                <p>Ask CloudSage to investigate your AWS infrastructure, analyze metrics, and identify potential operational issues.</p>
              </div>
              <div className="stack">
                <span className="label-caps row"><Lightbulb size={13} /> Suggested prompts</span>
                <div className="prompt-grid">
                  {EXAMPLES.map((ex) => (
                    <button key={ex} type="button" className="prompt-card" onClick={() => setPrompt(ex)}>
                      <span className="icon-tile sm"><Sparkles size={13} /></span>
                      <span>{ex}</span>
                      <ArrowRight size={14} className="arrow" />
                    </button>
                  ))}
                </div>
              </div>
              <div className="info-tiles">
                <div className="info-tile"><span className="label-caps">Investigation stages</span><strong>Plan · Discover · Analyze · Report</strong></div>
                <div className="info-tile"><span className="label-caps">Evidence sources</span><strong>Describe APIs · Metrics · Logs</strong></div>
                <div className="info-tile"><span className="label-caps">Hypothesis clarity</span><strong>Facts vs hypotheses, scored</strong></div>
              </div>
            </>
          ) : (
            turns.map((t, i) => (
              <div key={t.investigation.id} className="stack-lg">
                <div className="msg">
                  <span className="msg-avatar"><User size={15} /></span>
                  <div>
                    <div className="msg-head">You <span className="xs faint mono">{formatTime(t.investigation.createdAt)}</span></div>
                    <p>{t.investigation.prompt}</p>
                  </div>
                </div>
                <AgentTurn turn={t} onUpdate={(next) => setTurns((all) => all.map((x, j) => (j === i ? next : x)))} />
              </div>
            ))
          )}
        </div>
      </div>

      <div className="composer-wrap">
        <form className="composer" onSubmit={submit}>
          <textarea
            aria-label="Investigation request"
            placeholder="Ask CloudSage about your AWS infrastructure..."
            value={prompt}
            maxLength={2000}
            rows={2}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void submit();
              }
            }}
          />
          <div className="composer-tools">
            <span className="icon-btn" style={{ width: 30, height: 30 }} aria-hidden title="Attachments arrive in a later phase"><Paperclip size={14} /></span>
            <label className="mini-select"><Globe size={13} />
              <select aria-label="Region" value={region} onChange={(e) => setRegion(e.target.value)}>
                {(connection?.allowedRegions ?? []).map((r) => <option key={r}>{r}</option>)}
              </select>
            </label>
            <label className="mini-select"><Clock size={13} />
              <select aria-label="Time range" value={hours} onChange={(e) => setHours(Number(e.target.value))}>
                {TIME_RANGES.map((h) => <option key={h} value={h}>{h < 48 ? `Last ${h}h` : `Last ${h / 24}d`}</option>)}
              </select>
            </label>
            <label className="mini-select hide-mobile"><Server size={13} />
              <input aria-label="Resource (optional)" placeholder="Resource (optional)" value={resource} onChange={(e) => setResource(e.target.value)} maxLength={256} />
            </label>
            <span className="row xs faint hide-mobile" style={{ marginLeft: "auto" }}><Lock size={11} /> Read-only</span>
            <button type="submit" className="btn btn-primary" disabled={!prompt.trim() || !connection || submitting} style={{ marginLeft: 8 }}>
              <Send size={13} /> {submitting ? "Starting..." : "Send"}
            </button>
          </div>
          {error && <div className="callout bad small" role="alert">{error}</div>}
        </form>
        <p className="composer-foot"><FlaskConical size={11} style={{ verticalAlign: -1 }} /> Local development uses sample AWS data. CloudSage never modifies AWS resources.</p>
      </div>
    </div>
  );
}
