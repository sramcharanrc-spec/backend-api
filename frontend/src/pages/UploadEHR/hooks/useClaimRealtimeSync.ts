import { useEffect, useState } from "react";
import {
  addConnectionHealthListener,
  addPipelineEventListener,
  WebSocketHealth,
} from "../../../services/websocket";
import { normalizePipelineEventPayload } from "../../../utils/pipelineSync";
import {
  eventToPipelinePatch,
  normalizeStepKey as normalizeLiveStepKey,
} from "../utils/pipelineLiveMerge";

type UseClaimRealtimeSyncOptions = {
  mergeItems?: (claims: any[]) => void;
  onCompleted?: (claimId: string, claim: any) => void;
};

export const UPLOAD_EHR_REALTIME_EVENT_TYPES = new Set([
  "agent_update",
  "pipeline_update",
  "pipeline_started",
  "pipeline_resumed",
  "pipeline_completed",
  "manual_review_required",
  "hitl_required",
  "case_created",
  "case_assigned",
  "case_escalated",
  "clearinghouse_queued",
  "clearinghouse_accepted",
  "payment_completed",
  "denial_analyzed",
  "claim_created",
  "claim_updated",
  "claim_processing",
  "claim_completed",
]);

const getClaimId = (item: any) =>
  item?.claim_id ||
  item?.claimId ||
  item?.id ||
  item?.payload?.claim_id ||
  item?.payload?.claimId ||
  item?.payload?.id ||
  item?.payload?.claim?.claim_id ||
  item?.payload?.claim?.claimId ||
  item?.payload?.claim?.id ||
  item?.claim?.claim_id ||
  item?.claim?.claimId ||
  item?.claim?.id ||
  item?.data?.claim_id ||
  item?.data?.claimId ||
  item?.data?.id ||
  item?.data?.claim?.claim_id ||
  item?.data?.claim?.claimId ||
  item?.data?.claim?.id;

const normalizeStatus = (value: any) =>
  String(value || "")
    .trim()
    .toUpperCase()
    .replace(/[\s-]+/g, "_");

const normalizeStage = (value: any) =>
  String(value || "")
    .trim()
    .toUpperCase()
    .replace(/[\s-]+/g, "_");

const toUiStage = (value: any) => {
  const stage = normalizeStage(value);

  if (stage === "EXTRACT" || stage === "EXTRACTION") {
    return "OCR";
  }

  if (stage === "VALIDATE") {
    return "VALIDATION";
  }

  if (
    stage === "ACK" ||
    stage === "ACKNOWLEDGMENT" ||
    stage === "ACKNOWLEDGEMENT" ||
    stage === "PAYER" ||
    stage === "PAYER_ACK" ||
    stage === "PAYER_ACKNOWLEDGMENT" ||
    stage === "PAYER_ACKNOWLEDGEMENT" ||
    stage === "PAYER_ACKNOWLEDGED"
  ) {
    return "ACKNOWLEDGMENT";
  }

  if (stage === "DENIAL" || stage === "DENIAL_AGENT" || stage === "DENIALAI") {
    return "DENIAL_AI";
  }

  if (stage === "FINISH" || stage === "COMPLETE") {
    return "ANALYTICS";
  }

  return stage || "PIPELINE";
};

const stageProgressMap: Record<string, number> = {
  UPLOAD_API: 5,
  QUEUE: 8,
  EXTRACT: 15,
  EXTRACTION: 15,
  OCR: 15,
  ELIGIBILITY: 25,
  VALIDATION: 40,
  COMPLIANCE: 55,
  SUBMISSION: 65,
  CLEARINGHOUSE: 70,
  ACK: 74,
  ACKNOWLEDGMENT: 74,
  ACKNOWLEDGEMENT: 74,
  PAYER: 74,
  PAYER_ACK: 74,
  PAYER_ACKNOWLEDGMENT: 74,
  PAYER_ACKNOWLEDGEMENT: 74,
  DENIAL: 80,
  DENIAL_AI: 80,
  PAYMENT: 88,
  LEARNING: 94,
  ANALYTICS: 100,
  FINISH: 100,
  COMPLETED: 100,
};

