export const STATUS_ALIAS: Record<string, string> = {
  SUCCESS: "COMPLETED",
  COMPLETE: "COMPLETED",
  DONE: "COMPLETED",
  PROCESS: "RUNNING",
  START: "RUNNING",
  STARTED: "RUNNING",
  INFO: "RUNNING",
  IN_PROGRESS: "RUNNING",
  ACTIVE: "RUNNING",
  ERROR: "FAILED",
  FAILURE: "FAILED",
};

export const PIPELINE_SEQUENCE = [
  "OCR",
  "VALIDATION",
  "COMPLIANCE",
  "SUBMISSION",
  "CLEARINGHOUSE",
  "ACKNOWLEDGMENT",
  "DENIAL_AI",
  "PAYMENT",
  "LEARNING",
  "ANALYTICS",
  "COMPLETED",
] as const;

const STAGE_ALIAS: Record<string, string> = {
  INTAKE: "OCR",
  EXTRACT: "OCR",
  EXTRACTION: "OCR",
  OCR_EXTRACTION: "OCR",
  RULES: "VALIDATION",
  RULES_VALIDATION: "VALIDATION",
  ELIGIBILITY: "VALIDATION",
  CLAIM_FORM: "SUBMISSION",
  CMS1500: "SUBMISSION",
  CMS_1500: "SUBMISSION",
  UB04: "SUBMISSION",
  UB_04: "SUBMISSION",
  EDI: "SUBMISSION",
  EDI_837: "SUBMISSION",
  X12: "SUBMISSION",
  "837": "SUBMISSION",
  ACK: "ACKNOWLEDGMENT",
  ACKNOWLEDGMENT: "ACKNOWLEDGMENT",
  ACKNOWLEDGEMENT: "ACKNOWLEDGMENT",
  PAYER: "ACKNOWLEDGMENT",
  PAYER_ACK: "ACKNOWLEDGMENT",
  PAYER_ACKNOWLEDGMENT: "ACKNOWLEDGMENT",
  PAYER_ACKNOWLEDGEMENT: "ACKNOWLEDGMENT",
  PAYER_ACKNOWLEDGED: "ACKNOWLEDGMENT",
  CLEARINGHOUSE_AUTO: "CLEARINGHOUSE",
  CLEARINGHOUSE_PENDING: "CLEARINGHOUSE",
  PENDING_CLEARINGHOUSE: "CLEARINGHOUSE",
  WAITING_FOR_APPROVAL: "CLEARINGHOUSE",
  DENIAL: "DENIAL_AI",
  DENIALAI: "DENIAL_AI",
  PAYMENT_RECONCILIATION: "PAYMENT",
  PAYMENT_POSTED: "PAYMENT",
  FEEDBACK: "LEARNING",
  FEEDBACK_LOOP: "LEARNING",
  PIPELINE_COMPLETED: "COMPLETED",
  CLAIM_COMPLETED: "COMPLETED",
  COMMAND_CENTER_TRANSFER: "COMPLETED",
  FINALIZED: "COMPLETED",
  CLOSED: "COMPLETED",
  PAID: "COMPLETED",
};

const READ_PATHS: Record<string, string[][]> = {
  claim_id: [["claim_id"], ["claimId"], ["data", "claim_id"], ["data", "claimId"], ["metadata", "claim_id"], ["claim", "claim_id"], ["data", "claim", "claim_id"], ["payload", "claim_id"], ["payload", "claim", "claim_id"]],
  timestamp: [["timestamp"], ["updated_at"], ["updatedAt"], ["created_at"], ["data", "timestamp"], ["metadata", "timestamp"], ["claim", "updated_at"], ["data", "claim", "updated_at"], ["payload", "updated_at"], ["payload", "claim", "updated_at"]],
  status: [["status"], ["pipeline_state"], ["pipeline_status"], ["state"], ["data", "status"], ["data", "pipeline_state"], ["metadata", "status"], ["claim", "status"], ["data", "claim", "status"], ["payload", "status"], ["payload", "claim", "status"], ["pipeline", "pipeline_state"]],
  stage: [["stage"], ["current_stage"], ["currentStage"], ["active_stage"], ["active_step"], ["current_step"], ["currentStep"], ["step"], ["agent"], ["current_agent"], ["type"], ["event"], ["data", "stage"], ["data", "current_stage"], ["data", "active_step"], ["metadata", "stage"], ["metadata", "current_stage"], ["pipeline", "current_stage"], ["pipeline", "active_step"]],
};

const readPath = (source: any, path: string[]) =>
  path.reduce((cursor, key) => (cursor && cursor[key] !== undefined ? cursor[key] : undefined), source);

