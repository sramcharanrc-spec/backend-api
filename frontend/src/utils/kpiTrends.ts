type ClaimLike = Record<string, any>;

const createdAtOf = (claim: ClaimLike) =>
  claim?.created_at ||
  claim?.claim?.created_at ||
  claim?.payload?.claim?.created_at ||
  claim?.payload?.created_at ||
  claim?.createdAt ||
  "";

const hasCreatedAtInRange = (claim: ClaimLike, start: Date, end?: Date) => {
  const createdAt = createdAtOf(claim);
  if (!createdAt) return false;

  const date = new Date(createdAt);
  if (Number.isNaN(date.getTime())) return false;

  return date >= start && (!end || date < end);
};

export const getClaimTrendPeriods = <T extends ClaimLike>(data: T[]) => {
  const safeData = Array.isArray(data) ? data : [];
  const now = new Date();
  const last7Days = new Date(now.getTime() - (7 * 24 * 60 * 60 * 1000));
  const last14Days = new Date(now.getTime() - (14 * 24 * 60 * 60 * 1000));

  const currentWeekClaims = safeData.filter((claim) => hasCreatedAtInRange(claim, last7Days));
  const previousWeekClaims = safeData.filter((claim) => hasCreatedAtInRange(claim, last14Days, last7Days));

  return {
    safeData,
    currentWeekClaims,
    previousWeekClaims,
  };
};

export const calculateTrend = (current: number, previous: number) => {
  if (previous === 0) return null;

  return Number((((current - previous) / previous) * 100).toFixed(1));
};
