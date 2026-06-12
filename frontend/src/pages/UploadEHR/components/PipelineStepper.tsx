import {
  AlertTriangle,
  Brain,
  Building2,
  CircleDollarSign,
  ClipboardCheck,
  FileCheck2,
  FileSearch,
  GraduationCap,
  Send,
  ShieldCheck,
} from "lucide-react";

type PipelineStepperProps = {
  item: any;
  pipelineData?: any;
  events?: any[];
};

type PipelineStageState =
  | "completed"
  | "approval"
  | "rejected"
  | "running"
  | "skipped"
  | "pending";

type PipelineStageConfig = {
  key: string;
  aliases: string[];
  label: string;
  icon: any;
};

type StageEvidence = {
  stage?: any;
  status?: any;
  message?: any;
  source:
    | "live"
    | "pipeline"
    | "itemPipeline"
    | "history"
    | "fallback"
    | "manual";
  raw?: any;
};

const PIPELINE_STAGES: PipelineStageConfig[] = [
  {
    key: "ocr",
    aliases: ["ocr", "extract", "extraction", "intake", "document_processing"],
    label: "OCR",
    icon: FileSearch,
  },
  {
    key: "validation",
    aliases: ["validate", "validation", "rules", "rules_validation", "eligibility"],
    label: "Validate",
    icon: ClipboardCheck,
  },
  {
    key: "compliance",
    aliases: ["compliance", "case_orchestrator", "case_orchestration"],
    label: "Compliance",
    icon: ShieldCheck,
  },
  {
    key: "submission",
    aliases: ["submission", "submit", "submitted"],
    label: "Submission",
    icon: Send,
  },
  {
    key: "clearinghouse",
    aliases: [
      "clearinghouse",
      "clearing_house",
      "clearinghouse_queued",
      "clearinghouse_accepted",
      "clearinghouse_review",
      "clearinghouse_approval",
      "waiting_for_approval",
      "pending_clearinghouse",
      "payer_review",
    ],
    label: "Clearinghouse",
    icon: Building2,
  },
  {
    key: "acknowledgment",
    aliases: [
      "ack",
      "acknowledgment",
      "acknowledgement",
      "acknowledged",
      "payer",
      "payer_acknowledgment",
      "payer_acknowledgement",
      "payer_ack",
      "payer_acknowledged",
      "277",
      "999",
    ],
    label: "Acknowledgment",
    icon: FileCheck2,
  },
  {
    key: "denial_ai",
    aliases: [
      "denial",
      "denial_ai",
      "denialai",
      "denial_analysis",
      "denial_analyzed",
      "denial_checked",
      "denial_ai_completed",
    ],
    label: "Denial AI",
    icon: AlertTriangle,
  },
  {
    key: "payment",
    aliases: ["payment", "paid", "payment_posting", "payment_completed"],
    label: "Payment",
    icon: CircleDollarSign,
  },
  {
    key: "learning",
    aliases: ["learning", "learning_updated", "feedback", "feedback_captured"],
    label: "Learning",
    icon: GraduationCap,
  },
  {
    key: "analytics",
    aliases: ["analytics", "analytics_done", "finish", "completed", "complete"],
    label: "Analytics",
    icon: Brain,
  },
];

const normalizeToken = (value: any) =>
  String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, "_")
    .replace(/__+/g, "_");

const normalizeStatus = (value: any) => {
  if (value === null || value === undefined || value === "") return "";

  if (typeof value === "object") {
    return String(
      value.status ||
        value.state ||
        value.pipeline_state ||
        value.pipeline_status ||
        value.current_status ||
        ""
    )
      .trim()
      .toUpperCase()
      .replace(/[\s-]+/g, "_")
      .replace(/__+/g, "_");
  }

  return String(value)
    .trim()
    .toUpperCase()
    .replace(/[\s-]+/g, "_")
    .replace(/__+/g, "_");
};

const formatDisplayStatus = (value: any) => {
  const normalized = normalizeStatus(value);

  if (!normalized || normalized === "PENDING") return "Pending";

  if (
    ["SKIPPED", "SKIP", "NOT_APPLICABLE", "NOT_APPLICABLE_FOR_DOCUMENT", "N_A", "NA"].includes(
      normalized
    )
  ) {
    return "Skipped";
  }

  if (["DENIAL_ANALYZED", "DENIAL_AI_COMPLETED"].includes(normalized)) {
    return "Completed";
  }

  if (normalized === "PAUSED") return "Paused";

  return normalized
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (char) => char.toUpperCase());
};