const normalizeActiveStep = (stage: any) => {
  const stageKey = toUiStage(stage);

  const map: Record<string, string> = {
    UPLOAD_API: "upload",
    QUEUE: "queue",
    EXTRACT: "extraction",
    EXTRACTION: "extraction",
    OCR: "extraction",
    ELIGIBILITY: "eligibility",
    VALIDATION: "validation",
    COMPLIANCE: "compliance",
    SUBMISSION: "submission",
    CLEARINGHOUSE: "clearinghouse",
    ACKNOWLEDGMENT: "acknowledgment",
    PAYER: "acknowledgment",
    PAYER_ACKNOWLEDGMENT: "acknowledgment",
    DENIAL: "denial_ai",
    DENIAL_AI: "denial_ai",
    PAYMENT: "payment",
    LEARNING: "learning",
    ANALYTICS: "analytics",
    FINISH: "completed",
    COMPLETED: "completed",
  };

  return map[stageKey] || String(stageKey || "pipeline").toLowerCase();
};

const isClearinghouseWaitingEvent = (event: any) => {
  const stage = normalizeStatus(
    event?.stage ||
      event?.current_stage ||
      event?.claim?.current_stage ||
      event?.claim?.stage ||
      event?.pipeline?.current_stage
  );

  const pipelineState = normalizeStatus(
    event?.pipeline_state ||
      event?.pipeline_status ||
      event?.pipeline?.pipeline_state ||
      event?.claim?.pipeline_state ||
      event?.claim?.pipeline_status
  );

  const status = normalizeStatus(
    event?.status ||
      event?.claim?.status ||
      event?.pipeline?.pipeline_status
  );

  const clearinghouseStatus = normalizeStatus(
    event?.clearinghouse_status ||
      event?.claim?.clearinghouse_status ||
      event?.pipeline?.clearinghouse_status
  );

  return (
    pipelineState === "WAITING_FOR_APPROVAL" ||
    pipelineState === "PENDING_CLEARINGHOUSE" ||
    pipelineState === "PENDING_APPROVAL" ||
    status === "WAITING_FOR_APPROVAL" ||
    status === "PENDING_CLEARINGHOUSE" ||
    status === "PENDING_APPROVAL" ||
    clearinghouseStatus === "PENDING_CLEARINGHOUSE" ||
    clearinghouseStatus === "WAITING_FOR_APPROVAL" ||
    event?.review_required === true ||
    event?.approval_required === true ||
    event?.pipeline_paused === true ||
    event?.claim?.review_required === true ||
    event?.claim?.approval_required === true ||
    event?.claim?.pipeline_paused === true ||
    event?.pipeline?.review_required === true ||
    event?.pipeline?.approval_required === true ||
    event?.pipeline?.pipeline_paused === true ||
    stage === "CLEARINGHOUSE_REVIEW" ||
    stage === "CLEARINGHOUSE_APPROVAL"
  );
};

const isCompletedEvent = (claim: any) => {
  const status = normalizeStatus(claim?.status);
  const pipelineState = normalizeStatus(claim?.pipeline_state);
  const stage = normalizeStatus(claim?.current_stage || claim?.stage);

  return (
    status === "COMPLETED" ||
    status === "COMPLETE" ||
    status === "PAID" ||
    status === "CLAIM_COMPLETED" ||
    status === "PAYMENT_COMPLETED" ||
    status === "FINALIZED" ||
    status === "SUCCESS" ||
    pipelineState === "COMPLETED" ||
    stage === "FINISH" ||
    stage === "ANALYTICS"
  );
};

const getProgressValue = (...values: any[]) => {
  for (const value of values) {
    const numeric = Number(value);

    if (Number.isFinite(numeric)) {
      return Math.max(0, Math.min(100, numeric));
    }
  }

  return undefined;
};

const isPlainObject = (value: any) =>
  Boolean(value && typeof value === "object" && !Array.isArray(value));

