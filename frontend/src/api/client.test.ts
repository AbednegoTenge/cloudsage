import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, createHttpApi } from "./client";

const BASE = "http://api.test/api/v1";

function mockFetch(status: number, body: unknown) {
  const fn = vi.fn(async (_url: string, _init?: RequestInit) =>
    new Response(status === 204 ? null : JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

describe("HTTP API client", () => {
  it("unwraps paginated investigations and sends camelCase filters", async () => {
    const fetchFn = mockFetch(200, { items: [{ id: "inv-1001" }], total: 1, limit: 100, offset: 0 });
    const items = await createHttpApi(BASE).listInvestigations({ status: "queued", connectionId: "c1", search: "" });
    expect(items).toEqual([{ id: "inv-1001" }]);
    const url = new URL(fetchFn.mock.calls[0][0]);
    expect(url.pathname).toBe("/api/v1/investigations");
    expect(Object.fromEntries(url.searchParams)).toEqual({ status: "queued", connectionId: "c1", limit: "100" });
  });

  it("uses connectionId for resource discovery", async () => {
    const fetchFn = mockFetch(200, []);
    await createHttpApi(BASE).listResources({ connectionId: "abc", service: "ec2" });
    expect(fetchFn.mock.calls[0][0]).toBe(`${BASE}/resources?connectionId=abc&service=ec2`);
  });

  it("surfaces the server's error detail", async () => {
    mockFetch(403, { detail: "Region eu-west-1 is not allowed for connection 'prod'" });
    const err = await createHttpApi(BASE)
      .createInvestigation({ prompt: "x", connectionId: "c", region: "eu-west-1", timeRangeHours: 1 })
      .catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(403);
    expect(err.message).toContain("not allowed");
  });

  it("joins validation errors", async () => {
    mockFetch(422, { detail: [{ msg: "AWS account IDs are exactly 12 digits" }, { msg: "bad region" }] });
    const err = await createHttpApi(BASE).listConnections().catch((e) => e);
    expect(err.message).toBe("AWS account IDs are exactly 12 digits; bad region");
  });

  it("handles 204 on delete", async () => {
    mockFetch(204, null);
    await expect(createHttpApi(BASE).deleteConnection("c1")).resolves.toBeUndefined();
  });
});
