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

const firstPresent = (...values: any[]) =>
  values.find((value) => value !== undefined && value !== null && value !== "");

const normalizeStatus = (value: any) =>
  String(value || "")
    .trim()
    .toUpperCase()
    .replace(/[\s-]+/g, "_")
    .replace(/__+/g, "_");

const normalizeEventType = (event: any) =>
  String(event?.type || event?.event || event?.data?.type || event?.payload?.type || "")
    .trim()
    .toLowerCase();

export const normalizeStepKey = (value: any) => {
  const raw = String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, "_")
    .replace(/__+/g, "_");

  const aliases: Record<string, string> = {
    extraction: "ocr",
    extract: "ocr",
    intake: "ocr",
    ocr: "ocr",
    document_processing: "ocr",

    validate: "validation",
    validation: "validation",
    rules: "validation",
    rules_validation: "validation",
    eligibility: "validation",

    compliance: "compliance",
    case_orchestrator: "compliance",
    case_orchestration: "compliance",

    submit: "submission",
    submitted: "submission",
    submission: "submission",

    clearinghouse: "clearinghouse",
    clearing_house: "clearinghouse",
    clearinghouse_queued: "clearinghouse",
    clearinghouse_accepted: "clearinghouse",
    clearinghouse_review: "clearinghouse",
    clearinghouse_approval: "clearinghouse",
    pending_clearinghouse: "clearinghouse",
    waiting_for_approval: "clearinghouse",

    ack: "acknowledgment",
    acknowledged: "acknowledgment",
    acknowledgment: "acknowledgment",
    acknowledgement: "acknowledgment",
    payer: "acknowledgment",
    payer_ack: "acknowledgment",
    payer_acknowledgment: "acknowledgment",
    payer_acknowledgement: "acknowledgment",

    denial: "denial_ai",
    denialai: "denial_ai",
    denial_ai: "denial_ai",
    denial_analysis: "denial_ai",
    denial_analyzed: "denial_ai",
    denial_checked: "denial_ai",

    payment: "payment",
    paid: "payment",
    payment_posting: "payment",
    payment_completed: "payment",

    learning: "learning",
    learning_updated: "learning",

    analytics: "analytics",
    analytics_done: "analytics",
    finish: "analytics",
    finalized: "analytics",
    completed: "analytics",
    complete: "analytics",
    claim_completed: "analytics",
    pipeline_completed: "analytics",
  };

  return aliases[raw] || raw;
};

const pipelineOf = (source: any) =>
  mergeObjects(
    source?.pipeline,
    source?.payload?.pipeline,
    source?.claim?.pipeline,
    source?.payload?.claim?.pipeline,
    source?.data?.pipeline,
    source?.data?.claim?.pipeline
  );

const nestedClaimOf = (source: any) =>
  mergeObjects(
    source?.payload?.claim,
    source?.data?.claim,
    source?.claim
  );

const caseOf = (source: any) =>
  mergeObjects(
    source?.case,
    source?.hitl_case,
    source?.hitlCase,
    source?.payload?.case,
    source?.payload?.hitl_case,
    source?.data?.case,
    source?.data?.hitl_case,
    source?.claim?.case,
    source?.claim?.hitl_case
  );

const claimIdOf = (source: any) =>
  firstPresent(
    source?.claim_id,
    source?.claimId,
    source?.id,
    source?.payload?.claim_id,
    source?.payload?.claimId,
    source?.payload?.claim?.claim_id,
    source?.payload?.claim?.claimId,
    source?.data?.claim_id,
    source?.data?.claimId,
    source?.data?.claim?.claim_id,
    source?.data?.claim?.claimId,
    source?.claim?.claim_id,
    source?.claim?.claimId
  );

const isFinalPipelineEvent = (event: any, stepKey?: string) => {
  const type = normalizeEventType(event);
  const status = normalizeStatus(
    firstPresent(
      event?.claim?.status,
      event?.payload?.claim?.status,
      event?.data?.claim?.status,
      event?.status,
      event?.pipeline_status,
      event?.pipeline_state
    )
  );
  const stage = normalizeStepKey(
    firstPresent(event?.stage, event?.current_stage, event?.active_step, stepKey)
  );

  return (
    type === "claim_completed" ||
    type === "pipeline_completed" ||
    status === "PAID" ||
    status === "CLAIM_COMPLETED" ||
    (status === "COMPLETED" && stage === "analytics")
  );
};

