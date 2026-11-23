// Domain types shared across the UI. They mirror the backend API schemas planned for Phase 2
// (see docs/ARCHITECTURE.md §3) so swapping mocks for the real API needs no UI changes.

export type AwsService = "ec2" | "ecs" | "rds" | "lambda" | "cloudwatch";

export type ConnectionStatus = "connected" | "unvalidated" | "error";

export interface AwsConnection {
  id: string;
  name: string;
  accountId: string;
  roleArn: string;
  externalId?: string;
  defaultRegion: string;
  allowedRegions: string[];
  status: ConnectionStatus;
  lastValidatedAt: string | null;
  statusMessage?: string;
}

export type InvestigationStatus = "queued" | "running" | "completed" | "failed" | "timed_out";

export type ResourceHealth = "healthy" | "degraded" | "unhealthy" | "unknown";

export interface ResourceRef {
  service: AwsService;
  resourceType: string; // e.g. "instance", "service", "function"
  identifier: string; // e.g. i-0abc..., arn:..., function name
  name?: string;
  health?: ResourceHealth;
}

export type IdentificationMode = "explicit" | "discovered";

export interface Investigation {
  id: string;
  title: string;
  prompt: string;
  connectionId: string;
  accountId: string;
  region: string;
  status: InvestigationStatus;
  identificationMode: IdentificationMode;
  services: AwsService[];
  resources: ResourceRef[];
  timeRange: { start: string; end: string };
  createdAt: string;
  completedAt: string | null;
  toolCallCount: number;
  severity?: "info" | "low" | "medium" | "high" | "critical";
}

export type InvestigationEventType =
  | "queued"
  | "planning"
  | "plan"
  | "tool_started"
  | "tool_completed"
  | "tool_failed"
  | "analyzing"
  | "report_ready"
  | "failed";

export interface InvestigationEvent {
  id: string;
  investigationId: string;
  seq: number;
  type: InvestigationEventType;
  message: string;
  createdAt: string;
  toolExecutionId?: string;
}

export type ToolExecutionStatus = "succeeded" | "failed" | "running";

/** Raw evidence returned by an AWS tool. Kept separate from the AI-generated report. */
export interface ToolExecution {
  id: string;
  investigationId: string;
  toolName: string;
  service: AwsService;
  input: Record<string, unknown>;
  output: unknown;
  status: ToolExecutionStatus;
  error?: string;
  durationMs: number;
  startedAt: string;
}

export type Confidence = "low" | "medium" | "high";

export interface Observation {
  /** An observed fact, always backed by one or more tool executions. */
  statement: string;
  evidenceIds: string[];
}

export interface Hypothesis {
  /** A potential root cause inferred from observations. Never presented as fact. */
  statement: string;
  confidence: Confidence;
  supportingObservations: number[];
}

export interface Recommendation {
  title: string;
  detail: string;
  priority: "now" | "next" | "later";
}

export interface MetricSeries {
  label: string;
  unit: string;
  evidenceId: string;
  points: { t: string; v: number }[];
  threshold?: number;
}

export interface InvestigationReport {
  investigationId: string;
  summary: string;
  observations: Observation[];
  metrics: MetricSeries[];
  logExcerpts: { evidenceId: string; logGroup: string; lines: string[] }[];
  hypotheses: Hypothesis[];
  recommendations: Recommendation[];
  confidence: Confidence;
  limitations: string[];
  modelId: string;
  generatedAt: string;
}

export interface InvestigationDetail {
  investigation: Investigation;
  events: InvestigationEvent[];
  toolExecutions: ToolExecution[];
  report: InvestigationReport | null;
}

export interface CreateInvestigationRequest {
  prompt: string;
  connectionId: string;
  region: string;
  timeRangeHours: number;
}

export interface DashboardSummary {
  investigationsLast7d: number;
  openIssues: number;
  avgTimeToReportSec: number;
  resourcesMonitored: Record<AwsService, number>;
  healthByService: { service: AwsService; healthy: number; degraded: number; unhealthy: number }[];
  dailyInvestigations: { day: string; count: number }[];
}

export interface UserSettings {
  displayName: string;
  email: string;
  defaultTimeRangeHours: number;
  defaultConnectionId: string | null;
  showRawEvidenceByDefault: boolean;
  maxToolCalls: number;
  investigationTimeoutSec: number;
}