export const readPipelineValue = (source: any, key: keyof typeof READ_PATHS | string) => {
  const paths = READ_PATHS[key] || [[key]];
  for (const path of paths) {
    const value = readPath(source, path);
    if (value !== undefined && value !== null && value !== "") return value;
  }
  return undefined;
};

export const normalizePipelineToken = (value: any) =>
  String(value || "")
    .trim()
    .replace(/[\s-]+/g, "_")
    .toUpperCase();

export const normalizePipelineStatus = (value: any, fallback?: string) => {
  const token = normalizePipelineToken(value);
  if (!token) return fallback;
  return STATUS_ALIAS[token] || token;
};

export const normalizePipelineStage = (value: any) => {
  const token = normalizePipelineToken(value);
  if (!token) return "";
  const withoutLifecycle = token
    .replace(/_(STARTED|START|RUNNING|PROCESSING|PROCESS|COMPLETED|COMPLETE|SUCCESS|FAILED|ERROR)$/g, "");
  const candidate = STAGE_ALIAS[token] || STAGE_ALIAS[withoutLifecycle] || withoutLifecycle;
  return STAGE_ALIAS[candidate] || candidate;
};

export const normalizePipelineStep = (value: any) => normalizePipelineStage(value).toLowerCase();

export const pipelineStageRank = (value: any) => {
  const stage = normalizePipelineStage(value);
  return PIPELINE_SEQUENCE.indexOf(stage as (typeof PIPELINE_SEQUENCE)[number]);
};

export const pipelineTimestampMs = (value: any) => {
  const raw = typeof value === "object" ? readPipelineValue(value, "timestamp") : value;
  if (!raw) return -1;
  const timestamp = new Date(raw).getTime();
  return Number.isFinite(timestamp) ? timestamp : -1;
};

export const pipelineEventKey = (event: any) => {
  const claimId = readPipelineValue(event, "claim_id") || "global";
  const stage = normalizePipelineStage(readPipelineValue(event, "stage")) || "unknown";
  const timestamp = readPipelineValue(event, "timestamp") || "";
  return `${claimId}|${stage}|${timestamp}`;
};

export const isPipelineRollback = (current: any, incoming: any) => {
  const currentRank = Math.max(
    pipelineStageRank(readPipelineValue(current, "stage")),
    pipelineStageRank(readPipelineValue(current, "status"))
  );
  const incomingRank = Math.max(
    pipelineStageRank(readPipelineValue(incoming, "stage")),
    pipelineStageRank(readPipelineValue(incoming, "status"))
  );

  if (currentRank < 0 || incomingRank < 0) return false;
  return incomingRank < currentRank;
};

export const normalizePipelineEventPayload = <T extends Record<string, any>>(payload: T): T => {
  const status = normalizePipelineStatus(readPipelineValue(payload, "status"));
  const pipeline = payload.pipeline || {};
  const data = payload.data || {};
  const dataPipeline = data.pipeline || {};
  const currentStage = payload.current_stage ?? payload.currentStage ?? pipeline.current_stage ?? data.current_stage ?? data.currentStage ?? dataPipeline.current_stage;
  const stageValue = payload.stage ?? pipeline.stage ?? data.stage ?? dataPipeline.stage;
  const activeStep = payload.active_step ?? payload.current_step ?? payload.currentStep ?? pipeline.active_step ?? pipeline.current_step ?? data.active_step ?? data.current_step ?? data.currentStep ?? dataPipeline.active_step;
  const stage = stageValue ? normalizePipelineStage(stageValue) : payload.stage;
  const normalizedCurrentStage = currentStage ? normalizePipelineStage(currentStage) : payload.current_stage ?? payload.currentStage;
  const currentStep = activeStep ? normalizePipelineStage(activeStep) : payload.current_step ?? payload.currentStep ?? payload.active_step;
  const timestamp = readPipelineValue(payload, "timestamp") || new Date().toISOString();

  return {
    ...payload,
    status,
    pipeline_state: normalizePipelineStatus(payload.pipeline_state ?? payload.data?.pipeline_state ?? status),
    stage: stage || payload.stage || undefined,
    current_stage: normalizedCurrentStage || undefined,
    currentStage: normalizedCurrentStage || undefined,
    current_step: currentStep || payload.current_step || payload.currentStep || payload.active_step || undefined,
    currentStep: currentStep || payload.currentStep || payload.current_step || payload.active_step || undefined,
    active_step: currentStep || payload.active_step || payload.current_step || payload.currentStep || undefined,
    timestamp,
  };
};
