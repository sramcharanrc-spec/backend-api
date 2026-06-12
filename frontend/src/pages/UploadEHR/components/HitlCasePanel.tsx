import React from "react";

type HitlCasePanelProps = {
  claimId: string;
  hitlCase: any;
  claim?: any;
  pipeline?: any;
  actionMessage?: string;
  onRouteCase: (claimId: string, role: string) => void;
  onApproveHitlCase: (claimId: string) => void;
  onEscalateHitlCase: (claimId: string) => void;
};

const asArray = (value: any): any[] => {
  if (!value) return [];
  return Array.isArray(value) ? value : [value];
};

const normalizeText = (value: any): string => {
  if (value === null || value === undefined || value === "") {
    return "Not reported";
  }

  if (typeof value === "string") {
    return value;
  }

  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }

  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
};

const getNestedCase = (value: any) => {
  if (!value) return null;

  return (
    value?.case ||
    value?.hitl_case ||
    value?.hitlCase ||
    value?.caseRecord ||
    value?.review_case ||
    value?.payload?.case ||
    value?.payload?.hitl_case ||
    value?.claim?.case ||
    value?.claim?.hitl_case ||
    value?.pipeline?.case ||
    null
  );
};

const getCompliance = (claim: any, hitlCase: any, pipeline: any) => {
  return (
    claim?.compliance ||
    hitlCase?.compliance ||
    hitlCase?.claim?.compliance ||
    pipeline?.compliance ||
    {}
  );
};

const getFailedRules = (claim: any, hitlCase: any, pipeline: any): any[] => {
  const compliance = getCompliance(claim, hitlCase, pipeline);

  return [
    ...asArray(compliance?.failed_rules),
    ...asArray(compliance?.failures),
    ...asArray(claim?.failed_rules),
    ...asArray(hitlCase?.failed_rules),
    ...asArray(pipeline?.failed_rules),
  ].filter(Boolean);
};

const getCaseReasons = (caseData: any, claim: any, hitlCase: any, pipeline: any): string[] => {
  const compliance = getCompliance(claim, hitlCase, pipeline);
  const failedRules = getFailedRules(claim, hitlCase, pipeline);

  const reasons = [
    ...asArray(caseData?.case_reasons),
    ...asArray(caseData?.issues),
    ...asArray(caseData?.reasons),
    ...asArray(claim?.issues),
    ...asArray(compliance?.issues),
    ...asArray(compliance?.warnings),
    claim?.failure_reason,
    claim?.reason,
    compliance?.reason,
    compliance?.message,
    hitlCase?.reason,
  ].filter(Boolean);

  failedRules.forEach((rule) => {
    const ruleName = rule?.rule || rule?.code || rule?.label || "Rule";
    const reason = rule?.reason || rule?.message || rule?.status || "Failed";
    reasons.push(`${ruleName}: ${reason}`);
  });

  const unique = Array.from(new Set(reasons.map((item) => normalizeText(item))));

  return unique.length ? unique : ["Human review required"];
};

const buildFallbackCase = (claim: any, pipeline: any, hitlCase: any) => {
  const source = claim || hitlCase?.claim || hitlCase || {};
  const pipe = pipeline || hitlCase?.pipeline || source?.pipeline || {};
  const compliance = getCompliance(source, hitlCase, pipe);
  const failedRules = getFailedRules(source, hitlCase, pipe);

  const statusValue = String(
    source?.status ||
      source?.pipeline_state ||
      source?.pipeline_status ||
      pipe?.pipeline_state ||
      pipe?.pipeline_status ||
      ""
  ).toUpperCase();

  const isHitl =
    source?.review_required ||
    source?.approval_required ||
    source?.pipeline_paused ||
    source?.waiting_for_human ||
    pipe?.review_required ||
    pipe?.approval_required ||
    pipe?.pipeline_paused ||
    pipe?.waiting_for_human ||
    ["HITL_REQUIRED", "HUMAN_REVIEW_REQUIRED", "WAITING_FOR_REVIEW", "PAUSED"].includes(statusValue);

  if (!isHitl) return null;

  const firstFailedRule = failedRules[0] || {};
  const failedRule =
    source?.failed_rule ||
    compliance?.failed_rule ||
    compliance?.rule ||
    firstFailedRule?.rule ||
    firstFailedRule?.label;

  const reason =
    source?.failure_reason ||
    source?.reason ||
    compliance?.reason ||
    compliance?.issues?.[0] ||
    firstFailedRule?.reason ||
    firstFailedRule?.message ||
    "Human review required";

  return {
    case_id: source?.case_id || pipe?.case_id,
    status: source?.review_status || source?.status || pipe?.pipeline_status,
    assigned_to: source?.assigned_to,
    priority: compliance?.severity || source?.severity || firstFailedRule?.severity,
    escalation_level: source?.escalation_level,
    review_required: true,
    approval_required: true,
    pipeline_paused: true,
    waiting_for_human: true,
    case_reasons: [failedRule ? `${failedRule}: ${reason}` : reason],
    history: source?.stage_history || [],
    failed_rules: failedRules,
  };
};

const getCaseStatus = (caseData: any, claim: any, pipeline: any): string => {
  return normalizeText(
      caseData?.status ||
      claim?.review_status ||
      claim?.status ||
      claim?.pipeline_status ||
      pipeline?.pipeline_status
  );
};

const getCaseId = (caseData: any, claim: any, pipeline: any): string => {
  return normalizeText(
      caseData?.case_id ||
      caseData?.id ||
      claim?.case_id ||
      pipeline?.case_id
  );
};

