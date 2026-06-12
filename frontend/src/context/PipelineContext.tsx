import React, { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useRef } from "react";
import { PipelineEvent } from "../services/websocket";
import { usePipelineSubscription } from "../hooks/usePipelineSubscription";
import {
  normalizePipelineEventPayload,
  normalizePipelineStatus,
  normalizePipelineStep,
  pipelineEventKey,
} from "../utils/pipelineSync";

export type ClaimPipelineState = {
  claimId: string;
  claimType?: string;
  uploadMode?: string;
  uploadSource?: string;
  currentAgent?: string;
  currentStep?: string;
  status?: string;
  submissionId?: string;
  submissionStatus?: string;
  complianceStatus?: string;
  validationStatus?: string;
  analyticsStatus?: string;
  paymentStatus?: string;
  currentStage?: string;
  queueState?: string;
  progress?: number;
  pipelineLoaded?: boolean;
  completedStages?: string[];
  snapshot?: Record<string, any>;
  pipelineSteps: Record<string, boolean | string>;
  updatedAt?: string;
  events: PipelineEvent[];
};

export type BulkProgressState = {
  queued: number;
  processing: number;
  completed: number;
  failed: number;
};

type PipelineContextValue = {
  claims: Record<string, ClaimPipelineState>;
  events: PipelineEvent[];
  bulkProgress: BulkProgressState;
  upsertClaimSnapshot: (claimId: string, patch: Partial<ClaimPipelineState>) => void;
  clearPipelineState: () => void;
  dispatchClaimEvent: (event: PipelineEvent) => void;
  getClaimState: (claimId?: string) => ClaimPipelineState | undefined;
};

const PipelineContext = createContext<PipelineContextValue | undefined>(undefined);

const terminalStatuses = new Set(["COMPLETED", "PAID", "ACKNOWLEDGED"]);
const failedStatuses = new Set(["FAILED", "DENIED", "REJECTED", "HITL_REQUIRED", "HARD_REJECT"]);
const processingStatuses = new Set(["PROCESSING", "RUNNING"]);
const queuedStatuses = new Set(["QUEUED", "PENDING", "NEW", "CREATED", "SUBMITTED", "WAITING_FOR_APPROVAL", "WAITING_FOR_REVIEW"]);
const STEP_MAP: Record<string, string> = {
  intake: "intake",
  intake_started: "intake",
  intake_running: "intake",
  intake_completed: "intake",
  upload: "intake",
  claim_created: "intake",
  ocr: "ocr",
  ocr_extraction: "ocr",
  ocr_started: "ocr",
  ocr_running: "ocr",
  ocr_completed: "ocr",
  extract: "ocr",
  extraction: "ocr",
  extraction_done: "ocr",
  extracted: "ocr",
  mapped: "ocr",
  validation_completed: "validation",
  compliance_completed: "compliance",
  submission: "submission",
  submission_started: "submission",
  submission_running: "submission",
  submission_completed: "submission",
  claim_form: "submission",
  cms1500: "submission",
  cms_1500: "submission",
  ub04: "submission",
  ub_04: "submission",
  generating_cms1500: "submission",
  generating_ub04: "submission",
  edi: "submission",
  edi_837: "submission",
  x12: "submission",
  "837": "submission",
  generating_837: "submission",
  sending_to_clearinghouse: "submission",
  denial: "denial_ai",
  denial_ai: "denial_ai",
  denialai: "denial_ai",
  denied: "denial_ai",
  learning: "learning",
  feedback: "learning",
  feedback_loop: "learning",
  analytics: "analytics",
  acknowledgment: "clearinghouse",
  ack: "clearinghouse",
  clearinghouse_auto: "clearinghouse",
  waiting_for_approval: "clearinghouse",
  pending_clearinghouse: "clearinghouse",
  eligibility: "validation",
  eligibility_checked: "validation",
  eligibility_completed: "validation",
  payment_reconciliation: "payment",
  payment_posted: "payment",
};

