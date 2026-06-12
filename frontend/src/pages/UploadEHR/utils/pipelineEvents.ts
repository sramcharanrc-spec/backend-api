import { normalizePipelineEventPayload } from "../../../utils/pipelineSync";
import { getClaimId } from "./claimGetters";
import { normalizeStatus } from "./claimStatus";

const normalizeKey = (value: any) => normalizeStatus(value);

const isPlainObject = (value: any) =>
  Boolean(value) && typeof value === "object" && !Array.isArray(value);

const compactValue = (value: any) => {
  if (value === undefined || value === null) return "";
  return String(value).trim();
};

const getNestedPipeline = (event: any) =>
  event?.pipeline ||
  event?.data?.pipeline ||
  event?.payload?.pipeline ||
  event?.details?.pipeline ||
  event?.claim?.pipeline ||
  event?.data?.claim?.pipeline ||
  event?.payload?.claim?.pipeline ||
  {};

const getNestedClaim = (event: any) =>
  event?.claim ||
  event?.data?.claim ||
  event?.payload?.claim ||
  event?.details?.claim ||
  {};

export const getEventField = (event: any, field: string) => {
  const pipeline = getNestedPipeline(event);
  const claim = getNestedClaim(event);

  return (
    event?.[field] ??
    event?.data?.[field] ??
    event?.payload?.[field] ??
    event?.details?.[field] ??
    claim?.[field] ??
    pipeline?.[field]
  );
};

export const getEventClaimId = (event: any) =>
  getClaimId(event) ||
  getClaimId(getNestedClaim(event)) ||
  event?.data?.claim_id ||
  event?.data?.claim?.claim_id ||
  event?.metadata?.claim_id ||
  event?.details?.claim_id ||
  event?.details?.claim?.claim_id ||
  event?.pipeline?.claim_id ||
  event?.data?.pipeline?.claim_id ||
  event?.payload?.pipeline?.claim_id ||
  event?.claim_id ||
  "";

export const getEventStageKey = (event: any) =>
  normalizeKey(
    getEventField(event, "stage") ||
      getEventField(event, "current_stage") ||
      getEventField(event, "active_step") ||
      getEventField(event, "current_step") ||
      getEventField(event, "step")
  );

export const getEventPipelineState = (event: any) =>
  normalizeKey(
    getEventField(event, "pipeline_state") ||
      getEventField(event, "pipeline_status") ||
      getNestedPipeline(event)?.pipeline_state ||
      getNestedPipeline(event)?.pipeline_status
  );

export const getEventStatus = (event: any) =>
  normalizeKey(
    getEventField(event, "status") ||
      getEventField(event, "pipeline_state") ||
      getEventField(event, "pipeline_status")
  );

export const getEventTimestampMs = (event: any) => {
  const value =
    getEventField(event, "timestamp") ||
    getEventField(event, "updated_at") ||
    getEventField(event, "updatedAt") ||
    getEventField(event, "last_activity_at");

  const timestamp = new Date(value || 0).getTime();

  return Number.isFinite(timestamp) && timestamp > 0 ? timestamp : Date.now();
};

export const isClearinghouseWaitingEvent = (event: any) => {
  const stage = getEventStageKey(event);
  const status = getEventStatus(event);
  const pipelineState = getEventPipelineState(event);

  return (
    stage === "CLEARINGHOUSE" &&
    (status === "WAITING_FOR_APPROVAL" ||
      status === "PENDING_CLEARINGHOUSE" ||
      pipelineState === "WAITING_FOR_APPROVAL" ||
      pipelineState === "PENDING_CLEARINGHOUSE")
  );
};

export const isTerminalEvent = (event: any) => {
  const status = getEventStatus(event);
  const stage = getEventStageKey(event);
  const pipelineState = getEventPipelineState(event);

  if (isClearinghouseWaitingEvent(event)) return false;

  return (
    ["PAID", "COMPLETED", "COMPLETE", "SUCCESS", "FINISHED"].includes(status) ||
    ["PAID", "COMPLETED", "COMPLETE", "SUCCESS"].includes(pipelineState) ||
    ["FINISH", "ANALYTICS"].includes(stage)
  );
};

