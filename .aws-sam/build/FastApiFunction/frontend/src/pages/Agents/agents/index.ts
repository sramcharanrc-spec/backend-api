import { ETLAgent } from "./ETL/etl.config";
import { SummarizerAgent } from "./Summarizer/summarizer.config";
import { ClaimAgent } from "./Claim/claim.config";
import { AnalyticsAgent } from "./Analytics/analytics.config";
import { PaymentAgent } from "./Payment/payment.config";

export const agentsList = [ETLAgent, SummarizerAgent, ClaimAgent, AnalyticsAgent, PaymentAgent];