const STAGE_ORDER = ["ocr", "validation", "compliance", "submission", "clearinghouse", "denial_ai", "payment", "learning", "analytics", "completed"];
const EVENT_STAGE_ALIASES: Record<string, string> = {
  intake: "ocr",
  intake_started: "ocr",
  intake_running: "ocr",
  intake_completed: "ocr",
  upload: "ocr",
  claim_created: "ocr",
  ocr: "ocr",
  ocr_started: "ocr",
  ocr_running: "ocr",
  ocr_completed: "ocr",
  ocr_extraction: "ocr",
  extract: "ocr",
  extraction: "ocr",
  extraction_done: "ocr",
  extracted: "ocr",
  mapped: "ocr",
  validation: "validation",
  validation_started: "validation",
  validation_running: "validation",
  validation_completed: "validation",
  rules: "validation",
  rules_validation: "validation",
  rules_validated: "validation",
  eligibility: "validation",
  eligibility_started: "validation",
  eligibility_running: "validation",
  eligibility_completed: "validation",
  eligibility_checked: "validation",
  compliance: "compliance",
  compliance_started: "compliance",
  compliance_running: "compliance",
  compliance_completed: "compliance",
  claim_form: "submission",
  cms1500: "submission",
  cms_1500: "submission",
  ub04: "submission",
  ub_04: "submission",
  generating_cms1500: "submission",
  generating_ub04: "submission",
  edi: "submission",
  edi_837: "submission",
  x12: "submission",
  "837": "submission",
  generating_837: "submission",
  submission: "submission",
  submission_started: "submission",
  submission_running: "submission",
  submission_completed: "submission",
  sending_to_clearinghouse: "submission",
  clearinghouse: "clearinghouse",
  clearinghouse_pending: "clearinghouse",
  clearinghouse_started: "clearinghouse",
  clearinghouse_running: "clearinghouse",
  clearinghouse_completed: "clearinghouse",
  denial: "denial_ai",
  denial_ai: "denial_ai",
  denial_ai_started: "denial_ai",
  denial_ai_running: "denial_ai",
  denial_ai_completed: "denial_ai",
  payment: "payment",
  payment_started: "payment",
  payment_running: "payment",
  payment_completed: "payment",
  learning: "learning",
  learning_started: "learning",
  learning_running: "learning",
  learning_completed: "learning",
  analytics: "analytics",
  analytics_started: "analytics",
  analytics_running: "analytics",
  analytics_completed: "analytics",
  pipeline_completed: "completed",
  command_center_transfer: "completed",
  claim_completed: "completed",
};
const LIVE_HANDOFF_NEXT: Record<string, string> = {
  ocr: "validation",
  validation: "compliance",
  compliance: "submission",
  submission: "clearinghouse",
  clearinghouse: "payment",
  denial_ai: "payment",
  payment: "learning",
  learning: "analytics",
  analytics: "completed",
};
const LIVE_COMPLETED_BEFORE: Record<string, string[]> = {
  validation: ["OCR"],
  compliance: ["OCR", "VALIDATION"],
  submission: ["OCR", "VALIDATION", "COMPLIANCE"],
  clearinghouse: ["OCR", "VALIDATION", "COMPLIANCE", "SUBMISSION"],
  denial_ai: ["OCR", "VALIDATION", "COMPLIANCE", "SUBMISSION", "CLEARINGHOUSE"],
  payment: ["OCR", "VALIDATION", "COMPLIANCE", "SUBMISSION", "CLEARINGHOUSE", "DENIAL_AI"],
  learning: ["OCR", "VALIDATION", "COMPLIANCE", "SUBMISSION", "CLEARINGHOUSE", "DENIAL_AI", "PAYMENT"],
  analytics: ["OCR", "VALIDATION", "COMPLIANCE", "SUBMISSION", "CLEARINGHOUSE", "DENIAL_AI", "PAYMENT", "LEARNING"],
  completed: ["OCR", "VALIDATION", "COMPLIANCE", "SUBMISSION", "CLEARINGHOUSE", "DENIAL_AI", "PAYMENT", "LEARNING", "ANALYTICS"],
};

const normalize = (value?: string) => {
  return normalizePipelineStatus(value, "PENDING") || "PENDING";
};

const read = (event: PipelineEvent, key: string) =>
  event?.[key] ?? event?.data?.[key] ?? event?.metadata?.[key] ?? event?.data?.claim?.[key];

const readSnapshot = (event: PipelineEvent) =>
  event?.claim || event?.data?.claim || event?.payload?.claim || event?.payload || undefined;