const getPriority = (caseData: any, claim: any, hitlCase: any, pipeline: any): string => {
  const compliance = getCompliance(claim, hitlCase, pipeline);
  const failedRules = getFailedRules(claim, hitlCase, pipeline);
  const firstFailedRule = failedRules[0] || {};

  return normalizeText(
    caseData?.priority ||
      caseData?.severity ||
      compliance?.severity ||
      claim?.severity ||
      firstFailedRule?.severity
  );
};

const HitlCasePanel = ({
  claimId,
  hitlCase,
  claim,
  pipeline,
  actionMessage,
  onRouteCase,
  onApproveHitlCase,
  onEscalateHitlCase,
}: HitlCasePanelProps) => {
  const resolvedCase =
    getNestedCase(hitlCase) ||
    getNestedCase(claim) ||
    getNestedCase(pipeline) ||
    buildFallbackCase(claim, pipeline, hitlCase);

  const caseData = resolvedCase || {};

  const hasCase = Boolean(
    caseData?.case_id ||
      caseData?.id ||
      caseData?.status ||
      caseData?.case_reasons?.length ||
      caseData?.issues?.length ||
      caseData?.failed_rules?.length
  );

  const reviewRequired = Boolean(
    caseData?.review_required ||
      caseData?.approval_required ||
      caseData?.pipeline_paused ||
      claim?.review_required ||
      claim?.approval_required ||
      claim?.pipeline_paused ||
      pipeline?.review_required ||
      pipeline?.approval_required ||
      pipeline?.pipeline_paused
  );

  const reasons = getCaseReasons(caseData, claim, hitlCase, pipeline);
  const failedRules = getFailedRules(claim, hitlCase, pipeline);

  if (!hasCase && !reviewRequired) {
    return (
      <div className="hitl-case-panel">
        <div className="hitl-case-header">
          <div>
            <h3>HITL Case</h3>
            <p>Human review and escalation status</p>
          </div>
        </div>

        <div className="hitl-empty">
          No HITL case created for this claim.
        </div>
      </div>
    );
  }

  return (
    <div className="hitl-case-panel">
      <div className="hitl-case-header">
        <div>
          <h3>HITL Case</h3>
          <p>Human review and escalation status</p>
        </div>

        <button
          type="button"
          className="hitl-link-button"
          onClick={() => onRouteCase(claimId, "MA")}
        >
          Open Full Case
        </button>
      </div>

      {actionMessage ? (
        <div className="hitl-action-message">
          {actionMessage}
        </div>
      ) : null}

      <div className="hitl-case-grid">
        <div className="hitl-case-item">
          <span>Case ID</span>
          <strong>{getCaseId(caseData, claim, pipeline)}</strong>
        </div>

        <div className="hitl-case-item">
          <span>Status</span>
          <strong>{getCaseStatus(caseData, claim, pipeline)}</strong>
        </div>

        <div className="hitl-case-item">
          <span>Priority</span>
          <strong>{getPriority(caseData, claim, hitlCase, pipeline)}</strong>
        </div>

        <div className="hitl-case-item">
          <span>Assigned To</span>
          <strong>
            {normalizeText(
              caseData?.assigned_to ||
                caseData?.owner ||
                claim?.assigned_to
            )}
          </strong>
        </div>

        <div className="hitl-case-item">
          <span>Review Required</span>
          <strong>{reviewRequired ? "Yes" : "No"}</strong>
        </div>

        <div className="hitl-case-item">
          <span>Pipeline Paused</span>
          <strong>
            {caseData?.pipeline_paused ||
            claim?.pipeline_paused ||
            pipeline?.pipeline_paused
              ? "Yes"
              : "No"}
          </strong>
        </div>
      </div>

      <div className="hitl-section">
        <h4>Review Reasons</h4>

        {reasons.length ? (
          <ul>
            {reasons.map((reason, index) => (
              <li key={`${reason}-${index}`}>{reason}</li>
            ))}
          </ul>
        ) : (
          <p>No review reason reported.</p>
        )}
      </div>

      {failedRules.length ? (
        <div className="hitl-section">
          <h4>Failed Rules</h4>

          <ul>
            {failedRules.map((rule, index) => (
              <li key={`${rule?.rule || rule?.label || "rule"}-${index}`}>
                <strong>{normalizeText(rule?.rule || rule?.label || "Rule")}</strong>
                {": "}
                {normalizeText(rule?.reason || rule?.message || rule?.status || "Failed")}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {caseData?.history?.length ? (
        <div className="hitl-section">
          <h4>Case History</h4>

          <ul>
            {caseData.history.slice(0, 5).map((entry: any, index: number) => (
              <li key={index}>
                {normalizeText(entry?.stage || entry?.status || entry?.event)}
                {entry?.started_at ? ` - ${entry.started_at}` : ""}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="hitl-actions">
        <button
          type="button"
          onClick={() => onRouteCase(claimId, "MA")}
        >
          Route to MA
        </button>

        <button
          type="button"
          onClick={() => onRouteCase(claimId, "LEGAL")}
        >
          Send to Legal
        </button>

        <button
          type="button"
          onClick={() => onApproveHitlCase(claimId)}
        >
          Approve
        </button>

        <button
          type="button"
          onClick={() => onEscalateHitlCase(claimId)}
        >
          Escalate
        </button>
      </div>
    </div>
  );
};

export default HitlCasePanel;
