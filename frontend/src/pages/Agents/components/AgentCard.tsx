import { memo, useEffect, useMemo, useState, type KeyboardEvent } from "react";
import {
  Activity,
  AlertTriangle,
  Bot,
  BrainCircuit,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock3,
  Cpu,
  Database,
  Gauge,
  GitBranch,
  Network,
  Sparkles,
  Zap,
} from "lucide-react";
import type { AgentEvent, AgentEventHistoryItem, AgentEventStatus } from "../../../services/websocket";
import "./AgentCard.css";

interface Props {
  title?: string;
  status?: AgentEventStatus | "active" | "completed" | "pending" | "running" | "failed" | "warning" | "hitl" | "escalated" | string;
  details?: any;
  isActive?: boolean;
  event?: AgentEvent;
  events?: AgentEvent[];
  rawEvent?: any;
  onOpen?: () => void;
  agent?: any;
  onRun?: (...args: any[]) => void;
  onView?: (...args: any[]) => void;
}

type DisplayStatus = AgentEventStatus | "hitl" | "escalated";
type DetailField = { label: string; keys: string[]; format?: (value: any) => string };
type DetailSection = { title: string; fields: DetailField[]; preview?: string[] };
type OpenPanel = "json" | "logs" | "evidence" | "details" | null;

const formatPercentLike = (value: any) => {
  if (value === undefined || value === null || value === "") return "";
  if (typeof value === "string" && value.trim().endsWith("%")) return value;
  const numeric = Number(value);
  if (Number.isFinite(numeric)) return `${Math.round(numeric <= 1 ? numeric * 100 : numeric)}%`;
  return typeof value === "object" ? JSON.stringify(value) : String(value);
};