export const eventToPipelinePatch = (event: any = {}) => {
  const existingPipeline = pipelineOf(event);
  const stepKey = normalizeStepKey(
    firstPresent(
      event?.active_step,
      event?.step,
      event?.stage,
      event?.current_stage,
      event?.agent,
      event?.current_agent,
      existingPipeline?.active_step,
      existingPipeline?.current_stage
    )
  );
  const timestamp =
    event?.updated_at || event?.timestamp || event?.data?.timestamp || new Date().toISOString();
  const stepStatus = firstPresent(
    event?.status,
    event?.pipeline_status,
    event?.pipeline_state,
    existingPipeline?.pipeline_status,
    existingPipeline?.pipeline_state
  );
  const finalEvent = isFinalPipelineEvent(event, stepKey);
  const stageOnlyAgentEvent = normalizeEventType(event) === "agent_update" && !finalEvent;

  return {
    ...event,
    active_step: firstPresent(event?.active_step, stepKey, existingPipeline?.active_step),
    pipeline: {
      ...existingPipeline,
      current_stage: firstPresent(
        event?.current_stage,
        event?.stage,
        existingPipeline?.current_stage
      ),
      current_agent: firstPresent(
        event?.current_agent,
        event?.agent,
        existingPipeline?.current_agent
      ),
      active_step: firstPresent(event?.active_step, stepKey, existingPipeline?.active_step),
      pipeline_state: firstPresent(event?.pipeline_state, existingPipeline?.pipeline_state),
      pipeline_status: firstPresent(
        stageOnlyAgentEvent ? undefined : event?.pipeline_status,
        finalEvent ? event?.status : undefined,
        existingPipeline?.pipeline_status
      ),
      progress: event?.progress ?? existingPipeline?.progress,
      steps: {
        ...(existingPipeline?.steps || {}),
        ...(stepKey
          ? {
              [stepKey]: {
                status: stepStatus,
                stage: firstPresent(event?.stage, event?.current_stage),
                agent: firstPresent(event?.current_agent, event?.agent),
                progress: event?.progress,
                message: firstPresent(event?.message, event?.reason, stepStatus),
                updated_at: timestamp,
              },
            }
          : {}),
      },
    },
  };
};

export const mergePipeline = (oldClaim: any = {}, incoming: any = {}) => {
  const oldPipeline = pipelineOf(oldClaim);
  const eventPipeline = pipelineOf(incoming);

  return {
    ...oldPipeline,
    ...eventPipeline,
    steps: {
      ...(oldPipeline?.steps || {}),
      ...(eventPipeline?.steps || {}),
    },
    stage_status: {
      ...(oldPipeline?.stage_status || {}),
      ...(eventPipeline?.stage_status || {}),
    },
    agents: {
      ...(oldPipeline?.agents || {}),
      ...(eventPipeline?.agents || {}),
    },
    events: [
      ...(Array.isArray(oldPipeline?.events) ? oldPipeline.events : []),
      ...(Array.isArray(eventPipeline?.events) ? eventPipeline.events : []),
    ],
  };
};

export const mergeClaimLiveUpdate = (oldClaim: any = {}, rawEvent: any = {}) => {
  const event = eventToPipelinePatch(rawEvent);
  const pipeline = mergePipeline(oldClaim, event);
  const oldNestedClaim = nestedClaimOf(oldClaim);
  const incomingNestedClaim = nestedClaimOf(event);
  const eventCase = caseOf(event);
  const oldCase = caseOf(oldClaim);
  const stepKey = normalizeStepKey(
    firstPresent(event?.active_step, event?.stage, event?.current_stage)
  );
  const finalEvent = isFinalPipelineEvent(event, stepKey);
  const stageOnlyAgentEvent = normalizeEventType(event) === "agent_update" && !finalEvent;
  const currentStage = firstPresent(
    event?.current_stage,
    event?.stage,
    incomingNestedClaim?.current_stage,
    oldClaim?.current_stage,
    oldNestedClaim?.current_stage
  );
  const status = firstPresent(
    incomingNestedClaim?.status,
    finalEvent ? firstPresent(event?.status, event?.pipeline_status, event?.pipeline_state) : undefined,
    stageOnlyAgentEvent ? undefined : event?.pipeline_status,
    oldClaim?.status,
    oldNestedClaim?.status,
    event?.status && !stageOnlyAgentEvent
      ? event.status
      : undefined,
    "PROCESSING"
  );

  const mergedClaim = {
    ...oldClaim,
    ...event,
    ...incomingNestedClaim,

    claim_id:
      claimIdOf(event) ||
      claimIdOf(incomingNestedClaim) ||
      claimIdOf(oldClaim) ||
      claimIdOf(oldNestedClaim),

    status,
    current_stage: currentStage,
    current_agent: firstPresent(
      event?.current_agent,
      event?.agent,
      incomingNestedClaim?.current_agent,
      oldClaim?.current_agent,
      oldNestedClaim?.current_agent
    ),
    active_step: firstPresent(
      event?.active_step,
      stepKey,
      incomingNestedClaim?.active_step,
      oldClaim?.active_step
    ),
    progress: event?.progress ?? incomingNestedClaim?.progress ?? oldClaim?.progress,
    pipeline_state: firstPresent(
      event?.pipeline_state,
      incomingNestedClaim?.pipeline_state,
      oldClaim?.pipeline_state
    ),
    pipeline_status: firstPresent(
      stageOnlyAgentEvent ? undefined : event?.pipeline_status,
      finalEvent ? event?.status : undefined,
      incomingNestedClaim?.pipeline_status,
      oldClaim?.pipeline_status
    ),
    review_required:
      event?.review_required ??
      incomingNestedClaim?.review_required ??
      oldClaim?.review_required,
    approval_required:
      event?.approval_required ??
      incomingNestedClaim?.approval_required ??
      oldClaim?.approval_required,
    pipeline_paused:
      event?.pipeline_paused ??
      incomingNestedClaim?.pipeline_paused ??
      oldClaim?.pipeline_paused,
    pipeline,
    claim: {
      ...oldNestedClaim,
      ...incomingNestedClaim,
      pipeline,
    },
    updatedAt: event?.updated_at || event?.timestamp || new Date().toISOString(),
  };

  if (isPlainObject(eventCase) && Object.keys(eventCase).length > 0) {
    mergedClaim.case = mergeObjects(oldCase, eventCase);
    mergedClaim.hitl_case = mergedClaim.case;
    mergedClaim.case_id = mergedClaim.case.case_id || oldClaim?.case_id;
  }

  return mergedClaim;
};
