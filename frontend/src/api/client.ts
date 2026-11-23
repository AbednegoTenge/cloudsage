// Typed API client. Pages depend only on the `CloudSageApi` interface; the implementation is
// chosen by VITE_USE_MOCKS. Phase 2 fills in the HTTP implementation against /api/v1.
import type {
  AwsConnection,
  CreateInvestigationRequest,
  DashboardSummary,
  DiscoveredResource,
  Investigation,
  InvestigationDetail,
  InvestigationEvent,
  UserSettings,
} from "../types/domain";
import { createMockApi } from "./mockApi";

export interface InvestigationFilters {
  status?: Investigation["status"];
  connectionId?: string;
  search?: string;
}

export type Unsubscribe = () => void;

export interface CloudSageApi {
  getDashboard(): Promise<DashboardSummary>;
  listInvestigations(filters?: InvestigationFilters): Promise<Investigation[]>;
  getInvestigation(id: string): Promise<InvestigationDetail>;
  createInvestigation(req: CreateInvestigationRequest): Promise<Investigation>;
  /** Live progress (SSE in the real API). Replays past events, then streams new ones. */
  streamInvestigationEvents(id: string, onEvent: (e: InvestigationEvent) => void): Unsubscribe;
  /** Resource discovery within the selected account and region(s). */
  listResources(filter?: { connectionId?: string; service?: string }): Promise<DiscoveredResource[]>;
  listConnections(): Promise<AwsConnection[]>;
  createConnection(input: Omit<AwsConnection, "id" | "status" | "lastValidatedAt">): Promise<AwsConnection>;
  validateConnection(id: string): Promise<AwsConnection>;
  deleteConnection(id: string): Promise<void>;
  getSettings(): Promise<UserSettings>;
  updateSettings(s: UserSettings): Promise<UserSettings>;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

function createHttpApi(baseUrl: string): CloudSageApi {
  async function req<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await fetch(`${baseUrl}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      credentials: "include",
    });
    if (!res.ok) throw new ApiError((await res.text()) || res.statusText, res.status);
    return (res.status === 204 ? undefined : await res.json()) as T;
  }
  const qs = (f?: InvestigationFilters) => {
    const p = new URLSearchParams();
    Object.entries(f ?? {}).forEach(([k, v]) => v && p.set(k, String(v)));
    const s = p.toString();
    return s ? `?${s}` : "";
  };
  return {
    getDashboard: () => req("/dashboard"),
    listInvestigations: (f) => req(`/investigations${qs(f)}`),
    getInvestigation: (id) => req(`/investigations/${encodeURIComponent(id)}`),
    createInvestigation: (body) => req("/investigations", { method: "POST", body: JSON.stringify(body) }),
    streamInvestigationEvents(id, onEvent) {
      const es = new EventSource(`${baseUrl}/investigations/${encodeURIComponent(id)}/stream`, { withCredentials: true });
      es.onmessage = (m) => onEvent(JSON.parse(m.data) as InvestigationEvent);
      return () => es.close();
    },
    listResources: (f) => {
      const p = new URLSearchParams();
      if (f?.connectionId) p.set("connection_id", f.connectionId);
      if (f?.service) p.set("service", f.service);
      return req(`/resources${p.toString() ? `?${p}` : ""}`);
    },
    listConnections: () => req("/connections"),
    createConnection: (body) => req("/connections", { method: "POST", body: JSON.stringify(body) }),
    validateConnection: (id) => req(`/connections/${encodeURIComponent(id)}/validate`, { method: "POST" }),
    deleteConnection: (id) => req(`/connections/${encodeURIComponent(id)}`, { method: "DELETE" }),
    getSettings: () => req("/settings"),
    updateSettings: (body) => req("/settings", { method: "PUT", body: JSON.stringify(body) }),
  };
}

const useMocks = (import.meta.env.VITE_USE_MOCKS ?? "true") !== "false";

export const api: CloudSageApi = useMocks
  ? createMockApi()
  : createHttpApi(import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1");
