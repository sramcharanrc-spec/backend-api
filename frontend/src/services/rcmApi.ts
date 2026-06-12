import axios from "axios";
import { addPipelineEventListener } from "./websocket";
import type {
  AuditEvidence,
  CaseOrchestrationSummary,
  EnterpriseAnalytics,
  ExtractionSummary,
  OcrPreview,
  ValidationSummary,
} from "../types/enterprise";
import { normalizeClaimsResponse } from "../utils/claimSync";

export const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

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

const saveBlob = (blob: Blob, filename: string) => {
  const url = window.URL.createObjectURL(blob);

  try {
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
  } finally {
    window.URL.revokeObjectURL(url);
  }
};

const requireClaimId = (claimId: string) => {
  if (!claimId || !claimId.startsWith("CLM-")) {
    throw new Error(`Invalid claim_id: ${claimId}`);
  }

  return claimId;
};

/* ---------------- RECORDS / CLAIMS ---------------- */

export const getRecords = (summary = true) =>
  API.get(`/records?summary=${summary}`).then((res) => res.data);

export const getClaims = () =>
  API.get("/api/claims").then((res) => normalizeClaimsResponse(res.data));

export const getLatestClaims = (limit = 10) =>
  API.get(`/api/claims/latest?limit=${limit}`).then((res) =>
    normalizeClaimsResponse(res.data)
  );

export const getClaimDetails = (claimId: string) =>
  API.get(`/api/claims/${requireClaimId(claimId)}`).then((res) => res.data);

export const deleteClaim = (claimId: string, user?: { role?: string; email?: string }) =>
  API.delete(`/api/claims/${requireClaimId(claimId)}`, {
    headers: {
      "x-user-role": user?.role || "Admin",
      "x-user-email": user?.email || "admin@company.com",
    },
  }).then((res) => res.data);

/* ---------------- PIPELINE ---------------- */

export const getPipelineStatus = (claimId: string) =>
  API.get(`/api/claims/${requireClaimId(claimId)}/pipeline`).then((res) => res.data);

export const retryClaimValidation = (claimId: string) =>
  API.post(`/api/claims/${requireClaimId(claimId)}/retry-validation`).then(
    (res) => res.data
  );

/* ---------------- HITL / CASES ---------------- */

export const getCaseByClaim = (claimId: string) =>
  API.get(`/cases/by-claim/${requireClaimId(claimId)}`).then((res) => res.data);

export const createHitlCase = (
  claimId: string,
  data: {
    reason?: string;
    assigned_role?: string;
    assigned_team?: string;
    created_by?: string;
  } = {}
) =>
  API.post(`/api/claims/${requireClaimId(claimId)}/hitl-case`, {
    reason: data.reason || "Manual review required",
    assigned_role: data.assigned_role || "MA Team",
    assigned_team: data.assigned_team || data.assigned_role || "MA Team",
    created_by: data.created_by || "Claim Workspace",
  }).then((res) => res.data);

export const approveHitlCase = (claimId: string, userId = "Claim Workspace") =>
  API.post(`/api/case/${requireClaimId(claimId)}/approve`, null, {
    params: { user_id: userId },
  }).then((res) => res.data);

export const assignCase = (
  caseId: string,
  data: {
    assigned_role: string;
    assigned_team?: string;
    assigned_to?: string;
    assigned_by?: string;
    reason?: string;
  }
) =>
  API.put(`/cases/${caseId}/assign`, {
    assigned_role: data.assigned_role,
    assigned_team: data.assigned_team || data.assigned_role,
    assigned_to: data.assigned_to || "Queue Owner",
    assigned_by: data.assigned_by || "Claim Workspace",
    reason: data.reason || "Inline workspace routing",
  }).then((res) => res.data);

export const escalateCase = (
  caseId: string,
  reason = "Claim Workspace escalation",
  actor = "Claim Workspace"
) =>
  API.post(`/cases/${caseId}/escalate`, null, {
    params: { reason, actor },
  }).then((res) => res.data);

/* ---------------- CLEARINGHOUSE REVIEW ---------------- */

export const setClearinghouseMode = (
  claimId: string,
  processingMode: "AUTO" | "MANUAL",
  reviewer = "Claim Workspace"
) =>
  API.put(`/api/claims/${requireClaimId(claimId)}/clearinghouse-mode`, {
    processing_mode: processingMode,
    reviewer,
  }).then((res) => res.data);

export const acceptClearinghouse = (
  claimId: string,
  reviewer = "Claim Workspace"
) =>
  API.post(`/api/claims/${requireClaimId(claimId)}/approve`, {
    reviewer,
  }).then((res) => res.data);

export const rejectClearinghouse = (
  claimId: string,
  reason = "Rejected from Claim Workspace",
  reviewer = "Claim Workspace"
) =>
  API.post(`/api/claims/${requireClaimId(claimId)}/reject`, {
    claim_id: claimId,
    reason,
    reviewer,
  }).then((res) => res.data);

export const runClearinghouseAutoReview = (
  claimId: string,
  reviewer = "Claim Workspace Auto Mode"
) =>
  API.post(`/api/claims/${requireClaimId(claimId)}/clearinghouse-auto-review`, {
    reviewer,
  }).then((res) => res.data);