const normalizeStepKey = (value?: string) => {
  const key = String(value || "").trim().toLowerCase().replace(/[\s-]+/g, "_");
  return EVENT_STAGE_ALIASES[key] || STEP_MAP[key] || normalizePipelineStep(value) || key;
};

const eventStageKey = (event: PipelineEvent) => {
  const candidates = [
    read(event, "active_step"),
    read(event, "current_step"),
    event.step,
    read(event, "current_stage"),
    read(event, "active_stage"),
    event.stage,
    read(event, "current_agent"),
    event.agent,
    event.type,
    event.event,
  ];

  for (const value of candidates) {
    const token = normalizeStepKey(String(value || ""));
    if (!token) continue;
    if (STAGE_ORDER.includes(token)) return token;
    const match = STAGE_ORDER.find((stage) => token.includes(stage) || stage.includes(token));
    if (match) return match;
  }
  return "";
};

const completedBefore = (stageKey: string) => {
  if (LIVE_COMPLETED_BEFORE[stageKey]) return LIVE_COMPLETED_BEFORE[stageKey];
  const index = STAGE_ORDER.indexOf(stageKey);
  return index > 0 ? STAGE_ORDER.slice(0, index).map((stage) => stage.toUpperCase()) : [];
};

const nextStageAfter = (stageKey: string) => {
  if (LIVE_HANDOFF_NEXT[stageKey]) return LIVE_HANDOFF_NEXT[stageKey];
  const index = STAGE_ORDER.indexOf(stageKey);
  return index >= 0 ? STAGE_ORDER[index + 1] : undefined;
};

const getClaimId = (event: PipelineEvent) =>
  read(event, "claim_id") || read(event, "claimId") || event.pipeline?.claim_id;

const normalizeClaimType = (value?: string) => {
  const type = String(value || "").trim().toUpperCase().replace(/[-_\s]/g, "");
  if (type === "CMS1500" || type === "CMS") return "CMS1500";
  if (type === "UB04" || type === "UB") return "UB04";
  if (type === "BOTH" || type === "CMS1500UB04" || type === "UB04CMS1500") return "BOTH";
  return undefined;
};

const classifyStep = (event: PipelineEvent) =>
  normalizeStepKey(String(event.step || event.stage || event.agent || event.type || ""));

const stepFromPipeline = (event: PipelineEvent) => {
  const steps = event.pipeline?.steps;
  const directStep = classifyStep(event);
  const status = normalize(event.status);
  const directSteps: Record<string, boolean | string> = {};
  if (["denial_ai", "learning", "analytics", "payment", "clearinghouse"].includes(directStep)) {
    directSteps[directStep] = status;
    if (status === "COMPLETED" || status === "PAID" || status === "ACCEPTED" || status === "AUTO_ACCEPTED") {
      if (directStep === "denial_ai") directSteps.denial_ai_analyzed = true;
      if (directStep === "learning") directSteps.learning_updated = true;
      if (directStep === "analytics") directSteps.analytics_done = true;
      if (directStep === "payment") directSteps.paid = true;
      if (directStep === "clearinghouse") directSteps.clearinghouse_accepted = true;
    }
  }
  if (!steps || typeof steps !== "object") return directSteps;

  return Object.entries(steps).reduce<Record<string, boolean | string>>((acc, [key, value]) => {
    acc[key] = value as boolean | string;
    return acc;
  }, directSteps);
};

const orderEvents = (items: PipelineEvent[]) =>
  [...items].sort((a, b) => String(b.timestamp || "").localeCompare(String(a.timestamp || "")));

const isFinalClaimStatus = (status?: string) => ["PAID", "COMPLETED", "APPROVED", "REJECTED", "CLOSED", "FINALIZED"].includes(normalize(status));
const eventTime = (value?: string) => {
  const time = value ? new Date(value).getTime() : Date.now();
  return Number.isFinite(time) ? time : Date.now();
};
const samePayload = (left: any, right: any) => {
  try {
    return JSON.stringify(left) === JSON.stringify(right);
  } catch {
    return false;
  }
};

