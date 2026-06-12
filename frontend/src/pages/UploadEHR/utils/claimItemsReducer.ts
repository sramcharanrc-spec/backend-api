import type { ClaimItemsAction } from "./claimTypes";
import { getClaimId } from "./claimGetters";
import { hydrateClaim } from "./claimHydration";
import { mergeClaimLists } from "./claimMerge";

export const claimItemsReducer = (state: any[], action: ClaimItemsAction): any[] => {
  switch (action.type) {
    case "SET_ITEMS":
      return action.payload.map((item) => hydrateClaim(item));

    case "MERGE_ITEMS":
      return mergeClaimLists(state, action.payload);

    case "REMOVE_CLAIM":
      return state.filter((item) => getClaimId(item) !== action.claimId);

    case "RESET_CLAIMS":
      return [];

    case "WS_CLAIM_UPDATE":
    case "PIPELINE_UPDATE":
    case "CLAIM_COMPLETED":
      return mergeClaimLists(state, [action.payload]);

    default:
      return state;
  }
};

export default claimItemsReducer;