const mergeObjects = (...objects: any[]) =>
  objects.reduce((merged, current) => {
    if (!isPlainObject(current)) return merged;

    Object.entries(current).forEach(([key, value]) => {
      if (value === undefined || value === null || value === "") return;

      if (isPlainObject(value) && isPlainObject(merged[key])) {
        merged[key] = mergeObjects(merged[key], value);
        return;
      }

      merged[key] = value;
    });

    return merged;
  }, {} as Record<string, any>);

const mergePipelineObjects = (...pipelines: any[]) => {
  const merged = mergeObjects(...pipelines);

  return {
    ...merged,
    steps: mergeObjects(...pipelines.map((pipeline) => pipeline?.steps)),
    stage_status: mergeObjects(...pipelines.map((pipeline) => pipeline?.stage_status)),
    agents: mergeObjects(...pipelines.map((pipeline) => pipeline?.agents)),
  };
};

const hasKeys = (value: any) =>
  isPlainObject(value) && Object.keys(value).length > 0;

const getEventType = (event: any) =>
  String(event?.type || event?.event || event?.data?.type || event?.payload?.type || "")
    .trim()
    .toLowerCase();

const getEventCase = (event: any) =>
  mergeObjects(
    event?.data?.case,
    event?.payload?.case,
    event?.case,
    event?.data?.hitl_case,
    event?.payload?.hitl_case,
    event?.hitl_case,
    event?.hitlCase,
    event?.claim?.case,
    event?.claim?.hitl_case
  );

