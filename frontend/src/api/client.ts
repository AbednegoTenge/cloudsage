// Typed API client. Pages depend only on the `CloudSageApi` interface; the implementation is
// chosen by VITE_USE_MOCKS: the in-memory mock adapter, or the HTTP adapter for /api/v1.
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

/** Page envelope returned by list endpoints. */
interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

/** Turns FastAPI error bodies ({detail: string} or validation {detail: [{msg}]}) into text. */
async function errorMessage(res: Response): Promise<string> {
  const text = await res.text();
  try {
    const { detail } = JSON.parse(text) as { detail?: unknown };
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d) => (d && typeof d === "object" && "msg" in d ? String(d.msg) : String(d)))
        .join("; ");
    }
  } catch {
    // not JSON; fall through
  }
  return text || res.statusText;
}

export function createHttpApi(baseUrl: string): CloudSageApi {
  async function req<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await fetch(`${baseUrl}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      credentials: "include",
    });
    if (!res.ok) throw new ApiError(await errorMessage(res), res.status);
    return (res.status === 204 ? undefined : await res.json()) as T;
  }
  const query = (params: Record<string, string | number | undefined>) => {
    const p = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => v !== undefined && v !== "" && p.set(k, String(v)));
    const s = p.toString();
    return s ? `?${s}` : "";
  };
  const id = encodeURIComponent;
  return {
    getDashboard: () => req("/dashboard"),
    listInvestigations: async (f) => {
      const page = await req<Page<Investigation>>(
        `/investigations${query({ status: f?.status, connectionId: f?.connectionId, search: f?.search, limit: 100 })}`,
      );
      return page.items;
    },
    getInvestigation: (invId) => req(`/investigations/${id(invId)}`),
    createInvestigation: (body) => req("/investigations", { method: "POST", body: JSON.stringify(body) }),
    streamInvestigationEvents(invId, onEvent) {
      // The browser resends Last-Event-ID on reconnect, so the server resumes where it left off.
      const es = new EventSource(`${baseUrl}/investigations/${id(invId)}/stream`, { withCredentials: true });
      es.addEventListener("investigation", (m) => onEvent(JSON.parse((m as MessageEvent).data) as InvestigationEvent));
      es.addEventListener("end", () => es.close());
      return () => es.close();
    },
    listResources: (f) => req(`/resources${query({ connectionId: f?.connectionId, service: f?.service })}`),
    listConnections: () => req("/connections"),
    createConnection: (body) => req("/connections", { method: "POST", body: JSON.stringify(body) }),
    validateConnection: (connId) => req(`/connections/${id(connId)}/validate`, { method: "POST" }),
    deleteConnection: (connId) => req(`/connections/${id(connId)}`, { method: "DELETE" }),
    getSettings: () => req("/settings"),
    updateSettings: (body) => req("/settings", { method: "PUT", body: JSON.stringify(body) }),
  };
}

/** True when the UI runs on the in-memory mock adapter instead of the backend. */
export const usingMockApi = (import.meta.env.VITE_USE_MOCKS ?? "true") !== "false";

export const api: CloudSageApi = usingMockApi
  ? createMockApi()
  : createHttpApi(import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1");
