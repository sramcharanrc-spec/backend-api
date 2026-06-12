import { API_URL } from "../../../config";

export async function fetchCaseByClaimId(claimId: string) {
  const response = await fetch(`${API_URL}/cases/by-claim/${claimId}`);
  const data = await response.json().catch(() => ({}));

  return {
    ok: response.ok,
    status: response.status,
    data,
  };
}

export async function createHitlCase(
  claimId: string,
  payload: Record<string, any>
) {
  const response = await fetch(`${API_URL}/api/claims/${claimId}/hitl-case`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(data?.detail || data?.message || "HITL case creation failed");
  }

  return data;
}

export async function assignHitlCase(
  caseId: string,
  payload: Record<string, any>
) {
  const response = await fetch(`${API_URL}/cases/${caseId}/assign`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(data?.detail || data?.message || "Case routing failed");
  }

  return data;
}

export async function approveCaseByClaimId(
  claimId: string,
  userId = "Claim Workspace"
) {
  const params = new URLSearchParams();
  params.set("user_id", userId);

  const response = await fetch(`${API_URL}/api/case/${claimId}/approve?${params.toString()}`, {
    method: "POST",
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok && !String(data?.detail || "").toLowerCase().includes("already approved")) {
    throw new Error(data?.detail || data?.message || "HITL approval failed");
  }

  return data;
}

export async function escalateCase(
  caseId: string,
  reason = "Claim Workspace escalation",
  actor = "Claim Workspace"
) {
  const params = new URLSearchParams();
  params.set("reason", reason);
  params.set("actor", actor);

  const response = await fetch(`${API_URL}/cases/${caseId}/escalate?${params.toString()}`, {
    method: "POST",
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(data?.detail || data?.message || "Case escalation failed");
  }

  return data;
}