const AGENT_DETAIL_SECTIONS: Record<string, DetailSection[]> = {
  intake: [
    {
      title: "Document Details",
      fields: [
        { label: "File Name", keys: ["file_name", "filename", "document.file_name", "claim.filename"] },
        { label: "Document Type", keys: ["document_type", "doc_type", "claim_type", "form_type", "document.document_type"] },
        { label: "Source", keys: ["source", "upload_source", "document_source"] },
        { label: "Upload Time", keys: ["upload_time", "uploaded_at", "created_at", "timestamp"] },
        { label: "Total Pages", keys: ["total_pages", "pages", "page_count", "document.total_pages"] },
        { label: "OCR Engine", keys: ["ocr_engine", "engine", "textract_engine"] },
      ],
      preview: ["ocr_text_preview", "text_preview", "ocr_text", "text", "extracted_fields"],
    },
    {
      title: "Quality Metrics",
      fields: [
        { label: "OCR Quality", keys: ["ocr_quality", "quality_score", "details.ocr_quality"], format: formatPercentLike },
        { label: "Resolution", keys: ["resolution", "image_resolution"] },
        { label: "Missing Regions", keys: ["missing_regions", "missing_areas", "details.missing_regions"] },
      ],
    },
  ],
  ocr_extraction: [
    {
      title: "Extraction Details",
      fields: [
        { label: "Confidence Score", keys: ["ocr_confidence", "confidence", "ai_confidence", "details.confidence"], format: formatPercentLike },
        { label: "Fields Extracted", keys: ["fields", "fields_extracted", "field_count", "extracted_fields_count"] },
        { label: "Tables Extracted", keys: ["tables", "tables_extracted", "table_count"] },
        { label: "Lines Extracted", keys: ["lines", "lines_extracted", "line_count"] },
      ],
      preview: ["extracted_fields", "fields_preview", "output", "result"],
    },
  ],
  validation: [
    {
      title: "Medical Coding",
      fields: [
        { label: "CPT", keys: ["cpt", "cpt_codes", "medical_coding.cpt", "claim.cpt_codes"] },
        { label: "ICD", keys: ["icd", "icd_codes", "diagnosis_codes", "medical_coding.icd"] },
        { label: "Modifier Codes", keys: ["modifiers", "modifier_codes", "medical_coding.modifiers"] },
        { label: "HCPCS", keys: ["hcpcs", "hcpcs_codes", "medical_coding.hcpcs"] },
      ],
    },
    {
      title: "Validation Checks",
      fields: [
        { label: "Checks", keys: ["validation_checks", "checks", "validation_results", "details.checks"] },
        { label: "Validation Score", keys: ["validation_score", "score", "details.validation_score"], format: formatPercentLike },
      ],
    },
  ],
  eligibility: [
    {
      title: "Insurance",
      fields: [
        { label: "Payer", keys: ["payer", "insurance.payer", "payer_name"] },
        { label: "Plan", keys: ["plan", "insurance.plan", "plan_name"] },
        { label: "Member ID", keys: ["member_id", "insurance.member_id", "subscriber_id"] },
        { label: "Eligibility Status", keys: ["eligibility_status", "coverage_status", "status"] },
      ],
    },
    {
      title: "Coverage",
      fields: [
        { label: "Active Coverage", keys: ["active_coverage", "coverage.active", "coverage_active"] },
        { label: "Remaining Deductible", keys: ["remaining_deductible", "coverage.remaining_deductible", "deductible_remaining"] },
        { label: "Co-pay", keys: ["copay", "co_pay", "coverage.copay"] },
        { label: "Co-insurance", keys: ["coinsurance", "co_insurance", "coverage.coinsurance"] },
      ],
    },
  ],
  compliance: [
    {
      title: "Risk",
      fields: [
        { label: "HIPAA Violations", keys: ["hipaa_violations", "risk.hipaa_violations"] },
        { label: "Missing Consent", keys: ["missing_consent", "risk.missing_consent"] },
        { label: "Documentation Mismatch", keys: ["documentation_mismatch", "doc_mismatch"] },
        { label: "Medical Necessity", keys: ["medical_necessity", "risk.medical_necessity"] },
        { label: "Risk Score", keys: ["risk_score", "risk.score", "details.risk_score"], format: formatPercentLike },
      ],
    },
    {
      title: "Decision Logs",
      fields: [
        { label: "Rule", keys: ["rule", "decision.rule", "decision_logs.rule"] },
        { label: "Result", keys: ["result", "decision.result", "decision_logs.result"] },
        { label: "Action", keys: ["action", "decision.action", "decision_logs.action"] },
      ],
    },
  ],
  claim_form: [
    {
      title: "Form",
      fields: [
        { label: "Form Type", keys: ["form_type", "claim_type", "form.type"] },
        { label: "Generated PDF", keys: ["generated_pdf", "pdf_url", "file_url", "cms1500_pdf_url", "ub04_pdf_url"] },
        { label: "Fields Populated", keys: ["fields_populated", "fields_filled", "populated_fields"] },
        { label: "Missing Fields", keys: ["missing_fields", "missing_mapped_fields"] },
        { label: "Form Validation Score", keys: ["form_validation_score", "validation_score"], format: formatPercentLike },
      ],
      preview: ["thumbnail", "form_thumbnail", "pdf_thumbnail", "generated_form_preview"],
    },
  ],
  edi: [
    {
      title: "EDI",
      fields: [
        { label: "Transaction Type", keys: ["transaction_type", "edi_type", "x12_transaction"] },
        { label: "Submission Payload Size", keys: ["payload_size", "submission_payload_size", "edi_payload_size"] },
        { label: "Validation Status", keys: ["validation_status", "edi_validation_status", "status"] },
        { label: "EDI Generation Time", keys: ["edi_generation_time", "generation_time", "processing_time"] },
      ],
      preview: ["edi_payload", "x12", "payload"],
    },
  ],
  clearinghouse: [
    {
      title: "ACK",
      fields: [
        { label: "999", keys: ["ack_999", "999", "acknowledgment.999"] },
        { label: "277CA", keys: ["ack_277ca", "277ca", "acknowledgment.277ca"] },
      ],
    },
    {
      title: "Claim State",
      fields: [
        { label: "Received", keys: ["received", "claim_state.received"] },
        { label: "Validated", keys: ["validated", "claim_state.validated"] },
        { label: "Forwarded", keys: ["forwarded", "claim_state.forwarded"] },
        { label: "Rejected", keys: ["rejected", "claim_state.rejected"] },
        { label: "Errors", keys: ["errors", "clearinghouse_errors", "details.errors"] },
      ],
    },
  ],
  denial: [
    {
      title: "Denial",
      fields: [
        { label: "Code", keys: ["denial_code", "code", "denial.code"] },
        { label: "Root Cause", keys: ["root_cause", "denial.root_cause", "reason"] },
        { label: "Risk", keys: ["risk", "risk_score", "denial_risk", "details.risk_score"], format: formatPercentLike },
        { label: "Suggested Corrections", keys: ["suggested_corrections", "corrections", "recommendations"] },
        { label: "Appeal Generated", keys: ["appeal_generated", "appeal.generated"] },
        { label: "Retry Chance", keys: ["retry_chance", "retry_probability"] },
      ],
    },
  ],
  payment: [
    {
      title: "Payment",
      fields: [
        { label: "Expected", keys: ["expected", "expected_payment", "expected_amount"] },
        { label: "Received", keys: ["received", "received_payment", "paid_amount"] },
        { label: "Adjustment", keys: ["adjustment", "adjustment_amount"] },
        { label: "ERA", keys: ["era", "era_type", "835"] },
        { label: "Status", keys: ["payment_status", "status"] },
      ],
    },
  ],
  learning: [
    {
      title: "Learning",
      fields: [
        { label: "Patterns", keys: ["patterns", "learned_patterns", "pattern_summary"] },
        { label: "Suggestions", keys: ["suggestions", "recommendations"] },
        { label: "Learning Confidence", keys: ["learning_confidence", "confidence"], format: formatPercentLike },
      ],
    },
  ],
  analytics: [
    {
      title: "Analytics",
      fields: [
        { label: "Cycle", keys: ["cycle", "cycle_time", "processing_cycle"] },
        { label: "Payer", keys: ["payer", "payer_metrics", "payer_summary"] },
        { label: "Root Cause", keys: ["root_cause", "root_cause_summary"] },
        { label: "SLA", keys: ["sla", "sla_remaining", "sla_remaining_time"] },
      ],
    },
  ],
};

