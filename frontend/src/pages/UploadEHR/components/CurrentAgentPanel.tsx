import type { ProcessingMode } from "../utils/claimTypes";
import {
  getBackendProcessingMode,
  getClaimId,
  getWorkspaceStatus,
} from "../utils";

type CurrentAgentPanelProps = {
  item: any;
  processingMode: ProcessingMode;
  claimModeOverrides: Record<string, ProcessingMode>;
  onModeChange: (claimId: string, mode: ProcessingMode) => void;
  onApprove: (claimId: string, item: any) => void;
  onAcceptClearinghouse?: (claimId: string) => void;
  onReject: (claimId: string) => void;
  onEscalate: (claimId: string) => void;
  onRouteCase: (claimId: string, assignedRole: string) => void;
};

const claimPayloadOf = (item: any) =>
  item?.claim || item?.payload?.claim || item?.payload || item || {};

const pipelinePayloadOf = (item: any) =>
  item?.pipeline || item?.payload?.pipeline || item?.claim?.pipeline || item?.payload?.claim?.pipeline || {};

const normalizeStatus = (value: any) =>
  String(value || "")
    .trim()
    .toUpperCase()
    .replace(/[\s-]+/g, "_");

const isAcknowledgmentStage = (value: any) =>
  [
    "ACK",
    "ACKNOWLEDGMENT",
    "ACKNOWLEDGEMENT",
    "PAYER",
    "PAYER_ACK",
    "PAYER_ACKNOWLEDGMENT",
    "PAYER_ACKNOWLEDGEMENT",
    "PAYER_ACKNOWLEDGED",
  ].includes(normalizeStatus(value));

const formatDisplayStatus = (value: any, fallback = "Not reported") => {
  const normalized = normalizeStatus(value);
  if (!normalized) return fallback;

  return normalized
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (char) => char.toUpperCase());
};

const formatDisplayDate = (value: any) => {
  if (!value) return "Not reported";

  const date = new Date(value);
  if (!Number.isNaN(date.getTime())) return date.toLocaleString();

  return String(value);
};

const formatDuration = (item: any, pipeline: any) => {
  const raw =
    item?.processing_duration ||
    item?.duration ||
    item?.duration_seconds ||
    item?.claim?.processing_duration ||
    pipeline?.processing_duration ||
    pipeline?.duration ||
    pipeline?.duration_seconds;

  if (raw !== undefined && raw !== null && raw !== "") {
    const numeric = Number(raw);
    if (Number.isFinite(numeric)) return `${Math.round(numeric)}s`;
    return String(raw);
  }

  const startedAt = item?.started_at || item?.created_at || pipeline?.started_at;
  const completedAt = item?.completed_at || item?.updated_at || pipeline?.completed_at || pipeline?.updated_at;

  if (!startedAt || !completedAt) return "Not reported";

  const startMs = new Date(startedAt).getTime();
  const endMs = new Date(completedAt).getTime();

  if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs < startMs) return "Not reported";

  return `${Math.round((endMs - startMs) / 1000)}s`;
};

const formatConfidence = (item: any, pipeline: any) => {
  const raw =
    item?.confidence ??
    item?.confidence_score ??
    item?.ocr_confidence ??
    item?.payload?.confidence ??
    item?.claim?.confidence ??
    pipeline?.confidence;

  if (raw === undefined || raw === null || raw === "") return "Not reported";

  const numeric = Number(raw);
  if (!Number.isFinite(numeric)) return String(raw);

  const percent = numeric > 0 && numeric <= 1 ? numeric * 100 : numeric;
  return `${Math.round(percent)}%`;
};