/* ---------------- CLAIM ARTIFACTS ---------------- */

export const getExtractionSummary = (
  claimId: string
): Promise<ExtractionSummary> =>
  API.get(`/api/claims/${requireClaimId(claimId)}/extraction-summary`).then(
    (res) => res.data
  );

export const getOcrPreview = (claimId: string): Promise<OcrPreview> =>
  API.get(`/api/claims/${requireClaimId(claimId)}/ocr-preview`).then(
    (res) => res.data
  );

export const getValidationSummary = (
  claimId: string
): Promise<ValidationSummary> =>
  API.get(`/api/claims/${requireClaimId(claimId)}/validation-summary`).then(
    (res) => res.data
  );

export const getCaseOrchestration = (
  claimId: string
): Promise<CaseOrchestrationSummary> =>
  API.get(`/api/claims/${requireClaimId(claimId)}/case-orchestration`).then(
    (res) => res.data
  );

export const getAuditEvidence = (claimId: string): Promise<AuditEvidence> =>
  API.get(`/api/audit/${requireClaimId(claimId)}`).then((res) => res.data);

export const exportAuditEvidence = async (
  claimId: string,
  format: "json" | "csv" | "pdf"
) => {
  const res = await API.get(
    `/api/audit/${requireClaimId(claimId)}/export?format=${format}`,
    { responseType: "blob" }
  );

  saveBlob(res.data, `${claimId}-evidence.${format}`);
};

export const getClaimSuggestions = (claimId: string) =>
  API.get(`/api/claims/${requireClaimId(claimId)}/suggestions`).then(
    (res) => res.data
  );

export const applyClaimCorrection = (claimId: string, data: any) =>
  API.post(`/api/claims/${requireClaimId(claimId)}/apply-correction`, data).then(
    (res) => res.data
  );

export const getRepairHistory = (claimId: string) =>
  API.get(`/api/claims/${requireClaimId(claimId)}/repair-history`).then(
    (res) => res.data
  );

export const getDenialAnalysis = (claimId: string) =>
  API.get(`/api/claims/${requireClaimId(claimId)}/denial-analysis`).then(
    (res) => res.data
  );

export const generateAppeal = (claimId: string, data: any = {}) =>
  API.post(`/api/claims/${requireClaimId(claimId)}/generate-appeal`, data).then(
    (res) => res.data
  );

export const retrySubmission = (claimId: string, data: any = {}) =>
  API.post(`/api/claims/${requireClaimId(claimId)}/retry-submission`, data).then(
    (res) => res.data
  );

export const downloadCMS1500 = async (claimId: string) => {
  const res = await API.get(`/api/claims/${requireClaimId(claimId)}/cms1500`, {
    responseType: "blob",
  });

  saveBlob(res.data, `${claimId}-CMS1500.pdf`);
};

export const downloadUB04 = async (claimId: string) => {
  const res = await API.get(`/api/claims/${requireClaimId(claimId)}/ub04`, {
    responseType: "blob",
  });

  saveBlob(res.data, `${claimId}-UB04.pdf`);
};

export const downloadEDI = async (claimId: string) => {
  const res = await API.get(`/api/claims/${requireClaimId(claimId)}/edi`, {
    responseType: "blob",
  });

  saveBlob(res.data, `${claimId}.edi`);
};

/* ---------------- RCM / ANALYTICS ---------------- */

export const fetchAnalytics = () =>
  API.get("/api/rcm/analytics").then((res) => res.data);

export const fetchExtractionAnalytics = () =>
  API.get("/analytics/extraction").then((res) => res.data);

export const fetchEnterpriseAnalytics = (): Promise<EnterpriseAnalytics> =>
  API.get("/analytics/enterprise").then((res) => res.data);

export const fetchReconciliation = () =>
  API.get("/api/rcm/reconciliation").then((res) => res.data);

export const fetchSubmissions = () =>
  API.get("/api/rcm/submissions").then((res) => res.data);

export const submitClaim = (data: any) =>
  API.post("/api/rcm/submit", data).then((res) => res.data);

export const postPayment = (data: any) =>
  API.post("/api/rcm/payment", data).then((res) => res.data);

export const getPayments = () =>
  API.get("/api/rcm/payments").then((res) => res.data);

export const predictDenial = (data: any) =>
  API.post("/api/rcm/predict-denial", data).then((res) => res.data);

/* ---------------- LEGACY REVIEW ALIASES ---------------- */
/*
  Keep these aliases only for older components.
  New Claim Workspace code should prefer:
  - getClaimSuggestions()
  - applyClaimCorrection()
  - approveHitlCase()
  - acceptClearinghouse()
*/

export const getSuggestions = (id: string) => getClaimSuggestions(id);

export const fixClaim = (id: string, data: any) =>
  API.post(`/review/${id}/edit-and-resume`, data).then((res) => res.data);

/* ---------------- WEBSOCKET HELPER ---------------- */

export const connectWebSocket = (onMessage: (data: any) => void) => {
  const unsubscribe = addPipelineEventListener(onMessage);
  return { close: unsubscribe };
};

export default API;