// Client-side validation mirrors the backend rules (the backend remains the authority).

export const AWS_REGIONS = [
  "us-east-1", "us-east-2", "us-west-1", "us-west-2",
  "ca-central-1", "sa-east-1",
  "eu-west-1", "eu-west-2", "eu-west-3", "eu-central-1", "eu-north-1",
  "ap-south-1", "ap-southeast-1", "ap-southeast-2", "ap-northeast-1", "ap-northeast-2",
];

export interface ConnectionDraft {
  name: string;
  accountId: string;
  roleArn: string;
  externalId: string;
  defaultRegion: string;
  allowedRegions: string[];
}

export type ConnectionErrors = Partial<Record<keyof ConnectionDraft, string>>;

const ROLE_ARN = /^arn:aws(-[a-z]+)?:iam::(\d{12}):role\/[\w+=,.@\-/]{1,512}$/;

export function validateConnection(d: ConnectionDraft): ConnectionErrors {
  const e: ConnectionErrors = {};
  if (!d.name.trim()) e.name = "Name is required.";
  else if (d.name.length > 64) e.name = "Use 64 characters or fewer.";
  if (!/^\d{12}$/.test(d.accountId)) e.accountId = "AWS account IDs are exactly 12 digits.";
  const m = ROLE_ARN.exec(d.roleArn.trim());
  if (!m) e.roleArn = "Enter an IAM role ARN, e.g. arn:aws:iam::123456789012:role/CloudSageReadOnly.";
  else if (!e.accountId && m[2] !== d.accountId) e.roleArn = "The role must belong to the account above.";
  if (d.externalId && !/^[\w+=,.@:/-]{2,1224}$/.test(d.externalId)) e.externalId = "External ID contains invalid characters.";
  if (d.allowedRegions.length === 0) e.allowedRegions = "Select at least one region.";
  if (!d.allowedRegions.includes(d.defaultRegion)) e.defaultRegion = "Default region must be one of the allowed regions.";
  return e;
}

/** Looks like a long-lived access key; we refuse these anywhere in the UI. */
export function looksLikeAccessKey(value: string): boolean {
  return /\b(AKIA|ASIA)[0-9A-Z]{16}\b/.test(value);
}
