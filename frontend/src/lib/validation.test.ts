import { looksLikeAccessKey, validateConnection, type ConnectionDraft } from "./validation";

const ok: ConnectionDraft = {
  name: "Prod",
  accountId: "123456789012",
  roleArn: "arn:aws:iam::123456789012:role/CloudSageReadOnly",
  externalId: "",
  defaultRegion: "us-east-1",
  allowedRegions: ["us-east-1"],
};

describe("validateConnection", () => {
  it("accepts a valid draft", () => {
    expect(validateConnection(ok)).toEqual({});
  });
  it("requires a 12-digit account id", () => {
    expect(validateConnection({ ...ok, accountId: "1234" }).accountId).toBeDefined();
  });
  it("rejects a role from a different account", () => {
    expect(validateConnection({ ...ok, roleArn: "arn:aws:iam::999999999999:role/X" }).roleArn).toMatch(/belong/);
  });
  it("rejects non-role ARNs", () => {
    expect(validateConnection({ ...ok, roleArn: "arn:aws:iam::123456789012:user/bob" }).roleArn).toBeDefined();
  });
  it("requires default region within allowed regions", () => {
    expect(validateConnection({ ...ok, defaultRegion: "eu-west-1" }).defaultRegion).toBeDefined();
    expect(validateConnection({ ...ok, allowedRegions: [] }).allowedRegions).toBeDefined();
  });
});

describe("looksLikeAccessKey", () => {
  it("detects long-lived and temporary key ids", () => {
    expect(looksLikeAccessKey("AKIAABCDEFGHIJKLMNOP")).toBe(true);
    expect(looksLikeAccessKey("ASIAABCDEFGHIJKLMNOP")).toBe(true);
    expect(looksLikeAccessKey("arn:aws:iam::123456789012:role/X")).toBe(false);
  });
});
