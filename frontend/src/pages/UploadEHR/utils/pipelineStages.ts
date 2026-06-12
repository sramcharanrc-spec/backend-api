import { WORKSPACE_STAGES, STAGE_CLASS_MAP, stageAliases } from "./claimConstants";
import { normalizeStatus } from "./claimStatus";

export const stageDisplayFor = (key?: string | null) => {
  const normalized = normalizeWorkspaceStageKey(key);
  const stage = WORKSPACE_STAGES.find((item) => item.key === normalized);

  return stage?.label || normalized.replace(/_/g, " ");
};

export const pipelineStageUiState = (status?: string | null) => {
  const normalized = normalizeStatus(status);

  if (["COMPLETED", "COMPLETE", "SUCCESS"].includes(normalized)) return "completed";
  if (["RUNNING", "PROCESSING", "IN_PROGRESS"].includes(normalized)) return "running";
  if (["FAILED", "ERROR", "DENIED", "REJECTED"].includes(normalized)) return "failed";
  if (["WARNING", "HITL_REQUIRED", "WAITING_FOR_REVIEW", "WAITING_FOR_APPROVAL"].includes(normalized)) return "warning";

  return "pending";
};

export const pipelineStageClassName = (status?: string | null) =>
  STAGE_CLASS_MAP[normalizeStatus(status)] || pipelineStageUiState(status);

export const pipelineStageLabel = (status?: string | null) =>
  normalizeStatus(status).replace(/_/g, " ");

export const isPipelineCompleted = (pipeline: any) => {
  const status = normalizeStatus(pipeline?.overall_status || pipeline?.status || pipeline?.pipeline_state);
  return ["COMPLETED", "COMPLETE", "SUCCESS", "PAID"].includes(status);
};

export const activeAgentFromStages = (stages: any[] = []) =>
  stages.find((stage) => ["RUNNING", "PROCESSING"].includes(normalizeStatus(stage.status)))?.agent ||
  stages.find((stage) => ["RUNNING", "PROCESSING"].includes(normalizeStatus(stage.status)))?.label ||
  "Not reported";

export const createDefaultPipelineStages = () =>
  WORKSPACE_STAGES.map((stage) => ({
    ...stage,
    status: "PENDING",
  }));

export const stageStatusFromRawMap = (rawMap: Record<string, string> = {}) => {
  const result: Record<string, string> = {};

  Object.entries(rawMap).forEach(([key, value]) => {
    result[normalizeWorkspaceStageKey(key)] = normalizeStatus(value);
  });

  return result;
};

export const getBackendStageStatus = (pipeline: any, stageKey: string) =>
  pipeline?.stage_status?.[stageKey] ||
  pipeline?.pipeline?.stage_status?.[stageKey] ||
  pipeline?.stages?.find?.((stage: any) => normalizeWorkspaceStageKey(stage.id || stage.key) === stageKey)?.status;

export const getForcedStageStatus = (stageKey: string, currentStage?: string, status?: string) => {
  const normalizedStage = normalizeWorkspaceStageKey(stageKey);
  const normalizedCurrent = normalizeWorkspaceStageKey(currentStage);

  if (normalizedStage === normalizedCurrent) {
    return normalizeStatus(status || "RUNNING");
  }

  return undefined;
};

export const backendStageStatusFor = (pipeline: any, stageKey: string) =>
  normalizeStatus(getBackendStageStatus(pipeline, stageKey) || "PENDING");

export const normalizeWorkspaceStageKey = (key?: string | null) => {
  const normalized = normalizeStatus(key);
  return stageAliases[normalized] || normalized;
};

export const stageStatusFromMap = (map: Record<string, string> = {}, key: string) =>
  normalizeStatus(map[normalizeWorkspaceStageKey(key)] || "PENDING");

export const applyBackendStageStatus = (stages: any[], pipeline: any) =>
  stages.map((stage) => ({
    ...stage,
    status: backendStageStatusFor(pipeline, stage.key),
  }));

export const applyBackendCurrentStage = (stages: any[], currentStage?: string) => {
  const active = normalizeWorkspaceStageKey(currentStage);

  return stages.map((stage) => {
    if (stage.key === active && normalizeStatus(stage.status) === "PENDING") {
      return { ...stage, status: "RUNNING" };
    }

    return stage;
  });
};

export const getStageHistoryEntries = (pipeline: any, stageKey: string) =>
  pipeline?.events?.filter?.((event: any) => normalizeWorkspaceStageKey(event.stage) === normalizeWorkspaceStageKey(stageKey)) || [];

export const getStageHistoryStatus = (pipeline: any, stageKey: string) =>
  getStageHistoryEntries(pipeline, stageKey).at(-1)?.status;

export const getCompletedStageStatus = (pipeline: any, stageKey: string) =>
  getStageHistoryStatus(pipeline, stageKey) || backendStageStatusFor(pipeline, stageKey);

export const buildSyncedWorkspaceStages = (pipeline: any = {}) => {
  let stages = createDefaultPipelineStages();

  stages = applyBackendStageStatus(stages, pipeline);
  stages = applyBackendCurrentStage(stages, pipeline.current_stage);

  return stages;
};

export const buildStageTooltip = (stage: any) => ({
  task: stage.label || stage.key,
  status: stage.status || "PENDING",
  reasoning: stage.message || `${stage.label || stage.key} is ${pipelineStageLabel(stage.status)}`,
});