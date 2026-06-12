import { addPipelineEventListener } from "./websocket";

export const connectAnalyticsWS = (onMessage: (data: any) => void) => {
  const unsubscribe = addPipelineEventListener((msg) => {
    if (msg.type === "analytics_update") onMessage(msg.data);
    if (msg.step === "analytics" || msg.stage === "analytics") onMessage(msg.data || msg);
  });

  return { close: unsubscribe };
};
