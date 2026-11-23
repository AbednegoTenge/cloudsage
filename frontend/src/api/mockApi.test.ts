import { createMockApi } from "./mockApi";
import type { InvestigationEvent } from "../types/domain";

describe("mock API", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  async function flush<T>(p: Promise<T>): Promise<T> {
    await vi.advanceTimersByTimeAsync(1000);
    return p;
  }

  it("detects an explicit EC2 instance id", async () => {
    const api = createMockApi();
    const inv = await flush(api.createInvestigation({ prompt: "Why is i-0123456789abcdef0 unhealthy?", connectionId: "conn-prod", region: "us-east-1", timeRangeHours: 6 }));
    expect(inv.identificationMode).toBe("explicit");
    expect(inv.resources[0]).toMatchObject({ service: "ec2", identifier: "i-0123456789abcdef0" });
  });

  it("falls back to discovery when no identifier is given", async () => {
    const api = createMockApi();
    const inv = await flush(api.createInvestigation({ prompt: "Find unhealthy EC2 instances", connectionId: "conn-prod", region: "us-east-1", timeRangeHours: 6 }));
    expect(inv.identificationMode).toBe("discovered");
    expect(inv.resources).toHaveLength(0);
  });

  it("enforces the connection's region boundary", async () => {
    const api = createMockApi();
    const p = api.createInvestigation({ prompt: "x", connectionId: "conn-staging", region: "us-east-1", timeRangeHours: 6 });
    await expect(p).rejects.toThrow(/not allowed/);
  });

  it("streams progress events through to a report", async () => {
    const api = createMockApi();
    const inv = await flush(api.createInvestigation({ prompt: "Find unhealthy EC2 instances", connectionId: "conn-prod", region: "us-east-1", timeRangeHours: 6 }));
    const events: InvestigationEvent[] = [];
    const stop = api.streamInvestigationEvents(inv.id, (e) => events.push(e));
    await vi.advanceTimersByTimeAsync(15_000);
    stop();
    const types = events.map((e) => e.type);
    expect(types[0]).toBe("queued");
    expect(types).toContain("plan");
    expect(types.filter((t) => t === "tool_completed")).toHaveLength(3);
    expect(types.at(-1)).toBe("report_ready");
    const detail = await flush(api.getInvestigation(inv.id));
    expect(detail.investigation.status).toBe("completed");
    expect(detail.report).not.toBeNull();
  });
});
