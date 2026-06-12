import { getClaimId, getCreatedAt, getLastActivityAt, getUploadMode, getUploadSource } from "./claimGetters";
import { getWorkspaceStatus, getWorkspaceStatusRaw } from "./claimStatus";

const isPlainObject = (value: any) =>
  Boolean(value && typeof value === "object" && !Array.isArray(value));

export const mergeObjects = (fallback: any = {}, incoming: any = {}): any => {
  if (!isPlainObject(fallback) || !isPlainObject(incoming)) {
    return incoming ?? fallback;
  }

  const merged: Record<string, any> = { ...fallback };

  Object.entries(incoming).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") {
      return;
    }

    if (isPlainObject(value) && isPlainObject(merged[key])) {
      merged[key] = mergeObjects(merged[key], value);
      return;
    }

    merged[key] = value;
  });

  return merged;
};

const mergePipeline = (...pipelines: any[]) => {
  const merged = pipelines.reduce((current, next) => mergeObjects(current, next), {});

  return {
    ...merged,
    steps: pipelines.reduce((current, next) => mergeObjects(current, next?.steps), {}),
    stage_status: pipelines.reduce((current, next) => mergeObjects(current, next?.stage_status), {}),
    agents: pipelines.reduce((current, next) => mergeObjects(current, next?.agents), {}),
  };
};

const mergeCase = (...cases: any[]) =>
  cases.reduce((current, next) => mergeObjects(current, next), {});

const hasKeys = (value: any) =>
  isPlainObject(value) && Object.keys(value).length > 0;

export const canonicalizeClaimWorkflow = (item: any) => {
  const status = getWorkspaceStatus(item);

  return {
    ...item,
    status,
    pipeline_state: item?.pipeline_state || status,
  };
};

export const hydrateClaim = (item: any, fallback: any = {}) => {
  const claimId = getClaimId(item) || getClaimId(fallback);
  const status = getWorkspaceStatusRaw(item)
    ? getWorkspaceStatus(item)
    : getWorkspaceStatus(fallback);
  const merged = mergeObjects(fallback, item);
  const pipeline = mergePipeline(
    fallback?.pipeline,
    fallback?.payload?.pipeline,
    fallback?.claim?.pipeline,
    fallback?.payload?.claim?.pipeline,
    item?.pipeline,
    item?.payload?.pipeline,
    item?.claim?.pipeline,
    item?.payload?.claim?.pipeline,
    merged?.pipeline
  );
  const caseRecord = mergeCase(
    fallback?.case,
    fallback?.hitl_case,
    fallback?.claim?.case,
    fallback?.claim?.hitl_case,
    item?.case,
    item?.hitl_case,
    item?.hitlCase,
    item?.claim?.case,
    item?.claim?.hitl_case
  );

  return canonicalizeClaimWorkflow({
    ...merged,
    claim_id: claimId,
    status,
    ...(hasKeys(pipeline) ? { pipeline } : {}),
    ...(hasKeys(caseRecord)
      ? {
          case: caseRecord,
          hitl_case: caseRecord,
          case_id: caseRecord.case_id || merged?.case_id,
        }
      : {}),
    upload_mode: item?.upload_mode || item?.uploadMode || fallback?.upload_mode || getUploadMode(item),
    upload_source: item?.upload_source || item?.uploadSource || fallback?.upload_source || getUploadSource(item),
    created_at: getCreatedAt(item) || getCreatedAt(fallback),
    uploaded_at: item?.uploaded_at || fallback?.uploaded_at || getCreatedAt(item),
    last_activity_at: getLastActivityAt(item) || getLastActivityAt(fallback),
    updatedAt:
      item?.updatedAt ||
      item?.updated_at ||
      fallback?.updatedAt ||
      fallback?.updated_at ||
      item?.timestamp ||
      fallback?.timestamp ||
      getLastActivityAt(item) ||
      getLastActivityAt(fallback) ||
      new Date().toISOString(),
  });
};

export const claimStateToWorkspaceItem = (state: any) =>
  hydrateClaim(state);

export const hydrateCompletedClaim = (item: any) =>
  hydrateClaim({
    ...item,
    command_center: true,
    pipeline_completed: true,
  });