export const isRejectedEvent = (event: any) => {
  const status = getEventStatus(event);
  const pipelineState = getEventPipelineState(event);

  return [
    status,
    pipelineState,
  ].some((value) =>
    [
      "HARD_REJECT",
      "HARD_REJECTED",
      "REJECTED",
      "DENIED",
      "FAILED",
      "ERROR",
    ].includes(value)
  );
};

const getStageRank = (event: any) => {
  if (isTerminalEvent(event)) return 100;
  if (isRejectedEvent(event)) return 95;
  if (isClearinghouseWaitingEvent(event)) return 80;

  const stage = getEventStageKey(event);
  const status = getEventStatus(event);
  const pipelineState = getEventPipelineState(event);

  if (status === "WAITING_FOR_APPROVAL" || pipelineState === "WAITING_FOR_APPROVAL") return 80;
  if (stage === "ACKNOWLEDGMENT") return 75;
  if (stage === "CLEARINGHOUSE") return 70;
  if (stage === "SUBMISSION") return 60;
  if (stage === "COMPLIANCE") return 50;
  if (stage === "VALIDATION") return 40;
  if (stage === "ELIGIBILITY") return 30;
  if (["EXTRACTION", "EXTRACT", "OCR"].includes(stage)) return 20;

  return 10;
};

export const shouldReplaceStageEvent = (previous: any, incoming: any) => {
  if (!previous) return true;

  const previousRank = getStageRank(previous);
  const incomingRank = getStageRank(incoming);

  const previousTime = getEventTimestampMs(previous);
  const incomingTime = getEventTimestampMs(incoming);

  // Never let stale submission completed overwrite clearinghouse waiting.
  if (isClearinghouseWaitingEvent(previous)) {
    const incomingStage = getEventStageKey(incoming);
    const incomingStatus = getEventStatus(incoming);

    if (incomingStage === "SUBMISSION" && incomingStatus === "COMPLETED") {
      return false;
    }
  }

  // Do not move backward unless incoming is newer and meaningful.
  if (incomingRank < previousRank && incomingTime <= previousTime) {
    return false;
  }

  return incomingTime >= previousTime || incomingRank >= previousRank;
};

export const buildLiveAgentStageMap = (events: any[] = []) => {
  const map: Record<string, any> = {};

  events.forEach((event) => {
    const stage = getEventStageKey(event);
    if (!stage) return;

    if (!map[stage] || shouldReplaceStageEvent(map[stage], event)) {
      map[stage] = event;
    }
  });

  return map;
};

export const eventMessage = (event: any) =>
  getEventField(event, "message") ||
  getEventField(event, "reason") ||
  getEventField(event, "ai_summary") ||
  getEventField(event, "error") ||
  "";

export const eventTime = (event: any) =>
  getEventField(event, "timestamp") ||
  getEventField(event, "updated_at") ||
  getEventField(event, "updatedAt") ||
  "";

export const compactEventKey = (event: any) =>
  [
    compactValue(getEventClaimId(event)),
    compactValue(getEventStageKey(event)),
    compactValue(getEventStatus(event)),
    compactValue(getEventPipelineState(event)),
    compactValue(eventTime(event)),
  ].join(":");

