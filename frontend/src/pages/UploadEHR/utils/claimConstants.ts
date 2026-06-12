import {
  AlertTriangle,
  Brain,
  Building2,
  CircleDollarSign,
  ClipboardCheck,
  FileCheck2,
  FileSearch,
  Send,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

export const CLAIM_STORAGE_KEY = "ehr-unified-claims-v2";
export const PROCESSING_MODE_STORAGE_KEY = "ehr-clearinghouse-processing-mode-v1";
export const CLAIM_MODE_STORAGE_KEY = "ehr-claim-processing-mode-overrides-v1";
export const CLAIM_CASE_STORAGE_KEY = "ehr-claim-hitl-cases-v1";

export const LATEST_UPLOAD_WINDOW_MS = 2 * 60 * 1000;
export const NEW_CLAIM_HIGHLIGHT_MS = 30 * 1000;
export const MAX_RENDERED_CLAIM_ROWS = 120;
export const REFRESH_DEBOUNCE_MS = 650;
export const DEBUG_CLAIM_WORKSPACE = false;

export const LIVE_STATUSES = new Set([
  "PROCESSING",
  "ACTIVE",
  "RUNNING",
  "QUEUED",
  "PENDING",
  "VALIDATED",
  "WAITING_FOR_REVIEW",
  "WAITING_FOR_APPROVAL",
  "MANUAL_REVIEW_REQUIRED",
  "PENDING_CLEARINGHOUSE",
  "RETRYING",
]);

export const FAILED_STATUSES = new Set([
  "FAILED",
  "ERROR",
  "DENIED",
  "REJECTED",
  "HITL_REQUIRED",
  "MANUAL_REVIEW_REQUIRED",
  "WAITING_FOR_REVIEW",
  "HARD_REJECT",
]);

export const COMPLETE_STATUSES = new Set([
  "COMPLETED",
  "COMPLETE",
  "CLOSED",
  "FINALIZED",
  "REJECTED",
  "SUCCESS",
  "ARCHIVED",
  "PAID",
  "COMMAND_CENTER",
]);

export const FINALIZED_STATUSES = new Set([
  "COMPLETED",
  "COMPLETE",
  "CLOSED",
  "FINALIZED",
  "SUCCESS",
  "ARCHIVED",
  "PAID",
  "COMMAND_CENTER",
]);

export const PROCESSING_TERMINAL_STATES = new Set([
  "COMPLETED",
  "FAILED",
  "ERROR",
  "DENIED",
  "REJECTED",
]);

export const WORKFLOW_TERMINAL_STATES = new Set([
  "COMPLETED",
  "COMPLETE",
  "FAILED",
  "ERROR",
  "DENIED",
  "REJECTED",
  "PAID",
]);

export const WORKSPACE_VISIBLE_STATUSES = new Set([
  ...Array.from(LIVE_STATUSES),
  ...Array.from(FAILED_STATUSES),
  ...Array.from(COMPLETE_STATUSES),
]);

export const REVIEW_TAB_STATUSES = new Set([
  "HITL_REQUIRED",
  "HUMAN_REVIEW_REQUIRED",
  "MANUAL_REVIEW_REQUIRED",
  "WAITING_FOR_REVIEW",
  "WAITING_FOR_APPROVAL",
  "PENDING_CLEARINGHOUSE",
  "NEEDS_REVIEW",
  "HUMAN_REVIEW",
  "FAILED",
  "ERROR",
  "DENIED",
  "REJECTED",
  "HARD_REJECT",
]);

export const TERMINAL_COMPLETED_CLAIM_STATUSES = new Set([
  "COMPLETED",
  "COMPLETE",
  "FINALIZED",
  "CLOSED",
  "SUCCESS",
  "PAID",
  "COMMAND_CENTER",
]);

export const STEP_MAP: Record<string, string> = {
  OCR: "OCR",
  VALIDATION: "VALIDATION",
  COMPLIANCE: "COMPLIANCE",
  SUBMISSION: "SUBMISSION",
  CLEARINGHOUSE: "CLEARINGHOUSE",
  DENIAL_AI: "DENIAL_AI",
  PAYMENT: "PAYMENT",
  LEARNING: "LEARNING",
  ANALYTICS: "ANALYTICS",
};

export const WAITING_FOR_APPROVAL_STAGE_STATUS = "WAITING_FOR_APPROVAL";

export const INTAKE_STAGE_PROGRESS: Record<string, number> = {
  UPLOADING: 10,
  UPLOAD_STARTED: 12,
  UPLOAD_QUEUED: 18,
  OCR_STARTED: 30,
  OCR_RUNNING: 35,
  VALIDATION_STARTED: 52,
  VALIDATION_RUNNING: 58,
  COMPLIANCE_STARTED: 68,
  COMPLIANCE_RUNNING: 72,
  SAVING_CLAIM: 82,
  CLAIM_SAVED: 92,
  CLAIM_AVAILABLE: 100,
  COMPLETED: 100,
};

export const WORKSPACE_STAGES = [
  { key: "OCR", label: "OCR", icon: FileSearch },
  { key: "VALIDATION", label: "Validate", icon: ShieldCheck },
  { key: "COMPLIANCE", label: "Compliance", icon: ClipboardCheck },
  { key: "SUBMISSION", label: "Submission", icon: Send },
  { key: "CLEARINGHOUSE", label: "Clearinghouse", icon: Building2 },
  { key: "DENIAL_AI", label: "Denial AI", icon: AlertTriangle },
  { key: "PAYMENT", label: "Payment", icon: CircleDollarSign },
  { key: "LEARNING", label: "Learning", icon: Sparkles },
  { key: "ANALYTICS", label: "Analytics", icon: Brain },
];

export const LIVE_AGENT_STAGES = WORKSPACE_STAGES;
export const STEPPER_AGENT_STAGES = WORKSPACE_STAGES;

export const WAITING_COMPLETED_AGENT_STAGES = new Set([
  "OCR",
  "VALIDATION",
  "COMPLIANCE",
  "SUBMISSION",
]);

export const DOWNSTREAM_AGENT_STAGES = new Set([
  "CLEARINGHOUSE",
  "DENIAL_AI",
  "PAYMENT",
  "LEARNING",
  "ANALYTICS",
]);

export const LIVE_STAGE_ICONS: Record<string, any> = {
  OCR: FileSearch,
  VALIDATION: ShieldCheck,
  COMPLIANCE: ClipboardCheck,
  SUBMISSION: Send,
  CLEARINGHOUSE: Building2,
  DENIAL_AI: AlertTriangle,
  PAYMENT: CircleDollarSign,
  LEARNING: Sparkles,
  ANALYTICS: Brain,
  COMPLETED: FileCheck2,
};

export const STATUS_MAP: Record<string, string> = {
  PENDING_CLEARINGHOUSE: "Pending Clearinghouse",
  PIPELINE_PAUSED: "Pipeline Paused",
  WAITING_FOR_REVIEW: "Human Review",
  WAITING_FOR_APPROVAL: "Awaiting Clearinghouse",
  HITL_REQUIRED: "Needs Review",
  MANUAL_REVIEW_REQUIRED: "Manual Review Required",
  COMPLETED: "Completed",
  FAILED: "Failed",
  PROCESSING: "Processing",
};

export const STAGE_CLASS_MAP: Record<string, string> = {
  PENDING: "pending",
  RUNNING: "running",
  PROCESSING: "running",
  COMPLETED: "completed",
  SUCCESS: "completed",
  FAILED: "failed",
  ERROR: "failed",
  DENIED: "failed",
  REJECTED: "failed",
  WARNING: "warning",
  HITL_REQUIRED: "warning",
  WAITING_FOR_REVIEW: "warning",
  WAITING_FOR_APPROVAL: "warning",
};

export const stageAliases: Record<string, string> = {
  OCR_AGENT: "OCR",
  OCR: "OCR",
  VALIDATION_AGENT: "VALIDATION",
  VALIDATION: "VALIDATION",
  COMPLIANCE_AGENT: "COMPLIANCE",
  COMPLIANCE: "COMPLIANCE",
  SUBMISSION_AGENT: "SUBMISSION",
  SUBMISSION: "SUBMISSION",
  CLEARINGHOUSE_AGENT: "CLEARINGHOUSE",
  CLEARINGHOUSE: "CLEARINGHOUSE",
  DENIAL_AGENT: "DENIAL_AI",
  DENIAL_AI: "DENIAL_AI",
  PAYMENT_AGENT: "PAYMENT",
  PAYMENT: "PAYMENT",
  LEARNING_AGENT: "LEARNING",
  LEARNING: "LEARNING",
  ANALYTICS_AGENT: "ANALYTICS",
  ANALYTICS: "ANALYTICS",
};