const stageTerms = (stage: PipelineStageConfig) =>
  [stage.key, stage.label, ...stage.aliases].map(normalizeToken).filter(Boolean);

const stageMatches = (stage: PipelineStageConfig, value: any) => {
  const normalized = normalizeToken(value).replace(/_agent$/g, "");
  if (!normalized) return false;

  return stageTerms(stage).some(
    (term) => normalized === term || normalized.includes(term)
  );
};

const claimPayloadOf = (item: any) =>
  item?.claim || item?.payload?.claim || item?.payload || item || {};

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
    events: pipelines.flatMap((pipeline) =>
      Array.isArray(pipeline?.events) ? pipeline.events : []
    ),
  };
};

const mergePipelinePayload = (item: any, pipelineData: any = {}) => {
  return mergePipelineObjects(
    item?.pipeline,
    item?.payload?.pipeline,
    item?.claim?.pipeline,
    item?.payload?.claim?.pipeline,
    pipelineData,
    pipelineData?.pipeline
  );
};

const stageNameOf = (entry: any) =>
  entry?.stage ||
  entry?.stage_key ||
  entry?.current_stage ||
  entry?.active_step ||
  entry?.step ||
  entry?.id ||
  entry?.key ||
  entry?.name ||
  entry?.label ||
  entry?.agent ||
  entry?.current_agent ||
  entry?.type ||
  entry?.event;

const statusOf = (entry: any) =>
  entry?.status ||
  entry?.state ||
  entry?.pipeline_state ||
  entry?.pipeline_status ||
  entry?.result ||
  entry?.outcome ||
  entry?.value;

const messageOf = (entry: any) =>
  entry?.message ||
  entry?.reason ||
  entry?.ai_summary ||
  entry?.summary ||
  entry?.description ||
  entry?.current_step ||
  entry?.agent ||
  entry?.updated_at ||
  entry?.timestamp;

const timestampMs = (entry: any) => {
  const value =
    entry?.timestamp ||
    entry?.updated_at ||
    entry?.updatedAt ||
    entry?.completed_at ||
    entry?.started_at ||
    entry?.created_at;

  const timestamp = new Date(value || 0).getTime();
  return Number.isFinite(timestamp) ? timestamp : 0;
};

const normalizeStageEntry = (
  entry: any,
  source: StageEvidence["source"]
): StageEvidence => ({
  stage: stageNameOf(entry),
  status: statusOf(entry),
  message: messageOf(entry),
  source,
  raw: entry,
});

const entriesFromMap = (map: any, source: StageEvidence["source"]) => {
  if (!map || typeof map !== "object" || Array.isArray(map)) return [];

  return Object.entries(map).map(([stage, value]) => {
    if (value && typeof value === "object") {
      return normalizeStageEntry({ stage, ...(value as Record<string, any>) }, source);
    }

    return normalizeStageEntry({ stage, status: value }, source);
  });
};

const entriesFromList = (list: any, source: StageEvidence["source"]) =>
  Array.isArray(list) ? list.map((entry) => normalizeStageEntry(entry, source)) : [];

const collectPipelineEntries = (
  pipeline: any,
  source: StageEvidence["source"]
) => [
  ...entriesFromMap(pipeline?.stage_status, source),
  ...entriesFromMap(pipeline?.steps, source),
  ...entriesFromMap(pipeline?.agents, source),
  ...entriesFromList(pipeline?.steps, source),
  ...entriesFromList(pipeline?.stages, source),
  ...entriesFromList(pipeline?.stage_history, source),
  ...entriesFromList(pipeline?.agent_events, source),
  ...entriesFromList(pipeline?.events, source),
];

const collectHistoryEntries = (item: any) => [
  ...entriesFromList(item?.stage_history, "history"),
  ...entriesFromList(item?.audit_history, "history"),
  ...entriesFromList(item?.payload?.stage_history, "history"),
  ...entriesFromList(item?.claim?.stage_history, "history"),
  ...entriesFromList(item?.claim?.audit_history, "history"),
];

