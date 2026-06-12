import { useEffect } from "react";
import { addPipelineEventListener, PipelineEvent } from "../services/websocket";

export function usePipelineSubscription(onEvent: (event: PipelineEvent) => void) {
  useEffect(() => {
    const unsubscribe = addPipelineEventListener(onEvent);
    return unsubscribe;
  }, [onEvent]);
}
