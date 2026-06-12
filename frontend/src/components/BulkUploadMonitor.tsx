import React from "react";
import { ClaimPipelineState } from "../context/PipelineContext";
import ClaimStatusBadge from "./ClaimStatusBadge";

type Props = {
  claims: Record<string, ClaimPipelineState>;
  progress: {
    queued: number;
    processing: number;
    completed: number;
    failed: number;
  };
  onCMS1500?: (claim: ClaimPipelineState) => void;
  onUB04?: (claim: ClaimPipelineState) => void;
};

const getSupportedForms = (claimType?: string) => {
  const type = String(claimType || "").trim().toUpperCase().replace(/[-_\s]/g, "");
  if (type === "BOTH" || type === "CMS1500UB04" || type === "UB04CMS1500") return ["CMS1500", "UB04"];
  if (type === "CMS1500" || type === "CMS") return ["CMS1500"];
  if (type === "UB04" || type === "UB") return ["UB04"];
  return [];
};

const BulkUploadMonitor: React.FC<Props> = ({ claims, progress, onCMS1500, onUB04 }) => {
  const rows = Object.values(claims).slice(0, 25);

  return (
    <section className="card-box">
      <div className="table-toolbar">
        <div>
          <h3 className="text-base font-semibold text-slate-900">Bulk Upload Monitor</h3>
          <p className="text-sm text-slate-500">Realtime processing state from pipeline websocket events.</p>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          <span>Queued: {progress.queued}</span>
          <span>Processing: {progress.processing}</span>
          <span>Completed: {progress.completed}</span>
          <span>Failed: {progress.failed}</span>
        </div>
      </div>

      <div className="table-container">
        <table className="claims-table">
          <thead>
            <tr>
              <th>Claim ID</th>
              <th>Agent</th>
              <th>Status</th>
              <th>Compliance</th>
              <th>Submission</th>
              <th className="forms-col">Forms</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((claim) => {
              const forms = getSupportedForms(claim.claimType);

              return (
                <tr key={claim.claimId}>
                  <td><span className="claim-id">{claim.claimId}</span></td>
                  <td>{claim.currentAgent || claim.currentStep || "Queued"}</td>
                  <td><ClaimStatusBadge status={claim.status} /></td>
                  <td><ClaimStatusBadge status={claim.complianceStatus} /></td>
                  <td><ClaimStatusBadge status={claim.submissionStatus} /></td>
                  <td className="forms-cell">
                    {forms.includes("CMS1500") && (
                      <button className="form-btn cms1500" onClick={() => onCMS1500?.(claim)}>
                        CMS1500
                      </button>
                    )}
                    {forms.includes("UB04") && (
                      <button className="form-btn ub04" onClick={() => onUB04?.(claim)}>
                        UB04
                      </button>
                    )}
                    {forms.length === 0 && <span className="forms-empty">-</span>}
                  </td>
                </tr>
              );
            })}
            {rows.length === 0 && (
              <tr>
                <td colSpan={6} className="empty-state">No live bulk uploads yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
};

export default BulkUploadMonitor;
