import React from "react";

const stages = [
  "Submission",
  "Clearinghouse",
  "Accepted",
  "Denial",
  "Payment",
  "Feedback",
  "Learning",
  "Analytics",
];

const tooltip: Record<string, string> = {
  Submission: "Current task: generate EDI 837\nReasoning: normalize claim payload and submit to payer gateway\nConfidence: live",
  Clearinghouse: "Current task: validation and ACK review\nWarnings: denial risk, validation score, OCR confidence, compliance issues\nSuggestions: Auto Review or manual action",
  Accepted: "AI decision: auto/manual acceptance recorded\nNext: Denial AI",
  Denial: "Denial probability evaluated\nSuggested modifiers and medical necessity checks available",
  Payment: "Posting payment and reconciliation",
  Feedback: "Capturing reviewer and payment outcomes",
  Learning: "Learning reimbursement patterns\nTraining denial prediction model",
  Analytics: "Updating operational dashboards and latency metrics",
};

export default function ClaimPipeline({ stageIndex = 0 }: any) {
  return (
    <div className="ch-pipeline">
      {stages.map((stage, index) => (
        <div key={stage} className="ch-pipeline-node" title={tooltip[stage]}>
          <div className={index <= stageIndex ? "active" : ""} />
          <span>{stage}</span>
        </div>
      ))}
    </div>
  );
}
