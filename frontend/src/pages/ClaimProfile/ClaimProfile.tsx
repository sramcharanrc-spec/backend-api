import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { API_URL } from "../../config";
import ClaimArtifactButtons from "../../components/ClaimArtifactButtons";
import ClaimStatusBadge from "../../components/ClaimStatusBadge";
import PipelineTimeline from "../../components/PipelineTimeline";
import RealtimeAgentFeed from "../../components/RealtimeAgentFeed";
import { usePipeline } from "../../hooks/usePipeline";
import {
  applyClaimCorrection,
  generateAppeal,
  getClaimDetails,
  getDenialAnalysis,
  getClaimSuggestions,
  getPipelineStatus,
  getRepairHistory,
  retrySubmission,
  retryClaimValidation,
} from "../../services/rcmApi";
import "./ClaimProfile.css";

const money = (value: any) => {
  const amount = Number(value || 0);
  return amount.toLocaleString("en-US", { style: "currency", currency: "USD" });
};

const percent = (value: any) => {
  const number = Number(value || 0);
  return number <= 1 ? Math.round(number * 100) : Math.round(number);
};

const confidenceClass = (value: any, corrected?: boolean) => {
  if (corrected) return "corrected";
  const score = percent(value);
  if (score >= 85) return "high";
  if (score >= 70) return "medium";
  return "low";
};

