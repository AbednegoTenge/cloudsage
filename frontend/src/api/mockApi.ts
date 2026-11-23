// In-memory mock of the CloudSage API for Phase 1 / local development.
// The "agent" here is a scripted simulation so the UI can be exercised end to end;
// the real interpretation and planning happens in the backend agent (Phase 5).
import type { CloudSageApi } from "./client";
import { mockConnections, mockDashboard, mockDetail, mockInvestigations, mockSettings } from "../mocks/data";
import type {
  AwsConnection,
  AwsService,
  Investigation,
  InvestigationDetail,
  InvestigationEvent,
  ToolExecution,
} from "../types/domain";

const delay = <T>(value: T, ms = 250) => new Promise<T>((r) => setTimeout(() => r(structuredClone(value)), ms));

const RESOURCE_PATTERNS: { service: AwsService; type: string; re: RegExp }[] = [
  { service: "ec2", type: "instance", re: /\bi-[0-9a-f]{8,17}\b/i },
  { service: "lambda", type: "function", re: /lambda (?:function )?([a-z0-9-_]+)/i },
  { service: "ecs", type: "service", re: /ecs service ([a-z0-9-_]+)/i },
  { service: "rds", type: "db-instance", re: /rds (?:instance )?([a-z0-9-]+)/i },
];

function guessService(prompt: string): AwsService {
  const p = prompt.toLowerCase();
  if (/\blambda\b/.test(p)) return "lambda";
  if (/\becs\b|task|container/.test(p)) return "ecs";
  if (/\brds\b|database|postgres|mysql/.test(p)) return "rds";
  return "ec2";
}