const buildClaimFromRealtimeEvent = (event: any) => {
  const baseClaim = mergeObjects(
    event?.data?.claim,
    event?.payload?.claim,
    event?.claim
  );

  const pipeline = mergePipelineObjects(
    event?.data?.pipeline,
    event?.payload?.pipeline,
    event?.pipeline,
    event?.data?.claim?.pipeline,
    event?.payload?.claim?.pipeline,
    event?.claim?.pipeline,
    baseClaim?.pipeline
  );

  const claimId = getClaimId(event) || getClaimId(baseClaim);
  const eventCase = getEventCase(event);
  const timestamp = event?.timestamp || new Date().toISOString();

  if (isClearinghouseWaitingEvent(event)) {
    const progress =
      getProgressValue(event?.progress, baseClaim?.progress, pipeline?.progress) ??
      70;

    return {
      ...baseClaim,
      claim_id: claimId,
      id: baseClaim?.id || claimId,
      status: "PENDING_CLEARINGHOUSE",
      stage: "CLEARINGHOUSE",
      current_stage: "CLEARINGHOUSE",
      current_agent: "CLEARINGHOUSE",
      active_step: "clearinghouse",
      pipeline_state: "WAITING_FOR_APPROVAL",
      pipeline_status: "WAITING_FOR_APPROVAL",
      pipeline_result: "WAITING_FOR_APPROVAL",
      clearinghouse_status: "PENDING_CLEARINGHOUSE",
      review_required: true,
      approval_required: true,
      pipeline_paused: true,
      progress,
      pipeline: {
        ...mergePipelineObjects(pipeline, {
          steps: {
            clearinghouse: {
              status: "WAITING_FOR_APPROVAL",
              stage: "CLEARINGHOUSE",
              agent: "CLEARINGHOUSE",
              progress,
              message: "Awaiting clearinghouse approval",
              updated_at: timestamp,
            },
          },
          stage_status: {
            clearinghouse: "WAITING_FOR_APPROVAL",
          },
        }),
        pipeline_state: "WAITING_FOR_APPROVAL",
        pipeline_status: "WAITING_FOR_APPROVAL",
        pipeline_result: "WAITING_FOR_APPROVAL",
        current_stage: "CLEARINGHOUSE",
        current_agent: "CLEARINGHOUSE",
        active_step: "clearinghouse",
        clearinghouse_status: "PENDING_CLEARINGHOUSE",
        review_required: true,
        approval_required: true,
        pipeline_paused: true,
        progress,
      },
      ...(hasKeys(eventCase)
        ? { case: eventCase, hitl_case: eventCase, case_id: eventCase.case_id }
        : {}),
      updatedAt: timestamp,
      updated_at: timestamp,
      last_activity_at: timestamp,
      __realtime: true,
    };
  }

  const backendStage = normalizeStage(
    event?.current_stage ||
      event?.stage ||
      baseClaim?.current_stage ||
      baseClaim?.stage ||
      pipeline?.current_stage ||
      pipeline?.active_step ||
      "PIPELINE"
  );

  const currentStage = toUiStage(backendStage);

  const backendAgent =
    event?.current_agent ||
    baseClaim?.current_agent ||
    pipeline?.current_agent ||
    currentStage;

  const currentAgent =
    toUiStage(backendAgent) === "ACKNOWLEDGMENT"
      ? "PAYER_ACKNOWLEDGMENT"
      : backendAgent;

  const activeStep =
    event?.active_step ||
    baseClaim?.active_step ||
    pipeline?.active_step ||
    normalizeActiveStep(currentStage);

  const rawStatus = normalizeStatus(
    event?.status ||
      baseClaim?.status ||
      pipeline?.pipeline_status ||
      "PROCESSING"
  );
  const stepKey = normalizeLiveStepKey(activeStep || currentStage);
  const eventType = getEventType(event);
  const finalClaimEvent =
    eventType === "claim_completed" ||
    eventType === "pipeline_completed" ||
    rawStatus === "PAID" ||
    rawStatus === "CLAIM_COMPLETED" ||
    (rawStatus === "COMPLETED" && stepKey === "analytics");
  const stageOnlyAgentEvent = eventType === "agent_update" && !finalClaimEvent;

  const pipelineState =
    event?.pipeline_state ||
    baseClaim?.pipeline_state ||
    pipeline?.pipeline_state ||
    (rawStatus === "COMPLETED" || rawStatus === "PAID"
      ? currentStage === "ANALYTICS" || currentStage === "FINISH"
        ? "COMPLETED"
        : `${currentStage}_COMPLETED`
      : `${currentStage}_RUNNING`);

  const progress =
    getProgressValue(event?.progress, baseClaim?.progress, pipeline?.progress) ??
    stageProgressMap[currentStage] ??
    10;

  const uiStatus =
    stageOnlyAgentEvent
      ? baseClaim?.status || event?.claim?.status || "PROCESSING"
      : rawStatus === "RUNNING" ||
        rawStatus.endsWith("_RUNNING") ||
        String(pipelineState).endsWith("_RUNNING")
      ? "PROCESSING"
      : rawStatus === "SUCCESS"
      ? "COMPLETED"
      : rawStatus;

  const pipelineStatus =
    (stageOnlyAgentEvent ? undefined : event?.pipeline_status) ||
    baseClaim?.pipeline_status ||
    pipeline?.pipeline_status ||
    (finalClaimEvent ? rawStatus : undefined);

  const pipelineResult =
    event?.pipeline_result ||
    baseClaim?.pipeline_result ||
    pipeline?.pipeline_result;

  return {
    ...baseClaim,
    ...event,
    claim_id: claimId,
    id: baseClaim?.id || event?.id || claimId,
    status: uiStatus,
    backend_stage: backendStage,
    backend_agent: backendAgent,
    stage: currentStage,
    current_stage: currentStage,
    current_agent: currentAgent,
    active_step: activeStep,
    pipeline_state: pipelineState,
    pipeline_status: pipelineStatus,
    pipeline_result: pipelineResult,
    clearinghouse_status:
      event?.clearinghouse_status ||
      baseClaim?.clearinghouse_status ||
      pipeline?.clearinghouse_status,
    review_required:
      event?.review_required ?? baseClaim?.review_required ?? false,
    approval_required:
      event?.approval_required ?? baseClaim?.approval_required ?? false,
    pipeline_paused:
      event?.pipeline_paused ?? baseClaim?.pipeline_paused ?? false,
    progress,
    pipeline: {
      ...pipeline,
      steps: {
        ...(pipeline?.steps || {}),
        ...(stepKey
          ? {
              [stepKey]: {
                status: rawStatus,
                stage: currentStage,
                agent: currentAgent,
                progress,
                message: event?.message || rawStatus,
                updated_at: timestamp,
              },
            }
          : {}),
      },
      stage_status: {
        ...(pipeline?.stage_status || {}),
        ...(stepKey ? { [stepKey]: rawStatus } : {}),
      },
      pipeline_state: pipelineState,
      pipeline_status: pipelineStatus,
      pipeline_result: pipelineResult,
      current_stage: currentStage,
      current_agent: currentAgent,
      active_step: activeStep,
      progress,
    },
    ...(hasKeys(eventCase)
      ? { case: eventCase, hitl_case: eventCase, case_id: eventCase.case_id }
      : {}),
    updatedAt: timestamp,
    updated_at: timestamp,
    last_activity_at: timestamp,
    __realtime: true,
  };
};