const getClaimId = (item: any) =>
  String(
    item?.claim_id ||
      item?.claim?.claim_id ||
      item?.payload?.claim_id ||
      item?.payload?.claim?.claim_id ||
      ""
  );

const collectLiveEntries = (
  events: any[] = [],
  pipeline: any = {},
  claimId?: string
) => {
  const externalEvents = Array.isArray(events) ? events : [];
  const pipelineEvents = Array.isArray(pipeline?.events) ? pipeline.events : [];

  return [...externalEvents, ...pipelineEvents]
    .filter((event) => {
      if (!claimId) return true;

      const eventClaimId =
        event?.claim_id ||
        event?.claimId ||
        event?.claim?.claim_id ||
        event?.data?.claim_id ||
        event?.payload?.claim_id;

      if (!eventClaimId) return true;

      return String(eventClaimId) === String(claimId);
    })
    .flatMap((entry) => [
      normalizeStageEntry(entry, "live"),
      ...collectPipelineEntries(entry?.pipeline, "live"),
      ...collectPipelineEntries(entry?.claim?.pipeline, "live"),
      ...collectPipelineEntries(entry?.payload?.pipeline, "live"),
      ...collectPipelineEntries(entry?.payload?.claim?.pipeline, "live"),
      ...collectPipelineEntries(entry?.data?.pipeline, "live"),
      ...collectPipelineEntries(entry?.data?.claim?.pipeline, "live"),
    ]);
};

const latestForStage = (stage: PipelineStageConfig, entries: StageEvidence[]) =>
  entries
    .filter((entry) => stageMatches(stage, entry.stage))
    .sort((a, b) => timestampMs(b.raw) - timestampMs(a.raw))[0];

const stageStateFromStatus = (status: any): PipelineStageState => {
  const normalized = normalizeStatus(status);

  if (
    [
      "COMPLETED",
      "COMPLETE",
      "SUCCESS",
      "DONE",
      "PAID",
      "ACCEPTED",
      "APPROVED",
      "AUTO_APPROVED",
      "DENIAL_ANALYZED",
      "DENIAL_AI_COMPLETED",
      "PAYMENT_COMPLETED",
      "CLAIM_COMPLETED",
    ].includes(normalized) ||
    normalized.endsWith("_COMPLETED")
  ) {
    return "completed";
  }

  if (
    [
      "SKIPPED",
      "SKIP",
      "NOT_APPLICABLE",
      "NOT_APPLICABLE_FOR_DOCUMENT",
      "N_A",
      "NA",
    ].includes(normalized)
  ) {
    return "skipped";
  }

  if (
    [
      "WAITING_FOR_APPROVAL",
      "PENDING_APPROVAL",
      "PENDING_CLEARINGHOUSE",
      "HITL_REQUIRED",
      "HUMAN_REVIEW_REQUIRED",
      "MANUAL_REVIEW_REQUIRED",
      "WAITING_FOR_REVIEW",
      "PAUSED",
    ].includes(normalized)
  ) {
    return "approval";
  }

  if (
    [
      "HARD_REJECT",
      "HARD_REJECTED",
      "REJECTED",
      "DENIED",
      "FAILED",
      "ERROR",
      "FAILED_VALIDATION",
      "VALIDATION_FAILED",
    ].includes(normalized)
  ) {
    return "rejected";
  }

  if (
    [
      "RUNNING",
      "PROCESSING",
      "IN_PROGRESS",
      "ACTIVE",
      "QUEUED",
      "DENIAL_AI_RUNNING",
      "DENIAL_AI_REQUIRED",
    ].includes(normalized)
  ) {
    return "running";
  }

  return "pending";
};

const claimStatusOf = (item: any, pipeline: any) => {
  const claim = claimPayloadOf(item);

  return normalizeStatus(
    item?.status ||
      claim?.status ||
      pipeline?.overall_status ||
      pipeline?.status ||
      pipeline?.pipeline_state ||
      pipeline?.pipeline_status ||
      claim?.pipeline_state ||
      claim?.pipeline_status ||
      item?.pipeline_state ||
      item?.pipeline_status
  );
};

