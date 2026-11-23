// Canned data for local development (VITE_USE_MOCKS=true). Account IDs use the AWS
// documentation placeholder ranges; nothing here is real infrastructure.
import type {
  AwsConnection,
  DashboardSummary,
  DiscoveredResource,
  Investigation,
  InvestigationDetail,
  InvestigationEvent,
  InvestigationReport,
  MetricSeries,
  ToolExecution,
  UserSettings,
} from "../types/domain";

const NOW = new Date("2026-11-23T10:30:00Z").getTime();
const iso = (minsAgo: number) => new Date(NOW - minsAgo * 60_000).toISOString();

export const mockConnections: AwsConnection[] = [
  {
    id: "conn-prod",
    name: "Production",
    accountId: "111122223333",
    roleArn: "arn:aws:iam::111122223333:role/CloudSageReadOnly",
    externalId: "cs-7f3a9c",
    defaultRegion: "us-east-1",
    allowedRegions: ["us-east-1", "us-west-2", "eu-west-1"],
    status: "connected",
    lastValidatedAt: iso(42),
  },
  {
    id: "conn-staging",
    name: "Staging",
    accountId: "444455556666",
    roleArn: "arn:aws:iam::444455556666:role/CloudSageReadOnly",
    externalId: "cs-19be02",
    defaultRegion: "eu-west-1",
    allowedRegions: ["eu-west-1"],
    status: "connected",
    lastValidatedAt: iso(60 * 5),
  },
  {
    id: "conn-sandbox",
    name: "Data sandbox",
    accountId: "777788889999",
    roleArn: "arn:aws:iam::777788889999:role/CloudSageReadOnly",
    defaultRegion: "us-west-2",
    allowedRegions: ["us-west-2"],
    status: "error",
    lastValidatedAt: iso(60 * 26),
    statusMessage: "sts:AssumeRole denied: trust policy does not allow the CloudSage principal.",
  },
];

