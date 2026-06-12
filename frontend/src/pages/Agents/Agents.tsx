import React, { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  Bell,
  Bot,
  BrainCircuit,
  CheckCircle2,
  CircleDollarSign,
  ClipboardCheck,
  Cpu,
  Database,
  FileSearch,
  Gauge,
  GitBranch,
  HeartPulse,
  Network,
  RefreshCw,
  Route,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
  User,
  X,
  Zap,
} from "lucide-react";
import ClaimStatusBadge from "../../components/ClaimStatusBadge";
import { API_URL } from "../../config";
import { ClaimPipelineState } from "../../context/PipelineContext";
import { usePipeline } from "../../hooks/usePipeline";
import {
  AgentEvent,
  PipelineEvent,
  connectPipelineWS,
  WebSocketHealth,
} from "../../services/websocket";
import {
  AgentDetail,
  AgentStatusResponse,
  fetchAgentStatus,
} from "../../services/agentApi";
import {
  downloadCMS1500,
  downloadEDI,
  downloadUB04,
  generateAppeal,
  retrySubmission,
} from "../../services/rcmApi";
import { normalizeClaimsResponse } from "../../utils/claimSync";
import AgentCard from "./components/AgentCard";
import EnterpriseClaimObservability from "./components/EnterpriseClaimObservability";
import "./agents.css";

type WsState = "CONNECTED" | "CONNECTING" | "DISCONNECTED" | "ERROR";

const PIPELINE_STAGES = [
  { key: "intake", label: "OCR / Intake Agent", icon: Bot, stepKeys: ["intake", "upload", "claim_created", "case_orchestrated"] },
  { key: "ocr_extraction", label: "OCR Extraction Agent", icon: FileSearch, stepKeys: ["ocr", "ocr_extraction", "extract", "extraction", "extraction_done", "extracted", "mapped"] },
  { key: "validation", label: "Validation Agent", icon: ShieldCheck, stepKeys: ["validation", "rules", "rules_validation", "rules_validated", "validated"] },
  { key: "eligibility", label: "Eligibility Agent", icon: CheckCircle2, stepKeys: ["eligibility", "eligibility_checked", "insurance_verified"] },
  { key: "compliance", label: "Compliance Agent", icon: ClipboardCheck, stepKeys: ["compliance", "compliance_checked", "compliance_logged"] },
  { key: "claim_form", label: "CMS1500 / UB04 Agent", icon: FileSearch, stepKeys: ["claim_form", "cms1500", "cms_1500", "ub04", "ub_04", "generating_cms1500", "generating_ub04"] },
  { key: "edi", label: "EDI Agent", icon: Send, stepKeys: ["edi", "edi_837", "837", "x12", "generating_837", "submission", "submitted", "sending_to_clearinghouse"] },
  { key: "clearinghouse", label: "Clearinghouse Agent", icon: Network, stepKeys: ["clearinghouse", "clearinghouse_queued", "clearinghouse_accepted", "acknowledgment", "ack"] },
  { key: "denial", label: "Denial Prediction Agent", icon: AlertTriangle, stepKeys: ["denial", "denial_checked", "denial_ai_analyzed", "denial_ai"] },
  { key: "payment", label: "Payment Agent", icon: CircleDollarSign, stepKeys: ["payment", "paid", "era", "payment_reconciliation"] },
  { key: "learning", label: "Learning Agent", icon: Sparkles, stepKeys: ["feedback", "learning", "learning_updated", "feedback_loop"] },
  { key: "analytics", label: "Analytics Agent", icon: BrainCircuit, stepKeys: ["analytics", "analytics_done", "metrics", "pipeline_completed"] },
];

const BACKEND_AGENT_STAGE_MAP: Record<string, string> = {
  supervisor: "intake",
  extraction: "ocr_extraction",
  eligibility: "eligibility",
  validation: "validation",
  compliance: "compliance",
  submission: "edi",
  acknowledgment: "clearinghouse",
  denial: "denial",
  payment: "payment",
  learning: "learning",
  analytics: "analytics",
};

type AgentStatus = "ACTIVE" | "COMPLETED" | "WAITING" | "FAILED" | "PENDING" | "HITL" | "ESCALATED";

type AgentModel = {
  key: string;
  label: string;
  purpose: string;
  icon: any;
  status: AgentStatus;
  currentTask: string;
  decision: string;
  reasoning: string;
  confidence: number;
  progress: number;
  duration: string;
  queueLatency: string;
  automationScore: number;
  health: string;
  workerId: string;
  queueName: string;
  websocketLatency: string;
  redisLatency: string;
  executionNode: string;
  retryCount: number;
  throughput: string;
  receivedFrom: string;
  sendingTo: string;
  nextAction: string;
  dataAnalyzed: string[];
  rulesExecuted: string[];
  logs: PipelineEvent[];
  event: AgentEvent;
  history: AgentEvent[];
  rawEvent?: PipelineEvent;
  apiResponses: string[];
  validationDetails: string[];
  denialAnalysis: string[];
  payload: any;
  recommendations: string[];
};

type MonitorState = {
  events: PipelineEvent[];
  claims: Record<string, ClaimPipelineState>;
};

class AgentCardBoundary extends React.PureComponent<{ children: React.ReactNode; agentLabel: string }, { hasError: boolean }> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error) {
    console.error("Agent card render failed", this.props.agentLabel, error);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="ao-agent-error-boundary">
          <AlertTriangle size={18} />
          <strong>{this.props.agentLabel}</strong>
          <span>Unable to render the latest payload safely.</span>
        </div>
      );
    }

    return this.props.children;
  }
}

const getEventClaimId = (event: PipelineEvent) =>
  readEventData(event, "claim_id") || readEventData(event, "claimId") || event.pipeline?.claim_id;

const normalize = (value?: string) => String(value || "PENDING").trim().toUpperCase();
const isRunning = (status?: string) => ["RUNNING", "PROCESSING", "STARTED", "IN_PROGRESS", "INFO"].includes(normalize(status));
const isComplete = (status?: string) => ["COMPLETED", "PAID", "ACKNOWLEDGED", "SUCCESS", "ACCEPTED", "VALIDATED"].includes(normalize(status));
const isFailed = (status?: string) => ["FAILED", "ERROR", "DENIED", "REJECTED"].includes(normalize(status));

const readEventData = (event?: PipelineEvent, key?: string) => {
  if (!event || !key) return undefined;
  return event[key] ?? event.data?.[key] ?? event.metadata?.[key] ?? event.details?.[key] ?? event.data?.details?.[key] ?? event.data?.claim?.[key] ?? event.pipeline?.[key];
};

const STEP_ALIASES: Record<string, string> = {
  intake: "intake",
  intake_started: "intake",
  intake_running: "intake",
  intake_completed: "intake",
  upload: "intake",
  claim_created: "intake",
  case_orchestrated: "intake",
  ocr: "ocr_extraction",
  ocr_extraction: "ocr_extraction",
  extract: "ocr_extraction",
  extraction: "ocr_extraction",
  ocr_running: "ocr_extraction",
  extraction_done: "ocr_extraction",
  extracted: "ocr_extraction",
  mapped: "ocr_extraction",
  validation_running: "validation",
  rules: "validation",
  rules_validation: "validation",
  rules_validated: "validation",
  validated: "validation",
  eligibility: "eligibility",
  eligibility_checked: "eligibility",
  insurance_verified: "eligibility",
  compliance_running: "compliance",
  compliance_checked: "compliance",
  compliance_logged: "compliance",
  claim_form: "claim_form",
  cms1500: "claim_form",
  cms_1500: "claim_form",
  ub04: "claim_form",
  ub_04: "claim_form",
  generating_cms1500: "claim_form",
  generating_ub04: "claim_form",
  edi: "edi",
  edi_837: "edi",
  x12: "edi",
  "837": "edi",
  submit: "edi",
  submitted: "edi",
  submission: "edi",
  submission_running: "edi",
  submission_completed: "edi",
  generating_837: "edi",
  sending_to_clearinghouse: "edi",
  clearinghouse_pending: "clearinghouse",
  pending_clearinghouse: "clearinghouse",
  waiting_for_approval: "clearinghouse",
  acknowledgment: "clearinghouse",
  ack: "clearinghouse",
  clearinghouse_queued: "clearinghouse",
  clearinghouse_accepted: "clearinghouse",
  denial_ai: "denial",
  denialai: "denial",
  denial_checked: "denial",
  denial_ai_analyzed: "denial",
  era: "payment",
  paid: "payment",
  feedback: "learning",
  feedback_loop: "learning",
  learning_updated: "learning",
  analytics_done: "analytics",
  metrics: "analytics",
};

