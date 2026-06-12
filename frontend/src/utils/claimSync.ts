export type ClaimLike = Record<string, any>;

export const normalizeClaimsResponse = (data: any): ClaimLike[] => {
  const claims =
    Array.isArray(data)
      ? data
      : data?.records ||
        data?.claims ||
        data?.items ||
        (Array.isArray(data?.data) ? data.data : undefined) ||
        data?.data?.records ||
        data?.data?.claims ||
        data?.data?.items ||
        [];

  return Array.isArray(claims) ? claims : [];
};

export const claimIdOf = (claim: any): string =>
  String(
    claim?.claim_id ||
      claim?.claimId ||
      claim?.id ||
      claim?.claim?.claim_id ||
      claim?.payload?.claim_id ||
      claim?.payload?.claim?.claim_id ||
      claim?.data?.claim_id ||
      claim?.data?.claim?.claim_id ||
      claim?.details?.claim_id ||
      claim?.details?.claim?.claim_id ||
      ""
  ).trim();

export const claimTimestampOf = (claim: any): number => {
  if (!claim) return -1;

  const value =
    claim.last_activity_at ||
    claim.lastActivityAt ||
    claim.updatedAt ||
    claim.updated_at ||
    claim.payload?.last_activity_at ||
    claim.payload?.updated_at ||
    claim.claim?.updated_at ||
    claim.details?.timestamp ||
    claim.timestamp ||
    claim.created_at ||
    claim.createdAt;

  if (!value) return -1;

  const timestamp = new Date(value).getTime();
  return Number.isNaN(timestamp) ? -1 : timestamp;
};

const FINAL_STATUSES = new Set(["ACCEPTED", "APPROVED", "PAID", "COMPLETED", "FINALIZED", "CLOSED"]);

const isFinalClaim = (claim: any): boolean => {
  const status = String(claim?.status || claim?.claim?.status || claim?.payload?.claim?.status || "").toUpperCase();
  return FINAL_STATUSES.has(status) || claim?.pipeline_completed === true || claim?.command_center === true;
};

export const reconcileClaim = (existing: ClaimLike = {}, incoming: ClaimLike = {}): ClaimLike => {
  const existingTs = claimTimestampOf(existing);
  const incomingTs = claimTimestampOf(incoming);
  const claimId = claimIdOf(incoming) || claimIdOf(existing);

  if (isFinalClaim(existing) && !isFinalClaim(incoming) && incomingTs <= existingTs) {
    return {
      ...incoming,
      ...existing,
      claim_id: claimId,
    };
  }

  if (existingTs > incomingTs && incomingTs !== -1) {
    return {
      ...incoming,
      ...existing,
      claim_id: claimId,
    };
  }

  if (existingTs > -1 && incomingTs === -1) {
    return {
      ...incoming,
      ...existing,
      claim_id: claimId,
    };
  }

  return {
    ...existing,
    ...incoming,
    claim_id: claimId,
  };
};

export const mergeClaims = (current: ClaimLike[] = [], incoming: ClaimLike[] = []): ClaimLike[] => {
  if (current.length > 0 && (!incoming || incoming.length === 0)) {
    console.log("[sync] preserving existing claims");
    return current;
  }

  const map = new Map<string, ClaimLike>();

  current.forEach((claim) => {
    const claimId = claimIdOf(claim);
    if (claimId) map.set(claimId, claim);
  });

  incoming.forEach((claim) => {
    const claimId = claimIdOf(claim);
    if (!claimId) {
      console.warn("[merge] missing claim_id", claim);
      return;
    }

    const existing = map.get(claimId) || {};
    map.set(claimId, existing ? reconcileClaim(existing, claim) : { ...claim, claim_id: claimId });
  });

  return Array.from(map.values()).sort((a, b) => claimTimestampOf(b) - claimTimestampOf(a));
};

export const displayText = (value: any, fallback = "-"): string => {
  if (value === undefined || value === null || value === "") return fallback;
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map((item) => displayText(item, "")).filter(Boolean).join(", ") || fallback;
  if (typeof value === "object") {
    const candidate =
      value.name ||
      value.full_name ||
      value.patient_name ||
      value.payer_name ||
      value.label ||
      value.value;
    return candidate && typeof candidate === "object" ? displayText(candidate, fallback) : candidate ? String(candidate) : fallback;
  }
  return fallback;
};
