import { timestampOf } from "./claimDates";
import { getClaimId } from "./claimGetters";
import { hydrateClaim } from "./claimHydration";
import { mergeClaimLiveUpdate } from "./pipelineLiveMerge";

export const samePayload = (a: any, b: any) => {
  try {
    return JSON.stringify(a) === JSON.stringify(b);
  } catch {
    return false;
  }
};

export const getItemsSignature = (items: any[]) =>
  items
    .map((item) =>
      JSON.stringify({
        id: getClaimId(item),
        status: item?.status,
        progress: syncProgressOf(item),
        current_stage: item?.current_stage || item?.stage,
        current_agent: item?.current_agent || item?.agent,
        pipeline_state: item?.pipeline_state,
        pipeline_status: item?.pipeline_status,
        steps: item?.pipeline?.steps,
        case_status: item?.case?.status || item?.hitl_case?.status,
        assigned_role: item?.case?.assigned_role || item?.hitl_case?.assigned_role,
        updated_at: item?.updatedAt || item?.updated_at || item?.last_activity_at,
      })
    )
    .join("|");

export const syncProgressOf = (item: any) =>
  Number(item?.progress ?? item?.pipeline?.progress ?? 0);

export const mergeSyncedClaimState = (current: any, incoming: any) =>
  hydrateClaim(mergeClaimLiveUpdate(current || {}, incoming || {}), current || {});

export const reconcileClaimState = mergeSyncedClaimState;

export const mergeClaimLists = (current: any[] = [], incoming: any[] = []) => {
  const map = new Map<string, any>();

  current.forEach((item) => {
    const id = getClaimId(item);
    if (id) map.set(id, hydrateClaim(item));
  });

  incoming.forEach((item) => {
    const id = getClaimId(item);
    if (!id) return;

    const existing = map.get(id);
    map.set(id, mergeSyncedClaimState(existing || {}, item));
  });

  return Array.from(map.values()).sort((a, b) => timestampOf(b) - timestampOf(a));
};
