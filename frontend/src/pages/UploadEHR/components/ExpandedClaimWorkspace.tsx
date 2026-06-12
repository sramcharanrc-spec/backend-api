import React from "react";
import { Trash2 } from "lucide-react";

import type { ProcessingMode } from "../utils/claimTypes";
import AIInsightsPanel from "./AIInsightsPanel";
import CurrentAgentPanel from "./CurrentAgentPanel";
import PatientProviderPanel from "./PatientProviderPanel";
import PipelineStepper from "./PipelineStepper";
import HitlCasePanel from "./HitlCasePanel";

type ExpandedClaimWorkspaceProps = {
  item: any;
  pipelineData?: any;
  events?: any[];
  processingMode: ProcessingMode;
  claimModeOverrides: Record<string, ProcessingMode>;
  onOpenProfile: (claimId: string) => void;
  onDeleteRequest: (item: any) => void;
  onModeChange: (claimId: string, mode: ProcessingMode) => void;
  onApprove: (claimId: string, item?: any) => void;
  onAcceptClearinghouse?: (claimId: string) => void;
  onReject: (claimId: string) => void;
  onEscalate: (claimId: string) => void;
  onRouteCase: (claimId: string, assignedRole: string) => void;
};

const safeText = (value: any, fallback = "Not reported") => {
  if (value === undefined || value === null || value === "") return fallback;
  if (typeof value === "object") {
    const text =
      value.summary ||
      value.status ||
      value.message ||
      value.label ||
      value.name;

    if (text !== undefined && text !== null && text !== "") return String(text);

    try {
      return JSON.stringify(value);
    } catch {
      return fallback;
    }
  }

  return String(value);
};

const formatDisplayDate = (value: any) => {
  if (!value) return "Not reported";

  const raw = String(value).trim();

  if (/^\d{4}-\d{2}-\d{2}/.test(raw)) {
    const date = new Date(raw);

    if (!Number.isNaN(date.getTime())) {
      return date.toLocaleString();
    }
  }

  return raw;
};

const formatDisplayStatus = (value: any) => {
  if (!value) return "Not reported";

  return String(value)
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (char) => char.toUpperCase());
};

const shortText = (value: any, maxLength = 28) => {
  const text = safeText(value);

  if (text.length <= maxLength) return text;

  return `${text.slice(0, maxLength - 3)}...`;
};

const getBackendClaimPayload = (item: any) =>
  item?.claim || item?.payload?.claim || item?.payload || item || {};

const getBackendPipelinePayload = (item: any) =>
  item?.pipeline ||
  item?.payload?.pipeline ||
  item?.claim?.pipeline ||
  item?.payload?.claim?.pipeline ||
  {};

const getBackendHitlCase = (item: any, pipelineData?: any) => {
  const claim = getBackendClaimPayload(item);
  const pipeline = pipelineData || getBackendPipelinePayload(item);

  return (
    item?.hitl_case ||
    item?.hitlCase ||
    item?.case ||
    item?.payload?.hitl_case ||
    item?.payload?.case ||
    item?.claim?.hitl_case ||
    item?.claim?.case ||
    claim?.hitl_case ||
    claim?.case ||
    pipeline?.hitl_case ||
    pipeline?.case ||
    null
  );
};

const getClaimId = (item: any) => {
  const claim = getBackendClaimPayload(item);

  return (
    item?.claim_id ||
    claim?.claim_id ||
    item?.payload?.claim_id ||
    "Not reported"
  );
};

const getSummaryPipelinePayload = (item: any, pipelineData?: any) => {
  const itemPipeline = getBackendPipelinePayload(item);
  const claimPipeline = item?.claim?.pipeline || item?.payload?.claim?.pipeline || {};
  const livePipeline = pipelineData || {};

  return {
    ...itemPipeline,
    ...claimPipeline,
    ...livePipeline,

    steps: {
      ...(itemPipeline?.steps || {}),
      ...(claimPipeline?.steps || {}),
      ...(livePipeline?.steps || {}),
    },

    stage_status: {
      ...(itemPipeline?.stage_status || {}),
      ...(claimPipeline?.stage_status || {}),
      ...(livePipeline?.stage_status || {}),
    },

    agents: {
      ...(itemPipeline?.agents || {}),
      ...(claimPipeline?.agents || {}),
      ...(livePipeline?.agents || {}),
    },
  };
};