const eventKey = (event: any) =>
  [
    event?.event_id || event?.id || "",
    getClaimId(event) || "global",
    getEventType(event) || event?.stage || event?.current_stage || "event",
    event?.stage || event?.current_stage || event?.active_step || "",
    event?.status || event?.pipeline_state || "",
    event?.timestamp || event?.updated_at || "",
  ].join("|");

export const useClaimRealtimeSync = ({
  mergeItems,
  onCompleted,
}: UseClaimRealtimeSyncOptions = {}) => {
  const [wsHealth, setWsHealth] = useState<WebSocketHealth>({
    status: "DISCONNECTED",
    connected: false,
    attempts: 0,
  });

  const [pollingFallbackActive, setPollingFallbackActive] = useState(false);
  const [events, setEvents] = useState<any[]>([]);

  useEffect(() => {
    return addConnectionHealthListener((health) => {
      setWsHealth(health);
      setPollingFallbackActive(
        !health.connected && health.status !== "CONNECTING"
      );
    });
  }, []);

  useEffect(() => {
    return addPipelineEventListener((rawPayload: any) => {
      const payload = normalizePipelineEventPayload(rawPayload);
      const claimId = getClaimId(payload) || getClaimId(rawPayload);

      if (!claimId) {
        console.info("[ws] ignoring event without claim_id", rawPayload);
        return;
      }

      const liveEvent = {
        ...rawPayload,
        ...payload,
        claim_id: claimId,
        claim: {
          ...(rawPayload?.claim || {}),
          ...(payload?.claim || {}),
          ...(payload?.data?.claim || {}),
        },
        pipeline: {
          ...(rawPayload?.pipeline || {}),
          ...(rawPayload?.payload?.pipeline || {}),
          ...(payload?.pipeline || {}),
          ...(payload?.payload?.pipeline || {}),
          ...(payload?.data?.pipeline || {}),
          ...(rawPayload?.claim?.pipeline || {}),
          ...(rawPayload?.payload?.claim?.pipeline || {}),
          ...(payload?.claim?.pipeline || {}),
          ...(payload?.payload?.claim?.pipeline || {}),
          ...(payload?.data?.claim?.pipeline || {}),
        },
        case:
          rawPayload?.case ||
          payload?.case ||
          payload?.data?.case ||
          rawPayload?.hitl_case ||
          payload?.hitl_case ||
          payload?.data?.hitl_case,
        hitl_case:
          rawPayload?.hitl_case ||
          payload?.hitl_case ||
          payload?.data?.hitl_case ||
          rawPayload?.case ||
          payload?.case ||
          payload?.data?.case,
      };

      const patchedEvent = eventToPipelinePatch(liveEvent);

      setEvents((prev) => [
        patchedEvent,
        ...prev.filter((event) => eventKey(event) !== eventKey(patchedEvent)),
      ].slice(0, 120));

      const claim = buildClaimFromRealtimeEvent(patchedEvent);

      mergeItems?.([claim]);

      if (isCompletedEvent(claim)) {
        onCompleted?.(claimId, claim);
      }
    });
  }, [mergeItems, onCompleted]);

  return {
    wsHealth,
    events,
    backendHealthy: wsHealth.connected ? true : null,
    pollingFallbackActive,
    pollingFallbackStopped: false,
  };
};