const ClaimProfile: React.FC = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState<any>({});
  const [pipelineDetails, setPipelineDetails] = useState<any>(null);
  const [suggestions, setSuggestions] = useState<any[]>([]);
  const [repairHistory, setRepairHistory] = useState<any>({ corrections: [], logs: [] });
  const [denialAi, setDenialAi] = useState<any>({});
  const [appeal, setAppeal] = useState<any>({});
  const [aiBusy, setAiBusy] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const { claim: liveClaim, claimEvents } = usePipeline(id);

  useEffect(() => {
    if (!id) return;

    setLoading(true);
    Promise.allSettled([
      fetch(`${API_URL}/api/records/${id}`).then((res) => {
        if (!res.ok) throw new Error("Claim profile failed to load");
        return res.json();
      }),
      getClaimDetails(id),
      getPipelineStatus(id),
      getClaimSuggestions(id),
      getRepairHistory(id),
      getDenialAnalysis(id),
    ])
      .then(([recordResult, claimResult, pipelineResult, suggestionResult, historyResult, denialResult]) => {
        const record = recordResult.status === "fulfilled" ? recordResult.value : {};
        const claimDetails = claimResult.status === "fulfilled" ? claimResult.value : {};
        const pipeline = pipelineResult.status === "fulfilled" ? pipelineResult.value : null;
        console.log("Pipeline API:", pipeline);
        console.log("Claim status:", claimDetails?.status || record?.status || pipeline?.overall_status);
        const suggestionData = suggestionResult.status === "fulfilled" ? suggestionResult.value : { suggestions: [] };
        const historyData = historyResult.status === "fulfilled" ? historyResult.value : { corrections: [], logs: [] };
        const denialData = denialResult.status === "fulfilled" ? denialResult.value : { analysis: {} };
        setData({
          ...record,
          ...claimDetails,
          claim: record?.claim || claimDetails?.claim || claimDetails?.payload || {},
        });
        setPipelineDetails(pipeline);
        setSuggestions(suggestionData.suggestions || []);
        setRepairHistory(historyData);
        setDenialAi(denialData.analysis || {});
        setAppeal({ appeal_text: denialData.analysis?.appeal_text });
      })
      .catch((err) => setError(err.message || "Claim profile failed to load"))
      .finally(() => setLoading(false));
  }, [id]);

  const claim = data?.claim || {};
  const patient = claim?.patient || {};
  const provider = claim?.provider || {};
  const denial = data?.denial || claim?.denial_risk || {};
  const payment = data?.payment || claim?.payment || {};
  const financials = data?.financials || payment?.financials || {};
  const pipeline = pipelineDetails?.stages ? pipelineDetails : pipelineDetails?.pipeline || data?.pipeline?.steps || data?.pipeline || {};
  const pipelineCompleted = String(pipelineDetails?.overall_status || data?.status || claim?.status || "").toUpperCase() === "COMPLETED";
  const validation = data?.validation || pipelineDetails?.validation || {};
  const compliance = data?.compliance || pipelineDetails?.compliance_results || {};
  const learning = data?.learning || pipelineDetails?.learning_metrics || {};
  const analytics = data?.analytics || pipelineDetails?.analytics_summary || {};
  const clearinghouse = data?.clearinghouse || pipelineDetails?.clearinghouse_ack || {};
  const extraction = claim?.extraction || data?.extraction || {};
  const fieldConfidence = claim?.field_confidence || data?.field_confidence || [];
  const services = claim?.services || data?.services || [];

  const fieldMeta = (field: string) => {
    const source = Array.isArray(fieldConfidence)
      ? fieldConfidence.find((item: any) => item.field === field || item.field?.endsWith(`.${field}`))
      : fieldConfidence?.[field];
    return source || claim?.ai_fields?.[field] || data?.ai_fields?.[field] || {};
  };

  const FieldValue = ({ field, value }: { field: string; value: any }) => {
    const meta = fieldMeta(field);
    const corrected = Boolean(meta.corrected || meta.human_corrected || meta.verified_by);
    const score = percent(meta.confidence ?? meta.ocr_confidence ?? claim?.confidence ?? 0);
    const source = meta.source || meta.ocr_source || meta.box || "OCR Agent";
    const title = [
      corrected ? "Human corrected" : "Extracted by OCR Agent",
      `Confidence: ${score || 0}%`,
      `Source: ${source}`,
    ].join("\n");

    return (
      <span className={`ai-field ${confidenceClass(score, corrected)}`} title={title}>
        <span>{value || "Not captured"}</span>
        <i>{corrected ? "Corrected" : "AI"}</i>
        {meta.ocr_source || meta.source ? <i>OCR</i> : null}
        {score >= 85 ? <i>Verified</i> : null}
      </span>
    );
  };

  const refreshAiRepair = async () => {
    if (!id) return;
    const [suggestionData, historyData] = await Promise.all([
      getClaimSuggestions(id),
      getRepairHistory(id),
    ]);
    setSuggestions(suggestionData.suggestions || []);
    setRepairHistory(historyData);
  };

  const handleApplySuggestion = async (suggestion: any, action = "accepted") => {
    if (!id) return;
    setAiBusy(`${action}-${suggestion.field}`);
    try {
      await applyClaimCorrection(id, {
        action,
        suggestions: [suggestion],
      });
      await refreshAiRepair();
    } finally {
      setAiBusy("");
    }
  };

  const handleAutoApply = async () => {
    if (!id) return;
    setAiBusy("auto");
    try {
      await applyClaimCorrection(id, {
        action: "accepted",
        suggestions,
      });
      const validationResult = await retryClaimValidation(id);
      setData((prev: any) => ({
        ...prev,
        claim: validationResult.claim || prev.claim,
        validation: validationResult.validation,
        status: validationResult.status,
      }));
      await refreshAiRepair();
    } finally {
      setAiBusy("");
    }
  };

  const handleRetryValidation = async () => {
    if (!id) return;
    setAiBusy("retry");
    try {
      const validationResult = await retryClaimValidation(id);
      setData((prev: any) => ({
        ...prev,
        claim: validationResult.claim || prev.claim,
        validation: validationResult.validation,
        status: validationResult.status,
      }));
      await refreshAiRepair();
    } finally {
      setAiBusy("");
    }
  };

  const handleGenerateAppeal = async () => {
    if (!id) return;
    setAiBusy("appeal");
    try {
      const result = await generateAppeal(id);
      setDenialAi(result.analysis || {});
      setAppeal(result.appeal || {});
    } finally {
      setAiBusy("");
    }
  };

  const handleDenialAutoFix = async () => {
    if (!id) return;
    setAiBusy("denial-fix");
    try {
      const result = await retrySubmission(id);
      setData((prev: any) => ({ ...prev, claim: result.claim || prev.claim, status: result.status }));
    } finally {
      setAiBusy("");
    }
  };

  if (loading) {
    return <div className="profile-page"><div className="profile-state">Loading claim profile...</div></div>;
  }

  if (error) {
    return <div className="profile-page"><div className="profile-state error-state">{error}</div></div>;
  }

  return (
    <div className="profile-page">
      <div className="profile-header">
        <div>
          <button className="back-btn" onClick={() => navigate("/upload")}>Back to workqueue</button>
          <h2>Claim {id}</h2>
          <p>{patient.name || "Unknown patient"} - {data?.status || claim?.status || liveClaim?.status || "PENDING"}</p>
        </div>
        <div className="profile-total">
          <span>Total Charge</span>
          <strong>{money(claim?.total_charge || data?.total_charge)}</strong>
        </div>
      </div>

      <div className="profile-grid">
        <section className="profile-card">
          <h3>Patient Info</h3>
          <dl>
            <dt>Name</dt><dd><FieldValue field="patient.name" value={patient.name || "Unknown"} /></dd>
            <dt>DOB</dt><dd><FieldValue field="patient.dob" value={patient.dob} /></dd>
            <dt>Member ID</dt><dd><FieldValue field="patient.member_id" value={patient.member_id} /></dd>
          </dl>
        </section>

        <section className="profile-card">
          <h3>Provider Info</h3>
          <dl>
            <dt>Name</dt><dd><FieldValue field="provider.name" value={provider.name} /></dd>
            <dt>NPI</dt><dd><FieldValue field="provider.npi" value={provider.npi} /></dd>
            <dt>Tax ID</dt><dd><FieldValue field="provider.tax_id" value={provider.tax_id} /></dd>
          </dl>
        </section>

        <section className="profile-card">
          <h3>Financial</h3>
          <dl>
            <dt>Total</dt><dd>{money(claim?.total_charge || data?.total_charge)}</dd>
            <dt>Paid</dt><dd>{money(payment?.paid_amount || financials?.received)}</dd>
            <dt>Status</dt><dd><ClaimStatusBadge status={liveClaim?.paymentStatus || financials?.status || claim?.payment_status || data?.status} /></dd>
          </dl>
        </section>

        <section className="profile-card">
          <h3>Denial</h3>
          <dl>
            <dt>Risk</dt><dd>{denial?.risk_score ?? denial?.denial_risk ?? 0}</dd>
            <dt>Reason</dt><dd>{denial?.reason || "No denial reason recorded"}</dd>
            <dt>Suggestion</dt><dd>{denial?.suggestion || "None"}</dd>
          </dl>
        </section>
      </div>

      <section className="profile-card profile-wide">
        <h3>Pipeline Status</h3>
        <PipelineTimeline pipeline={pipeline} liveState={liveClaim} />
        <div className="ai-flow-status">
          <span>Textract <ClaimStatusBadge status={claim?.extraction ? "COMPLETE" : "PENDING"} /></span>
          <span>AI Suggestions <ClaimStatusBadge status={pipelineCompleted ? "COMPLETE" : aiBusy ? "RUNNING" : suggestions.length ? "COMPLETE" : "PENDING"} /></span>
          <span>Auto Correction <ClaimStatusBadge status={repairHistory?.corrections?.length ? "COMPLETE" : "PENDING"} /></span>
          <span>Validation Retry <ClaimStatusBadge status={validation?.valid ? "SUCCESS" : "PENDING"} /></span>
        </div>
      </section>

      <section className="profile-card profile-wide">
        <h3>Universal Extraction Intelligence</h3>
        <div className="denial-ai-grid">
          <div><span>Extraction Confidence</span><strong>{extraction.extraction_confidence ?? 0}%</strong></div>
          <div><span>Validation Score</span><strong>{validation.validation_score ?? extraction.validation_score ?? 0}%</strong></div>
          <div><span>OCR Quality</span><strong>{extraction.ocr_quality ?? 0}%</strong></div>
          <div><span>Service Extraction</span><strong>{extraction.service_confidence ?? extraction.service_extraction ?? 0}%</strong></div>
          <div><span>Risk Score</span><strong>{validation.risk_score ?? extraction.risk_score ?? 0}%</strong></div>
          <div><span>Form Type</span><strong>{claim.form_type || claim.form_detection?.form_type || "Unknown"}</strong></div>
        </div>
        <div className="ai-suggestions-table">
          <div className="ai-suggestions-head">
            <span>DOS</span><span>CPT</span><span>Modifier</span><span>Charge</span><span>Units</span>
          </div>
          {services.map((service: any, index: number) => (
            <div className="ai-suggestions-row" key={`${service.cpt || service.cpt_code}-${index}`}>
              <span>{service.date_of_service || "-"}</span>
              <span><FieldValue field={`services.${index}.cpt`} value={service.cpt || service.cpt_code || "-"} /></span>
              <span><FieldValue field={`services.${index}.modifier`} value={service.modifier || service.modifiers?.join(", ") || "-"} /></span>
              <span>{money(service.charge)}</span>
              <span>{service.units || 1}</span>
            </div>
          ))}
          {services.length === 0 && <div className="profile-state">No service lines extracted. This claim should route to HITL review.</div>}
        </div>
        <div className="repair-history-list">
          {fieldConfidence.filter((item: any) => Number(item.confidence) < 0.75).slice(0, 8).map((item: any, index: number) => (
            <div key={`${item.field}-${index}`} className="repair-history-item">
              <strong>{item.field}</strong>
              <span>{item.value || "missing"}</span>
              <ClaimStatusBadge status={`${Math.round(Number(item.confidence || 0) * 100)}%`} />
            </div>
          ))}
        </div>
      </section>

      {id && <ClaimArtifactButtons claimId={id} />}

      <section className="profile-card profile-wide">
        <div className="ai-panel-header">
          <div>
            <h3>AI Suggestions & Claim Repair</h3>
            <p>Review suggested corrections, apply trusted repairs, and retry validation.</p>
          </div>
          <div className="ai-panel-actions">
            <button disabled={!suggestions.length || Boolean(aiBusy)} onClick={handleAutoApply}>
              {aiBusy === "auto" ? "Applying..." : "Auto-apply"}
            </button>
            <button disabled={Boolean(aiBusy)} onClick={handleRetryValidation}>
              {aiBusy === "retry" ? "Retrying..." : "Retry Validation"}
            </button>
          </div>
        </div>

        <div className="ai-suggestions-table">
          <div className="ai-suggestions-head">
            <span>Field</span>
            <span>Current</span>
            <span>Suggested</span>
            <span>Confidence</span>
            <span>Actions</span>
          </div>
          {!pipelineCompleted && suggestions.map((suggestion, index) => (
            <div className="ai-suggestions-row" key={`${suggestion.field}-${index}`}>
              <span>{suggestion.field}</span>
              <span>{JSON.stringify(suggestion.current ?? null)}</span>
              <span>{JSON.stringify(suggestion.suggested ?? null)}</span>
              <span>{Math.round(Number(suggestion.confidence || 0) * 100)}%</span>
              <span>
                <button disabled={Boolean(aiBusy)} onClick={() => handleApplySuggestion(suggestion, "accepted")}>Accept</button>
                <button disabled={Boolean(aiBusy)} onClick={() => handleApplySuggestion(suggestion, "rejected")}>Reject</button>
              </span>
            </div>
          ))}
          {pipelineCompleted && <div className="profile-state">Pipeline complete. No active AI suggestions.</div>}
          {!pipelineCompleted && suggestions.length === 0 && <div className="profile-state">No AI suggestions available for this claim.</div>}
        </div>
      </section>

      <section className="profile-card profile-wide">
        <h3>Repair History</h3>
        <div className="repair-history-list">
          {(repairHistory?.corrections || []).slice(0, 8).map((item: any) => (
            <div key={item.id} className="repair-history-item">
              <strong>{item.field}</strong>
              <span>{JSON.stringify(item.previous)} {"->"} {JSON.stringify(item.corrected)}</span>
              <ClaimStatusBadge status={item.accepted || item.source} />
            </div>
          ))}
          {(repairHistory?.corrections || []).length === 0 && <p>No repairs recorded yet.</p>}
        </div>
      </section>

      <section className="profile-card profile-wide">
        <div className="ai-panel-header">
          <div>
            <h3>AI Denial Intelligence</h3>
            <p>LLM-assisted root cause, payer rules, appeal draft, and resubmission strategy.</p>
          </div>
          <div className="ai-panel-actions">
            <button disabled={Boolean(aiBusy)} onClick={handleDenialAutoFix}>
              {aiBusy === "denial-fix" ? "Fixing..." : "Auto-fix"}
            </button>
            <button disabled={Boolean(aiBusy)} onClick={handleGenerateAppeal}>
              {aiBusy === "appeal" ? "Generating..." : "Generate Appeal"}
            </button>
          </div>
        </div>

        <div className="denial-ai-grid">
          <div>
            <span>Root Cause</span>
            <strong>{denialAi.root_cause || denialAi.denial_reason || "No denial analysis yet"}</strong>
          </div>
          <div>
            <span>Retry Probability</span>
            <strong>{Math.round(Number(denialAi.retry_probability || 0) * 100)}%</strong>
          </div>
          <div>
            <span>Medical Necessity</span>
            <strong>{denialAi.medical_necessity || "Pending review"}</strong>
          </div>
          <div>
            <span>Resubmission Strategy</span>
            <strong>{denialAi.resubmission_strategy || "Generate analysis to view strategy"}</strong>
          </div>
        </div>

        <div className="denial-suggestion-list">
          <h4>Denial Suggestions</h4>
          {[...(denialAi.suggested_corrections || []), ...(denialAi.modifier_suggestions || []), ...(denialAi.icd_suggestions || [])].map((item: any, index: number) => (
            <div key={`${item.field}-${index}`} className="repair-history-item">
              <strong>{item.field || "claim"}</strong>
              <span>{JSON.stringify(item.suggested || item)}</span>
              <ClaimStatusBadge status={item.confidence ? `${Math.round(Number(item.confidence) * 100)}%` : "AI"} />
            </div>
          ))}
        </div>

        <div className="appeal-preview">
          <h4>Appeal Preview</h4>
          <pre>{appeal.appeal_text || denialAi.appeal_text || "Generate an appeal to preview payer-ready language."}</pre>
        </div>
      </section>

      <div className="profile-grid profile-wide">
        <section className="profile-card">
          <h3>Validation Results</h3>
          <dl>
            <dt>Status</dt><dd><ClaimStatusBadge status={liveClaim?.validationStatus || validation?.status} /></dd>
            <dt>Errors</dt><dd>{JSON.stringify(validation?.errors || validation?.issues || [])}</dd>
            <dt>Agent</dt><dd>{liveClaim?.currentAgent || "Not running"}</dd>
          </dl>
        </section>

        <section className="profile-card">
          <h3>Compliance Results</h3>
          <dl>
            <dt>Status</dt><dd><ClaimStatusBadge status={liveClaim?.complianceStatus || compliance?.status} /></dd>
            <dt>Finding</dt><dd>{compliance?.finding || compliance?.message || "No compliance findings recorded"}</dd>
            <dt>Submission</dt><dd><ClaimStatusBadge status={liveClaim?.submissionStatus || clearinghouse?.status} /></dd>
          </dl>
        </section>

        <section className="profile-card">
          <h3>Clearinghouse ACK</h3>
          <dl>
            <dt>ACK</dt><dd>{clearinghouse?.ack_code || clearinghouse?.message || "No ACK received yet"}</dd>
            <dt>Submission ID</dt><dd>{liveClaim?.submissionId || data?.submission_id || "Pending"}</dd>
            <dt>Updated</dt><dd>{liveClaim?.updatedAt ? new Date(liveClaim.updatedAt).toLocaleString() : "Pending"}</dd>
          </dl>
        </section>

        <section className="profile-card">
          <h3>Learning & Analytics</h3>
          <dl>
            <dt>Learning</dt><dd>{learning?.accuracy || learning?.score || "Pending"}</dd>
            <dt>Latency</dt><dd>{analytics?.latency_ms ? `${analytics.latency_ms} ms` : "Pending"}</dd>
            <dt>Summary</dt><dd>{analytics?.summary || "Awaiting analytics agent"}</dd>
          </dl>
        </section>
      </div>

      <RealtimeAgentFeed events={claimEvents} title="Claim Detail Timeline" />
    </div>
  );
};

export default ClaimProfile;
