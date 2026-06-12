export type AgentStatus = "idle" | "running" | "completed";

export interface Agent {
  id: string;
  name: string;
  description: string;
  status: AgentStatus;
  successRate: number;
  lastRun?: string;
}