const normalizeStatus = (value: any): DisplayStatus => {
  const status = String(value || "pending").trim().toLowerCase().replace(/[\s-]+/g, "_");
  if (["active", "running", "processing", "started", "in_progress"].includes(status)) return "running";
  if (["escalated", "escalation", "manual_escalation"].includes(status)) return "escalated";
  if (["hitl", "hitl_required", "human_review", "manual_review", "waiting_for_review", "warning", "warnings", "partial", "completed_with_warnings"].includes(status)) return "hitl";
  if (["completed", "complete", "success", "accepted", "paid", "acknowledged"].includes(status)) return "completed";
  if (["failed", "failure", "error", "denied", "rejected", "hard_reject"].includes(status)) return "failed";
  return "pending";
};

const nestedValue = (source: any, key: string) => {
  if (!source || !key) return undefined;
  if (!key.includes(".")) return source[key];
  return key.split(".").reduce((current, segment) => current?.[segment], source);
};

const buildMetricRows = (source: any) => {
  const rows = [
    ["Progress", readValue(source, "progress")],
    ["Duration", readValue(source, "duration_seconds")],
    ["Score", readValue(source, "score") ?? readValue(source, "validation_score")],
    ["Risk", readValue(source, "risk_score") ?? readValue(source, "risk_score_percent")],
    ["Status", readValue(source, "status")],
    ["Next", readValue(source, "next_agent")],
  ];

  return rows.filter(([, value]) => value !== undefined && value !== null && value !== "");
};

const sourceCandidates = (source: any) => [
  source,

  source?.agent_detail,
  source?.agent_detail?.output,

  source?.rawEvent,
  source?.rawEvent?.agent_detail,
  source?.rawEvent?.agent_detail?.output,

  source?.event,
  source?.event?.agent_detail,
  source?.event?.agent_detail?.output,

  source?.payload,
  source?.payload?.agent_detail,
  source?.payload?.agent_detail?.output,

  source?.data,
  source?.data?.agent_detail,
  source?.data?.agent_detail?.output,

  source?.details,
  source?.metadata,
  source?.data?.details,
  source?.data?.claim,
  source?.claim,
  source?.snapshot,
  source?.pipeline,
  source?.agent_event,
  source?.agent_event?.metrics,
];

const readValue = (source: any, key: string) => {
  for (const candidate of sourceCandidates(source)) {
    const value = nestedValue(candidate, key);
    if (value !== undefined && value !== null && value !== "") return value;
  }
  return undefined;
};

const readFirst = (source: any, keys: string[]) => {
  for (const key of keys) {
    const value = readValue(source, key);
    if (value !== undefined && value !== null && value !== "") return value;
  }
  return undefined;
};

const toNumber = (value: any) => {
  if (value === undefined || value === null || value === "") return undefined;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : undefined;
};