const buildClearinghouseWaitingState = (payload: any, rawPayload: any, claimId: string) => {
  const claim = {
    ...getNestedClaim(rawPayload),
    ...getNestedClaim(payload),
    ...(payload?.claim || {}),
  };

  const pipeline = {
    ...getNestedPipeline(rawPayload),
    ...getNestedPipeline(payload),
    ...(payload?.pipeline || {}),
  };

  const progress = Number(payload?.progress ?? rawPayload?.progress ?? pipeline?.progress ?? 70);

  return {
    ...claim,
    ...payload,
    claim_id: claimId,
    status: "WAITING_FOR_APPROVAL",
    stage: "CLEARINGHOUSE",
    current_stage: "CLEARINGHOUSE",
    current_agent: "CLEARINGHOUSE",
    active_step: "clearinghouse",
    pipeline_state: "WAITING_FOR_APPROVAL",
    pipeline_status: "WAITING_FOR_APPROVAL",
    review_required: true,
    approval_required: true,
    pipeline_paused: true,
    progress: Number.isFinite(progress) ? progress : 70,
    pipeline: {
      ...pipeline,
      pipeline_state: "WAITING_FOR_APPROVAL",
      pipeline_status: "WAITING_FOR_APPROVAL",
      current_stage: "CLEARINGHOUSE",
      current_agent: "CLEARINGHOUSE",
      active_step: "clearinghouse",
      review_required: true,
      approval_required: true,
      pipeline_paused: true,
      progress: Number.isFinite(progress) ? progress : 70,
      steps: {
        ...(pipeline?.steps || {}),
        submitted: true,
        clearinghouse_queued: true,
        clearinghouse_accepted: false,
        acknowledged: false,
        denial_checked: false,
        paid: false,
        learning_updated: false,
        analytics_done: false,
      },
      stage_status: {
        ...(pipeline?.stage_status || {}),
        OCR: "COMPLETED",
        ELIGIBILITY: "COMPLETED",
        VALIDATION: "COMPLETED",
        COMPLIANCE: "COMPLETED",
        SUBMISSION: "COMPLETED",
        CLEARINGHOUSE: "WAITING_FOR_APPROVAL",
        DENIAL_AI: "PENDING",
        PAYMENT: "PENDING",
        LEARNING: "PENDING",
        ANALYTICS: "PENDING",
      },
    },
    updatedAt: payload?.timestamp || rawPayload?.timestamp || new Date().toISOString(),
    last_activity_at: payload?.timestamp || rawPayload?.timestamp || new Date().toISOString(),
  };
};

export const backendStateFromPayload = (rawPayload: any) => {
  const payload = normalizePipelineEventPayload(rawPayload);
  const claimId = getEventClaimId(payload) || getEventClaimId(rawPayload);

  if (isClearinghouseWaitingEvent(payload) || isClearinghouseWaitingEvent(rawPayload)) {
    return buildClearinghouseWaitingState(payload, rawPayload, claimId);
  }

  const claim = {
    ...getNestedClaim(rawPayload),
    ...getNestedClaim(payload),
    ...(payload?.claim || payload?.data?.claim || rawPayload?.claim || {}),
  };

  const pipeline = {
    ...getNestedPipeline(rawPayload),
    ...getNestedPipeline(payload),
    ...(payload?.pipeline || {}),
  };

  const status = getEventStatus(payload) || getEventStatus(rawPayload);
  const stage =
    payload?.current_stage ||
    payload?.stage ||
    rawPayload?.current_stage ||
    rawPayload?.stage ||
    pipeline?.current_stage;

  const normalizedStage = normalizeKey(stage);

  return {
    ...claim,
    ...payload,
    claim_id: claimId,
    status,
    stage: normalizedStage || status,
    pipeline_state:
      payload?.pipeline_state ||
      rawPayload?.pipeline_state ||
      pipeline?.pipeline_state ||
      status,
    pipeline_status:
      payload?.pipeline_status ||
      rawPayload?.pipeline_status ||
      pipeline?.pipeline_status ||
      status,
    current_stage: normalizedStage || status,
    current_agent:
      payload?.current_agent ||
      rawPayload?.current_agent ||
      payload?.agent ||
      pipeline?.current_agent,
    active_step:
      payload?.active_step ||
      rawPayload?.active_step ||
      payload?.current_step ||
      rawPayload?.current_step ||
      payload?.step ||
      pipeline?.active_step,
    progress:
      payload?.progress ??
      rawPayload?.progress ??
      payload?.data?.progress ??
      pipeline?.progress,
    pipeline,
    updatedAt: payload?.timestamp || rawPayload?.timestamp || new Date().toISOString(),
    last_activity_at: payload?.timestamp || rawPayload?.timestamp || new Date().toISOString(),
  };
};

export const processingStatusMessage = (event: any) => {
  const message = eventMessage(event);
  if (message) return message;

  const stage = getEventStageKey(event);
  const status = getEventStatus(event);

  if (!stage && !status) return "Processing update";

  return `${stage} ${status}`.trim();
};