const derivePatch = (event: PipelineEvent): Partial<ClaimPipelineState> => {
  const backendState =
    (event.pipeline && Object.keys(event.pipeline).length ? event.pipeline : undefined) ||
    (event.claim && typeof event.claim === "object" ? event.claim : undefined) ||
    (event.data && Object.keys(event.data).length ? event.data : undefined) ||
    event;
  const pipeline = backendState.pipeline || event.pipeline || {};
  const status = normalize(backendState.pipeline_state || backendState.status || event.pipeline_state || event.status);
  const currentStage = backendState.current_stage ?? backendState.currentStage ?? event.current_stage ?? event.currentStage;
  const currentAgent = backendState.current_agent ?? backendState.currentAgent ?? event.current_agent ?? event.currentAgent;
  const activeStep = backendState.active_step ?? backendState.current_step ?? backendState.currentStep ?? event.active_step ?? event.current_step ?? event.currentStep;
  const claimType =
    normalizeClaimType(backendState.claim_type) ||
    normalizeClaimType(backendState.claimType) ||
    normalizeClaimType(backendState.form_type) ||
    normalizeClaimType(backendState.formType);
  const uploadMode = backendState.upload_mode || backendState.uploadMode;
  const uploadSource = backendState.upload_source || backendState.uploadSource || backendState.source;
  const rawProgress = backendState.progress ?? event.progress;
  const explicitProgress =
    rawProgress !== undefined && rawProgress !== null && rawProgress !== ""
      ? Number(rawProgress)
      : undefined;

  const patch: Partial<ClaimPipelineState> = {
    currentAgent,
    currentStage,
    currentStep: activeStep ? normalizeStepKey(activeStep) : undefined,
    status,
    queueState: backendState.queue_state || backendState.queueState,
    progress: Number.isFinite(explicitProgress) ? Math.min(100, Math.max(0, Math.round(Number(explicitProgress)))) : undefined,
    completedStages: backendState.completed_stages || backendState.completedStages || pipeline.completed_stages,
    submissionId: backendState.submission_id || backendState.submissionId || event.submission_id,
    snapshot: backendState,
    pipelineSteps: pipeline.steps || backendState.steps || {},
    pipelineLoaded: true,
    updatedAt: backendState.updated_at || backendState.updatedAt || event.timestamp || new Date().toISOString(),
  };

  if (claimType) patch.claimType = claimType;
  if (uploadMode) patch.uploadMode = String(uploadMode).toLowerCase();
  if (uploadSource) patch.uploadSource = String(uploadSource).toUpperCase();

  return patch;
};

type PipelineReducerState = {
  claims: Record<string, ClaimPipelineState>;
  events: PipelineEvent[];
};

type PipelineAction =
  | { type: "PIPELINE_UPDATE"; event: PipelineEvent }
  | { type: "CLAIM_UPDATE"; event: PipelineEvent }
  | { type: "PROGRESS_UPDATE"; event: PipelineEvent }
  | { type: "STATUS_UPDATE"; event: PipelineEvent }
  | { type: "WS_CLAIM_UPDATE"; event: PipelineEvent }
  | { type: "WS_STAGE_UPDATE"; event: PipelineEvent }
  | { type: "CLAIM_PROGRESS_UPDATE"; event: PipelineEvent }
  | { type: "CLAIM_COMPLETED"; event: PipelineEvent }
  | { type: "WS_EVENT_BATCH"; events: PipelineEvent[] }
  | { type: "API_CLAIM_SNAPSHOT"; claimId: string; patch: Partial<ClaimPipelineState> }
  | { type: "REMOVE_CLAIM"; claimId: string }
  | { type: "CLEAR" };

type PipelineEventAction = Exclude<PipelineAction, { type: "WS_EVENT_BATCH" } | { type: "API_CLAIM_SNAPSHOT" } | { type: "REMOVE_CLAIM" } | { type: "CLEAR" }>;

const actionForPipelineEvent = (event: PipelineEvent): PipelineEventAction => {
  const eventName = String(event.type || event.event || "").toLowerCase();
  const status = normalize(event.status || read(event, "status"));
  const actionType =
    eventName.includes("completed") || eventName.includes("command_center") || isFinalClaimStatus(status)
      ? "STATUS_UPDATE"
      : event.progress !== undefined || read(event, "progress") !== undefined
      ? "PROGRESS_UPDATE"
      : event.stage || event.step || read(event, "current_stage")
      ? "PIPELINE_UPDATE"
      : "CLAIM_UPDATE";

  return { type: actionType, event } as PipelineEventAction;
};