export const mockInvestigations: Investigation[] = [
  {
    id: "inv-1042",
    summary: "Root volume filled to 100%, pinning CPU and failing the reachability check. System host check is healthy.",
    title: "EC2 instance i-0a1b2c3d4e5f67890 failing status checks",
    prompt: "Investigate why EC2 instance i-0a1b2c3d4e5f67890 is unhealthy.",
    connectionId: "conn-prod",
    accountId: "111122223333",
    region: "us-east-1",
    status: "completed",
    identificationMode: "explicit",
    services: ["ec2", "cloudwatch"],
    resources: [
      { service: "ec2", resourceType: "instance", identifier: "i-0a1b2c3d4e5f67890", name: "api-worker-3", health: "unhealthy" },
    ],
    timeRange: { start: iso(60 * 6 + 18), end: iso(18) },
    createdAt: iso(18),
    completedAt: iso(16),
    toolCallCount: 6,
    severity: "high",
  },
  {
    id: "inv-1041",
    summary: "2 of 46 instances flagged: api-worker-3 failing reachability, batch-runner-1 with elevated CPU credit usage.",
    title: "Discover unhealthy EC2 instances in production",
    prompt: "Find unhealthy EC2 instances in my AWS account.",
    connectionId: "conn-prod",
    accountId: "111122223333",
    region: "us-east-1",
    status: "completed",
    identificationMode: "discovered",
    services: ["ec2"],
    resources: [
      { service: "ec2", resourceType: "instance", identifier: "i-0a1b2c3d4e5f67890", name: "api-worker-3", health: "unhealthy" },
      { service: "ec2", resourceType: "instance", identifier: "i-0fedcba9876543210", name: "batch-runner-1", health: "degraded" },
    ],
    timeRange: { start: iso(60 * 2 + 25), end: iso(25) },
    createdAt: iso(25),
    completedAt: iso(24),
    toolCallCount: 3,
    severity: "medium",
  },
  {
    id: "inv-1040",
    summary: "Collecting service events and task stop reasons for the in-progress deployment.",
    title: "ECS service payments-api stuck in deployment",
    prompt: "Why is the payments-api ECS service not finishing its deployment?",
    connectionId: "conn-prod",
    accountId: "111122223333",
    region: "us-east-1",
    status: "running",
    identificationMode: "explicit",
    services: ["ecs", "cloudwatch"],
    resources: [
      { service: "ecs", resourceType: "service", identifier: "arn:aws:ecs:us-east-1:111122223333:service/prod-core/payments-api", name: "payments-api", health: "degraded" },
    ],
    timeRange: { start: iso(60 * 3 + 2), end: iso(2) },
    createdAt: iso(2),
    completedAt: null,
    toolCallCount: 3,
  },
  {
    id: "inv-1039",
    summary: "Errors rose from ~2 to ~40 per 5 min after a configuration change at 07:50 UTC; duration also increased.",
    title: "Lambda order-processor error rate spike",
    prompt: "The order-processor Lambda started throwing errors this morning. What changed?",
    connectionId: "conn-prod",
    accountId: "111122223333",
    region: "us-west-2",
    status: "completed",
    identificationMode: "explicit",
    services: ["lambda", "cloudwatch"],
    resources: [
      { service: "lambda", resourceType: "function", identifier: "order-processor", name: "order-processor", health: "degraded" },
    ],
    timeRange: { start: iso(60 * 12 + 140), end: iso(140) },
    createdAt: iso(140),
    completedAt: iso(137),
    toolCallCount: 5,
    severity: "medium",
  },
  {
    id: "inv-1038",
    summary: "Investigation failed: CloudSage could not assume the role for this account. Re-validate the IAM trust policy.",
    title: "RDS orders-db high CPU",
    prompt: "Check why the orders-db RDS instance has high CPU.",
    connectionId: "conn-sandbox",
    accountId: "777788889999",
    region: "us-west-2",
    status: "failed",
    identificationMode: "explicit",
    services: ["rds"],
    resources: [{ service: "rds", resourceType: "db-instance", identifier: "orders-db", name: "orders-db", health: "unknown" }],
    timeRange: { start: iso(60 * 30), end: iso(60 * 26) },
    createdAt: iso(60 * 26),
    completedAt: iso(60 * 26 - 1),
    toolCallCount: 0,
  },
  {
    id: "inv-1037",
    summary: "stg-catalog free storage fell below 12% after a bulk import; no other staging database is near its limit.",
    title: "Staging RDS storage nearing limit",
    prompt: "Are any staging databases running low on storage?",
    connectionId: "conn-staging",
    accountId: "444455556666",
    region: "eu-west-1",
    status: "completed",
    identificationMode: "discovered",
    services: ["rds", "cloudwatch"],
    resources: [{ service: "rds", resourceType: "db-instance", identifier: "stg-catalog", name: "stg-catalog", health: "degraded" }],
    timeRange: { start: iso(60 * 72), end: iso(60 * 48) },
    createdAt: iso(60 * 48),
    completedAt: iso(60 * 48 - 2),
    toolCallCount: 4,
    severity: "low",
  },
];

function series(
  label: string,
  unit: string,
  evidenceId: string,
  shape: (i: number) => number,
  opts: { points?: number; stepMin?: number; endMinsAgo?: number; threshold?: number } = {},
): MetricSeries {
  const { points = 72, stepMin = 5, endMinsAgo = 18, threshold } = opts;
  return {
    label,
    unit,
    evidenceId,
    threshold,
    points: Array.from({ length: points }, (_, i) => ({
      t: iso(endMinsAgo + (points - 1 - i) * stepMin),
      v: Math.round(shape(i) * 10) / 10,
    })),
  };
}

const jitter = (i: number, amp: number) => Math.sin(i * 1.7) * amp + Math.cos(i * 0.6) * amp * 0.5;

