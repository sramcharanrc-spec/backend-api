const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export type AgentStatus =
  | "PENDING"
  | "RUNNING"
  | "COMPLETED"
  | "FAILED"
  | "WARNING"
  | string;

export type AgentDetail = {
  key: string;
  agent: string;
  stage: string;
  status: AgentStatus;
  active_step?: string;
  message?: string;
  started_at?: string | null;
  completed_at?: string | null;
  duration_seconds?: number | null;
  progress?: number | null;
  passed?: boolean;
  score?: number | null;
  risk_score?: number | null;
  risk_score_percent?: number | null;
  errors?: unknown[];
  warnings?: unknown[];
  output?: Record<string, unknown>;
  next_agent?: string | null;
};

export type AgentStatusResponse = {
  claim_id: string;
  status?: string;
  pipeline_state?: string;
  pipeline_status?: string;
  current_stage?: string;
  current_agent?: string;
  active_step?: string;
  progress?: number;
  completed_agents?: number;
  total_agents?: number;
  agents: AgentDetail[];
  legacy_statuses?: Record<string, string>;
  updated_at?: string;
};

export async function fetchAgentStatus(
  claimId: string
): Promise<AgentStatusResponse> {
  if (!claimId) {
    throw new Error("claimId is required");
  }

  const res = await fetch(
    `${API_URL}/api/rcm/agents/status/${encodeURIComponent(claimId)}`
  );

  if (!res.ok) {
    const errorText = await res.text().catch(() => "");
    throw new Error(
      `Failed to fetch agent status: ${res.status} ${res.statusText} ${errorText}`
    );
  }

  return res.json();
}