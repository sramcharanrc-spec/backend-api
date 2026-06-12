export type UploadStatus = "idle" | "loading" | "success" | "error";

export type ClaimTab =
  | "latest"
  | "all"
  | "bulk"
  | "single"
  | "live"
  | "review"
  | "rejected"
  | "completed";

export type ProcessingMode = "AUTO" | "MANUAL";

export type ProcessingClaim = {
  id: string;
  temp_id?: string;
  upload_session_id?: string;
  isTemporary?: boolean;
  claim_id?: string;
  filename?: string;
  job_id?: string;
  stage: string;
  status: string;
  progress: number;
  startedAt: string;
  updatedAt?: string;
  message?: string;
};

export type FormPreview = {
  title: string;
  claimId: string;
  form: "CMS1500" | "UB04";
  endpointUrl?: string;
  url?: string;
};

export type PipelineStageStatus =
  | "PENDING"
  | "RUNNING"
  | "COMPLETED"
  | "FAILED"
  | "REJECTED"
  | "DENIED"
  | "WARNING"
  | "HITL_REQUIRED"
  | "MANUAL_REVIEW_REQUIRED"
  | "WAITING_FOR_REVIEW"
  | "WAITING_FOR_APPROVAL"
  | string;

export type BackendPipelineStage = {
  id: string;
  key?: string;
  label?: string;
  status: PipelineStageStatus;
  started_at?: string;
  completed_at?: string;
  duration?: string | number;
  progress?: number;
  agent?: string;
  message?: string;
};

export type BackendPipelineData = {
  claim_id?: string;
  overall_status?: string;
  current_stage?: string;
  current_agent?: string | null;
  workflow_state?: string;
  started_at?: string;
  completed_at?: string;
  duration?: string | number;
  progress?: number;
  stage_status?: Record<string, string>;
  stages?: BackendPipelineStage[];
  events?: any[];
  pipeline?: any;
};

export type ClaimItemsAction =
  | { type: "SET_ITEMS"; payload: any[] }
  | { type: "MERGE_ITEMS"; payload: any[] }
  | { type: "REMOVE_CLAIM"; claimId: string }
  | { type: "RESET_CLAIMS" }
  | { type: "WS_CLAIM_UPDATE"; payload: any }
  | { type: "PIPELINE_UPDATE"; payload: any }
  | { type: "CLAIM_COMPLETED"; payload: any };

export type CompletedClaimsAction =
  | { type: "SET_COMPLETED"; payload: any[] }
  | { type: "MERGE_COMPLETED"; payload: any[] }
  | { type: "REMOVE_COMPLETED"; claimId: string }
  | { type: "RESET_COMPLETED" };