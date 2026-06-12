import { useMemo } from "react";
import { usePipelineContext } from "../context/PipelineContext";

export function usePipeline(claimId?: string) {
  const context = usePipelineContext();
  const claim = context.getClaimState(claimId);

  const claimEvents = useMemo(() => {
    if (!claimId) return context.events;
    return context.events.filter(
      (event) =>
        event.claim_id === claimId ||
        event.data?.claim_id === claimId ||
        event.data?.claimId === claimId ||
        event.metadata?.claim_id === claimId ||
        event.metadata?.claimId === claimId
    );
  }, [claimId, context.events]);

  return {
    ...context,
    claim,
    claimEvents,
  };
}