const ec2Tools: ToolExecution[] = [
  {
    id: "te-1",
    investigationId: "inv-1042",
    toolName: "ec2_describe_instance",
    service: "ec2",
    input: { instance_id: "i-0a1b2c3d4e5f67890", region: "us-east-1" },
    output: {
      InstanceId: "i-0a1b2c3d4e5f67890",
      InstanceType: "t3.large",
      State: "running",
      LaunchTime: "2026-10-02T08:14:51Z",
      AvailabilityZone: "us-east-1b",
      Tags: { Name: "api-worker-3", service: "api", team: "platform" },
      RootDevice: { VolumeId: "vol-0123abcd4567ef890", SizeGiB: 30 },
    },
    status: "succeeded",
    durationMs: 412,
    startedAt: iso(17.8),
  },
  {
    id: "te-2",
    investigationId: "inv-1042",
    toolName: "ec2_get_status_checks",
    service: "ec2",
    input: { instance_id: "i-0a1b2c3d4e5f67890", region: "us-east-1" },
    output: {
      SystemStatus: { Status: "ok" },
      InstanceStatus: { Status: "impaired", Details: [{ Name: "reachability", Status: "failed", ImpairedSince: iso(52) }] },
      ScheduledEvents: [],
    },
    status: "succeeded",
    durationMs: 288,
    startedAt: iso(17.7),
  },
  {
    id: "te-3",
    investigationId: "inv-1042",
    toolName: "cloudwatch_get_metric_data",
    service: "cloudwatch",
    input: { namespace: "AWS/EC2", metric: "CPUUtilization", dimensions: { InstanceId: "i-0a1b2c3d4e5f67890" }, period: 300, stat: "Average", hours: 6 },
    output: { datapoints: 72, max: 99.6, avg_last_60m: 98.9 },
    status: "succeeded",
    durationMs: 631,
    startedAt: iso(17.5),
  },
  {
    id: "te-4",
    investigationId: "inv-1042",
    toolName: "cloudwatch_get_metric_data",
    service: "cloudwatch",
    input: { namespace: "CWAgent", metric: "disk_used_percent", dimensions: { InstanceId: "i-0a1b2c3d4e5f67890", path: "/" }, period: 300, stat: "Maximum", hours: 6 },
    output: { datapoints: 72, max: 100, first_reached_100: iso(55) },
    status: "succeeded",
    durationMs: 587,
    startedAt: iso(17.4),
  },
  {
    id: "te-5",
    investigationId: "inv-1042",
    toolName: "cloudwatch_query_logs",
    service: "cloudwatch",
    input: { log_group: "/platform/api-worker", query: "fields @timestamp, @message | filter @message like /ERROR|No space/ | limit 50", hours: 2 },
    output: { matched: 214, returned: 50, truncated: true },
    status: "succeeded",
    durationMs: 2140,
    startedAt: iso(17.2),
  },
  {
    id: "te-6",
    investigationId: "inv-1042",
    toolName: "cloudwatch_describe_alarms",
    service: "cloudwatch",
    input: { resource_id: "i-0a1b2c3d4e5f67890" },
    output: { alarms: [{ AlarmName: "api-worker-3-status-check", State: "ALARM", Since: iso(50) }] },
    status: "succeeded",
    durationMs: 205,
    startedAt: iso(17.0),
  },
];