const currentStageOf = (item: any, pipeline: any) => {
  const claim = claimPayloadOf(item);

  return (
    item?.current_stage ||
    item?.stage ||
    item?.active_step ||
    item?.current_agent ||
    claim?.current_stage ||
    claim?.stage ||
    claim?.active_step ||
    claim?.current_agent ||
    pipeline?.current_stage ||
    pipeline?.active_step ||
    pipeline?.workflow_state ||
    pipeline?.current_agent ||
    item?.currentStep ||
    item?.payload?.stage ||
    item?.payload?.current_stage
  );
};

const isApprovalClaim = (status: string, currentStage: any) => {
  if (
    [
      "PAID",
      "COMPLETED",
      "CLAIM_COMPLETED",
      "PAYMENT_COMPLETED",
      "ANALYTICS_COMPLETED",
      "DENIAL_ANALYZED",
      "DENIAL_AI_COMPLETED",
    ].includes(status)
  ) {
    return false;
  }

  const normalizedStage = normalizeToken(currentStage);

  return (
    ["WAITING_FOR_APPROVAL", "PENDING_APPROVAL", "PENDING_CLEARINGHOUSE"].includes(status) ||
    [
      "waiting_for_approval",
      "pending_approval",
      "pending_clearinghouse",
      "clearinghouse_approval",
      "clearinghouse_review",
    ].includes(normalizedStage)
  );
};

const isRejectedClaim = (status: string) =>
  ["HARD_REJECT", "HARD_REJECTED", "REJECTED", "DENIED", "FAILED", "ERROR"].includes(
    status
  );

const isHitlClaim = (status: string) =>
  [
    "HITL_REQUIRED",
    "HUMAN_REVIEW_REQUIRED",
    "MANUAL_REVIEW_REQUIRED",
    "WAITING_FOR_REVIEW",
    "NEEDS_REVIEW",
    "HUMAN_REVIEW",
  ].includes(status);

const isEobEraClaim = (item: any, pipeline: any) => {
  const claim = claimPayloadOf(item);
  const status = claimStatusOf(item, pipeline);
  const currentStage = normalizeToken(currentStageOf(item, pipeline));

  const docType = normalizeStatus(
    claim?.document_type ||
      claim?.form_type ||
      claim?.doc_type ||
      item?.document_type ||
      item?.form_type ||
      item?.doc_type
  );
  const documentStatus = normalizeStatus(
    claim?.document_status ||
      claim?.document_state ||
      item?.document_status ||
      item?.document_state
  );

  return (
    ["EOB_ERA", "EOB", "ERA", "DENIAL_AI_ONLY", "DENIAL_ANALYSIS_ONLY"].includes(docType) ||
    docType.includes("EOB") ||
    docType.includes("ERA") ||
    documentStatus.includes("EOB") ||
    documentStatus.includes("ERA") ||
    documentStatus.includes("DENIAL_AI_ONLY") ||
    claim?.denial_ai_required === true ||
    item?.denial_ai_required === true ||
    status === "DENIAL_AI_REQUIRED" ||
    status === "DENIAL_AI_RUNNING" ||
    status === "DENIAL_ANALYZED" ||
    currentStage === "denial_ai"
  );
};

const explicitEntriesForStage = (
  stage: PipelineStageConfig,
  entries: StageEvidence[]
) =>
  entries.filter(
    (entry) =>
      entry.source !== "fallback" &&
      entry.source !== "manual" &&
      stageMatches(stage, entry.stage)
  );