const getExpandedSummaryCards = (item: any, pipelineData?: any) => {
  const claim = getBackendClaimPayload(item);
  const pipeline = getSummaryPipelinePayload(item, pipelineData);


  const completedAt =
    item?.completed_at ||
    item?.finalized_at ||
    claim?.completed_at ||
    claim?.finalized_at ||
    pipeline?.completed_at ||
    pipeline?.finalized_at ||
    item?.updated_at ||
    item?.created_at;

  const duration =
    item?.processing_duration ||
    claim?.processing_duration ||
    pipeline?.processing_duration ||
    pipeline?.duration_seconds ||
    item?.duration_seconds ||
    claim?.duration_seconds;

  const payment =
    item?.payment_status ||
    claim?.payment_status ||
    pipeline?.payment_status ||
    item?.payment?.status ||
    claim?.payment?.status ||
    item?.payload?.payment?.status;

  const denial =
    item?.denial_status ||
    claim?.denial_status ||
    pipeline?.denial_status ||
    item?.payload?.denial_ai?.status ||
    item?.denial_ai?.status;

  const analytics =
    item?.analytics_summary ||
    claim?.analytics_summary ||
    pipeline?.analytics_summary ||
    item?.analytics?.summary ||
    claim?.analytics?.summary ||
    item?.payload?.analytics?.summary;

  const pipelineResult =
    item?.pipeline_result ||
    claim?.pipeline_result ||
    pipeline?.pipeline_result ||
    item?.final_pipeline_result ||
    claim?.final_pipeline_result ||
    pipeline?.pipeline_state ||
    pipeline?.overall_status ||
    pipeline?.status ||
    item?.status ||
    claim?.status;

  return [
    ["Completed At", completedAt ? formatDisplayDate(completedAt) : "Not reported"],
    ["Duration", duration ? `${duration}s` : "Not reported"],
    ["Payment", payment ? formatDisplayStatus(payment) : "Not reported"],
    ["Denial", denial ? formatDisplayStatus(denial) : "Not reported"],
    ["Analytics", safeText(analytics)],
    ["Pipeline Result", pipelineResult ? formatDisplayStatus(pipelineResult) : "Not reported"],
  ];
};

const buildDisplayItem = (item: any, pipelineData?: any) => {
  const claim = getBackendClaimPayload(item);
  const pipeline = getSummaryPipelinePayload(item, pipelineData);

  return {
    ...item,

    pipeline,

    status:
      item?.status ||
      claim?.status ||
      item?.payload?.claim?.status ||
      pipeline?.pipeline_status ||
      pipeline?.overall_status ||
      pipeline?.status ||
      pipeline?.pipeline_state,

    current_stage:
      item?.current_stage ||
      item?.stage ||
      item?.active_step ||
      claim?.current_stage ||
      claim?.stage ||
      claim?.active_step ||
      pipeline?.current_stage ||
      pipeline?.stage ||
      pipeline?.active_step,

    current_agent:
      item?.current_agent ||
      item?.agent ||
      claim?.current_agent ||
      claim?.agent ||
      pipeline?.current_agent ||
      pipeline?.agent,

    active_step:
      item?.active_step ||
      claim?.active_step ||
      pipeline?.active_step ||
      pipeline?.workflow_state,

    progress:
      item?.progress ??
      claim?.progress ??
      pipeline?.progress,

    pipeline_state:
      item?.pipeline_state ||
      claim?.pipeline_state ||
      pipeline?.pipeline_state,

    pipeline_status:
      item?.pipeline_status ||
      claim?.pipeline_status ||
      pipeline?.pipeline_status,

    review_required:
      item?.review_required ??
      claim?.review_required ??
      pipeline?.review_required ??
      false,

    approval_required:
      item?.approval_required ??
      claim?.approval_required ??
      pipeline?.approval_required ??
      false,

    pipeline_paused:
      item?.pipeline_paused ??
      claim?.pipeline_paused ??
      pipeline?.pipeline_paused ??
      false,

    waiting_for_human:
      item?.waiting_for_human ??
      claim?.waiting_for_human ??
      pipeline?.waiting_for_human ??
      false,

    case: item?.case || claim?.case || pipeline?.case,
    hitl_case:
      item?.hitl_case ||
      claim?.hitl_case ||
      pipeline?.hitl_case ||
      pipeline?.case,
    case_id: item?.case_id || claim?.case_id || pipeline?.case_id,

    claim: {
      ...(claim || {}),
      pipeline,
    },
  };
};

const getFormLabel = (item: any) => {
  const claim = getBackendClaimPayload(item);

  const form =
    claim?.form_type ||
    item?.form_type ||
    claim?.document_type ||
    item?.document_type ||
    claim?.form ||
    item?.form;

  return form || "Not reported";
};