const EVENT_STAGE_MAP: Record<string, string> = {
  intake: "intake",
  ocr: "ocr_extraction",
  ocr_extraction: "ocr_extraction",
  extraction: "ocr_extraction",
  validation: "validation",
  eligibility: "eligibility",
  compliance: "compliance",
  claim_form: "claim_form",
  cms1500: "claim_form",
  ub04: "claim_form",
  edi: "edi",
  submission: "edi",
  clearinghouse: "clearinghouse",
  denial: "denial",
  denial_ai: "denial",
  payment: "payment",
  learning: "learning",
  analytics: "analytics",
};

const normalizeToken = (value?: string) => String(value || "").trim().toLowerCase().replace(/[\s-]+/g, "_");

const eventStageKey = (event?: PipelineEvent) => {
  const candidates = [
    event?.agent_detail?.key,
    event?.agent_detail?.stage,
    event?.agent_detail?.agent,
    readEventData(event, "active_step"),
    readEventData(event, "current_step"),
    event?.step,
    readEventData(event, "current_stage"),
    readEventData(event, "active_stage"),
    event?.stage,
    readEventData(event, "current_agent"),
    event?.agent,
    event?.type,
    event?.event,
  ].map((value) => normalizeToken(String(value || "")));

  for (const candidate of candidates) {
    if (!candidate) continue;

    if (BACKEND_AGENT_STAGE_MAP[candidate]) {
      return BACKEND_AGENT_STAGE_MAP[candidate];
    }

    if (EVENT_STAGE_MAP[candidate]) {
      return EVENT_STAGE_MAP[candidate];
    }

    if (STEP_ALIASES[candidate]) {
      return STEP_ALIASES[candidate];
    }

    const match = Object.keys(EVENT_STAGE_MAP).find((key) =>
      candidate.includes(key)
    );

    if (match) {
      return EVENT_STAGE_MAP[match];
    }

    const aliasMatch = Object.entries(STEP_ALIASES).find(([alias]) =>
      candidate.includes(alias)
    );

    if (aliasMatch) {
      return aliasMatch[1];
    }
  }

  return "";
};
const claimStageKey = (claim?: ClaimPipelineState) =>
  STEP_ALIASES[normalizeToken(claim?.currentStep)] ||
  STEP_ALIASES[normalizeToken(claim?.currentStage)] ||
  STEP_ALIASES[normalizeToken(claim?.currentAgent)] ||
  EVENT_STAGE_MAP[normalizeToken(claim?.currentStep)] ||
  EVENT_STAGE_MAP[normalizeToken(claim?.currentStage)] ||
  EVENT_STAGE_MAP[normalizeToken(claim?.currentAgent)] ||
  "";

const stageOrderIndex = (stageKey: string) => PIPELINE_STAGES.findIndex((stage) => stage.key === stageKey);

const durationFor = (event?: PipelineEvent) => {
  const raw =
    event?.agent_detail?.duration_seconds ??
    readEventData(event, "duration_seconds") ??
    readEventData(event, "execution_time") ??
    readEventData(event, "execution_time_seconds") ??
    readEventData(event, "duration") ??
    readEventData(event, "latency_ms");

  const value = Number(raw);

  if (!Number.isFinite(value) || value <= 0) {
    return "";
  }

  const rawKey = String(raw).toLowerCase();

  if (rawKey.includes("ms") || value > 30) {
    return `${Math.round(value)}ms`;
  }

  return `${value.toFixed(2)}s`;
};

const latencyFor = (event?: PipelineEvent) => {
  const timestamp = event?.timestamp || event?.data?.timestamp || event?.metadata?.timestamp;
  if (!timestamp) return "";
  const value = Date.now() - new Date(timestamp).getTime();
  if (!Number.isFinite(value) || value < 0) return "";
  return `${value}ms`;
};

const confidenceFor = (event?: PipelineEvent, fallback?: number) => {
  const raw =
    event?.agent_detail?.score ??
    readEventData(event, "confidence") ??
    readEventData(event, "ai_confidence") ??
    readEventData(event, "score") ??
    readEventData(event, "validation_score");

  const value = raw === undefined || raw === null || raw === "" ? fallback : Number(raw);

  if (value === undefined || !Number.isFinite(Number(value))) return 0;

  return Math.min(
    100,
    Math.max(0, value <= 1 ? Math.round(value * 100) : Math.round(value))
  );
};

const eventText = (event: PipelineEvent) =>
  String(
    event.agent_detail?.message ||
      event.message ||
      event.data?.message ||
      event.data?.reason ||
      event.metadata?.message ||
      event.step ||
      event.stage ||
      event.type ||
      "Pipeline event"
  );

const eventAgent = (event: PipelineEvent) =>
  String(
    event.agent_detail?.agent ||
      event.agent ||
      event.step ||
      event.stage ||
      event.type ||
      "orchestration"
  ).replace(/_/g, " ");

const eventTone = (event: PipelineEvent) => {
  const blob = `
    ${event.type}
    ${event.agent_detail?.agent}
    ${event.agent_detail?.key}
    ${event.agent_detail?.status}
    ${event.agent}
    ${event.status}
    ${event.step}
    ${event.stage}
  `.toLowerCase();

  if (blob.includes("denial") || isFailed(event.agent_detail?.status || event.status)) return "danger";
  if (blob.includes("learning") || blob.includes("analytics")) return "purple";
  if (blob.includes("payment") || isComplete(event.agent_detail?.status || event.status)) return "success";
  if (isRunning(event.agent_detail?.status || event.status)) return "active";
  return "neutral";
};

const eventTime = (event?: PipelineEvent) => {
  const raw = event?.timestamp || event?.data?.timestamp || event?.metadata?.timestamp;
  const date = raw ? new Date(raw) : new Date();
  return Number.isNaN(date.getTime()) ? "--:--:--" : date.toLocaleTimeString();
};

const eventPayload = (event?: PipelineEvent) => {
  if (!event) return {};

  return (
    event.agent_detail?.output ||
    event.claim ||
    event.payload?.claim ||
    event.data?.claim ||
    event.data?.details ||
    event.details ||
    event.data ||
    event.metadata ||
    event ||
    {}
  );
};

const eventValue = (event: PipelineEvent | undefined, ...keys: string[]) => {
  if (!event) return undefined;
  const payload = eventPayload(event);
  for (const key of keys) {
    const value =
      event[key] ??
      event.data?.[key] ??
      event.metadata?.[key] ??
      event.details?.[key] ??
      event.data?.details?.[key] ??
      event.pipeline?.[key] ??
      payload?.[key];
    if (value !== undefined && value !== null && value !== "") return value;
  }
  return undefined;
};

const numericEventValue = (event: PipelineEvent | undefined, ...keys: string[]) => {
  const value = eventValue(event, ...keys);
  if (value === undefined || value === null || value === "") return undefined;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : undefined;
};

const agentEventStatus = (status: AgentStatus, event?: PipelineEvent): AgentEvent["status"] => {
  const normalized = normalize(
    event?.agent_detail?.status ||
      event?.agent_event?.status ||
      event?.status ||
      status
  );
  if (normalized.includes("ESCALATED")) return "escalated";
  if (normalized.includes("HITL") || normalized.includes("HUMAN_REVIEW") || normalized.includes("MANUAL_REVIEW")) return "hitl";
  if (isFailed(normalized)) return "failed";
  if (normalized.includes("WARNING")) return "warning";
  if (isComplete(normalized)) return "completed";
  if (isRunning(normalized) || status === "ACTIVE") return "running";
  return "pending";
};

const historyItemsFromEvent = (event?: PipelineEvent): AgentEvent["event_history"] => {
  const explicit = event?.agent_event?.event_history || eventValue(event, "event_history", "eventHistory", "history");
  if (Array.isArray(explicit)) return explicit;
  return undefined;
};