const claimEventList = (event: PipelineEvent, current: ClaimPipelineState) =>
  orderEvents([event, ...(current.events || [])]).slice(0, 120);

const mergeClaimPatch = (
  current: ClaimPipelineState | undefined,
  claimId: string,
  patch: Partial<ClaimPipelineState>,
  event?: PipelineEvent
) => {
  const existing = current || { claimId, pipelineSteps: {}, events: [] };
  const incomingTime = eventTime(patch.updatedAt);
  const existingTime = existing.updatedAt ? eventTime(existing.updatedAt) : 0;
  const existingProgress = existing.progress === undefined || existing.progress === null ? undefined : Number(existing.progress);
  const patchProgress = patch.progress === undefined || patch.progress === null ? undefined : Number(patch.progress);
  const stale = Boolean(
    existingTime &&
    incomingTime < existingTime &&
    Number.isFinite(existingProgress) &&
    Number.isFinite(patchProgress) &&
    Number(patchProgress) < Number(existingProgress)
  );

  if (stale) {
    console.log("[sync] stale ignored");
    return event ? { ...existing, events: claimEventList(event, existing) } : existing;
  }

  const progress =
    existingProgress === undefined && patchProgress === undefined
      ? undefined
      : Math.max(
          Number.isFinite(existingProgress) ? Number(existingProgress) : 0,
          Number.isFinite(patchProgress) ? Number(patchProgress) : 0
        );

  return {
    ...existing,
    ...patch,
    claimId,
    progress,
    currentStage: patch.currentStage || existing.currentStage,
    pipelineSteps: {
      ...(existing.pipelineSteps || {}),
      ...(patch.pipelineSteps || {}),
    },
    events: event ? claimEventList(event, existing) : orderEvents([...(patch.events || []), ...(existing.events || [])]).slice(0, 160),
    updatedAt: patch.updatedAt || existing.updatedAt || new Date().toISOString(),
  };
};

const pipelineReducer = (state: PipelineReducerState, action: PipelineAction): PipelineReducerState => {
  if (!["WS_EVENT_BATCH"].includes(action.type)) {
    console.groupCollapsed("[pipeline-reducer] Reducer update", action.type);
    console.log("Action", action);
    console.groupEnd();
  }
  if (action.type === "CLEAR") return { claims: {}, events: [] };
  if (action.type === "WS_EVENT_BATCH") {
    return action.events.reduce((nextState, event) => pipelineReducer(nextState, actionForPipelineEvent(event)), state);
  }
  if (action.type === "REMOVE_CLAIM") {
    const next = { ...state.claims };
    delete next[action.claimId];
    return { ...state, claims: next };
  }
  if (action.type === "API_CLAIM_SNAPSHOT") {
    const current = state.claims[action.claimId];
    const nextClaim = mergeClaimPatch(current, action.claimId, action.patch);
    if (current && samePayload(current, nextClaim)) return state;

    return {
      ...state,
      claims: {
        ...state.claims,
        [action.claimId]: nextClaim,
      },
    };
  }

  const event = normalizePipelineEventPayload(action.event);
  const claimId = getClaimId(event);
  const events = event.type === "pong" ? state.events : [event, ...state.events].slice(0, 200);
  if (!claimId) return { ...state, events };
  if ((event.type || event.event) === "claim_deleted") {
    const next = { ...state.claims };
    delete next[claimId];
    return { claims: next, events };
  }

  const current = state.claims[claimId];
  const patch = derivePatch(event);
  const currentFinal = isFinalClaimStatus(current?.status);
  const patchWaiting = ["WAITING_FOR_APPROVAL", "WAITING_FOR_REVIEW"].includes(normalize(patch.status));
  if (currentFinal && patchWaiting) return { ...state, events };
  const nextClaim = mergeClaimPatch(current, claimId, patch, event);

  return {
    claims: {
      ...state.claims,
      [claimId]: nextClaim,
    },
    events,
  };
};