const clampPercent = (value?: number) =>
  value === undefined ? undefined : Math.min(100, Math.max(0, value <= 1 ? Math.round(value * 100) : Math.round(value)));

const stringifyValue = (value: any) => {
  if (value === undefined || value === null || value === "") return "";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
};

const countValue = (value: any) => {
  if (value === undefined || value === null || value === "") return undefined;
  if (Array.isArray(value)) return value.length;
  if (typeof value === "object") return Object.keys(value).length;
  return 1;
};

const previewEntries = (value: any) => {
  if (value === undefined || value === null || value === "") return [];
  if (Array.isArray(value)) {
    return value.slice(0, 5).map((item, index) => ({
      label: String(index + 1),
      value: stringifyValue(item),
    }));
  }
  if (typeof value === "object") {
    return Object.entries(value).slice(0, 6).map(([key, entry]) => ({
      label: key,
      value: stringifyValue(entry),
    }));
  }
  return [{ label: "value", value: stringifyValue(value) }];
};

const toWarnings = (value: any): string[] => {
  if (!value) return [];
  if (Array.isArray(value)) return value.flatMap(toWarnings);
  if (typeof value === "object") return Object.entries(value).map(([key, entry]) => `${key}: ${stringifyValue(entry)}`);
  return [String(value)];
};