const ec2Report: InvestigationReport = {
  investigationId: "inv-1042",
  summary:
    "Instance api-worker-3 (i-0a1b2c3d4e5f67890) has been failing its instance reachability check for ~52 minutes while the underlying host (system check) is healthy. The root volume reached 100% usage shortly before the check began failing, CPU has been pinned near 99% since, and application logs repeatedly report write failures due to no space left on device.",
  observations: [
    { statement: "Instance status check is 'impaired' (reachability failed since ~52 min ago); system status check is 'ok'.", evidenceIds: ["te-2"] },
    { statement: "Root filesystem '/' disk_used_percent reached 100% at ~55 min ago and has stayed there.", evidenceIds: ["te-4"] },
    { statement: "CPUUtilization averaged 98.9% over the last 60 minutes (6-hour max 99.6%).", evidenceIds: ["te-3"] },
    { statement: "214 log events matched ERROR / 'No space left on device' in /platform/api-worker in the last 2 hours (50 returned).", evidenceIds: ["te-5"] },
    { statement: "CloudWatch alarm api-worker-3-status-check has been in ALARM for ~50 minutes.", evidenceIds: ["te-6"] },
  ],
  metrics: [
    series("CPUUtilization (Average)", "%", "te-3", (i) => (i < 58 ? 34 + jitter(i, 6) : 99 - Math.abs(jitter(i, 0.8))), { threshold: 90 }),
    series("disk_used_percent / (Maximum)", "%", "te-4", (i) => (i < 60 ? Math.min(100, 71 + i * 0.48) : 100), { threshold: 90 }),
  ],
  logExcerpts: [
    {
      evidenceId: "te-5",
      logGroup: "/platform/api-worker",
      lines: [
        "2026-11-23T09:38:02Z ERROR worker.spool: write failed: [Errno 28] No space left on device: '/var/spool/api/batch-8812.tmp'",
        "2026-11-23T09:38:02Z ERROR worker.retry: retrying job 8812 (attempt 4/5) in 0.5s",
        "2026-11-23T09:41:17Z ERROR logrotate: error writing /var/log/api/app.log.1: No space left on device",
        "2026-11-23T09:44:55Z ERROR worker.retry: retrying job 8812 (attempt 5/5) in 0.5s",
      ],
    },
  ],
  hypotheses: [
    {
      title: "Root volume exhausted by spool files and logs",
      score: 0.86,
      statement: "Root volume exhaustion (spool files and unrotated logs) caused the retry loop and CPU saturation, making the guest OS unresponsive to reachability probes.",
      confidence: "high",
      supportingObservations: [0, 1, 2, 3],
    },
    {
      title: "Log rotation undersized for current traffic",
      score: 0.62,
      statement: "Log rotation failed once the disk filled, accelerating the problem; it may have been undersized for current traffic before today.",
      confidence: "medium",
      supportingObservations: [1, 3],
    },
  ],
  recommendations: [
    { title: "Free disk space on the root volume", detail: "Connect via Session Manager (if the agent responds) or stop/start after detaching, then clear /var/spool/api/*.tmp and rotated logs.", priority: "now" },
    { title: "Cap the worker retry loop", detail: "Add backoff and a dead-letter path for jobs failing with ENOSPC so a full disk cannot pin CPU.", priority: "next" },
    { title: "Right-size and alarm on disk usage", detail: "Consider increasing the 30 GiB root volume and add a disk_used_percent > 80% alarm for the api-worker group.", priority: "later" },
  ],
  confidence: "high",
  limitations: [
    "Memory metrics are not published by this instance's CloudWatch agent configuration, so memory pressure could not be assessed.",
    "Log query returned 50 of 214 matching events; earlier events were not reviewed.",
    "CloudSage is read-only and did not inspect the filesystem directly.",
  ],
  modelId: "configured-bedrock-model",
  generatedAt: iso(16),
};

function eventsFor(inv: Investigation, tools: ToolExecution[], done: boolean): InvestigationEvent[] {
  const base = new Date(inv.createdAt).getTime();
  const evts: Omit<InvestigationEvent, "id" | "seq" | "investigationId">[] = [
    { type: "queued", message: "Investigation queued.", createdAt: new Date(base).toISOString() },
    { type: "planning", message: `Interpreting request; scope ${inv.accountId} / ${inv.region}.`, createdAt: new Date(base + 1500).toISOString() },
    {
      type: "plan",
      message:
        inv.identificationMode === "explicit"
          ? `Resource identifier supplied (${inv.resources[0]?.identifier}). Plan: describe resource, check health, pull metrics and logs.`
          : "No identifier supplied. Plan: discover resources in scope, filter by health, then drill into affected resources.",
      createdAt: new Date(base + 3200).toISOString(),
    },
  ];
  tools.forEach((t, i) => {
    const s = new Date(t.startedAt).getTime();
    evts.push({ type: "tool_started", message: `Running ${t.toolName}`, createdAt: new Date(s).toISOString(), toolExecutionId: t.id });
    if (t.status !== "running")
      evts.push({
        type: t.status === "succeeded" ? "tool_completed" : "tool_failed",
        message: `${t.toolName} ${t.status === "succeeded" ? "completed" : "failed"} in ${t.durationMs} ms`,
        createdAt: new Date(s + t.durationMs).toISOString(),
        toolExecutionId: t.id,
      });
    void i;
  });
  if (done) {
    evts.push({ type: "analyzing", message: "Correlating evidence and drafting report.", createdAt: new Date(base + 100_000).toISOString() });
    evts.push({ type: "report_ready", message: "Report generated.", createdAt: inv.completedAt ?? new Date(base + 120_000).toISOString() });
  }
  return evts.map((e, i) => ({ ...e, id: `${inv.id}-ev-${i + 1}`, seq: i + 1, investigationId: inv.id }));
}