const buildStageEvidence = (item: any, pipelineData: any = {}, events: any[] = []) => {
  const mergedPipeline = mergePipelinePayload(item, pipelineData);

  const normalizedItem = {
    ...item,
    pipeline: mergedPipeline,
    claim: {
      ...(item?.claim || {}),
      pipeline: mergedPipeline,
    },
  };

  const claimId = getClaimId(normalizedItem);
  const liveEntries = collectLiveEntries(events, mergedPipeline, claimId);
  const pipelineEntries = collectPipelineEntries(mergedPipeline, "pipeline");
  const historyEntries = collectHistoryEntries(normalizedItem);

  const claimStatus = claimStatusOf(normalizedItem, mergedPipeline);
  const currentStage = currentStageOf(normalizedItem, mergedPipeline);
  const isEobEra = isEobEraClaim(normalizedItem, mergedPipeline);

  const entriesByPriority = [liveEntries, pipelineEntries, historyEntries];

  let stages = PIPELINE_STAGES.map((stage) => {
    const evidence =
      entriesByPriority.map((entries) => latestForStage(stage, entries)).find(Boolean) ||
      (stageMatches(stage, currentStage)
        ? ({
            stage: currentStage,
            status: claimStatus,
            message: "Current pipeline stage",
            source: "fallback",
          } as StageEvidence)
        : ({
            stage: stage.key,
            status: "PENDING",
            message: "Awaiting event",
            source: "fallback",
          } as StageEvidence));

    return {
      ...stage,
      status: normalizeStatus(evidence.status) || "PENDING",
      state: stageStateFromStatus(evidence.status),
      message: evidence.message || "Awaiting event",
      source: evidence.source,
      raw: evidence.raw,
    };
  });

  if (isEobEra) {
    stages = stages.map((stage) => {
      if (stage.key === "ocr") {
        return {
          ...stage,
          status: stage.status === "PENDING" ? "COMPLETED" : stage.status,
          state: stage.state === "pending" ? "completed" : stage.state,
          message:
            stage.message === "Awaiting event"
              ? "Document processed"
              : stage.message,
          source: "manual" as StageEvidence["source"],
        };
      }

      if (
        [
          "validation",
          "compliance",
          "submission",
          "clearinghouse",
          "acknowledgment",
        ].includes(stage.key)
      ) {
        return {
          ...stage,
          status: "SKIPPED",
          state: "skipped" as PipelineStageState,
          message: "Skipped for EOB/ERA document",
          source: "manual" as StageEvidence["source"],
        };
      }

      if (stage.key === "denial_ai") {
        if (["completed", "rejected"].includes(stage.state)) {
          return stage;
        }

        if (["DENIAL_ANALYZED", "COMPLETED", "PAID", "CLAIM_COMPLETED"].includes(claimStatus)) {
          return {
            ...stage,
            status: "COMPLETED",
            state: "completed" as PipelineStageState,
            message: "Denial analysis completed",
            source: "manual" as StageEvidence["source"],
          };
        }

        if (["DENIAL_AI_REQUIRED", "DENIAL_AI_RUNNING"].includes(claimStatus)) {
          return {
            ...stage,
            status: "RUNNING",
            state: "running" as PipelineStageState,
            message: "Denial analysis in progress",
            source: "manual" as StageEvidence["source"],
          };
        }
      }

      if (
        stage.key === "payment" &&
        stage.state === "pending" &&
        ["PAID", "PAYMENT_COMPLETED"].includes(claimStatus)
      ) {
        return {
          ...stage,
          status: "COMPLETED",
          state: "completed" as PipelineStageState,
          message: "Payment completed",
          source: "manual" as StageEvidence["source"],
        };
      }

      if (
        stage.key === "analytics" &&
        stage.state === "pending" &&
        ["COMPLETED", "CLAIM_COMPLETED"].includes(claimStatus)
      ) {
        return {
          ...stage,
          status: "COMPLETED",
          state: "completed" as PipelineStageState,
          message: "Analytics completed",
          source: "manual" as StageEvidence["source"],
        };
      }

      return stage;
    });
  }

  if (isHitlClaim(claimStatus)) {
    const currentStageConfig = PIPELINE_STAGES.find((stage) =>
      stageMatches(stage, currentStage)
    );
    const approvalStageKey = currentStageConfig?.key || "compliance";
    const approvalIndex = PIPELINE_STAGES.findIndex(
      (stage) => stage.key === approvalStageKey
    );

    stages = stages.map((stage, index) => {
      const hasExplicitEvidence =
        explicitEntriesForStage(stage, [
          ...liveEntries,
          ...pipelineEntries,
          ...historyEntries,
        ]).length > 0;

      if (index < approvalIndex && stage.state === "pending") {
        return {
          ...stage,
          status: "COMPLETED",
          state: "completed" as PipelineStageState,
          message: "Completed before manual review",
          source: "manual" as StageEvidence["source"],
        };
      }

      if (
        stage.key === approvalStageKey &&
        !["completed", "rejected"].includes(stage.state)
      ) {
        return {
          ...stage,
          status: claimStatus,
          state: "approval" as PipelineStageState,
          message:
            stage.message === "Awaiting event"
              ? "Waiting for human review"
              : stage.message,
        };
      }

      if (index > approvalIndex && !hasExplicitEvidence) {
        return {
          ...stage,
          status: "PENDING",
          state: "pending" as PipelineStageState,
          message: "Pending manual review decision",
        };
      }

      return stage;
    });
  }

  if (isApprovalClaim(claimStatus, currentStage)) {
    stages = stages.map((stage) => {
      if (
        ["ocr", "validation", "compliance", "submission"].includes(stage.key) &&
        stage.state === "pending"
      ) {
        return {
          ...stage,
          status: "COMPLETED",
          state: "completed" as PipelineStageState,
          message: "Completed before clearinghouse approval",
          source: "manual" as StageEvidence["source"],
        };
      }

      if (
        stage.key === "clearinghouse" &&
        !["completed", "rejected"].includes(stage.state)
      ) {
        return {
          ...stage,
          status: "WAITING_FOR_APPROVAL",
          state: "approval" as PipelineStageState,
          message: "Awaiting clearinghouse approval",
          source: stage.source,
        };
      }

      if (
        ["denial_ai", "payment", "learning", "analytics"].includes(stage.key) &&
        explicitEntriesForStage(stage, [...liveEntries, ...pipelineEntries, ...historyEntries])
          .length === 0
      ) {
        return {
          ...stage,
          status: "PENDING",
          state: "pending" as PipelineStageState,
          message: "Pending clearinghouse decision",
        };
      }

      return stage;
    });
  }

  if (isRejectedClaim(claimStatus)) {
    const explicitRejectedStage = stages.find((stage) => stage.state === "rejected");
    const currentStageConfig = PIPELINE_STAGES.find((stage) =>
      stageMatches(stage, currentStage)
    );
    const rejectedStageKey = explicitRejectedStage?.key || currentStageConfig?.key || "clearinghouse";
    const rejectedIndex = PIPELINE_STAGES.findIndex(
      (stage) => stage.key === rejectedStageKey
    );

    stages = stages.map((stage, index) => {
      if (stage.key === rejectedStageKey) {
        return {
          ...stage,
          status: claimStatus,
          state: "rejected" as PipelineStageState,
          message:
            stage.message === "Awaiting event"
              ? "Claim rejected at this stage"
              : stage.message,
        };
      }

      if (index > rejectedIndex) {
        return {
          ...stage,
          status: "PENDING",
          state: "pending" as PipelineStageState,
          message: "Not reached after rejection",
        };
      }

      if (stage.state === "completed") return stage;

      return {
        ...stage,
        status: "PENDING",
        state: "pending" as PipelineStageState,
      };
    });
  }

  if (
    !isEobEra &&
    ["PAID", "COMPLETED", "CLAIM_COMPLETED"].includes(claimStatus)
  ) {
    stages = stages.map((stage) => ({
      ...stage,
      status: "COMPLETED",
      state: "completed" as PipelineStageState,
      message: stage.message === "Awaiting event" ? "Completed" : stage.message,
      source: stage.source === "fallback" ? ("manual" as StageEvidence["source"]) : stage.source,
    }));
  }

  return stages;
};

const StepIcon = ({
  stage,
}: {
  stage: PipelineStageConfig & { state: PipelineStageState };
}) => {
  const Icon = stage.icon || FileCheck2;
  return <Icon size={17} />;
};

const PipelineStepper = ({ item, pipelineData, events = [] }: PipelineStepperProps) => {
  const stages = buildStageEvidence(item, pipelineData, events);

    console.log("[PIPELINE STEPPER LIVE]", {
    claimId: item?.claim_id || item?.claim?.claim_id,
    activeStep: pipelineData?.active_step || item?.active_step,
    status: item?.status || pipelineData?.pipeline_status,
    steps: pipelineData?.steps || item?.pipeline?.steps,
  }); 

  return (
    <section className="cw-expanded-stepper">
      {stages.map((stage, index) => (
        <div className={`cw-expanded-step ${stage.state}`} key={stage.key}>
          <div className="cw-expanded-step-line" />

          <div className="cw-expanded-step-icon">
            <StepIcon stage={stage} />
          </div>

          <strong>
            {index + 1}. {stage.label}
          </strong>

          <span>{formatDisplayStatus(stage.status)}</span>
          <small>{stage.message || "Awaiting event"}</small>
        </div>
      ))}
    </section>
  );
};

export default PipelineStepper;