const getUploadedBy = (item: any) => {
  const claim = getBackendClaimPayload(item);

  return (
    item?.uploaded_by ||
    item?.created_by ||
    claim?.uploaded_by ||
    claim?.created_by ||
    "Not reported"
  );
};

const getUploadSource = (item: any) => {
  const claim = getBackendClaimPayload(item);

  return (
    item?.upload_source ||
    item?.source ||
    claim?.upload_source ||
    claim?.source ||
    "Not reported"
  );
};

const getUploadedAt = (item: any) => {
  const claim = getBackendClaimPayload(item);

  return item?.uploaded_at || item?.created_at || claim?.uploaded_at || claim?.created_at;
};

const ExpandedClaimWorkspace: React.FC<ExpandedClaimWorkspaceProps> = ({
  item,
  pipelineData,
  processingMode,
  claimModeOverrides,
  onOpenProfile,
  onDeleteRequest,
  onModeChange,
  onApprove,
  onAcceptClearinghouse,
  onReject,
  onEscalate,
  onRouteCase,
  events = [],
}) => {
  
  const displayItem = buildDisplayItem(item, pipelineData);
  const pipeline = displayItem.pipeline || getSummaryPipelinePayload(displayItem, pipelineData);
  const claimId = getClaimId(displayItem);
  const summaryCards = getExpandedSummaryCards(displayItem, pipeline);
  const hitlCase = getBackendHitlCase(displayItem, pipeline);

  return (
    <div className="cw-expanded-screenshot-shell">
      <section className="cw-expanded-top-card">
        <div className="cw-expanded-top-grid">
          <span>
            Claim ID: <strong>{claimId}</strong>
          </span>

          <span>
            Source: <strong>{getUploadSource(displayItem)}</strong>
          </span>

          <span>
            Uploaded: <strong>{formatDisplayDate(getUploadedAt(displayItem))}</strong>
          </span>

          <span>
            By: <strong>{getUploadedBy(displayItem)}</strong>
          </span>

          <span>
            Forms: <strong>{getFormLabel(displayItem)}</strong>
          </span>

          <button
            type="button"
            className="cw-profile-link"
            onClick={() => onOpenProfile(claimId)}
          >
            Claim Profile
          </button>
        </div>

        <button
          type="button"
          className="cw-delete-inline"
          onClick={() => onDeleteRequest(displayItem)}
        >
          <Trash2 size={14} /> Delete
        </button>
      </section>

      <section className="cw-expanded-summary-cards">
        {summaryCards.map(([label, value]) => (
          <div className="cw-expanded-summary-card" key={label} title={String(value)}>
            <span>{label}</span>
            <strong>{shortText(value, 30)}</strong>
          </div>
        ))}
      </section>

      <PipelineStepper
        item={displayItem}
        pipelineData={pipeline}
        events={events}
      />

      <section className="cw-expanded-main-grid">
        <PatientProviderPanel item={displayItem} />

        <CurrentAgentPanel
          item={displayItem}
          processingMode={processingMode}
          claimModeOverrides={claimModeOverrides}
          onModeChange={onModeChange}
          onApprove={onApprove}
          onAcceptClearinghouse={onAcceptClearinghouse}
          onReject={onReject}
          onEscalate={onEscalate}
          onRouteCase={onRouteCase}
        />

        <AIInsightsPanel item={displayItem} />
      </section>

      <section className="cw-expanded-bottom-grid">
        <HitlCasePanel
          claimId={claimId}
          hitlCase={hitlCase}
          claim={displayItem}
          pipeline={pipeline}
          onRouteCase={onRouteCase}
          onApproveHitlCase={(id) => onApprove(id, displayItem)}
          onEscalateHitlCase={onEscalate}
        />

        <div className="cw-panel">
          <div className="cw-panel-title">
            <div>
              <h3>Routing Flow</h3>
              <p>Current operational ownership</p>
            </div>

            <span className="cw-live-pill">Realtime</span>
          </div>

          <div className="cw-routing-flow">
            <span>1</span>
            <strong>
              {safeText(
                hitlCase?.assigned_role ||
                  hitlCase?.assigned_team ||
                  hitlCase?.assigned_to ||
                  displayItem?.assigned_to
              )}
            </strong>
            <em>Active</em>
          </div>
        </div>
      </section>
    </div>
  );
};

export default ExpandedClaimWorkspace;