function genericDetail(inv: Investigation): InvestigationDetail {
  if (inv.status === "failed") {
    return {
      investigation: inv,
      toolExecutions: [],
      report: null,
      events: [
        ...eventsFor(inv, [], false),
        {
          id: `${inv.id}-ev-fail`,
          seq: 4,
          investigationId: inv.id,
          type: "failed",
          message: "Could not obtain temporary credentials: sts:AssumeRole was denied for this connection. Validate the connection's trust policy.",
          createdAt: inv.completedAt ?? inv.createdAt,
        },
      ],
    };
  }
  const svc = inv.resources[0]?.service ?? "ec2";
  const start = new Date(inv.createdAt).getTime();
  const tools: ToolExecution[] = Array.from({ length: inv.toolCallCount }, (_, i) => ({
    id: `${inv.id}-te-${i + 1}`,
    investigationId: inv.id,
    toolName: i === 0 ? `${svc}_describe` : i % 2 ? "cloudwatch_get_metric_data" : "cloudwatch_query_logs",
    service: i === 0 ? svc : "cloudwatch",
    input: { identifier: inv.resources[0]?.identifier, region: inv.region },
    output: { note: "Mock evidence payload" },
    status: inv.status === "running" && i === inv.toolCallCount - 1 ? "running" : "succeeded",
    durationMs: 300 + i * 170,
    startedAt: new Date(start + 5000 + i * 2500).toISOString(),
  }));
  const done = inv.status === "completed";
  return {
    investigation: inv,
    toolExecutions: tools,
    events: eventsFor(inv, tools, done),
    report: done
      ? {
          investigationId: inv.id,
          summary: `Investigation of ${inv.resources.map((r) => r.name ?? r.identifier).join(", ")} completed. See observations for the evidence retrieved.`,
          observations: tools.map((t) => ({ statement: `${t.toolName} returned data for ${inv.resources[0]?.identifier}.`, evidenceIds: [t.id] })),
          metrics: [
            series("Errors (Sum)", "count", tools[1]?.id ?? "", (i) => (i > 50 ? 40 + jitter(i, 10) : 2 + Math.abs(jitter(i, 1.5))), { endMinsAgo: 140 }),
          ],
          logExcerpts: [],
          hypotheses: [{ title: "Recent configuration change", score: 0.64, statement: "A configuration change near the start of the error spike is the most likely trigger.", confidence: "medium", supportingObservations: [0] }],
          recommendations: [{ title: "Review recent deployments", detail: "Compare the current configuration with the previous version.", priority: "now" }],
          confidence: "medium",
          limitations: ["Mock report generated for local development."],
          modelId: "configured-bedrock-model",
          generatedAt: inv.completedAt ?? inv.createdAt,
        }
      : null,
  };
}

export function mockDetail(id: string): InvestigationDetail | null {
  const inv = mockInvestigations.find((i) => i.id === id);
  if (!inv) return null;
  if (inv.id === "inv-1042") {
    return { investigation: inv, toolExecutions: ec2Tools, events: eventsFor(inv, ec2Tools, true), report: ec2Report };
  }
  return genericDetail(inv);
}

