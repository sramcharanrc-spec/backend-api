import { API_URL } from "../../../config";
import { fetchClaimWithFallback } from "./claimApi";
import type { ProcessingMode } from "../utils/claimTypes";

const toPipelinePayload = (data: any = {}) => {
  const pipeline =
    data?.pipeline ||
    data?.payload?.pipeline ||
    data?.claim?.pipeline ||
    data?.payload?.claim?.pipeline;

  if (pipeline) return pipeline;

  return {
    current_stage: data?.current_stage || data?.stage,
    current_agent: data?.current_agent || data?.agent,
    active_step: data?.active_step || data?.current_step,
    pipeline_state: data?.pipeline_state,
    pipeline_status: data?.pipeline_status || data?.status,
    progress: data?.progress,
    steps: data?.pipeline_steps,
  };
};

export async function fetchClaimPipeline(claimId: string) {
  const data = await fetchClaimWithFallback(claimId);

  return toPipelinePayload(data || {});
}

export async function retryClaimValidation(claimId: string) {
  const response = await fetch(`${API_URL}/api/claims/${claimId}/retry-validation`, {
    method: "POST",
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(data?.detail || data?.message || "Retry validation failed");
  }

  return data;
}

export async function approveClearinghouseClaim(claimId: string) {
  const response = await fetch(`${API_URL}/api/claims/${claimId}/approve`, {
    method: "POST",
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(data?.detail || data?.message || "Claim approval failed");
  }

  return data;
}

export async function rejectClaim(claimId: string, reason = "Rejected from Claim Workspace") {
  const response = await fetch(`${API_URL}/api/claims/${claimId}/reject`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ reason }),
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(data?.detail || data?.message || "Claim rejection failed");
  }

  return data;
}

export async function updateClearinghouseMode(
  claimId: string,
  mode: ProcessingMode
) {
  const response = await fetch(`${API_URL}/api/claims/${claimId}/clearinghouse-mode`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      processing_mode: mode,
      mode,
    }),
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(data?.detail || data?.message || "Processing mode update failed");
  }

  return data;
}

export async function runClearinghouseAutoReview(claimId: string) {
  const response = await fetch(`${API_URL}/api/claims/${claimId}/clearinghouse-auto-review`, {
    method: "POST",
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(data?.detail || data?.message || "Auto review failed");
  }

  return data;
}

export async function resumeClaimPipeline(claimId: string) {
  const response = await fetch(`${API_URL}/api/claims/${claimId}/approve`, {
    method: "POST",
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(data?.detail || data?.message || "Resume pipeline failed");
  }

  return data;
}
