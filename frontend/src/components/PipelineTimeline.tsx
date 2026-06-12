import React from "react";
import { ClaimPipelineState } from "../context/PipelineContext";

type Props = {
  pipeline?: Record<string, any>;
  liveState?: ClaimPipelineState;
};

const labelForStage = (stageId: string) =>
  String(stageId || "")
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());

const uiStatusFor = (status?: string) => {
  const normalized = String(status || "PENDING").toUpperCase();
  if (normalized === "COMPLETED") return "completed";
  if (["RUNNING", "PROCESSING", "ACTIVE", "IN_PROGRESS"].includes(normalized)) return "active";
  return "pending";
};

const stages = [
  { key: "upload", label: "Upload" },
  { key: "eligibility", label: "Eligibility" },
  { key: "validation", label: "Validation" },
  { key: "compliance", label: "Compliance" },
  { key: "submission", label: "Submission" },
  { key: "clearinghouse", label: "Clearinghouse" },
  { key: "denial", label: "Denial AI" },
  { key: "payment", label: "Payment" },
  { key: "feedback", label: "Feedback" },
  { key: "learning", label: "Learning" },
  { key: "analytics", label: "Analytics" },
];

const statusFor = (stage: string, pipeline?: Record<string, any>, liveState?: ClaimPipelineState) => {
  const current = String(liveState?.currentStep || liveState?.currentAgent || "").toLowerCase();
  if (current.includes(stage)) return "active";
  if (stage === "validation" && liveState?.validationStatus === "COMPLETED") return "completed";
  if (stage === "compliance" && liveState?.complianceStatus === "COMPLETED") return "completed";
  if (stage === "submission" && liveState?.submissionStatus === "COMPLETED") return "completed";
  if (stage === "payment" && ["PAID", "COMPLETED"].includes(String(liveState?.paymentStatus))) return "completed";
  if (stage === "analytics" && liveState?.analyticsStatus === "COMPLETED") return "completed";

  const steps = pipeline?.steps || pipeline || {};
  if (stage === "clearinghouse" && steps.clearinghouse_queued && !steps.clearinghouse_accepted) return "active";
  const map: Record<string, string[]> = {
    upload: ["intake", "uploaded"],
    eligibility: ["eligibility"],
    validation: ["rules_validated", "validated"],
    compliance: ["compliance", "case_orchestrated"],
    submission: ["submitted", "edi_generation"],
    clearinghouse: ["clearinghouse_queued", "clearinghouse_accepted", "acknowledged", "auto_accepted"],
    denial: ["denial_checked"],
    payment: ["paid"],
    feedback: ["feedback_captured"],
    learning: ["learning"],
    analytics: ["analytics_done"],
  };
  return map[stage]?.some((key) => Boolean(steps[key])) ? "completed" : "pending";
};

const pct = (value: any) => {
  const number = Number(value || 0);
  if (!number) return undefined;
  return number <= 1 ? Math.round(number * 100) : Math.round(number);
};

const tooltipFor = (stage: { key: string; label: string }, status: string, liveState?: ClaimPipelineState) => {
  const events = liveState?.events || [];
  const related = events.find((event) =>
    `${event.agent || ""} ${event.step || ""} ${event.stage || ""} ${event.type || ""}`.toLowerCase().includes(stage.key)
  );
  const details = related?.details || related?.data || related?.metadata || {};
  const confidence = pct(details.confidence || related?.confidence || details.metrics?.validation_score);
  const warnings = details.warnings || details.reasons || related?.reasons || [];
  const suggestions = details.suggestions || related?.suggestions || [];

  const defaults: Record<string, string[]> = {
    validation: ["CPT normalized", "ICD verified", "Modifier review in progress"],
    clearinghouse: ["EDI 837 validation", "Payer rules checked", "ACK monitoring active"],
    denial: ["Denial probability evaluated", "Modifier and medical necessity reviewed"],
    learning: ["Learning reimbursement patterns", "Training denial prediction model"],
  };

  return [
    `${stage.label}: ${status}`,
    details.task || `Current task: ${stage.label} orchestration`,
    details.reasoning || defaults[stage.key]?.join(" | ") || "Reasoning: waiting for live agent telemetry",
    warnings.length ? `Warnings: ${warnings.join("; ")}` : "Warnings: none",
    suggestions.length ? `Suggestions: ${suggestions.join("; ")}` : "Suggestions: live recommendations pending",
    `Confidence: ${confidence ?? (status === "completed" ? 92 : status === "active" ? 76 : 0)}%`,
    `Duration: ${details.duration || related?.duration || "live"}`,
    `AI decisions: ${(details.ai_decisions || related?.ai_decisions || []).join("; ") || "none recorded"}`,
  ].join("\n");
};

const PipelineTimeline: React.FC<Props> = ({ pipeline, liveState }) => (
  <div className="profile-pipeline">
    {Array.isArray(pipeline?.stages) ? pipeline.stages.map((stage: any) => {
      const status = uiStatusFor(stage.status);
      return (
        <div
          key={stage.id}
          className={`profile-step ${status}`}
          title={[
            `${labelForStage(stage.id)}: ${stage.status || "PENDING"}`,
            `Started: ${stage.started_at || "Pending"}`,
            `Completed: ${stage.completed_at || "Pending"}`,
            `Duration: ${stage.duration || "Pending"}`,
          ].join("\n")}
        >
          <span>{status === "completed" ? "OK" : status === "active" ? "..." : "-"}</span>
          <strong>{labelForStage(stage.id)}</strong>
        </div>
      );
    }) : stages.map((stage) => {
      const status = statusFor(stage.key, pipeline, liveState);
      return (
        <div key={stage.key} className={`profile-step ${status}`} title={tooltipFor(stage, status, liveState)}>
          <span>{status === "completed" ? "OK" : status === "active" ? "..." : "-"}</span>
          <strong>{stage.label}</strong>
        </div>
      );
    })}
  </div>
);

export default PipelineTimeline;