export function createMockApi(): CloudSageApi {
  let connections: AwsConnection[] = structuredClone(mockConnections);
  const investigations: Investigation[] = structuredClone(mockInvestigations);
  const details = new Map<string, InvestigationDetail>();
  const listeners = new Map<string, Set<(e: InvestigationEvent) => void>>();
  let settings = structuredClone(mockSettings);
  let nextId = 1043;

  const getDetail = (id: string): InvestigationDetail | null => details.get(id) ?? mockDetail(id);

  function emit(id: string, e: InvestigationEvent) {
    const d = details.get(id);
    if (d) d.events.push(e);
    listeners.get(id)?.forEach((fn) => fn(e));
  }

  function simulate(inv: Investigation) {
    const service = inv.services[0];
    const explicit = inv.identificationMode === "explicit";
    const toolNames = explicit
      ? [`${service}_describe_${service === "lambda" ? "function" : service === "ecs" ? "service" : "instance"}`, "cloudwatch_get_metric_data", "cloudwatch_query_logs"]
      : [`${service}_discover_resources`, `${service}_get_health`, "cloudwatch_get_metric_data"];
    const steps: { at: number; run: () => void }[] = [];
    let seq = 1;
    const ev = (type: InvestigationEvent["type"], message: string, toolExecutionId?: string): InvestigationEvent => ({
      id: `${inv.id}-ev-${seq}`,
      seq: seq++,
      investigationId: inv.id,
      type,
      message,
      toolExecutionId,
      createdAt: new Date().toISOString(),
    });
    steps.push({ at: 300, run: () => emit(inv.id, ev("queued", "Investigation queued.")) });
    steps.push({ at: 900, run: () => { inv.status = "running"; emit(inv.id, ev("planning", `Interpreting request; scope ${inv.accountId} / ${inv.region}.`)); } });
    steps.push({
      at: 1800,
      run: () =>
        emit(
          inv.id,
          ev("plan", explicit
            ? `Identified ${service.toUpperCase()} resource ${inv.resources[0]?.identifier}. Plan: describe it, check health, pull metrics and logs.`
            : `No identifier supplied. Plan: discover ${service.toUpperCase()} resources in ${inv.region}, filter by health, drill into affected ones.`),
        ),
    });
    toolNames.forEach((name, i) => {
      const teId = `${inv.id}-te-${i + 1}`;
      const at = 2600 + i * 1400;
      steps.push({
        at,
        run: () => {
          const te: ToolExecution = {
            id: teId,
            investigationId: inv.id,
            toolName: name,
            service: name.startsWith("cloudwatch") ? "cloudwatch" : service,
            input: { region: inv.region, ...(inv.resources[0] ? { identifier: inv.resources[0].identifier } : {}) },
            output: null,
            status: "running",
            durationMs: 0,
            startedAt: new Date().toISOString(),
          };
          details.get(inv.id)?.toolExecutions.push(te);
          inv.toolCallCount += 1;
          emit(inv.id, ev("tool_started", `Running ${name}`, teId));
        },
      });
      steps.push({
        at: at + 1000,
        run: () => {
          const te = details.get(inv.id)?.toolExecutions.find((t) => t.id === teId);
          if (te) Object.assign(te, { status: "succeeded", durationMs: 1000, output: { note: "Mock evidence payload" } });
          emit(inv.id, ev("tool_completed", `${name} completed in 1000 ms`, teId));
        },
      });
    });
    const end = 2600 + toolNames.length * 1400 + 400;
    steps.push({ at: end, run: () => emit(inv.id, ev("analyzing", "Correlating evidence and drafting report.")) });
    steps.push({
      at: end + 1500,
      run: () => {
        inv.status = "completed";
        inv.completedAt = new Date().toISOString();
        const d = details.get(inv.id);
        const template = mockDetail("inv-1039")?.report;
        if (d && template) {
          d.report = {
            ...template,
            investigationId: inv.id,
            summary: "Mock investigation finished. In Phase 5 this report is produced by the Bedrock-backed agent from the evidence above.",
            observations: d.toolExecutions.map((t) => ({ statement: `${t.toolName} returned data.`, evidenceIds: [t.id] })),
            generatedAt: inv.completedAt,
          };
        }
        emit(inv.id, ev("report_ready", "Report generated."));
      },
    });
    steps.forEach((s) => setTimeout(s.run, s.at));
  }

  return {
    getDashboard: () => delay(mockDashboard),
    async listInvestigations(f) {
      const s = f?.search?.toLowerCase();
      const items = investigations
        .filter((i) => !f?.status || i.status === f.status)
        .filter((i) => !f?.connectionId || i.connectionId === f.connectionId)
        .filter((i) => !s || i.title.toLowerCase().includes(s) || i.prompt.toLowerCase().includes(s) || i.resources.some((r) => r.identifier.toLowerCase().includes(s)));
      return delay(items);
    },
    async getInvestigation(id) {
      const d = getDetail(id);
      if (!d) throw new Error(`Investigation ${id} not found`);
      return delay(d);
    },
    async createInvestigation(req) {
      const conn = connections.find((c) => c.id === req.connectionId);
      if (!conn) throw new Error("Unknown AWS connection");
      if (!conn.allowedRegions.includes(req.region)) throw new Error(`Region ${req.region} is not allowed for ${conn.name}`);
      const service = guessService(req.prompt);
      const match = RESOURCE_PATTERNS.find((p) => p.service === service)?.re.exec(req.prompt);
      const identifier = match ? (match[1] ?? match[0]) : undefined;
      const now = Date.now();
      const inv: Investigation = {
        id: `inv-${nextId++}`,
        title: req.prompt.length > 70 ? `${req.prompt.slice(0, 67)}...` : req.prompt,
        prompt: req.prompt,
        connectionId: conn.id,
        accountId: conn.accountId,
        region: req.region,
        status: "queued",
        identificationMode: identifier ? "explicit" : "discovered",
        services: [service, "cloudwatch"],
        resources: identifier ? [{ service, resourceType: RESOURCE_PATTERNS.find((p) => p.service === service)!.type, identifier }] : [],
        timeRange: { start: new Date(now - req.timeRangeHours * 3_600_000).toISOString(), end: new Date(now).toISOString() },
        createdAt: new Date(now).toISOString(),
        completedAt: null,
        toolCallCount: 0,
      };
      investigations.unshift(inv);
      details.set(inv.id, { investigation: inv, events: [], toolExecutions: [], report: null });
      simulate(inv);
      return delay(inv, 150);
    },
    streamInvestigationEvents(id, onEvent) {
      getDetail(id)?.events.forEach(onEvent);
      if (!listeners.has(id)) listeners.set(id, new Set());
      listeners.get(id)!.add(onEvent);
      return () => listeners.get(id)?.delete(onEvent);
    },
    listConnections: () => delay(connections),
    async createConnection(input) {
      const c: AwsConnection = { ...input, id: `conn-${Math.random().toString(36).slice(2, 8)}`, status: "unvalidated", lastValidatedAt: null };
      connections = [...connections, c];
      return delay(c);
    },
    async validateConnection(id) {
      const c = connections.find((x) => x.id === id);
      if (!c) throw new Error("Connection not found");
      if (c.id !== "conn-sandbox") {
        c.status = "connected";
        c.statusMessage = undefined;
      }
      c.lastValidatedAt = new Date().toISOString();
      return delay(c, 900);
    },
    async deleteConnection(id) {
      connections = connections.filter((c) => c.id !== id);
      return delay(undefined);
    },
    getSettings: () => delay(settings),
    async updateSettings(s) {
      settings = structuredClone(s);
      return delay(settings);
    },
  };
}