const classifyBulkStatus = (claim: ClaimPipelineState) => {
  const status = normalize(claim.paymentStatus || claim.submissionStatus || claim.status);

  if (terminalStatuses.has(status)) return "completed";
  if (failedStatuses.has(status)) return "failed";
  if (processingStatuses.has(status)) return "processing";
  if (queuedStatuses.has(status)) return "queued";
  return claim.currentAgent || claim.currentStep ? "processing" : "queued";
};

export const PipelineProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [state, dispatch] = useReducer(pipelineReducer, { claims: {}, events: [] });
  const seenEventKeys = useRef<Set<string>>(new Set());
  const pendingEventsRef = useRef<PipelineEvent[]>([]);
  const flushTimerRef = useRef<number | null>(null);

  const clearPipelineState = useCallback(() => {
    seenEventKeys.current.clear();
    pendingEventsRef.current = [];
    if (flushTimerRef.current) {
      window.clearTimeout(flushTimerRef.current);
      flushTimerRef.current = null;
    }
    dispatch({ type: "CLEAR" });
  }, []);

  const upsertClaimSnapshot = useCallback((claimId: string, patch: Partial<ClaimPipelineState>) => {
    if (!claimId) return;
    dispatch({ type: "API_CLAIM_SNAPSHOT", claimId, patch });
  }, []);

  const flushPipelineEvents = useCallback(() => {
    flushTimerRef.current = null;
    const batch = pendingEventsRef.current;
    pendingEventsRef.current = [];
    if (batch.length) dispatch({ type: "WS_EVENT_BATCH", events: batch });
  }, []);

  const enqueuePipelineEvent = useCallback((event: PipelineEvent) => {
    pendingEventsRef.current.push(event);
    if (pendingEventsRef.current.length >= 24) {
      if (flushTimerRef.current) window.clearTimeout(flushTimerRef.current);
      flushPipelineEvents();
      return;
    }

    if (!flushTimerRef.current) {
      flushTimerRef.current = window.setTimeout(flushPipelineEvents, 120);
    }
  }, [flushPipelineEvents]);

  const handlePipelineEvent = useCallback((event: PipelineEvent) => {
    const normalizedEvent = normalizePipelineEventPayload(event);
    if (normalizedEvent.type === "pong") return;

    const claimId = getClaimId(normalizedEvent);
    const eventKey = pipelineEventKey(normalizedEvent);

    if (seenEventKeys.current.has(eventKey)) {
      console.groupCollapsed("[pipeline-reducer] Ignored duplicate event", eventKey);
      console.log("Duplicate event", normalizedEvent);
      console.groupEnd();
      return;
    }
    seenEventKeys.current.add(eventKey);
    if (seenEventKeys.current.size > 1000) {
      seenEventKeys.current = new Set([...seenEventKeys.current].slice(-500));
    }

    enqueuePipelineEvent(normalizedEvent);
  }, [enqueuePipelineEvent]);

  useEffect(() => {
    return () => {
      if (flushTimerRef.current) window.clearTimeout(flushTimerRef.current);
      flushTimerRef.current = null;
      pendingEventsRef.current = [];
    };
  }, []);

  usePipelineSubscription(handlePipelineEvent);

  const bulkProgress = useMemo(() => {
    return Object.values(state.claims).reduce(
      (acc, claim) => {
        acc[classifyBulkStatus(claim)] += 1;
        return acc;
      },
      { queued: 0, processing: 0, completed: 0, failed: 0 }
    );
  }, [state.claims]);

  const getClaimState = useCallback((claimId?: string) => (claimId ? state.claims[claimId] : undefined), [state.claims]);
  const dispatchClaimEvent = useCallback((event: PipelineEvent) => handlePipelineEvent(event), [handlePipelineEvent]);

  const value = useMemo(
    () => ({ claims: state.claims, events: state.events, bulkProgress, upsertClaimSnapshot, clearPipelineState, dispatchClaimEvent, getClaimState }),
    [state.claims, state.events, bulkProgress, upsertClaimSnapshot, clearPipelineState, dispatchClaimEvent, getClaimState]
  );

  return <PipelineContext.Provider value={value}>{children}</PipelineContext.Provider>;
};

export const usePipelineContext = () => {
  const context = useContext(PipelineContext);
  if (!context) throw new Error("usePipelineContext must be used inside PipelineProvider");
  return context;
};
