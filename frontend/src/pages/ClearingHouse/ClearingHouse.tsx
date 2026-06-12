import React, { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Bot, CheckCircle2, FileText, GitBranch, RotateCcw, Search, Sparkles, UserCheck, XCircle } from "lucide-react";
import ClaimPipeline from "./components/ClaimPipeline";
import EDIViewer from "./components/EDIViewer";
import { API_URL } from "../../config";
import {
  applyClaimCorrection,
  downloadEDI,
  getClaims,
  getDenialAnalysis,
  retrySubmission,
} from "../../services/rcmApi";
import { addPipelineEventListener } from "../../services/websocket";
import { claimIdOf, displayText, mergeClaims, normalizeClaimsResponse } from "../../utils/claimSync";
import "./ClearingHouse.css";

const tabs = ["PENDING_CLEARINGHOUSE", "MANUAL_REVIEW_REQUIRED", "AUTO_PROCESSING", "ACCEPTED", "REJECTED", "RESUBMITTED"];
const clearinghouseStatuses = new Set(["PENDING_CLEARINGHOUSE", "MANUAL_REVIEW_REQUIRED", "AUTO_PROCESSING", "ACCEPTED", "REJECTED", "RESUBMITTED"]);

const statusLabel: Record<string, string> = {
  PENDING_CLEARINGHOUSE: "Pending Review",
  MANUAL_REVIEW_REQUIRED: "Manual Review Required",
  ACCEPTED: "Accepted",
  REJECTED: "Rejected",
  RESUBMITTED: "Resubmitted",
  AUTO_PROCESSING: "Auto Processing",
};

const lifecycleIndex = (claim: any) => {
  const steps = claim?.pipeline?.steps || claim?.payload?.pipeline?.steps || {};
  if (steps.analytics_done || claim.status === "COMPLETED") return 7;
  if (steps.learning_updated) return 6;
  if (steps.feedback_captured) return 5;
  if (steps.paid || claim.status === "PAID") return 4;
  if (steps.denial_checked) return 3;
  if (steps.clearinghouse_accepted || claim.status === "ACCEPTED") return 2;
  if (steps.submitted || claim.status === "PENDING_CLEARINGHOUSE") return 1;
  return 0;
};

const risk = (claim: any) =>
  claim?.denial_ai?.risk_score ||
  claim?.payload?.denial_ai?.risk_score ||
  claim?.claim?.risk_score ||
  claim?.payload?.claim?.risk_score ||
  0;

const asPercent = (value: any) => {
  const number = Number(value || 0);
  if (!number) return 0;
  return Math.min(100, Math.max(0, number <= 1 ? number * 100 : number));
};

const getValidationScore = (claim: any) =>
  asPercent(
    claim?.validation?.validation_score ||
      claim?.payload?.validation?.validation_score ||
      claim?.payload?.validation?.score ||
      claim?.payload?.claim?.extraction?.validation_score ||
      claim?.payload?.claim?.extraction?.service_confidence ||
      88
  );

const getMode = (claim: any) =>
  String(claim.processing_mode || claim.clearinghouse?.processing_mode || claim.payload?.clearinghouse?.processing_mode || claim.payload?.claim?.processing_mode || "MANUAL").toUpperCase();

const getEdiStatus = (claim: any) => {
  const steps = claim?.pipeline?.steps || claim?.payload?.pipeline?.steps || {};
  if (steps.acknowledged) return "277CA ACK";
  if (steps.submitted || claimStatus(claim) === "PENDING_CLEARINGHOUSE") return "837 Sent";
  return "EDI Pending";
};

const responseTime = (claim: any) => {
  if (!claim.updated_at) return "Live";
  const minutes = Math.max(1, Math.round((Date.now() - new Date(claim.updated_at).getTime()) / 60000));
  return minutes > 90 ? `${Math.round(minutes / 60)}h` : `${minutes}m`;
};

const aiRecommendation = (claim: any, analysis?: any) =>
  displayText(
    analysis?.ai_suggestion ||
      claim?.payload?.denial_ai?.ai_suggestion ||
      claim?.denial_ai?.ai_suggestion ||
      (risk(claim) > 70 ? "Route to HITL before payer response" : getMode(claim) === "AUTO" ? "Eligible for auto acceptance" : "Ready for review")
  );

const claimStatus = (claim: any) => String(claim.status || claim.payload?.claim?.status || "NEW").toUpperCase();