const pipelineEventToAgentEvent = (
  event: PipelineEvent | undefined,
  stage: (typeof PIPELINE_STAGES)[number],
  claim: ClaimPipelineState | undefined,
  fallbackStatus: AgentStatus
): AgentEvent => {
  const detail = event?.agent_detail;
  const metrics = (eventValue(event, "metrics") || {}) as Record<string, any>;
  const processingTime =
    event?.agent_event?.processing_time ??
    numericEventValue(event, "processing_time", "processingTime", "processing_time_ms", "execution_time", "duration", "latency_ms") ??
    (numericEventValue(event, "processing_time_seconds", "execution_time_seconds") !== undefined
      ? Number(numericEventValue(event, "processing_time_seconds", "execution_time_seconds")) * 1000
      : undefined);
  const confidence = event?.agent_event?.confidence ?? confidenceFor(event);
  const stageText =
    event?.agent_event?.stage ||
    String(eventValue(event, "stage", "current_stage", "active_step", "current_step") || event?.stage || event?.step || "");

  return {
  claim_id: String(
    event?.agent_event?.claim_id ||
      (event ? getEventClaimId(event) : "") ||
      claim?.claimId ||
      ""
  ),
  agent: String(
    detail?.agent ||
      event?.agent_event?.agent ||
      eventValue(event, "agent", "current_agent") ||
      stage.label
  ),
  stage: String(
    detail?.stage ||
      event?.agent_event?.stage ||
      stageText
  ),
  status: agentEventStatus(fallbackStatus, event),
  started_at: String(
    detail?.started_at ||
      event?.agent_event?.started_at ||
      eventValue(event, "started_at", "startedAt", "timestamp") ||
      event?.timestamp ||
      ""
  ),
  completed_at:
    detail?.completed_at ||
    event?.agent_event?.completed_at ||
    eventValue(event, "completed_at", "completedAt"),
  processing_time:
    detail?.duration_seconds !== undefined && detail?.duration_seconds !== null
      ? Number(detail.duration_seconds) * 1000
      : processingTime,
  confidence: confidence || undefined,
  reasoning:
    detail?.message ||
    event?.agent_event?.reasoning ||
    eventValue(event, "reasoning", "reason"),
  input: event?.agent_event?.input || eventValue(event, "input", "input_data", "inputData"),
  output:
    detail?.output ||
    event?.agent_event?.output ||
    eventValue(
      event,
      "output",
      "output_data",
      "outputData",
      "result",
      "response",
      "extracted_fields",
      "generated_artifacts",
      "edi_payload",
      "validation_results",
      "denial_analysis",
      "era_response"
    ),
  warnings:
    detail?.warnings ||
    event?.agent_event?.warnings ||
    eventValue(event, "warnings", "warning", "errors", "issues"),
  metrics: {
    cpu: event?.agent_event?.metrics?.cpu ?? numericEventValue(event, "cpu") ?? (Number.isFinite(Number(metrics.cpu)) ? Number(metrics.cpu) : undefined),
    memory: event?.agent_event?.metrics?.memory ?? numericEventValue(event, "memory") ?? (Number.isFinite(Number(metrics.memory)) ? Number(metrics.memory) : undefined),
    tokens: event?.agent_event?.metrics?.tokens ?? numericEventValue(event, "tokens") ?? (Number.isFinite(Number(metrics.tokens)) ? Number(metrics.tokens) : undefined),
    latency:
      event?.agent_event?.metrics?.latency ??
      numericEventValue(event, "latency", "latency_ms", "websocket_latency") ??
      (Number.isFinite(Number(metrics.latency)) ? Number(metrics.latency) : undefined),
    throughput: event?.agent_event?.metrics?.throughput ?? numericEventValue(event, "throughput") ?? (Number.isFinite(Number(metrics.throughput)) ? Number(metrics.throughput) : undefined),
  },
  ai_summary:
    detail?.message ||
    event?.agent_event?.ai_summary ||
    eventValue(event, "ai_summary", "summary"),
  next_agent:
    detail?.next_agent ||
    event?.agent_event?.next_agent ||
    eventValue(event, "next_agent", "nextAgent", "handoff_to", "target_agent"),
  event_history: historyItemsFromEvent(event),
};
};
const toList = (value: any): string[] => {
  if (!value) return [];
  if (Array.isArray(value)) return value.flatMap(toList);
  if (typeof value === "object") return Object.entries(value).slice(0, 8).map(([key, entry]) => `${key}: ${typeof entry === "object" ? JSON.stringify(entry) : entry}`);
  return [String(value)];
};

const uniqueList = (...values: any[]) =>
  Array.from(new Set(values.flatMap(toList).map((value) => String(value || "").trim()).filter(Boolean)));

const eventKey = (event: PipelineEvent) =>
  [
    event.type || event.event,
    getEventClaimId(event) || "global",
    event.agent_detail?.key ||
      event.agent_detail?.agent ||
      event.agent ||
      event.step ||
      event.stage,
    event.status || event.agent_detail?.status || "UNKNOWN",
  ].join("|");

const orderEvents = (items: PipelineEvent[]) =>
  [...items].sort((a, b) => String(b.timestamp || "").localeCompare(String(a.timestamp || "")));

const eventPatch = (event: PipelineEvent): Partial<ClaimPipelineState> => {
  const stage = readEventData(event, "current_stage") || readEventData(event, "active_stage") || event.stage;
  const agent = readEventData(event, "current_agent") || event.agent || stage;
  const step = readEventData(event, "active_step") || readEventData(event, "current_step") || event.step || stage;
  const status = readEventData(event, "status") || readEventData(event, "pipeline_state") || event.status;
  const progress = Number(readEventData(event, "progress"));
  const stageKey = eventStageKey(event);
  const pipelineSteps: Record<string, boolean | string> = {
    ...(event.pipeline?.steps || {}),
  };

  if (stageKey) {
    if (isRunning(status)) {
      pipelineSteps[stageKey] = "RUNNING";
    }

    if (isComplete(status)) {
      pipelineSteps[stageKey] = true;
      pipelineSteps[`${stageKey}_done`] = true;
      pipelineSteps[`${stageKey}_checked`] = true;
    }

    if (isFailed(status)) {
      pipelineSteps[stageKey] = "FAILED";
    }
  }

  if (stageKey === "clearinghouse") {
    pipelineSteps.clearinghouse_queued = true;
  }

  return {
    currentAgent: agent ? String(agent).toUpperCase() : undefined,
    currentStage: stage ? normalize(String(stage)) : undefined,
    currentStep: step ? String(step) : undefined,
    status: status ? normalize(String(status)) : undefined,
    progress: Number.isFinite(progress) && progress > 0 ? Math.min(100, Math.max(0, Math.round(progress))) : undefined,
    pipelineSteps,
    updatedAt: readEventData(event, "updated_at") || event.timestamp || new Date().toISOString(),
  };
};

