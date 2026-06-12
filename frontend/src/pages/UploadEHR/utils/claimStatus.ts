import type { ProcessingMode } from "./claimTypes";
import {
  COMPLETE_STATUSES,
  FAILED_STATUSES,
  FINALIZED_STATUSES,
  REVIEW_TAB_STATUSES,
  STAGE_CLASS_MAP,
  STATUS_MAP,
  TERMINAL_COMPLETED_CLAIM_STATUSES,
  WORKSPACE_VISIBLE_STATUSES,
} from "./claimConstants";
import { getClaimId } from "./claimGetters";

export const normalizeStatus = (status?: string | null) =>
  String(status || "PENDING").trim().toUpperCase().replace(/[\s-]+/g, "_");

export const normalizeValue = normalizeStatus;

export const displayStatus = (status?: string | null) => {
  const normalized = normalizeStatus(status);
  return STATUS_MAP[normalized] || normalized.replace(/_/g, " ");
};

export const normalizeStepKey = (value?: string | null) =>
  normalizeStatus(value);

export const normalizeAgentStageKey = normalizeStepKey;

export const normalizeAgentStatus = (value?: string | null) => {
  const status = normalizeStatus(value);

  if (["START", "STARTED", "INFO", "PROCESSING", "IN_PROGRESS"].includes(status)) return "RUNNING";
  if (["SUCCESS", "DONE", "COMPLETE", "COMPLETED", "ACCEPTED"].includes(status)) return "COMPLETED";
  if (["ERROR", "FAILURE", "FAILED", "DENIED", "REJECTED"].includes(status)) return "FAILED";
  if (["WARN", "WARNING", "PARTIAL"].includes(status)) return "WARNING";

  return status;
};

export const isExplicitFailedStatus = (status?: string | null) =>
  FAILED_STATUSES.has(normalizeStatus(status));

export const statusClass = (status?: string | null) =>
  `cw-status ${normalizeStatus(status).toLowerCase()}`;

export const getCanonicalStage = normalizeStepKey;
export const getCanonicalStatus = normalizeStatus;

export const getWorkspaceStatusRaw = (item: any) =>
  item?.status ||
  item?.pipeline_state ||
  item?.payload?.status ||
  item?.payload?.pipeline_state ||
  item?.payload?.claim?.status ||
  item?.claim?.status;

export const getWorkspaceStatus = (item: any) =>
  normalizeStatus(getWorkspaceStatusRaw(item));

export const isWorkspaceVisibleClaim = (item: any) =>
  WORKSPACE_VISIBLE_STATUSES.has(getWorkspaceStatus(item));

export const getQueueState = (item: any) =>
  normalizeStatus(item?.queue_state || item?.payload?.queue_state || item?.claim?.queue_state);

export const isWaitingForClearinghouseApproval = (item: any) => {
  const status = getWorkspaceStatus(item);
  return status === "WAITING_FOR_APPROVAL" || status === "PENDING_CLEARINGHOUSE";
};

export const isHitlReviewClaim = (item: any) =>
  REVIEW_TAB_STATUSES.has(getWorkspaceStatus(item));

export const isDownstreamRunningOrComplete = (item: any) => {
  const status = getWorkspaceStatus(item);
  return COMPLETE_STATUSES.has(status) || status === "PROCESSING" || status === "RUNNING";
};

export const getBackendProcessingMode = (
  item: any,
  overrides: Record<string, ProcessingMode> = {},
  globalMode: ProcessingMode = "MANUAL"
): ProcessingMode => {
  const claimId = getClaimId(item);

  const raw =
    item?.clearinghouse_processing_mode ||
    item?.processing_mode ||
    item?.payload?.clearinghouse_processing_mode ||
    item?.payload?.processing_mode ||
    (claimId && overrides[claimId]) ||
    globalMode;

  return String(raw || "MANUAL").toUpperCase() === "AUTO" ? "AUTO" : "MANUAL";
};

export const hasCaseFlag = (item: any) =>
  Boolean(item?.case_id || item?.case?.case_id || item?.hitl_case_id || item?.has_case);

export const shouldFetchCaseForClaim = (item: any) =>
  isHitlReviewClaim(item) || hasCaseFlag(item);

export const isFinalizedClaim = (item: any) =>
  FINALIZED_STATUSES.has(getWorkspaceStatus(item));

export const getCurrentAgent = (item: any) =>
  item?.current_agent ||
  item?.currentAgent ||
  item?.payload?.current_agent ||
  item?.payload?.claim?.current_agent ||
  item?.claim?.current_agent ||
  "Not reported";

export const getCurrentStep = (item: any) =>
  item?.active_step ||
  item?.current_step ||
  item?.currentStep ||
  item?.current_stage ||
  item?.currentStage ||
  item?.payload?.active_step ||
  item?.payload?.current_step ||
  "Not reported";

export const getReviewStatus = (item: any, mode: ProcessingMode = "MANUAL") => {
  const status = getWorkspaceStatus(item);

  if (["HITL_REQUIRED", "HUMAN_REVIEW_REQUIRED", "MANUAL_REVIEW_REQUIRED", "NEEDS_REVIEW"].includes(status)) {
    return "Needs Review";
  }

  if (status === "WAITING_FOR_REVIEW") return "Pending Review";
  if (status === "WAITING_FOR_APPROVAL" || status === "PENDING_CLEARINGHOUSE") return "Awaiting Clearinghouse";
  if (status === "REJECTED" || status === "DENIED" || status === "HARD_REJECT") return "Rejected";
  if (mode === "AUTO") return "Auto Processing";

  return displayStatus(status);
};

export const isCompliancePaused = (item: any) =>
  getWorkspaceStatus(item) === "PIPELINE_PAUSED";

export const isManualReviewPaused = (item: any) =>
  ["MANUAL_REVIEW_REQUIRED", "WAITING_FOR_REVIEW", "HITL_REQUIRED"].includes(getWorkspaceStatus(item));

export const isHardRejected = (item: any) =>
  ["HARD_REJECT", "REJECTED", "DENIED"].includes(getWorkspaceStatus(item));

export const complianceReason = (item: any) =>
  item?.compliance_reason || item?.reason || item?.payload?.reason || "";

export const isCompletedWorkspaceClaim = (item: any) => {
  const status = getWorkspaceStatus(item);

  return Boolean(
    item?.pipeline_completed === true ||
      item?.command_center === true ||
      item?.command_center_claim === true ||
      TERMINAL_COMPLETED_CLAIM_STATUSES.has(status)
  );
};

export const isTerminalCompletedClaim = isCompletedWorkspaceClaim;

export const isFinalStatus = (status?: string | null) => {
  const normalized = normalizeStatus(status);
  return COMPLETE_STATUSES.has(normalized) || FAILED_STATUSES.has(normalized);
};

export const deriveBackendActionMessage = (data: any) =>
  data?.message || data?.detail || data?.status || "Action completed.";

export const getSuggestedCaseRole = (item: any) => {
  const status = getWorkspaceStatus(item);

  if (status === "DENIED" || status === "REJECTED") return "Legal Team";
  if (status === "HITL_REQUIRED" || status === "MANUAL_REVIEW_REQUIRED") return "MA Team";

  return "HEOR Team";
};

export const pipelineStageClassName = (status?: string | null) =>
  STAGE_CLASS_MAP[normalizeStatus(status)] || "pending";