export const mockDashboard: DashboardSummary = {
  investigationsLast7d: 38,
  openIssues: 4,
  avgTimeToReportSec: 94,
  resourcesMonitored: { ec2: 46, ecs: 12, rds: 7, lambda: 31, cloudwatch: 0 },
  healthByService: [
    { service: "ec2", healthy: 43, degraded: 2, unhealthy: 1 },
    { service: "ecs", healthy: 10, degraded: 2, unhealthy: 0 },
    { service: "rds", healthy: 6, degraded: 1, unhealthy: 0 },
    { service: "lambda", healthy: 29, degraded: 2, unhealthy: 0 },
  ],
  dailyInvestigations: [
    { day: "Nov 17", count: 3 },
    { day: "Nov 18", count: 6 },
    { day: "Nov 19", count: 4 },
    { day: "Nov 20", count: 8 },
    { day: "Nov 21", count: 5 },
    { day: "Nov 22", count: 2 },
    { day: "Nov 23", count: 10 },
  ],
  healthTimeline: Array.from({ length: 13 }, (_, i) => ({
    t: iso(18 + (12 - i) * 5),
    healthy: Math.round(88 - Math.sin(i / 2) * 2 - (i > 8 ? 1 : 0)),
    unhealthy: Math.round(2 + (i > 6 ? 2 : 0) + Math.abs(Math.cos(i / 3))),
  })),
};

export const mockResources: DiscoveredResource[] = [
  { service: "ec2", resourceType: "instance", identifier: "i-0a1b2c3d4e5f67890", name: "api-worker-3", region: "us-east-1", health: "unhealthy", observedAt: iso(16) },
  { service: "ec2", resourceType: "instance", identifier: "i-0fedcba9876543210", name: "batch-runner-1", region: "us-east-1", health: "degraded", observedAt: iso(24) },
  { service: "ec2", resourceType: "instance", identifier: "i-0123456789abcdef0", name: "api-worker-1", region: "us-east-1", health: "healthy", observedAt: iso(22) },
  { service: "ec2", resourceType: "instance", identifier: "i-0abcdef1234567890", name: "api-worker-2", region: "us-east-1", health: "healthy", observedAt: iso(22) },
  { service: "ec2", resourceType: "instance", identifier: "i-09a8b7c6d5e4f3210", name: "bastion", region: "us-west-2", health: "healthy", observedAt: iso(40) },
  { service: "ecs", resourceType: "service", identifier: "arn:aws:ecs:us-east-1:111122223333:service/prod-core/payments-api", name: "payments-api", region: "us-east-1", health: "degraded", observedAt: iso(2) },
  { service: "ecs", resourceType: "service", identifier: "arn:aws:ecs:us-east-1:111122223333:service/prod-core/checkout", name: "checkout", region: "us-east-1", health: "healthy", observedAt: iso(12) },
  { service: "ecs", resourceType: "service", identifier: "arn:aws:ecs:eu-west-1:111122223333:service/prod-eu/auth-service", name: "auth-service", region: "eu-west-1", health: "healthy", observedAt: iso(30) },
  { service: "rds", resourceType: "db-instance", identifier: "orders-db", name: "orders-db", region: "us-east-1", health: "healthy", observedAt: iso(35) },
  { service: "rds", resourceType: "db-instance", identifier: "reporting-replica", name: "reporting-replica", region: "us-east-1", health: "degraded", observedAt: iso(50) },
  { service: "lambda", resourceType: "function", identifier: "order-processor", name: "order-processor", region: "us-west-2", health: "degraded", observedAt: iso(137) },
  { service: "lambda", resourceType: "function", identifier: "invoice-renderer", name: "invoice-renderer", region: "us-east-1", health: "healthy", observedAt: iso(60) },
  { service: "lambda", resourceType: "function", identifier: "audit-event-archiver", name: "audit-event-archiver", region: "us-east-1", health: "healthy", observedAt: iso(75) },
];

export const mockSettings: UserSettings = {
  displayName: "Cloud Engineer",
  email: "engineer@example.com",
  defaultTimeRangeHours: 6,
  defaultConnectionId: "conn-prod",
  showRawEvidenceByDefault: false,
  maxToolCalls: 25,
  investigationTimeoutSec: 300,
  defaultRegion: "us-east-1",
  investigationDepth: "balanced",
  autoOpenReport: false,
  includeLogs: true,
  includeDeployments: true,
  notifyOnFailed: true,
  notifyOnCompleted: false,
  weeklyDigest: true,
};