const formatDuration = (processingTime?: number, startedAt?: string, completedAt?: string, nowTick?: number) => {
  let ms = processingTime;
  if (ms === undefined && startedAt) {
    const start = new Date(startedAt).getTime();
    const end = completedAt ? new Date(completedAt).getTime() : nowTick;
    if (Number.isFinite(start) && Number.isFinite(end)) ms = Math.max(0, Number(end) - start);
  }
  if (ms === undefined || !Number.isFinite(ms)) return "";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(ms < 10000 ? 1 : 0)}s`;
};

const formatClock = (value?: string) => {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleTimeString();
};

const metricValue = (label: string, value?: number) => {
  if (value === undefined || !Number.isFinite(value)) return "--";
  if (["CPU", "Confidence"].includes(label)) return `${Math.round(value)}%`;
  if (label === "Memory") return `${Math.round(value)} MB`;
  if (label === "Latency") return `${Math.round(value)}ms`;
  if (label === "Tokens") return Intl.NumberFormat(undefined, { notation: value > 999 ? "compact" : "standard" }).format(value);
  return String(value);
};

const fromAnyEvent = (source: any, title?: string, status?: Props["status"]): AgentEvent => {
  const metrics = readValue(source, "metrics") || {};
  const confidence = clampPercent(toNumber(readValue(source, "confidence") ?? readValue(source, "ai_confidence")));
  const processingTime =
    toNumber(readValue(source, "processing_time")) ??
    toNumber(readValue(source, "processingTime")) ??
    toNumber(readValue(source, "processing_time_ms")) ??
    toNumber(readValue(source, "latency_ms"));

  return {
    claim_id: String(readValue(source, "claim_id") || readValue(source, "claimId") || ""),
    agent: String(title || readValue(source, "agent") || readValue(source, "current_agent") || readValue(source, "name") || ""),
    stage: String(readValue(source, "stage") || readValue(source, "current_stage") || readValue(source, "active_step") || readValue(source, "current_step") || ""),
    status: normalizeStatus(status || readValue(source, "status")),
    started_at: String(readValue(source, "started_at") || readValue(source, "startedAt") || readValue(source, "timestamp") || ""),
    completed_at: readValue(source, "completed_at") || readValue(source, "completedAt"),
    processing_time: processingTime,
    confidence,
    reasoning: readValue(source, "reasoning") || readValue(source, "reason"),
    input: readValue(source, "input") || readValue(source, "input_data"),
    output: readValue(source, "output") || readValue(source, "output_data") || readValue(source, "result"),
    warnings: readValue(source, "warnings") || readValue(source, "warning"),
    metrics: {
      cpu: toNumber(metrics.cpu ?? readValue(source, "cpu")),
      memory: toNumber(metrics.memory ?? readValue(source, "memory")),
      tokens: toNumber(metrics.tokens ?? readValue(source, "tokens")),
      latency: toNumber(metrics.latency ?? readValue(source, "latency") ?? readValue(source, "latency_ms")),
      throughput: toNumber(metrics.throughput ?? readValue(source, "throughput")),
    },
    ai_summary: readValue(source, "ai_summary") || readValue(source, "summary"),
    next_agent: readValue(source, "next_agent") || readValue(source, "handoff_to") || readValue(source, "target_agent"),
    event_history: readValue(source, "event_history") || readValue(source, "eventHistory"),
  };
};

function AgentCard({
  title,
  status,
  details,
  isActive = false,
  event,
  events = [],
  rawEvent,
  onOpen,
  agent,
}: Props) {
  const [openPanel, setOpenPanel] = useState<OpenPanel>(null);
  const [nowTick, setNowTick] = useState(Date.now());

  const source = agent || rawEvent || details || event || {};
  const agentEvent = useMemo(
    () => event || fromAnyEvent(agent || details || rawEvent || {}, title, status),
    [agent, details, event, rawEvent, status, title]
  );
  const normalizedStatus = normalizeStatus(status || agent?.status || agentEvent.status);
  const running = normalizedStatus === "running";

  useEffect(() => {
    if (!running || !agentEvent.started_at || agentEvent.completed_at || agentEvent.processing_time !== undefined) return;
    const timer = window.setInterval(() => setNowTick(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [agentEvent.completed_at, agentEvent.processing_time, agentEvent.started_at, running]);

  const duration = useMemo(
    () => formatDuration(agentEvent.processing_time, agentEvent.started_at, agentEvent.completed_at, running ? nowTick : undefined),
    [agentEvent.completed_at, agentEvent.processing_time, agentEvent.started_at, nowTick, running]
  );

  const confidence = clampPercent(agentEvent.confidence);
  const progress = clampPercent(toNumber(readFirst(source, ["progress", "event.progress", "rawEvent.progress"]))) ?? confidence ?? (normalizedStatus === "completed" ? 100 : 0);
  const warnings = useMemo(() => toWarnings(agentEvent.warnings || readFirst(source, ["warnings", "details.warnings", "warning"])), [agentEvent.warnings, source]);
  const errors = useMemo(() => toWarnings(readFirst(source, ["errors", "details.errors", "error", "issues"])), [source]);
  const inputEntries = useMemo(() => previewEntries(agentEvent.input), [agentEvent.input]);
  const outputEntries = useMemo(() => previewEntries(agentEvent.output), [agentEvent.output]);
  const inputCount = countValue(agentEvent.input);
  const outputCount = countValue(agentEvent.output);

  const metricItems = useMemo(() => {
    const metrics = agentEvent.metrics || {};
    const cpu = metrics.cpu ?? toNumber(readFirst(source, ["metrics.cpu", "cpu"]));
    const memory = metrics.memory ?? toNumber(readFirst(source, ["metrics.memory", "memory"]));
    const latency = metrics.latency ?? toNumber(readFirst(source, ["metrics.latency", "latency", "latency_ms"]));
    const tokens = metrics.tokens ?? toNumber(readFirst(source, ["metrics.tokens", "tokens"]));
    return [
      { label: "CPU", value: cpu, icon: Cpu, percent: clampPercent(cpu) },
      { label: "Memory", value: memory, icon: Database },
      { label: "Latency", value: latency, icon: Zap },
      { label: "Tokens", value: tokens, icon: BrainCircuit },
      confidence !== undefined ? { label: "Confidence", value: confidence, icon: Gauge, percent: confidence } : undefined,
      metrics.throughput !== undefined ? { label: "Throughput", value: metrics.throughput, icon: Network } : undefined,
    ].filter(Boolean) as { label: string; value?: number; icon: any; percent?: number }[];
  }, [agentEvent.metrics, confidence, source]);

  const timeline = useMemo(() => {
    const explicit = (agentEvent.event_history || []) as AgentEventHistoryItem[];
    const fromEvents = events.map((item) => ({
      timestamp: item.completed_at || item.started_at,
      event: item.stage || item.status,
      detail: item.ai_summary || item.reasoning || item.status,
    }));
    const current =
      agentEvent.started_at && (agentEvent.stage || agentEvent.reasoning || agentEvent.ai_summary)
        ? [{
            timestamp: agentEvent.completed_at || agentEvent.started_at,
            event: agentEvent.stage || agentEvent.status,
            detail: agentEvent.ai_summary || agentEvent.reasoning || agentEvent.status,
          }]
        : [];

    const seen = new Set<string>();
    return [...explicit, ...fromEvents, ...current]
      .filter((item) => item.timestamp && item.event)
      .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
      .filter((item) => {
        const key = `${item.timestamp}|${item.event}|${item.detail}`;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      });
  }, [agentEvent, events]);

  const timelineWindow = timeline.slice(Math.max(0, timeline.length - 32));
  const activityItems = useMemo(() => {
    const values = [
      agentEvent.stage,
      agentEvent.ai_summary,
      ...timelineWindow.slice(-5).map((item) => item.detail || item.event),
    ];
    return Array.from(new Set(values.map((item) => String(item || "").trim()).filter(Boolean))).slice(0, 6);
  }, [agentEvent.ai_summary, agentEvent.stage, timelineWindow]);

  const displayTitle = title || agentEvent.agent || agent?.title || agent?.name || "";
  const RawIcon = agent?.icon || Bot;
  const rawPayload = rawEvent || agent?.payload || source || agentEvent;
  const hasInputOutput = inputCount !== undefined || outputCount !== undefined || inputEntries.length > 0 || outputEntries.length > 0;
  const showMetrics = progress !== undefined || metricItems.length > 0 || duration;
  const lastUpdated = String(readFirst(source, ["updated_at", "updatedAt", "last_updated", "timestamp", "rawEvent.timestamp"]) || "");
  const currentTask = String(readFirst(source, ["current_task", "currentTask", "task", "message", "event.stage"]) || agent?.currentTask || agentEvent.stage || "");
  const currentStep = String(readFirst(source, ["current_step", "currentStep", "active_step", "stage", "event.stage"]) || agentEvent.stage || "");
  const threshold = toNumber(readFirst(source, ["confidence_threshold", "hitl_threshold", "threshold"]));
  const hitlTriggered =
    Boolean(readFirst(source, ["hitl_triggered", "requires_hitl", "manual_review_required"])) ||
    (confidence !== undefined && threshold !== undefined && confidence < threshold);
  const executionRows = [
    ["Started At", formatClock(agentEvent.started_at) || "--"],
    ["Last Updated", formatClock(lastUpdated) || "--"],
    ["Completed At", formatClock(agentEvent.completed_at) || "--"],
    ["Duration", duration || "--"],
    ["Current Task", currentTask || currentStep || normalizedStatus.toUpperCase()],
    ["Current Step", currentStep || "--"],
    ["Warning Count", warnings.length],
    ["Error Count", errors.length],
  ];
  const detailSections = useMemo(() => {
    const key = String(agent?.key || "").toLowerCase();
    return (AGENT_DETAIL_SECTIONS[key] || []).map((section) => ({
      ...section,
      rows: section.fields.map((field) => {
        const rawValue = readFirst(source, field.keys);
        return {
          label: field.label,
          value: rawValue === undefined || rawValue === null || rawValue === "" ? undefined : field.format ? field.format(rawValue) : stringifyValue(rawValue),
        };
      }),
      previews: (section.preview || []).flatMap((keyName) => previewEntries(readValue(source, keyName))).slice(0, 6),
    }));
  }, [agent?.key, source]);
  const evidenceEntries = useMemo(
    () => previewEntries(readFirst(source, ["evidence", "audit_evidence", "source_documents", "documents", "citations", "output"])),
    [source]
  );
  const summaryText = String(agentEvent.ai_summary || agentEvent.reasoning || readFirst(source, ["summary", "ai_summary"]) || "").trim();
  const togglePanel = (panel: OpenPanel) => {
    setOpenPanel((current) => (current === panel ? null : panel));
  };
  const interactiveProps = onOpen
    ? {
        role: "button",
        tabIndex: 0,
        onClick: onOpen,
        onKeyDown: (keyboardEvent: KeyboardEvent<HTMLElement>) => {
          if (keyboardEvent.key === "Enter" || keyboardEvent.key === " ") onOpen();
        },
      }
    : {};

  const StatusIcon = normalizedStatus === "completed" ? CheckCircle2 : ["failed", "hitl", "escalated"].includes(normalizedStatus) ? AlertTriangle : Activity;

  return (
    <article className={`agent-card ${isActive || running ? "active-agent" : ""} ${normalizedStatus}-agent`} {...interactiveProps}>
      <div className="agent-card-glow" />
      {(isActive || running) && <div className="agent-card-particles" />}

      <header className="agent-card-header">
        <div className="agent-title">
          <span><RawIcon size={17} /></span>
          <div>
            <strong>{displayTitle}</strong>
            <small>{currentStep || agentEvent.stage || "Pending websocket step"}</small>
          </div>
        </div>

        <div className="agent-header-right">
          <span className={`agent-pulse ${normalizedStatus}`} />
          <small className="agent-live-label">{running ? "Live" : lastUpdated ? "Updated" : "Standby"}</small>
          <small className="agent-duration"><Clock3 size={12} />{duration || "--"}</small>
          <div className={`agent-badge ${normalizedStatus}`}><StatusIcon size={12} />{normalizedStatus.toUpperCase()}</div>
        </div>
      </header>

      <div className="agent-header-progress">
        <div>
          <span>Progress</span>
          <strong>{progress}%</strong>
        </div>
        <i><b style={{ width: `${progress}%` }} /></i>
      </div>

      <div className="agent-body">
        {activityItems.length > 0 && (
          <section className="agent-section agent-live-activity">
            <div className="agent-section-title"><Activity size={14} />Live AI activity</div>
            <div className="agent-activity-list">
              {activityItems.map((item) => <span key={item}>{item}</span>)}
            </div>
          </section>
        )}
      <div className="agent-metrics-grid">
        {buildMetricRows(agent).map(([label, value]) => (
          <div className="agent-metric" key={label}>
            <span>{label}</span>
            <strong>{String(value)}</strong>
          </div>
        ))}
      </div>
        <section className="agent-section">
          <div className="agent-section-title"><Clock3 size={14} />Execution details</div>
          <div className="agent-execution-grid">
            {executionRows.map(([label, value]) => (
              <div key={String(label)}>
                <span>{label}</span>
                <strong>{String(value)}</strong>
              </div>
            ))}
          </div>
        </section>

        {hitlTriggered && (
          <section className="agent-section agent-warning-box">
            <div className="agent-section-title"><AlertTriangle size={14} />HITL Triggered</div>
            <p>Confidence fell below the emitted threshold or the backend marked this step for human review.</p>
          </section>
        )}

        {detailSections.map((section) => (
          <section className="agent-section" key={section.title}>
            <div className="agent-section-title"><Database size={14} />{section.title}</div>
            <div className="agent-kv-list">
              {section.rows.map((row) => (
                <p key={row.label}>
                  <strong>{row.label}</strong>
                  <span className={!row.value ? "agent-empty-value" : ""}>{row.value ?? "--"}</span>
                </p>
              ))}
            </div>
            {section.previews.length > 0 && (
              <div className="agent-kv-list output">
                {section.previews.map((item) => (
                  <p key={`${section.title}-${item.label}`}>
                    <strong>{item.label}</strong>
                    <span>{item.value}</span>
                  </p>
                ))}
              </div>
            )}
          </section>
        ))}

        {hasInputOutput && (
          <section className="agent-section">
            <div className="agent-section-title"><GitBranch size={14} />Input / Output</div>
            <div className="agent-io-grid">
              {inputCount !== undefined && <div><span>Input data count</span><strong>{inputCount}</strong></div>}
              {outputCount !== undefined && <div><span>Output generated</span><strong>{outputCount}</strong></div>}
            </div>
            {inputEntries.length > 0 && (
              <div className="agent-kv-list">
                {inputEntries.map((item) => <p key={`input-${item.label}`}><strong>{item.label}</strong>{item.value}</p>)}
              </div>
            )}
            {outputEntries.length > 0 && (
              <div className="agent-kv-list output">
                {outputEntries.map((item) => <p key={`output-${item.label}`}><strong>{item.label}</strong>{item.value}</p>)}
              </div>
            )}
          </section>
        )}

        {agentEvent.reasoning && (
          <section className="agent-section agent-reasoning-box">
            <div className="agent-section-title"><Sparkles size={14} />AI reasoning</div>
            <p key={agentEvent.reasoning} className="agent-typing">{agentEvent.reasoning}</p>
          </section>
        )}

        {agentEvent.ai_summary && (
          <section className="agent-section agent-summary-box">
            <div className="agent-section-title"><BrainCircuit size={14} />Explanation</div>
            <p>{agentEvent.ai_summary}</p>
          </section>
        )}

        {showMetrics && (
          <section className="agent-section">
            <div className="agent-section-title"><Gauge size={14} />Metrics</div>
            {progress !== undefined && (
              <div className="agent-confidence">
                <div>
                  <span>{readValue(source, "progress") !== undefined ? "Progress" : "Confidence"}</span>
                  <strong>{progress}%</strong>
                </div>
                <i><b style={{ width: `${progress}%` }} /></i>
              </div>
            )}
            <div className="agent-metric-grid">
              {duration && <div><Clock3 size={13} /><span>Duration</span><strong>{duration}</strong></div>}
              {metricItems.map((item) => {
                const Icon = item.icon;
                return (
                  <div key={item.label}>
                    <Icon size={13} />
                    <span>{item.label}</span>
                    <strong>{metricValue(item.label, item.value)}</strong>
                    {item.percent !== undefined && <i><b style={{ width: `${item.percent}%` }} /></i>}
                  </div>
                );
              })}
            </div>
          </section>
        )}

        {warnings.length > 0 && (
          <section className="agent-section agent-warning-box">
            <div className="agent-section-title"><AlertTriangle size={14} />Warnings</div>
            {warnings.map((warning, index) => <p key={`${warning}-${index}`}>{warning}</p>)}
          </section>
        )}

        {errors.length > 0 && (
          <section className="agent-section agent-error-box">
            <div className="agent-section-title"><AlertTriangle size={14} />Errors</div>
            {errors.map((error, index) => <p key={`${error}-${index}`}>{error}</p>)}
          </section>
        )}

        {agentEvent.next_agent && (
          <section className="agent-section">
            <div className="agent-section-title"><GitBranch size={14} />Agent handoff</div>
            <div className="agent-handoff">
              <strong>{displayTitle}</strong>
              <i />
              <strong>{agentEvent.next_agent}</strong>
            </div>
          </section>
        )}

        {timelineWindow.length > 0 && (
          <section className="agent-section">
            <div className="agent-section-title"><Clock3 size={14} />Event timeline</div>
            <div className="agent-timeline">
              {timelineWindow.map((item, index) => (
                <p key={`${item.timestamp}-${item.event}-${index}`}>
                  <time>{formatClock(item.timestamp)}</time>
                  <strong>{item.event}</strong>
                  {item.detail && <span>{item.detail}</span>}
                </p>
              ))}
            </div>
          </section>
        )}
      </div>

      <footer className="agent-footer" onClick={(clickEvent) => clickEvent.stopPropagation()}>
        <div className="agent-footer-summary">
          <span>AI Summary</span>
          <p>{summaryText || "No backend summary emitted yet."}</p>
        </div>
        <div className="agent-footer-actions">
          {[
            ["json", "View JSON"],
            ["logs", "View Logs"],
            ["evidence", "View Evidence"],
            ["details", "Expand Details"],
          ].map(([panel, label]) => (
            <button key={panel} type="button" onClick={() => togglePanel(panel as OpenPanel)}>
              {openPanel === panel ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              {label}
            </button>
          ))}
        </div>

        {openPanel === "json" && <pre className="agent-json">{JSON.stringify(rawPayload, null, 2)}</pre>}

        {openPanel === "logs" && (
          <div className="agent-timeline agent-footer-panel">
            {timelineWindow.length ? timelineWindow.map((item, index) => (
              <p key={`footer-log-${item.timestamp}-${item.event}-${index}`}>
                <time>{formatClock(item.timestamp)}</time>
                <strong>{item.event}</strong>
                {item.detail && <span>{item.detail}</span>}
              </p>
            )) : <p><time>--:--:--</time><strong>Logs</strong><span>No logs emitted for this agent yet.</span></p>}
          </div>
        )}

        {openPanel === "evidence" && (
          <div className="agent-kv-list agent-footer-panel">
            {evidenceEntries.length ? evidenceEntries.map((item) => (
              <p key={`evidence-${item.label}`}><strong>{item.label}</strong><span>{item.value}</span></p>
            )) : <p><strong>Evidence</strong><span>No evidence payload emitted yet.</span></p>}
          </div>
        )}

        {openPanel === "details" && (
          <div className="agent-kv-list agent-footer-panel">
            {executionRows.map(([label, value]) => (
              <p key={`detail-${String(label)}`}><strong>{label}</strong><span>{String(value)}</span></p>
            ))}
          </div>
        )}
      </footer>
    </article>
  );
}

export default memo(AgentCard);