const mergeClaimSnapshot = (current: ClaimPipelineState | undefined, claimId: string, patch: Partial<ClaimPipelineState>, event?: PipelineEvent): ClaimPipelineState => {
  const eventList = event ? orderEvents([event, ...(current?.events || [])]) : current?.events || [];
  const seen = new Set<string>();
  const events = eventList.filter((entry) => {
    const key = eventKey(entry);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).slice(0, 150);

  return {
    ...(current || { claimId, pipelineSteps: {}, events: [] }),
    ...patch,
    claimId,
    progress: patch.progress ?? current?.progress,
    pipelineSteps: {
      ...(current?.pipelineSteps || {}),
      ...(patch.pipelineSteps || {}),
    },
    events,
  };
};

const monitorReducer = (state: MonitorState, action: { type: "SYNC_CONTEXT"; events: PipelineEvent[]; claims: Record<string, ClaimPipelineState> } | { type: "WS_CLAIM_EVENT"; event: PipelineEvent }) => {
  if (action.type === "WS_CLAIM_EVENT") {
    const claimId = getEventClaimId(action.event);
    const events = orderEvents([action.event, ...state.events]).filter((event, index, list) => list.findIndex((entry) => eventKey(entry) === eventKey(event)) === index).slice(0, 300);
    if (!claimId) return { ...state, events };
    return {
      events,
      claims: {
        ...state.claims,
        [claimId]: mergeClaimSnapshot(state.claims[claimId], claimId, eventPatch(action.event), action.event),
      },
    };
  }

  const seen = new Set<string>();
  const events = orderEvents([...action.events, ...state.events]).filter((event) => {
    const key = eventKey(event);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).slice(0, 300);
  const nextClaims = { ...state.claims };

  Object.entries(action.claims).forEach(([id, newClaim]) => {
    const existing = nextClaims[id];

    const newTime = new Date(newClaim.updatedAt || 0).getTime();
    const oldTime = new Date(existing?.updatedAt || 0).getTime();

    if (!existing || newTime > oldTime) {
      nextClaims[id] = newClaim;
    }
  });

  [...events].reverse().forEach((event) => {
    const claimId = getEventClaimId(event);
    if (!claimId) return;
    nextClaims[claimId] = mergeClaimSnapshot(nextClaims[claimId], claimId, eventPatch(event), event);
  });
  return { events, claims: nextClaims };
};

const stageStatus = (claim: ClaimPipelineState | undefined, stage: (typeof PIPELINE_STAGES)[number]) => {
  if (!claim) return "pending";
  const steps = claim.pipelineSteps || {};
  const events = claim.events || [];
  const activeStage = claimStageKey(claim);
  const activeIndex = stageOrderIndex(activeStage);
  const currentIndex = stageOrderIndex(stage.key);
  const matchingEvent = events.find((event) => eventStageKey(event) === stage.key);
  const allStageKeys = [stage.key, ...stage.stepKeys];
  const stepDone = allStageKeys.some((key) => steps[key] === true || Boolean(steps[key] && isComplete(String(steps[key]))) || Boolean(steps[`${key}_done`] || steps[`${key}_checked`]));
  const stepFailed = allStageKeys.some((key) => Boolean(steps[key] && isFailed(String(steps[key]))));
  const normalizedStatus = normalize(claim.status);
  if (stepFailed || (matchingEvent && isFailed(matchingEvent.status))) return "failed";
  if (stepDone || (matchingEvent && isComplete(matchingEvent.status))) return "completed";
  if (stage.key === activeStage) {
    if (stage.key === "clearinghouse" && ["WAITING_FOR_APPROVAL", "PENDING_CLEARINGHOUSE", "CLEARINGHOUSE_PENDING"].includes(normalizedStatus)) return "waiting";
    return "running";
  }
  if ((activeIndex >= 0 && currentIndex >= 0 && currentIndex < activeIndex) || stepDone || (matchingEvent && isComplete(matchingEvent.status))) return "completed";
  return "pending";
};

const progressForClaim = (claim?: ClaimPipelineState) => {
  if (!claim) return 0;
  if (claim.progress !== undefined && claim.progress > 0) {
    return Math.min(100, Math.max(0, claim.progress));
  }

  const complete = PIPELINE_STAGES.filter((stage) => stageStatus(claim, stage) === "completed").length;
  const active = PIPELINE_STAGES.some((stage) => stageStatus(claim, stage) === "running") ? 0.5 : 0;
  return Math.round(((complete + active) / PIPELINE_STAGES.length) * 100);
};

const compactNumber = (value: number) =>
  Intl.NumberFormat(undefined, { notation: value > 999 ? "compact" : "standard", maximumFractionDigits: 1 }).format(value || 0);

const agentDetailToPipelineEvent = (
  claimId: string,
  detail: AgentDetail,
  snapshot?: AgentStatusResponse
): PipelineEvent => {
  const mappedStage =
    BACKEND_AGENT_STAGE_MAP[normalizeToken(detail.key)] ||
    BACKEND_AGENT_STAGE_MAP[normalizeToken(detail.stage)] ||
    normalizeToken(detail.key) ||
    normalizeToken(detail.stage);

  return {
    type: "agent_update",
    event: "agent_update",
    claim_id: claimId,
    agent: detail.agent,
    stage: mappedStage,
    current_stage: detail.stage,
    current_agent: detail.agent,
    active_step: mappedStage,
    status: detail.status,
    progress: detail.progress ?? snapshot?.progress,
    pipeline_state: snapshot?.pipeline_state,
    pipeline_status: snapshot?.pipeline_status,
    timestamp: detail.completed_at || detail.started_at || snapshot?.updated_at || new Date().toISOString(),
    message: detail.message,
    agent_detail: detail,
    data: {
      agent_detail: detail,
      output: detail.output,
    },
  };
};

export default function Agents() {
  const location = useLocation();
  const incomingClaimId = (location.state as any)?.claimId;
  const { claims, events, bulkProgress, upsertClaimSnapshot } = usePipeline();

  const [selectedClaimId, setSelectedClaimId] = useState<string>(incomingClaimId || "");
  const [query, setQuery] = useState("");
  const [pipelineNodes, setPipelineNodes] = useState<string[]>([]);
  const [recordsLoaded, setRecordsLoaded] = useState(false);
  const [lastAction, setLastAction] = useState("");
  const [selectedAgent, setSelectedAgent] = useState<AgentModel | null>(null);
  const [agentSnapshot, setAgentSnapshot] = useState<AgentStatusResponse | null>(null);
  const [agentDetails, setAgentDetails] = useState<AgentDetail[]>([]);
  const [claimWsState, setClaimWsState] = useState<WsState>("DISCONNECTED");
  const reasoningConsoleRef = useRef<HTMLDivElement | null>(null);
  const drawerRef = useRef<HTMLElement | null>(null);
  const [monitorState, dispatchMonitor] = useReducer(monitorReducer, { events: events.slice(0, 200), claims });

  useEffect(() => {
    dispatchMonitor({ type: "SYNC_CONTEXT", events, claims });
  }, [events, claims]);

  const monitorEvents = monitorState.events;
  const monitorClaims = monitorState.claims;

  useEffect(() => {
    const loadRecords = async () => {
      try {
        const res = await fetch(`${API_URL}/records?summary=true`);
        if (!res.ok) throw new Error(`Records request failed: ${res.status}`);
        const data = await res.json();
        const records = normalizeClaimsResponse(data);

        records.forEach((record: any) => {
          const claimId = record.claim_id || record.claimId;
          if (!claimId) return;
          const current = claims[claimId];
          upsertClaimSnapshot(claimId, {
            currentAgent: current?.currentAgent || record.currentAgent || record.current_agent || record.stage || "QUEUE",
            currentStep: current?.currentStep || record.currentStep || record.current_step || record.status,
            currentStage: current?.currentStage || record.current_stage || record.pipeline?.current_stage,
            status: current?.status || record.status || "QUEUED",
            progress: current?.progress ?? record.progress,
            submissionId: current?.submissionId || record.claim?.submission_id || record.submission_id,
            updatedAt: current?.updatedAt || record.updated_at || record.created_at || new Date().toISOString(),
            pipelineSteps: current?.pipelineSteps || record.pipeline?.steps || record.pipelineSteps || {},
            snapshot: record,
          });
        });

        if (incomingClaimId) setSelectedClaimId(incomingClaimId);
        else if (!selectedClaimId && records[0]?.claim_id) setSelectedClaimId(records[0].claim_id);
        setRecordsLoaded(true);
      } catch (err) {
        console.error("Failed to load records", err);
        setRecordsLoaded(false);
      }
    };

    loadRecords();
  }, [incomingClaimId, upsertClaimSnapshot]);

  useEffect(() => {
    if (!selectedAgent) return;

    requestAnimationFrame(() => {
      drawerRef.current?.scrollTo({
        top: 0,
        behavior: "auto",
      });

      drawerRef.current?.focus();
    });
  }, [selectedAgent?.key]);

  useEffect(() => {
  const loadPipelineNodes = async () => {
    try {
      const res = await fetch(`${API_URL}/api/rcm/agents/pipeline`);
      const data = res.ok ? await res.json() : {};
      setPipelineNodes(Array.isArray(data?.pipeline) ? data.pipeline : []);
    } catch (error) {
      console.error("Pipeline nodes refresh failed", error);
    }
  };

  loadPipelineNodes();
}, []);



  const loadAgentSnapshot = useCallback(
    async (claimId: string) => {
      if (!claimId) return;

      try {
        const snapshot = await fetchAgentStatus(claimId);

        setAgentSnapshot(snapshot);
        setAgentDetails(snapshot.agents || []);

        upsertClaimSnapshot(claimId, {
          currentAgent: snapshot.current_agent || snapshot.current_stage || "QUEUE",
          currentStep: snapshot.active_step || snapshot.current_stage || snapshot.pipeline_status,
          currentStage: snapshot.current_stage,
          status: snapshot.pipeline_status || snapshot.status || "QUEUED",
          progress: snapshot.progress,
          updatedAt: snapshot.updated_at || new Date().toISOString(),
          pipelineSteps: {},
          snapshot,
        });

        (snapshot.agents || []).forEach((detail) => {
          dispatchMonitor({
            type: "WS_CLAIM_EVENT",
            event: agentDetailToPipelineEvent(claimId, detail, snapshot),
          });
        });
      } catch (error) {
        console.error("Failed to load agent snapshot", error);
      }
    },
    [upsertClaimSnapshot]
  );
  const liveClaims = useMemo(
    () => Object.values(monitorClaims).sort((a, b) => String(b.updatedAt || "").localeCompare(String(a.updatedAt || ""))),
    [monitorClaims]
  );

  useEffect(() => {
    if (!selectedClaimId) return;
    loadAgentSnapshot(selectedClaimId);
  }, [selectedClaimId, loadAgentSnapshot]);

  useEffect(() => {
    if (!selectedClaimId) return;

    let closed = false;
    let connection: { close: () => void } | null = null;

    setClaimWsState("CONNECTING");

    connectPipelineWS(
      selectedClaimId,
      (event) => {
        if (closed) return;

        dispatchMonitor({ type: "WS_CLAIM_EVENT", event });

        if (event.agent_detail?.key) {
          setAgentDetails((previous) => {
            const exists = previous.some(
              (agent) => agent.key === event.agent_detail?.key
            );

            if (!exists) {
              return [...previous, event.agent_detail as AgentDetail];
            }

            return previous.map((agent) =>
              agent.key === event.agent_detail?.key
                ? { ...agent, ...event.agent_detail }
                : agent
            );
          });
        }

        setAgentSnapshot((previous) => {
          if (!previous) return previous;

          return {
            ...previous,
            current_agent: event.current_agent || previous.current_agent,
            current_stage: event.current_stage || previous.current_stage,
            active_step: event.active_step || previous.active_step,
            progress: event.progress ?? previous.progress,
            pipeline_state: event.pipeline_state || previous.pipeline_state,
            pipeline_status: event.pipeline_status || previous.pipeline_status,
            updated_at: event.timestamp || previous.updated_at,
          };
        });
      },
      {
        onHealth: (health: WebSocketHealth) => {
          setClaimWsState(
            health.status === "CONNECTED"
              ? "CONNECTED"
              : health.status === "CONNECTING"
              ? "CONNECTING"
              : health.status === "ERROR"
              ? "ERROR"
              : "DISCONNECTED"
          );
        },
      }
    ).then((wsConnection) => {
      if (closed) {
        wsConnection.close();
        return;
      }

      connection = wsConnection;
    });

    return () => {
      closed = true;
      connection?.close();
      setClaimWsState("DISCONNECTED");
    };
  }, [selectedClaimId]);


  useEffect(() => {
    if (!selectedClaimId && liveClaims[0]) setSelectedClaimId(liveClaims[0].claimId);
  }, [liveClaims, selectedClaimId]);

  const filteredClaims = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return liveClaims;
    return liveClaims.filter((claim) =>
      [
        claim.claimId,
        claim.submissionId,
        claim.currentAgent,
        claim.currentStep,
        claim.status,
        ...claim.events.map(eventText),
      ]
        .join(" ")
        .toLowerCase()
        .includes(needle)
    );
  }, [liveClaims, query]);

  const selected =
    selectedClaimId && monitorClaims[selectedClaimId]
      ? monitorClaims[selectedClaimId]
      : !selectedClaimId
      ? filteredClaims[0]
      : undefined;

  const selectedEvents = useMemo(() => {
    if (!selected) return [];
    return monitorEvents.filter((event) => getEventClaimId(event) === selected.claimId).slice(0, 150);
  }, [monitorEvents, selected?.claimId]);

  const apiAgentEvents = useMemo(() => {
    if (!selectedClaimId || !agentDetails.length) return [];

    return agentDetails.map((detail) =>
      agentDetailToPipelineEvent(selectedClaimId, detail, agentSnapshot || undefined)
    );
  }, [selectedClaimId, agentDetails, agentSnapshot]);

  const pipelineEvents = useMemo(() => {
    if (!selected) return [];

    return orderEvents([
      ...apiAgentEvents,
      ...(selectedEvents || []),
      ...(selected.events || []),
    ])
      .filter((event, index, list) => list.findIndex((entry) => eventKey(entry) === eventKey(event)) === index)
      .slice(0, 150);
  }, [selected, selectedEvents, apiAgentEvents]);
  const wsAgentState = useMemo(() => {
    const state: Record<string, Record<string, PipelineEvent>> = {};
    monitorEvents.forEach((event) => {
      const claimId = getEventClaimId(event);
      const stageKey = eventStageKey(event);
      if (!claimId || !stageKey) return;
      state[claimId] = state[claimId] || {};
      const current = state[claimId][stageKey];
      if (!current || String(event.timestamp || "").localeCompare(String(current.timestamp || "")) > 0) {
        state[claimId][stageKey] = event;
      }
    });
    return state;
  }, [monitorEvents]);
  const latestPipelineEvent = pipelineEvents[0];
  const pipelineProgress = progressForClaim(selected);
  const wsConnected = claimWsState === "CONNECTED";

  const agentModels = useMemo<AgentModel[]>(() => {
    if (!selected) return [];
    return PIPELINE_STAGES.map((stage, index) => {
      const stageEvents = pipelineEvents.filter((event) => eventStageKey(event) === stage.key);
      const latest = stageEvents[0] || wsAgentState[selected.claimId]?.[stage.key];
      const state = stageStatus(selected, stage);
      const latestStatus = normalize(latest?.agent_event?.status || latest?.status);
      const status: AgentStatus =
        latestStatus.includes("ESCALATED") ? "ESCALATED" :
        latestStatus.includes("HITL") || latestStatus.includes("HUMAN_REVIEW") || latestStatus.includes("MANUAL_REVIEW") ? "HITL" :
        state === "running" ? "ACTIVE" :
        state === "completed" ? "COMPLETED" :
        state === "waiting" ? "WAITING" :
        state === "failed" ? "FAILED" :
        "PENDING";
      const nextStage = PIPELINE_STAGES[index + 1]?.label;
      const previousStage = PIPELINE_STAGES[index - 1]?.label;
      const payload = eventPayload(latest);
      const explicitTask = eventValue(latest, "current_task", "current_action", "action", "task", "message", "active_step", "current_step");
      const explicitNextAction = eventValue(latest, "next_action", "next_step", "next_agent", "handoff_to", "target_agent");
      const progress = Number(eventValue(latest, "progress"));
      const history = stageEvents
        .map((stageEvent) => pipelineEventToAgentEvent(stageEvent, stage, selected, agentEventStatus(status, stageEvent) === "running" ? "ACTIVE" : status))
        .filter((stageEvent) => stageEvent.started_at || stageEvent.stage || stageEvent.reasoning || stageEvent.ai_summary);
      const normalizedAgentEvent = {
        ...pipelineEventToAgentEvent(latest, stage, selected, status),
        next_agent: String(explicitNextAction || latest?.agent_event?.next_agent || (status !== "PENDING" ? nextStage || "" : "") || "") || undefined,
      };
      const recommendations = uniqueList(
        latest?.data?.suggestion,
        latest?.data?.recommendation,
        latest?.metadata?.suggestion,
        latest?.agent_event?.ai_summary,
        payload.ai_suggestions,
        payload.suggestions,
        payload.recommendations,
        payload.ai_suggestion,
        payload.resubmission_strategy,
        payload.appeal_summary
      ).slice(0, 4);
      const passedRules = uniqueList(
        latest?.agent_detail?.passed_rules,
        latest?.agent_detail?.output?.passed_rules,
        payload.passed_rules
      ).slice(0, 10);

      const warningRules = uniqueList(
        latest?.agent_detail?.warning_rules,
        latest?.agent_detail?.warnings,
        latest?.agent_detail?.output?.warning_rules,
        latest?.agent_detail?.output?.issues,
        payload.warning_rules,
        payload.issues
      ).slice(0, 10);

      const failedRules = uniqueList(
        latest?.agent_detail?.failed_rules,
        latest?.agent_detail?.errors,
        latest?.agent_detail?.output?.failed_rules,
        latest?.agent_detail?.output?.failures,
        payload.failed_rules,
        payload.failures
      ).slice(0, 10);

      const extractedRules = uniqueList(
        passedRules,
        warningRules,
        failedRules,
        latest?.agent_detail?.executed_rules,
        latest?.agent_detail?.output?.executed_rules,
        latest?.data?.rules,
        latest?.metadata?.rules,
        payload.executed_rules,
        payload.rules,
        payload.checks
      ).slice(0, 20);
      const apiResponses = uniqueList(
        latest?.data?.api_response,
        latest?.data?.api_responses,
        latest?.metadata?.api_response,
        payload.api_response,
        payload.response,
        payload.acknowledgment,
        payload.era_response
      ).slice(0, 6);
      const validationDetails = uniqueList(
        latest?.agent_detail?.passed_rule_count !== undefined
          ? `Passed rules: ${latest.agent_detail.passed_rule_count}`
          : undefined,
        latest?.agent_detail?.warning_rule_count !== undefined
          ? `Warning rules: ${latest.agent_detail.warning_rule_count}`
          : undefined,
        latest?.agent_detail?.failed_rule_count !== undefined
          ? `Failed rules: ${latest.agent_detail.failed_rule_count}`
          : undefined,
        payload.passed_rule_count !== undefined
          ? `Passed rules: ${payload.passed_rule_count}`
          : undefined,
        payload.warning_rule_count !== undefined
          ? `Warning rules: ${payload.warning_rule_count}`
          : undefined,
        payload.failed_rule_count !== undefined
          ? `Failed rules: ${payload.failed_rule_count}`
          : undefined,
        latest?.data?.validation_results,
        latest?.data?.validation,
        payload.validation,
        payload.validation_results,
        payload.compliance,
        payload.compliance_results
      ).slice(0, 12);
      const denialAnalysis = uniqueList(
        latest?.data?.denial_analysis,
        latest?.data?.analysis,
        payload.denial_ai,
        payload.denial_risk,
        payload.analysis
      ).slice(0, 8);
      const reasoning = String(normalizedAgentEvent.reasoning || "");
      const decision = normalize(latest?.data?.decision || latest?.metadata?.decision || latest?.status || selected.status || status).replace(/_/g, " ");
      const confidence = normalizedAgentEvent.confidence || 0;
      return {
        key: stage.key,
        label: stage.label,
        purpose: String(eventValue(latest, "purpose", "description") || normalizedAgentEvent.ai_summary || ""),
        icon: stage.icon,
        status,
        currentTask: String(explicitTask || normalizedAgentEvent.stage || selected.currentStep || selected.currentStage || "").replace(/_/g, " "),
        decision,
        reasoning,
        confidence,
        progress: Number.isFinite(progress) && progress > 0 ? Math.min(100, Math.max(0, Math.round(progress))) : status === "COMPLETED" ? 100 : status === "ACTIVE" ? Math.max(0, selected.progress || 0) : 0,
        duration: durationFor(latest),
        queueLatency: String(latest?.data?.queue_latency || latest?.metadata?.queue_latency || ""),
        automationScore: confidence || 0,
        health: status === "FAILED" ? "ALERT" : status === "ACTIVE" ? "LIVE" : status === "WAITING" ? "WAITING" : status === "COMPLETED" ? "HEALTHY" : "IDLE",
        workerId: String(eventValue(latest, "worker_id", "workerId", "worker") || ""),
        queueName: String(eventValue(latest, "queue_name", "queue", "queue_state") || ""),
        websocketLatency: latencyFor(latest),
        redisLatency: String(eventValue(latest, "redis_latency", "redis_latency_ms") || ""),
        executionNode: String(eventValue(latest, "execution_node", "node", "service") || ""),
        retryCount: Number(eventValue(latest, "retry_count", "retries") || 0),
        throughput: String(eventValue(latest, "throughput", "events_per_second", "rate") || `${stageEvents.length} events`),
        receivedFrom: String(eventValue(latest, "received_from", "source_agent") || previousStage || ""),
        sendingTo: String(explicitNextAction || nextStage || ""),
        nextAction: String(explicitNextAction || normalizedAgentEvent.next_agent || ""),
        dataAnalyzed: uniqueList(latest?.data?.data_analyzed, payload.data_analyzed, Object.keys(payload || {}).slice(0, 5)).slice(0, 7),
        rulesExecuted: uniqueList(extractedRules).slice(0, 7),
        logs: stageEvents.slice(0, 18),
        event: normalizedAgentEvent,
        history,
        rawEvent: latest,
        apiResponses,
        validationDetails,
        denialAnalysis,
        payload,
        recommendations,
      };
    });
  }, [pipelineEvents, selected?.claimId, selected?.currentAgent, selected?.currentStage, selected?.currentStep, selected?.status, selected?.updatedAt, selected?.progress, wsAgentState]);

  const openAgentDrawer = useCallback((agent: AgentModel) => setSelectedAgent(agent), []);
  useEffect(() => {
    if (!selectedAgent) return;
    const liveAgent = agentModels.find((agent) => agent.key === selectedAgent.key);
    if (liveAgent) setSelectedAgent(liveAgent);
  }, [agentModels, selectedAgent?.key]);
  const activeAgents = agentModels.filter((agent) => agent.status === "ACTIVE").length;
  const runningClaims = liveClaims.filter((claim) => isRunning(claim.status) || isRunning(claim.currentStep)).length;
  const queueJobs = Number(bulkProgress.queued ?? 0);

  const activeWorkers = agentModels.filter(
    (agent) => agent.status === "ACTIVE"
  ).length;


  const learningUpdates = monitorEvents.filter((event) =>
    `${event.agent} ${event.type} ${event.stage}`.toLowerCase().includes("learning")
  ).length;

  const denialAiActive = agentModels.some(
    (agent) =>
      agent.key === "denial" &&
      !["COMPLETED", "PENDING"].includes(agent.status)
  );

  const kpis = [
    {
      label: "Active Agents",
      value: activeAgents,
      trend: `${agentModels.length} monitored`,
      icon: Cpu,
      tone: "blue",
    },
    {
      label: "Running Claims",
      value: runningClaims,
      trend: `${liveClaims.length} total`,
      icon: Activity,
      tone: "cyan",
    },
    {
      label: "Queue Jobs",
      value: queueJobs,
      trend: "pipeline queue",
      icon: Database,
      tone: "purple",
    },
    {
      label: "WebSocket",
      value: wsConnected ? "LIVE" : claimWsState,
      trend: selectedClaimId || "no claim selected",
      icon: Zap,
      tone: "green",
    },
    {
      label: "Denial AI Active",
      value: denialAiActive ? "ON" : "IDLE",
      trend: `${monitorEvents.filter((event) =>
        `${event.agent} ${event.type}`.toLowerCase().includes("denial")
      ).length} events`,
      icon: AlertTriangle,
      tone: "red",
    },
    {
      label: "Learning Updates",
      value: learningUpdates,
      trend: "agent events",
      icon: Sparkles,
      tone: "orange",
    },
  ];

  const headerStats = [
    {
      label: "WebSocket",
      value: wsConnected ? "Live" : claimWsState,
      icon: Zap,
      ok: wsConnected,
    },
    {
      label: "Agents",
      value: compactNumber(agentModels.length),
      icon: Cpu,
      ok: agentModels.length > 0,
    },
    {
      label: "Queue",
      value: compactNumber(queueJobs),
      icon: Route,
      ok: queueJobs === 0,
    },
  ];

  const claimEvents = selected ? monitorEvents.filter((event) => !getEventClaimId(event) || getEventClaimId(event) === selected.claimId) : monitorEvents;
  const visibleClaimEvents = useMemo(() => claimEvents.slice(0, 64), [claimEvents]);
  const reasoningLogs = useMemo(() => {
    return [...pipelineEvents]
      .filter((event) => eventText(event) || event.reasoning || event.ai_summary)
      .sort((a, b) => new Date(a.timestamp || 0).getTime() - new Date(b.timestamp || 0).getTime())
      .slice(-80);
  }, [pipelineEvents]);

  useEffect(() => {
    const node = reasoningConsoleRef.current;
    if (!node) return;
    node.scrollTop = node.scrollHeight;
  }, [reasoningLogs.length]);

  const runClaimAction = async (action: string) => {
    if (!selected?.claimId) return;
    setLastAction(`${action} started for ${selected.claimId}`);
    try {
      if (action === "retry") await retrySubmission(selected.claimId);
      if (action === "appeal") await generateAppeal(selected.claimId);
      if (action === "cms1500") await downloadCMS1500(selected.claimId);
      if (action === "ub04") await downloadUB04(selected.claimId);
      if (action === "edi") await downloadEDI(selected.claimId);
      setLastAction(`${action} completed for ${selected.claimId}`);
    } catch (err) {
      console.error(`Claim action failed: ${action}`, err);
      setLastAction(`${action} failed for ${selected.claimId}`);
    }
  };

  return (
    <div className="orchestration-page">
      <header className="ao-header">
        <div>
          <p className="ao-eyebrow">Mission Control / Autonomous Healthcare AI</p>
          <h1>AI Orchestration Monitor</h1>
          <p>Realtime autonomous healthcare AI execution visibility</p>
        </div>

        <div className="ao-header-controls">
          {headerStats.map((item) => {
            const Icon = item.icon;
            return (
              <div className="ao-status-pill" key={item.label}>
                <Icon size={15} />
                <span className={item.ok ? "online" : "standby"} />
                <strong>{item.value}</strong>
                <small>{item.label}</small>
              </div>
            );
          })}
          <button className="ao-icon-button" aria-label="Notifications">
            <Bell size={18} />
            <span>{monitorEvents.length}</span>
          </button>
          <button className="ao-profile" aria-label="Profile menu">
            <User size={16} />
          </button>
        </div>
      </header>

      <section className="ao-kpi-grid">
        {kpis.map((kpi) => {
          const Icon = kpi.icon;
          const progress = typeof kpi.value === "number" ? Math.min(100, kpi.value * 12) : kpi.value === "ON" ? 100 : 38;
          return (
            <div className={`ao-kpi ${kpi.tone}`} key={kpi.label}>
              <div className="ao-kpi-icon"><Icon size={20} /></div>
              <span>{kpi.label}</span>
              <strong>{kpi.value}</strong>
              <small>{kpi.trend}</small>
              <div className="ao-mini-progress"><i style={{ width: `${Math.max(10, progress)}%` }} /></div>
            </div>
          );
        })}
      </section>

      <section className="ao-claim-toolbar">
        <label className="ao-search">
          <Search size={17} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search claim, payer, agent, event..." />
        </label>
        <label className="ao-claim-select">
          <span>Claim Focus</span>
          <select value={selected?.claimId || ""} onChange={(event) => setSelectedClaimId(event.target.value)}>
            {filteredClaims.map((claim) => (
              <option key={claim.claimId} value={claim.claimId}>
                {claim.claimId} - {normalize(claim.status)}
              </option>
            ))}
          </select>
        </label>
        <div className="ao-action-row">
          <button onClick={() => runClaimAction("retry")} disabled={!selected}><RefreshCw size={15} /> Retry</button>
          <button onClick={() => runClaimAction("appeal")} disabled={!selected}><Sparkles size={15} /> Appeal</button>
          <button onClick={() => runClaimAction("cms1500")} disabled={!selected}>CMS1500</button>
          <button onClick={() => runClaimAction("ub04")} disabled={!selected}>UB04</button>
          <button onClick={() => runClaimAction("edi")} disabled={!selected}>EDI</button>
        </div>
        {lastAction && <small className="ao-last-action">{lastAction}</small>}
      </section>

      <main className="ao-monitor-grid">
        <section className="ao-main-stack">
          <section className="ao-panel ao-pipeline-panel">
            <div className="ao-panel-head">
              <div>
                <p className="ao-eyebrow">Live Orchestration Pipeline</p>
                <h2>{selected?.claimId || "Waiting for live claim"}</h2>
              </div>
              <div className="ao-progress-orb" style={{ ["--value" as string]: `${pipelineProgress}%` }}>
                <strong>{pipelineProgress}%</strong>
                <span>complete</span>
              </div>
            </div>

            <div className="ao-pipeline-viz">
              {PIPELINE_STAGES.map((stage, index) => {
                const Icon = stage.icon;
                const state = stageStatus(selected, stage);
                const matching = pipelineEvents.find((event) => eventStageKey(event) === stage.key);
                const confidence = confidenceFor(matching);
                return (
                  <div className={`ao-stage ${state}`} key={stage.key}>
                    {index > 0 && <span className="ao-stage-link" />}
                    <div className="ao-stage-core">
                      <Icon size={21} />
                    </div>
                    <strong>{stage.label}</strong>
                    {durationFor(matching) && <small>{durationFor(matching)}</small>}
                    {confidence ? <em>{confidence}% confidence</em> : null}
                  </div>
                );
              })}
            </div>
          </section>

          <EnterpriseClaimObservability claimId={selected?.claimId} />

          <section className="ao-panel ao-communication-panel">
            <div className="ao-panel-head compact">
              <div>
                <p className="ao-eyebrow">Agent Handoff</p>
                <h2>Autonomous handoff path</h2>
              </div>
              <GitBranch size={18} />
            </div>
            <div className="ao-agent-handoff-vertical">
              {agentModels.map((agent, index) => {
                const Icon = agent.icon;
                return (
                  <div className={`ao-handoff-node ${agent.status.toLowerCase()}`} key={agent.key}>
                    <span><Icon size={16} /></span>
                    <div>
                      <strong>{agent.label.replace(" Agent", "")}</strong>
                      <small>{agent.currentTask || agent.status}</small>
                    </div>
                    <em>{agent.status}</em>
                    {index < agentModels.length - 1 && <i />}
                  </div>
                );
              })}
            </div>
          </section>

          <section className="ao-panel">
            <div className="ao-panel-head compact">
              <div>
                <p className="ao-eyebrow">Live Agent Grid</p>
                <h2>{agentModels.length} monitored AI agents</h2>
              </div>
              <span className="ao-subtle">{pipelineNodes.length ? `${pipelineNodes.length} graph nodes` : "websocket state"}</span>
            </div>

            <div className="ao-agent-grid">
              {agentModels.map((agent) => (
                <AgentCardBoundary key={agent.key} agentLabel={agent.label}>
                  <div className="ao-agent-card-shell">
                    <AgentCard
                      title={agent.label}
                      status={agent.event.status}
                      event={agent.event}
                      events={agent.history}
                      rawEvent={agent.rawEvent || agent.payload}
                      agent={agent}
                      isActive={agent.status === "ACTIVE"}
                      onOpen={() => openAgentDrawer(agent)}
                    />

                    <button
                      type="button"
                      className="ao-agent-expand-button"
                      onClick={(event) => {
                        event.stopPropagation();
                        openAgentDrawer(agent);
                      }}
                    >
                      Expand Details
                    </button>
                  </div>
                </AgentCardBoundary>
              ))}
              {agentModels.length === 0 && (
                recordsLoaded ? (
                  <div className="ao-empty">
                    <Bot size={22} />
                    <strong>No agent events for the selected claim yet.</strong>
                    <span>Waiting for orchestration websocket events.</span>
                  </div>
                ) : (
                  <div className="ao-skeleton-grid">
                    {PIPELINE_STAGES.slice(0, 6).map((stage) => <div className="ao-skeleton-card" key={stage.key} />)}
                  </div>
                )
              )}
            </div>
          </section>
        </section>

        <aside className="ao-panel ao-event-stream">
          <div className="ao-panel-head compact">
            <div>
              <p className="ao-eyebrow">Realtime Event Stream</p>
              <h2>Activity Feed</h2>
            </div>
            <span className={`ao-live-chip ${wsConnected ? "online" : ""}`}>{wsConnected ? "Live" : "Waiting"}</span>
          </div>
          <div className="ao-event-list">
            {visibleClaimEvents.map((event, index) => (
              <div className={`ao-event ${eventTone(event)}`} key={`${event.timestamp}-${event.type}-${index}`}>
                <span />
                <time>{event.timestamp ? new Date(event.timestamp).toLocaleTimeString() : "now"}</time>
                <strong>{eventAgent(event)}</strong>
                <p>{eventText(event)}</p>
              </div>
            ))}
            {claimEvents.length === 0 && <p className="ao-empty-copy">No websocket events received for this claim.</p>}
          </div>
        </aside>
      </main>

      <section className="ao-bottom-grid">
        <div className="ao-panel">
          <div className="ao-panel-head compact">
            <h2>Redis Queue Monitor</h2>
            <Database size={18} />
          </div>
          {[
            ["Claims queue", bulkProgress.queued ?? 0],
            ["Retry queue", bulkProgress.retry ?? 0],
            ["DLQ", bulkProgress.failed ?? 0],
            ["Active agents", activeWorkers],
          ].map(([label, value]) => (
            <div className="ao-telemetry-row" key={label}>
              <span>{label}</span>
              <strong>{compactNumber(Number(value || 0))}</strong>
              <i style={{ width: `${Math.min(100, Number(value || 0) * 12)}%` }} />
            </div>
          ))}
        </div>

        <div className="ao-panel">
          <div className="ao-panel-head compact">
            <h2>AI Reasoning Console</h2>
            <BrainCircuit size={18} />
          </div>
          <div className="ao-console reasoning-console" ref={reasoningConsoleRef}>
            {reasoningLogs.map((event, index) => (
              <p key={`${event.timestamp}-${eventAgent(event)}-${index}`}>
                <time>[{eventTime(event)}]</time>
                <span>{eventAgent(event)}</span>
                {event.reasoning || event.ai_summary || eventText(event)}
              </p>
            ))}
            {reasoningLogs.length === 0 && <p><time>[--:--:--]</time><span>Console</span>No reasoning events emitted for this claim yet.</p>}
          </div>
        </div>

        <div className="ao-panel">
          <div className="ao-panel-head compact">
            <h2>System Health</h2>
            <HeartPulse size={18} />
          </div>
          {[

              ["Claim WebSocket", claimWsState, wsConnected],
              ["Selected claim", selected?.claimId || "none", Boolean(selected?.claimId)],
              ["Agent cards", agentModels.length, agentModels.length > 0],
              ["Visible events", pipelineEvents.length, pipelineEvents.length > 0],
              [
                "Latest event latency",
                latestPipelineEvent?.timestamp
                  ? `${Math.max(
                      0,
                      Date.now() - new Date(latestPipelineEvent.timestamp).getTime()
                    )}ms`
                  : "pending",
                Boolean(latestPipelineEvent?.timestamp),
              ],
              ["Queue jobs", queueJobs, queueJobs === 0],
            
          ].map(([label, value, ok]) => (
            <div className="ao-health-row" key={label}>
              {ok ? <CheckCircle2 size={15} /> : <Gauge size={15} />}
              <span>{label}</span>
              <strong>{String(value)}</strong>
            </div>
          ))}
        </div>
      </section>

      {selectedAgent && (
        <div className="ao-drawer-backdrop" role="dialog" aria-modal="true" aria-label={`${selectedAgent.label} details`}>
          <aside
            ref={drawerRef}
            className="ao-agent-drawer"
            tabIndex={-1}
          >
            <button className="ao-drawer-close" onClick={() => setSelectedAgent(null)} aria-label="Close agent details"><X size={18} /></button>
            <div className="ao-panel-head">
              <div>
                <p className="ao-eyebrow">Agent Detail Console</p>
                <h2>{selectedAgent.label}</h2>
              </div>
              <ClaimStatusBadge status={selectedAgent.status} />
            </div>
            <p className="ao-drawer-purpose">{selectedAgent.purpose}</p>
            <div className="ao-drawer-metrics">
              {[
                ["Duration", selectedAgent.duration],
                ["Confidence", `${selectedAgent.confidence}%`],
                ["Queue latency", selectedAgent.queueLatency],
                ["Automation", `${selectedAgent.automationScore}%`],
                ["Health", selectedAgent.health],
                ["Decision", selectedAgent.decision],
                ["Worker", selectedAgent.workerId],
                ["Queue", selectedAgent.queueName],
                ["WS latency", selectedAgent.websocketLatency],
                ["Redis", selectedAgent.redisLatency],
                ["Node", selectedAgent.executionNode],
                ["Retries", selectedAgent.retryCount],
              ].map(([label, value]) => (
                <div key={label}>
                  <span>{label}</span>
                  <strong>{value}</strong>
                </div>
              ))}
            </div>
            <section>
              <h3>Orchestration Handoff</h3>
              <div className="ao-handoff-flow drawer">
                <div><span>Received From</span><strong>{selectedAgent.receivedFrom}</strong></div>
                <i />
                <div><span>Sending To</span><strong>{selectedAgent.sendingTo}</strong></div>
              </div>
            </section>
            <section>
              <h3>AI Reasoning</h3>
              <p>{selectedAgent.reasoning}</p>
            </section>
            <section>
              <h3>Data Analyzed</h3>
              <div className="ao-chip-row wide">{selectedAgent.dataAnalyzed.map((item) => <span key={item}>{item}</span>)}</div>
            </section>
              <section>
                <h3>Rules Executed / Passed</h3>
                <div className="ao-chip-row wide rules">
                  {(selectedAgent.rulesExecuted.length
                    ? selectedAgent.rulesExecuted
                    : ["No rule details emitted by backend yet."]
                  ).map((item) => (
                    <span key={item}>{item}</span>
                  ))}
                </div>
              </section>

              <section>
                <h3>API Responses</h3>
                <div className="ao-console">
                  {(selectedAgent.apiResponses.length
                    ? selectedAgent.apiResponses
                    : ["No API response emitted for this agent yet."]
                  ).map((item, index) => (
                    <p key={`${item}-${index}`}>
                      <span>API</span>
                      {item}
                    </p>
                  ))}
                </div>
              </section>
                            
              <h3>API Responses</h3>
              <div className="ao-console">
                {(selectedAgent.apiResponses.length ? selectedAgent.apiResponses : ["No API response emitted for this agent yet."]).map((item, index) => (
                  <p key={`${item}-${index}`}><span>API</span>{item}</p>
                ))}
              </div>
            <section>
              <h3>Validation Details</h3>
              <div className="ao-console">
                {(selectedAgent.validationDetails.length ? selectedAgent.validationDetails : ["No validation detail emitted for this agent yet."]).map((item, index) => (
                  <p key={`${item}-${index}`}><span>Rules</span>{item}</p>
                ))}
              </div>
            </section>
            <section>
              <h3>Denial Analysis</h3>
              <div className="ao-console">
                {(selectedAgent.denialAnalysis.length ? selectedAgent.denialAnalysis : ["No denial analysis emitted for this agent yet."]).map((item, index) => (
                  <p key={`${item}-${index}`}><span>Denial AI</span>{item}</p>
                ))}
              </div>
            </section>
            <section>
              <h3>AI Recommendations</h3>
              <div className="ao-console">
                {(selectedAgent.recommendations.length ? selectedAgent.recommendations : ["No recommendations emitted by backend yet."]).map((item, index) => (
                  <p key={`${item}-${index}`}><span>AI</span>{item}</p>
                ))}
              </div>
            </section>
            <section>
              <h3>Full Execution Timeline</h3>
              <div className="ao-full-log">
                {(selectedAgent.logs.length ? selectedAgent.logs : []).map((event, index) => (
                  <p key={`${event.timestamp}-${index}`}><time>[{eventTime(event)}]</time><strong>{eventAgent(event)}</strong>{eventText(event)}</p>
                ))}
                {selectedAgent.logs.length === 0 && <p><time>[--:--:--]</time><strong>Monitor</strong>No websocket events for this agent yet.</p>}
              </div>
            </section>
            <section>
              <h3>Payload Preview</h3>
              <pre>{JSON.stringify(selectedAgent.payload || {}, null, 2)}</pre>
            </section>
          </aside>
        </div>
      )}
    </div>
  );
}