const CurrentAgentPanel = ({
  item,
  processingMode,
  claimModeOverrides,
  onModeChange,
  onApprove,
  onAcceptClearinghouse,
  onReject,
  onEscalate,
  onRouteCase,
}: CurrentAgentPanelProps) => {
  const claim = claimPayloadOf(item);
  const pipeline = pipelinePayloadOf(item);
  const claimId = getClaimId(item);
  const mode = getBackendProcessingMode(item, claimModeOverrides, processingMode);

  const status = normalizeStatus(
    getWorkspaceStatus(item) ||
      item?.status ||
      claim?.status ||
      pipeline?.overall_status ||
      pipeline?.status ||
      pipeline?.pipeline_state ||
      "PENDING"
  );

  const currentStage =
    item?.current_stage ||
    item?.stage ||
    item?.workflow_stage ||
    item?.payload?.current_stage ||
    item?.payload?.stage ||
    claim?.current_stage ||
    claim?.stage ||
    pipeline?.current_stage ||
    pipeline?.active_step ||
    pipeline?.current_step ||
    status ||
    "Pipeline";

  const stage = normalizeStatus(currentStage);

  const currentAgent =
    item?.current_agent ||
    item?.current_agent_name ||
    item?.agent ||
    item?.agent_name ||
    item?.assigned_agent ||
    item?.active_agent ||
    item?.latest_agent ||
    item?.review_agent ||
    item?.payload?.current_agent ||
    item?.payload?.current_agent_name ||
    item?.payload?.agent ||
    item?.payload?.agent_name ||
    claim?.current_agent ||
    claim?.current_agent_name ||
    claim?.agent ||
    claim?.agent_name ||
    claim?.assigned_agent ||
    pipeline?.current_agent ||
    pipeline?.current_agent_name ||
    pipeline?.agent ||
    pipeline?.agent_name ||
    pipeline?.active_agent ||
    pipeline?.latest_agent ||
    currentStage ||
    "Pipeline";

  const startedAt =
    item?.started_at ||
    item?.created_at ||
    claim?.started_at ||
    claim?.created_at ||
    pipeline?.started_at;

  const workflowStatus =
    item?.workflow_state ||
    item?.active_step ||
    pipeline?.workflow_state ||
    pipeline?.current_step ||
    pipeline?.overall_status ||
    status;

  const isClearinghouseApproval =
    !isAcknowledgmentStage(stage) &&
    !isAcknowledgmentStage(currentStage) &&
    (status === "WAITING_FOR_APPROVAL" ||
      status === "PENDING_CLEARINGHOUSE" ||
      status === "PENDING_APPROVAL" ||
      stage === "CLEARINGHOUSE");

  const isHitlReview =
    status === "HUMAN_REVIEW_REQUIRED" ||
    status === "HITL_REQUIRED" ||
    status === "MANUAL_REVIEW_REQUIRED" ||
    stage === "HUMAN_REVIEW";

  return (
    <div className="cw-panel cw-current-agent-panel">
      <div className="cw-panel-title cw-agent-panel-title">
        <div>
          <h3>
            Current Agent: <b>{formatDisplayStatus(currentAgent, "Pipeline")}</b>
          </h3>
        </div>
        <span className="cw-live-pill">Live</span>
      </div>

      <div className="cw-agent-mode-box">
        <div className="cw-agent-mode-copy">
          <span>Processing Mode</span>
          <strong>{mode}</strong>
          <small>{mode === "AUTO" ? "AI auto-review enabled" : "Human review required"}</small>
        </div>

        <div className="cw-agent-mode-control">
          <select value={mode} onChange={(event) => onModeChange(claimId, event.target.value as ProcessingMode)}>
            <option value="MANUAL">Manual Review</option>
            <option value="AUTO">Auto Process</option>
          </select>

          <em>{formatDisplayStatus(workflowStatus, "Pipeline")}</em>
        </div>
      </div>

      <div className="cw-agent-stats">
        <div className="cw-agent-stat-card">
          <span className="cw-agent-stat-label">Status</span>
          <strong className="cw-agent-stat-value">{formatDisplayStatus(status)}</strong>
        </div>

        <div className="cw-agent-stat-card">
          <span className="cw-agent-stat-label">Stage</span>
          <strong className="cw-agent-stat-value">{formatDisplayStatus(currentStage, "Pipeline")}</strong>
        </div>

        <div className="cw-agent-stat-card">
          <span className="cw-agent-stat-label">Current Agent</span>
          <strong className="cw-agent-stat-value">{formatDisplayStatus(currentAgent, "Pipeline")}</strong>
        </div>

        <div className="cw-agent-stat-card">
          <span className="cw-agent-stat-label">Started At</span>
          <strong className="cw-agent-stat-value">{formatDisplayDate(startedAt)}</strong>
        </div>

        <div className="cw-agent-stat-card">
          <span className="cw-agent-stat-label">Duration</span>
          <strong className="cw-agent-stat-value">{formatDuration(item, pipeline)}</strong>
        </div>

        <div className="cw-agent-stat-card">
          <span className="cw-agent-stat-label">Confidence</span>
          <strong className="cw-agent-stat-value">{formatConfidence(item, pipeline)}</strong>
        </div>
      </div>

      <div className="cw-workflow-status-box">
        <strong>Current workflow status</strong>
        <span>{formatDisplayStatus(workflowStatus, "Pipeline")}</span>
        <small>
          <i /> {formatDisplayStatus(status)} in {formatDisplayStatus(currentStage, "Pipeline")}
        </small>
      </div>

      <div className="cw-action-grid">
        {isClearinghouseApproval ? (
          <button
            type="button"
            className="cw-btn primary"
            onClick={() => onAcceptClearinghouse?.(claimId)}
            disabled={!onAcceptClearinghouse}
          >
            Accept Clearinghouse
          </button>
        ) : isHitlReview ? (
          <button type="button" className="cw-btn primary" onClick={() => onApprove(claimId, item)}>
            Approve HITL
          </button>
        ) : null}

        <button type="button" className="cw-btn danger" onClick={() => onReject(claimId)}>
          Reject Claim
        </button>

        <button type="button" className="cw-btn secondary" onClick={() => onEscalate(claimId)}>
          Escalate
        </button>

        <button type="button" className="cw-btn secondary" onClick={() => onRouteCase(claimId, "MA Team")}>
          Send to MA
        </button>

        <button type="button" className="cw-btn secondary" onClick={() => onRouteCase(claimId, "HEOR Team")}>
          Send to HEOR
        </button>

        <button type="button" className="cw-btn secondary" onClick={() => onRouteCase(claimId, "Legal Team")}>
          Send to Legal
        </button>
      </div>
    </div>
  );
};

export default CurrentAgentPanel;
