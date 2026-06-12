import axios from "axios";

export const API_URL =
  import.meta.env.VITE_API_URL || "http://localhost:8000";

const API = axios.create({
  baseURL: API_URL,
  timeout: 15000,
});

API.interceptors.response.use(
  (response) => response,
  (error) => {
    const message =
      error?.response?.data?.detail ||
      error?.response?.data?.message ||
      error?.message ||
      "API request failed";

    return Promise.reject(new Error(message));
  }
);

const requireClaimId = (claimId: string) => {
  if (!claimId || !/^CLM-[a-f0-9]{10}$/i.test(claimId)) {
    throw new Error(`Invalid claim_id: ${claimId}`);
  }

  return claimId;
};

const requireSubmissionId = (submissionId: string) => {
  if (!submissionId) {
    throw new Error("submission_id is required");
  }

  return submissionId;
};

/**
 * Legacy RCM submit-from-S3 flow.
 * Keep this only if an older screen still submits by patient_id.
 * New Claim Workspace uploads should use /intake/upload.
 */
export const submitClaimFromS3 = async (patientId: string) => {
  const res = await API.post("/api/rcm/submit-from-s3", {
    patient_id: patientId,
  });

  return res.data;
};

/**
 * Legacy submission status lookup.
 * This uses submission_id, not claim_id.
 */
export const getClaimStatus = async (submissionId: string) => {
  const res = await API.get(
    `/api/rcm/status/${requireSubmissionId(submissionId)}`
  );

  return res.data;
};

/**
 * Legacy global RCM pipeline endpoint.
 */
export const getPipeline = async () => {
  const res = await API.get("/api/rcm/agents/pipeline");
  return res.data;
};

/**
 * Current backend claim detail endpoint.
 */
export const getClaimDetails = async (claimId: string) => {
  const res = await API.get(`/api/claims/${requireClaimId(claimId)}`);
  return res.data;
};

/**
 * Current backend claim pipeline endpoint.
 */
export const getClaimPipeline = async (claimId: string) => {
  const res = await API.get(`/api/claims/${requireClaimId(claimId)}/pipeline`);
  return res.data;
};

/**
 * HITL approval.
 * This should approve the human review case only.
 * In MANUAL clearinghouse mode, backend should stop at WAITING_FOR_APPROVAL.
 */
export const approveHitlCase = async (
  claimId: string,
  userId = "Claim Workspace"
) => {
  const res = await API.post(`/api/case/${requireClaimId(claimId)}/approve`, null, {
    params: {
      user_id: userId,
    },
  });

  return res.data;
};

/**
 * Explicit clearinghouse accept.
 * This is separate from HITL approval.
 * Downstream denial/payment/learning/analytics should run only after this action
 * or after an explicit auto-review accept.
 */
export const acceptClearinghouse = async (
  claimId: string,
  reviewer = "Claim Workspace"
) => {
  const res = await API.post(`/api/claims/${requireClaimId(claimId)}/approve`, {
    reviewer,
  });

  return res.data;
};

export const rejectClearinghouse = async (
  claimId: string,
  reason = "Rejected from Claim Workspace",
  reviewer = "Claim Workspace"
) => {
  const res = await API.post(`/api/claims/${requireClaimId(claimId)}/reject`, {
    claim_id: claimId,
    reason,
    reviewer,
  });

  return res.data;
};

export const setClearinghouseMode = async (
  claimId: string,
  processingMode: "AUTO" | "MANUAL",
  reviewer = "Claim Workspace"
) => {
  const res = await API.put(
    `/api/claims/${requireClaimId(claimId)}/clearinghouse-mode`,
    {
      processing_mode: processingMode,
      reviewer,
    }
  );

  return res.data;
};

export const runClearinghouseAutoReview = async (
  claimId: string,
  reviewer = "Claim Workspace Auto Mode"
) => {
  const res = await API.post(
    `/api/claims/${requireClaimId(claimId)}/clearinghouse-auto-review`,
    {
      reviewer,
    }
  );

  return res.data;
};

export const getCaseByClaim = async (claimId: string) => {
  const res = await API.get(`/cases/by-claim/${requireClaimId(claimId)}`);
  return res.data;
};

export const createHitlCase = async (
  claimId: string,
  data: {
    reason?: string;
    assigned_role?: string;
    assigned_team?: string;
    created_by?: string;
  } = {}
) => {
  const assignedRole = data.assigned_role || data.assigned_team || "MA Team";

  const res = await API.post(`/api/claims/${requireClaimId(claimId)}/hitl-case`, {
    reason: data.reason || "Manual review required",
    assigned_role: assignedRole,
    assigned_team: assignedRole,
    created_by: data.created_by || "Claim Workspace",
  });

  return res.data;
};

export const assignCase = async (
  caseId: string,
  assignedRole: "MA Team" | "HEOR Team" | "Legal Team"
) => {
  const res = await API.put(`/cases/${caseId}/assign`, {
    assigned_role: assignedRole,
    assigned_team: assignedRole,
    assigned_to: "Queue Owner",
    assigned_by: "Claim Workspace",
    reason: "Inline workspace routing",
  });

  return res.data;
};

export const escalateCase = async (
  caseId: string,
  reason = "Claim Workspace escalation",
  actor = "Claim Workspace"
) => {
  const res = await API.post(`/cases/${caseId}/escalate`, null, {
    params: {
      reason,
      actor,
    },
  });

  return res.data;
};

export default API;