const payerName = (claim: any) =>
  displayText(claim?.claim?.payer?.name || claim?.payload?.claim?.payer?.name || claim?.payer || claim?.payer_name, "Demo Payer");

const patientName = (claim: any) =>
  displayText(claim?.claim?.patient?.name || claim?.payload?.claim?.patient?.name || claim?.patient || claim?.patient_name, "Unknown patient");

const claimFromEvent = (event: any) => {
  const claimId = claimIdOf(event);
  if (!claimId) return null;
  const data = event?.data && typeof event.data === "object" ? event.data : {};
  const snapshot = event?.claim || data?.claim || event?.payload?.claim || event?.payload || {};
  return {
    ...snapshot,
    ...data,
    ...event,
    claim_id: claimId,
  };
};

const post = async (path: string, body?: any) => {
  const response = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
};

const ClearingHouse: React.FC = () => {
  const [claims, setClaims] = useState<any[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [selectedClaim, setSelectedClaim] = useState<any>(null);
  const [activeTab, setActiveTab] = useState("PENDING_CLEARINGHOUSE");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState<any>(null);
  const [analysis, setAnalysis] = useState<any>(null);
  const [ediData, setEdiData] = useState("");
  const [toast, setToast] = useState("");

  const loadClaims = async () => {
    const data = await getClaims();
    const apiClaims = normalizeClaimsResponse(data);
    setClaims((prev) => {
      const merged = mergeClaims(prev, apiClaims);
      setSelectedClaim((current: any) => merged.find((item: any) => claimIdOf(item) === claimIdOf(current)) || current || merged[0] || null);
      return merged;
    });
  };

  useEffect(() => {
    loadClaims().catch(console.error);
  }, []);

  useEffect(() => {
    return addPipelineEventListener((event) => {
      const eventName = event.event || event.type;
      if (
        [
          "clearinghouse_queued",
          "clearinghouse_accepted",
          "clearinghouse_auto_accepted",
          "auto_review_manual_required",
          "clearinghouse_rejected",
          "denial_detected",
          "payment_completed",
          "claim_resubmitted",
          "bulk_operation_started",
          "bulk_operation_progress",
          "bulk_operation_completed",
        ].includes(eventName)
      ) {
        setToast(`${eventName.replaceAll("_", " ")}${event.claim_id ? `: ${event.claim_id}` : ""}`);
        if (eventName.startsWith("bulk_operation")) setProgress(event);
        const claimUpdate = claimFromEvent(event);
        if (claimUpdate) {
          setClaims((prev) => mergeClaims(prev, [claimUpdate]));
        }
        loadClaims().catch(console.error);
      }
    });
  }, []);

  useEffect(() => {
    if (!claimIdOf(selectedClaim)) return;
    setAnalysis(selectedClaim.payload?.denial_ai || selectedClaim.denial_ai || null);
    const artifact = selectedClaim.artifact_paths?.edi || selectedClaim.payload?.generated_artifacts?.edi?.local_path;
    setEdiData(artifact ? `EDI artifact available: ${artifact}` : selectedClaim.claim?.submission_id ? `EDI837::${selectedClaim.claim.submission_id}` : "");
  }, [selectedClaim]);

  const filteredClaims = useMemo(() => {
    const token = search.toLowerCase().trim();
    return claims.filter((claim) => {
      const status = claimStatus(claim);
      const mode = getMode(claim);
      const inClearinghouse = clearinghouseStatuses.has(status) || claim.payload?.pipeline?.steps?.clearinghouse_queued || claim.payload?.pipeline?.steps?.clearinghouse_accepted;
      const tabMatch =
        activeTab === "AUTO_PROCESSING"
          ? mode === "AUTO" && !["ACCEPTED", "REJECTED", "RESUBMITTED"].includes(status)
          : status === activeTab || (activeTab === "PENDING_CLEARINGHOUSE" && status === "QUEUED");
      const text = `${claimIdOf(claim)} ${patientName(claim)} ${payerName(claim)}`.toLowerCase();
      return inClearinghouse && tabMatch && (!token || text.includes(token));
    });
  }, [claims, activeTab, search]);

  const counters = useMemo(() => {
    return tabs.reduce((acc: Record<string, number>, status) => {
      acc[status] = claims.filter((claim) => {
        const current = claimStatus(claim);
        if (!clearinghouseStatuses.has(current) && !claim.payload?.pipeline?.steps?.clearinghouse_queued && !claim.payload?.pipeline?.steps?.clearinghouse_accepted) return false;
        if (status === "AUTO_PROCESSING") return getMode(claim) === "AUTO" && !["ACCEPTED", "REJECTED", "RESUBMITTED"].includes(current);
        return current === status;
      }).length;
      return acc;
    }, {});
  }, [claims]);

  const queueClaims = useMemo(
    () => claims.filter((claim) => clearinghouseStatuses.has(claimStatus(claim)) || claim.payload?.pipeline?.steps?.clearinghouse_queued || claim.payload?.pipeline?.steps?.clearinghouse_accepted),
    [claims]
  );

  const analytics = useMemo(() => {
    const accepted = queueClaims.filter((claim) => claimStatus(claim) === "ACCEPTED" || claim.payload?.pipeline?.steps?.clearinghouse_accepted).length;
    const rejected = queueClaims.filter((claim) => claimStatus(claim) === "REJECTED").length;
    const auto = queueClaims.filter((claim) => getMode(claim) === "AUTO").length;
    const resub = queueClaims.filter((claim) => claimStatus(claim) === "RESUBMITTED").length;
    return {
      total: queueClaims.length,
      accepted,
      rejected,
      auto,
      resub,
      acceptanceRate: queueClaims.length ? Math.round((accepted / queueClaims.length) * 100) : 0,
      rejectionRate: queueClaims.length ? Math.round((rejected / queueClaims.length) * 100) : 0,
    };
  }, [queueClaims]);

  const runAction = async (label: string, action: () => Promise<any>) => {
    setLoading(true);
    try {
      const result = await action();
      setToast(label);
      if (result?.analysis) setAnalysis(result.analysis);
      await loadClaims();
      return result;
    } finally {
      setLoading(false);
    }
  };

  const acceptClaim = (claimId = claimIdOf(selectedClaim)) =>
    claimId && runAction("Claim accepted and pipeline resumed", () => post(`/api/rcm/approve/${claimId}?reviewer=ClearinghouseUser`));

  const rejectClaim = (claimId = claimIdOf(selectedClaim)) =>
    claimId && runAction("Claim rejected with AI remediation", () => post(`/api/rcm/reject/${claimId}?reviewer=ClearinghouseUser`));

  const resubmitClaim = (claimId = claimIdOf(selectedClaim)) =>
    claimId && runAction("Claim repaired and resubmitted", () => retrySubmission(claimId, { reviewer: "ClearinghouseUser" }));

  const autoReviewClaim = (claimId = claimIdOf(selectedClaim)) =>
    claimId && runAction("Auto clearinghouse review completed", () => post(`/api/claims/${claimId}/clearinghouse-auto-review`, { reviewer: "ClearinghouseAuto" }));

  const bulk = (operation: "bulk-accept" | "bulk-reject" | "bulk-resubmit") => {
    if (!selectedIds.length) return;
    runAction(`${operation} started`, () => post(`/api/rcm/${operation}`, { claim_ids: selectedIds, reviewer: "ClearinghouseUser" }));
    setSelectedIds([]);
  };

  const toggleSelected = (claimId: string) => {
    setSelectedIds((prev) => prev.includes(claimId) ? prev.filter((id) => id !== claimId) : [...prev, claimId]);
  };

  const selectAll = () => {
    const ids = filteredClaims.map((claim) => claimIdOf(claim));
    setSelectedIds(selectedIds.length === ids.length ? [] : ids);
  };

  const openAnalysis = async (claim: any) => {
    setSelectedClaim(claim);
    const data = await getDenialAnalysis(claimIdOf(claim));
    setAnalysis(data.analysis || {});
  };

  const applyAutoFix = async () => {
    const selectedClaimId = claimIdOf(selectedClaim);
    if (!selectedClaimId) return;
    const suggestions = (analysis?.suggested_corrections || analysis?.auto_correction_hints || []).map((item: any) =>
      typeof item === "string" ? { field: "claim", suggested: item, reason: item, confidence: analysis?.confidence || 0.8 } : item
    );
    await runAction("Auto-fix applied", () => applyClaimCorrection(selectedClaimId, { suggestions }));
  };

  return (
    <div className="clearinghouse-page">
      {toast && <div className="ch-toast" onAnimationEnd={() => setToast("")}>{toast}</div>}
      <header className="ch-header ch-enterprise-hero">
        <div>
          <p>Enterprise Clearinghouse Workspace</p>
          <h1>Realtime Payer Gateway Command Center</h1>
          <span>Focused queue for clearinghouse review, auto processing, payer acknowledgments, rejections, and resubmissions.</span>
        </div>
        <div className="ch-header-actions">
          <button disabled={loading || !selectedIds.length} onClick={() => bulk("bulk-accept")}><CheckCircle2 size={16} /> Bulk Accept</button>
          <button disabled={loading || !selectedIds.length} onClick={() => bulk("bulk-reject")}><XCircle size={16} /> Bulk Reject</button>
          <button disabled={loading || !selectedIds.length} onClick={() => bulk("bulk-resubmit")}><RotateCcw size={16} /> Bulk Resubmit</button>
        </div>
      </header>

      <section className="ch-kpis">
        <button className="metric"><span>Total Queue</span><strong>{analytics.total}</strong><small>clearinghouse scoped</small></button>
        <button className="metric success"><span>Acceptance</span><strong>{analytics.acceptanceRate}%</strong><small>{analytics.accepted} accepted</small></button>
        <button className="metric danger"><span>Rejection</span><strong>{analytics.rejectionRate}%</strong><small>{analytics.rejected} rejected</small></button>
        <button className="metric info"><span>Auto Mode</span><strong>{analytics.auto}</strong><small>AI auto review</small></button>
        <button className="metric purple"><span>Resubmission</span><strong>{analytics.resub}</strong><small>retry queue</small></button>
        <button className="metric"><span>Response SLA</span><strong>18m</strong><small>avg payer ack</small></button>
      </section>

      <section className="ch-tabs">
        {tabs.map((tab) => (
          <button key={tab} className={activeTab === tab ? "active" : ""} onClick={() => setActiveTab(tab)}>
            {statusLabel[tab]} <b>{counters[tab] || 0}</b>
          </button>
        ))}
      </section>

      {progress && (
        <div className="ch-progress">
          <span>{progress.operation?.replace("_", " ") || "Bulk operation"}</span>
          <div><i style={{ width: `${Math.round(((progress.processed || progress.success || 0) / Math.max(progress.total || 1, 1)) * 100)}%` }} /></div>
          <b>{progress.processed || progress.success || 0}/{progress.total || 0}</b>
        </div>
      )}

      <div className="ch-tools">
        <label><input type="checkbox" checked={filteredClaims.length > 0 && selectedIds.length === filteredClaims.length} onChange={selectAll} /> Select All</label>
        <div className="ch-search"><Search size={16} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search claim, patient, payer" /></div>
      </div>

      <main className="ch-layout">
        <section className="ch-table-card">
          <table className="ch-table">
            <thead>
              <tr>
                <th></th>
                <th>Payer</th>
                <th>Claim ID</th>
                <th>Validation Score</th>
                <th>Denial Risk</th>
                <th>Mode</th>
                <th>Current Clearinghouse Status</th>
                <th>EDI Status</th>
                <th>Response Time</th>
                <th>AI Recommendation</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredClaims.map((claim) => (
                <tr key={claimIdOf(claim)} className={claimIdOf(selectedClaim) === claimIdOf(claim) ? "selected" : ""} onClick={() => setSelectedClaim(claim)}>
                  <td><input type="checkbox" checked={selectedIds.includes(claimIdOf(claim))} onChange={(e) => { e.stopPropagation(); toggleSelected(claimIdOf(claim)); }} onClick={(e) => e.stopPropagation()} /></td>
                  <td>{payerName(claim)}</td>
                  <td><b>{claimIdOf(claim)}</b><small>{patientName(claim)}</small></td>
                  <td><div className="risk-meter score"><i style={{ width: `${getValidationScore(claim)}%` }} /></div><small>{Math.round(getValidationScore(claim))}%</small></td>
                  <td><div className="risk-meter"><i style={{ width: `${risk(claim)}%` }} /></div><small>{risk(claim)}</small></td>
                  <td><span className={`mode-pill ${getMode(claim).toLowerCase()}`}>{getMode(claim)}</span></td>
                  <td><span className={`ch-status ${claimStatus(claim).toLowerCase()}`}>{statusLabel[claimStatus(claim)] || claimStatus(claim)}</span></td>
                  <td>{getEdiStatus(claim)}</td>
                  <td>{responseTime(claim)}</td>
                  <td className="ai-cell">{aiRecommendation(claim, analysis)}</td>
                  <td>
                    <div className="row-actions">
                      <button onClick={(e) => { e.stopPropagation(); acceptClaim(claimIdOf(claim)); }}>Accept</button>
                      <button onClick={(e) => { e.stopPropagation(); rejectClaim(claimIdOf(claim)); }}>Reject</button>
                      <button onClick={(e) => { e.stopPropagation(); resubmitClaim(claimIdOf(claim)); }}>Retry</button>
                      <button onClick={(e) => { e.stopPropagation(); autoReviewClaim(claimIdOf(claim)); }}>Auto</button>
                      <button onClick={(e) => { e.stopPropagation(); window.location.href = `/case/${claimIdOf(claim)}`; }}>HITL</button>
                      <button onClick={(e) => { e.stopPropagation(); downloadEDI(claimIdOf(claim)); }}>EDI</button>
                      <button onClick={(e) => { e.stopPropagation(); window.location.href = `/claim/${claimIdOf(claim)}`; }}>Profile</button>
                    </div>
                  </td>
                </tr>
              ))}
              {!filteredClaims.length && <tr><td colSpan={11} className="empty">No clearinghouse claims in this queue.</td></tr>}
            </tbody>
          </table>
        </section>

        <aside className="ch-drawer">
          {selectedClaim ? (
            <>
              <div className="drawer-title">
                <div>
                  <p>Claim Detail</p>
                  <h2>{claimIdOf(selectedClaim)}</h2>
                </div>
                <span className={`ch-status ${claimStatus(selectedClaim).toLowerCase()}`}>{claimStatus(selectedClaim)}</span>
              </div>
              {(selectedClaim.processing_mode === "AUTO" || selectedClaim.clearinghouse?.processing_mode === "AUTO") && (
                <div className="auto-badge">Auto acceptance enabled</div>
              )}

              <div className="ch-intel-grid">
                <div><Bot size={16} /><span>Mode</span><b>{getMode(selectedClaim)}</b></div>
                <div><FileText size={16} /><span>EDI</span><b>{getEdiStatus(selectedClaim)}</b></div>
                <div><UserCheck size={16} /><span>Validation</span><b>{Math.round(getValidationScore(selectedClaim))}%</b></div>
                <div><AlertTriangle size={16} /><span>Risk</span><b>{risk(selectedClaim)}</b></div>
              </div>

              <div className="ch-pipeline-title"><GitBranch size={16} /> Clearinghouse Pipeline</div>
              <ClaimPipeline stageIndex={lifecycleIndex(selectedClaim)} />

              <div className="drawer-actions">
                <button disabled={loading} onClick={() => acceptClaim()}><CheckCircle2 size={16} /> Accept</button>
                <button disabled={loading} onClick={() => rejectClaim()}><XCircle size={16} /> Reject</button>
                <button disabled={loading} onClick={() => autoReviewClaim()}><Sparkles size={16} /> Auto Review</button>
                <button disabled={loading} onClick={() => resubmitClaim()}><RotateCcw size={16} /> Resubmit</button>
                <button onClick={() => downloadEDI(claimIdOf(selectedClaim))}>EDI</button>
              </div>

              <div className="ai-review">
                <Sparkles size={18} />
                <div>
                  <b>AI Suggestion</b>
                  <p>{displayText(analysis?.ai_suggestion || analysis?.resubmission_strategy || selectedClaim.payload?.denial_ai?.ai_suggestion, "No denial analysis generated yet.")}</p>
                  <button onClick={() => openAnalysis(selectedClaim)}>Analyze Denial</button>
                </div>
              </div>

              {analysis && (
                <div className="denial-modal">
                  <h3><AlertTriangle size={16} /> Denial Intelligence</h3>
                  <p><b>Reason:</b> {displayText(analysis.denial_reason || analysis.root_cause, "No reason detected")}</p>
                  <p><b>Confidence:</b> {Math.round(Number(analysis.confidence || 0) * 100)}%</p>
                  <p><b>Risk:</b> {displayText(analysis.risk_score, "0")}</p>
                  <button onClick={applyAutoFix}>Apply Auto-Fix</button>
                  <button onClick={() => resubmitClaim()}>Apply + Resubmit</button>
                </div>
              )}

              <div className="edi-panel">
                <h3>EDI 837 Preview</h3>
                <EDIViewer ediData={ediData} />
              </div>
            </>
          ) : (
            <div className="empty">Select a claim to inspect clearinghouse activity.</div>
          )}
        </aside>
      </main>
    </div>
  );
};

export default ClearingHouse;
