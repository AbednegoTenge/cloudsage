import { formatDuration, relativeTime, timeRangeLabel } from "./format";

describe("format helpers", () => {
  const now = new Date("2026-11-23T10:00:00Z").getTime();
  it("relativeTime", () => {
    expect(relativeTime("2026-11-23T09:59:30Z", now)).toBe("30s ago");
    expect(relativeTime("2026-11-23T09:15:00Z", now)).toBe("45m ago");
    expect(relativeTime("2026-11-23T05:00:00Z", now)).toBe("5h ago");
    expect(relativeTime("2026-11-20T10:00:00Z", now)).toBe("3d ago");
  });
  it("formatDuration", () => {
    expect(formatDuration(412)).toBe("412 ms");
    expect(formatDuration(2140)).toBe("2.1 s");
    expect(formatDuration(94_000)).toBe("1m 34s");
  });
  it("timeRangeLabel", () => {
    expect(timeRangeLabel("2026-11-23T04:00:00Z", "2026-11-23T10:00:00Z")).toBe("6 h");
    expect(timeRangeLabel("2026-11-16T10:00:00Z", "2026-11-23T10:00:00Z")).toBe("7 days");
  });
});
