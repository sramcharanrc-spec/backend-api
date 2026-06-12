import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { AlertTriangle, CheckCircle2, Clock3, MessageSquare, Plus, Route, Search, ShieldCheck, Sparkles, UserRoundCog } from "lucide-react";
import { API_URL } from "@/config";
import ClaimStatusBadge from "@/components/ClaimStatusBadge";
import PipelineTimeline from "@/components/PipelineTimeline";
import RealtimeAgentFeed from "@/components/RealtimeAgentFeed";
import { usePipeline } from "@/hooks/usePipeline";
import { addPipelineEventListener } from "@/services/websocket";
import { caseService, HitlCase } from "@/services/caseService";
import { generateAppeal, getDenialAnalysis, retrySubmission } from "@/services/rcmApi";
import "./CaseOrchestration.css";

const tabs = [
  { label: "Open Cases", status: "" },
  { label: "Escalated", status: "ESCALATED" },
  { label: "Compliance Review", status: "COMPLIANCE_REVIEW" },
  { label: "Legal Review", status: "LEGAL_REVIEW" },
  { label: "Approved", status: "APPROVED" },
  { label: "Closed", status: "CLOSED" },
];

const roles = ["MA Team", "HEOR Team", "Legal Team", "Compliance Team", "Admin"];

const statusForTab = (caseItem: HitlCase, activeTab: string) => {
  if (!activeTab) return !["APPROVED", "CLOSED"].includes(caseItem.status);
  return caseItem.status === activeTab;
};

const timeLeft = (value?: string) => {
  if (!value) return "No SLA";
  const diff = new Date(value).getTime() - Date.now();
  const abs = Math.abs(diff);
  const hours = Math.floor(abs / 3600000);
  const minutes = Math.floor((abs % 3600000) / 60000);
  return diff < 0 ? `${hours}h ${minutes}m overdue` : `${hours}h ${minutes}m left`;
};

const riskLabel = (value?: number) => {
  const risk = Number(value || 0);
  if (risk >= 75) return "Critical";
  if (risk >= 45) return "Elevated";
  return "Controlled";
};

export default function CaseOrchestration() {
  const { claimId } = useParams();
  const [data, setData] = useState<any>(null);
  const [formData, setFormData] = useState<any>({});
  const [editMode, setEditMode] = useState(false);
  const [denialAi, setDenialAi] = useState<any>({});
  const [caseBusy, setCaseBusy] = useState("");
  const [loading, setLoading] = useState(Boolean(claimId));
  const [error, setError] = useState("");
  const [cases, setCases] = useState<HitlCase[]>([]);
  const [selected, setSelected] = useState<HitlCase | null>(null);
  const [dashboard, setDashboard] = useState<Record<string, any>>({});
  const [activeTab, setActiveTab] = useState("");
  const [search, setSearch] = useState("");
  const [comment, setComment] = useState("");
  const [toast, setToast] = useState("");
  const [approvedState, setApprovedState] = useState(false);
  const { claims, claimEvents, claim: liveClaim } = usePipeline(claimId);

  const fetchQueue = async () => {
    const [items, summary] = await Promise.all([
      caseService.list(search ? { search } : {}),
      caseService.dashboard(),
    ]);
    setCases(items);
    setDashboard(summary);
    setSelected((current) => items.find((item) => item.case_id === current?.case_id) || items[0] || null);
  };

  useEffect(() => {
    if (claimId) return;
    fetchQueue().catch((err) => setError(String(err)));
  }, [claimId, search]);

  useEffect(() => {
    if (claimId) return;
    return addPipelineEventListener((event) => {
      if (["case_created", "case_escalated", "sla_warning", "denial_detected", "ai_correction", "compliance_review"].includes(event.event || event.type)) {
        setToast(`${event.event || event.type} received`);
        fetchQueue().catch(console.error);
      }
    });
  }, [claimId]);

  const filteredCases = useMemo(
    () => cases.filter((caseItem) => statusForTab(caseItem, activeTab)),
    [cases, activeTab]
  );

  const exceptionClaims = useMemo(
    () =>
      Object.values(claims).filter((claim) =>
        ["FAILED", "DENIED", "REJECTED", "HITL_REQUIRED"].includes(
          String(claim.status || claim.validationStatus || claim.complianceStatus).toUpperCase()
        )
      ),
    [claims]
  );

  const fetchData = async () => {
    if (!claimId) return;
    try {
      setLoading(true);
      setError("");
      const res = await fetch(`${API_URL}/api/case/${claimId}`);
      const json = await res.json();
      setData(json);
      if (json?.claim) setFormData(json.claim);
    } catch (err: any) {
      console.error("Fetch error:", err);
      setError("Failed to load case data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [claimId]);

  useEffect(() => {
    if (!claimId) return;
    getDenialAnalysis(claimId)
      .then((result) => setDenialAi(result.analysis || {}))
      .catch(() => setDenialAi({}));
  }, [claimId]);

  const postAction = async (url: string) => {
    await fetch(url, { method: "POST" });
    fetchData();
  };

  const handleSave = async () => {
    await fetch(`${API_URL}/api/case/${claimId}/fix`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        dob: formData?.patient?.dob,
        npi: formData?.provider?.npi,
      }),
    });
    setEditMode(false);
    fetchData();
  };

  const handleApprove = async () => {
    if (!claimId || approvedState) return;
    setCaseBusy("approve");
    try {
      const response = await fetch(`${API_URL}/api/case/${claimId}/approve?user_id=Kiran`, { method: "POST" });
      if (!response.ok) throw new Error(await response.text());
      const result = await response.json();
      setApprovedState(true);
      setToast("Approved Successfully. Pipeline Resumed.");
      setData((prev: any) => ({ ...prev, ...result, case: result.case || prev?.case, status: result.status || "APPROVED" }));
      await fetchData();
    } finally {
      setCaseBusy("");
    }
  };

  const handleApproveSuggestion = async () => {
    if (!claimId) return;
    setCaseBusy("approve-suggestion");
    try {
      const result = await retrySubmission(claimId);
      setData((prev: any) => ({ ...prev, claim: result.claim || prev?.claim, status: result.status }));
    } finally {
      setCaseBusy("");
    }
  };

  const handleGenerateAppeal = async () => {
    if (!claimId) return;
    setCaseBusy("appeal");
    try {
      const result = await generateAppeal(claimId);
      setDenialAi(result.analysis || {});
    } finally {
      setCaseBusy("");
    }
  };

  const refreshSelected = async (updated: HitlCase) => {
    setSelected(updated);
    await fetchQueue();
  };

  const handleCreateDemo = async () => {
    const created = await caseService.createDemo();
    setToast("Demo HITL case created");
    await refreshSelected(created);
  };

  const handleComment = async () => {
    if (!selected || !comment.trim()) return;
    const updated = await caseService.comment(selected.case_id, comment.trim());
    setComment("");
    await refreshSelected(updated);
  };

  if (!claimId) {
    return (
      <div className="case-workspace">
        {toast && <div className="case-toast" onAnimationEnd={() => setToast("")}>{toast}</div>}
        <div className="case-hero">
          <div>
            <p className="eyebrow">Enterprise HITL Case Command Center</p>
            <h2>Case Management Workspace</h2>
            <span>Focused view for HITL review, compliance exceptions, escalations, Legal, HEOR, MA, and approval workflows.</span>
          </div>
          <button className="case-action primary" onClick={handleCreateDemo}><Plus size={16} /> Demo Case</button>
        </div>

        <section className="case-kpis">
          <div><Clock3 size={18} /><span>Open</span><strong>{dashboard.open || 0}</strong></div>
          <div><AlertTriangle size={18} /><span>Escalated</span><strong>{dashboard.escalated || 0}</strong></div>
          <div><ShieldCheck size={18} /><span>SLA</span><strong>{dashboard.sla_attainment ?? 100}%</strong></div>
          <div><CheckCircle2 size={18} /><span>Approved</span><strong>{dashboard.approved || 0}</strong></div>
        </section>

        <div className="case-tabs">
          {tabs.map((tab) => (
            <button key={tab.label} className={activeTab === tab.status ? "active" : ""} onClick={() => setActiveTab(tab.status)}>
              {tab.label}
            </button>
          ))}
        </div>

        <div className="case-search">
          <Search size={16} />
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search case, claim, patient, or routing note" />
        </div>

        {error && <div className="case-error">{error}</div>}

        <div className="case-shell">
          <div className="case-queue">
            <div className="case-table-head">
              <span>Case ID</span>
              <span>Claim ID</span>
              <span>Assigned Team</span>
              <span>Current Owner</span>
              <span>SLA Remaining</span>
              <span>Escalation</span>
              <span>Approval</span>
              <span>Workflow Stage</span>
              <span>Denial Risk</span>
              <span>Priority</span>
              <span>AI Recommendation</span>
            </div>
            {filteredCases.map((caseItem) => (
              <button
                key={caseItem.case_id}
                className={`case-row ${selected?.case_id === caseItem.case_id ? "selected" : ""}`}
                onClick={() => setSelected(caseItem)}
              >
                <span><b>{caseItem.case_id}</b><small>{(caseItem as any).case_type || "HITL"}</small></span>
                <span>{caseItem.claim_id || "No claim linked"}</span>
                <span>{caseItem.assigned_role}</span>
                <span>{caseItem.assigned_to || "Queue Owner"}</span>
                <span className={caseItem.sla_status === "OVERDUE" ? "sla overdue" : "sla"}>{timeLeft(caseItem.sla_due_at)}</span>
                <span>Level {caseItem.escalation_level || 0}</span>
                <span><i className={`status-dot ${caseItem.status.toLowerCase()}`} />{caseItem.status}</span>
                <span>{(caseItem as any).workflow_stage || caseItem.status}</span>
                <span><meter min={0} max={100} value={caseItem.risk_score || 0} />{riskLabel(caseItem.risk_score)}</span>
                <span>{caseItem.priority || "MEDIUM"}</span>
                <span className="case-ai-cell">{caseItem.ai_suggestion || "Review evidence and route per SLA."}</span>
              </button>
            ))}
            {filteredCases.length === 0 && <div className="empty-state">No cases in this queue.</div>}
          </div>

          <aside className="case-detail">
            {selected ? (
              <>
                <div className="detail-title">
                  <div>
                    <h3>{selected.title}</h3>
                    <p>{selected.description || selected.claim_id}</p>
                  </div>
                  <span className={`badge ${selected.sla_status?.toLowerCase()}`}>{selected.sla_status}</span>
                </div>

                <div className="detail-actions">
                  <select value={selected.assigned_role} onChange={(e) => caseService.assign(selected.case_id, e.target.value).then(refreshSelected)}>
                    {roles.map((role) => <option key={role}>{role}</option>)}
                  </select>
                  <button disabled={selected.status === "APPROVED"} onClick={() => caseService.status(selected.case_id, "APPROVED").then(refreshSelected)}>Approve</button>
                  <button disabled={selected.status === "APPROVED"} onClick={() => caseService.escalate(selected.case_id).then(refreshSelected)}>Escalate</button>
                </div>
                {selected.status === "APPROVED" && <div className="approval-success"><b>Approved Successfully</b><span>Pipeline Resumed</span></div>}

                <div className="case-lifecycle">
                  {["Created", "Triage", "Evidence", "Routing", "Approval", "Resume"].map((stage, index) => (
                    <div key={stage} className={index <= Math.min(5, selected.escalation_level || 2) ? "active" : ""}>
                      <i>{index + 1}</i>
                      <span>{stage}</span>
                    </div>
                  ))}
                </div>

                <div className="ai-panel">
                  <Sparkles size={18} />
                  <div>
                    <b>AI Recommendation</b>
                    <p>{selected.ai_suggestion || "No recommendation generated yet."}</p>
                    <div className="risk-heat"><span style={{ width: `${selected.risk_score || 0}%` }} /></div>
                  </div>
                </div>

                <div className="mini-grid">
                  <div><Route size={16} /><span>Template</span><b>{selected.template_name || "Unknown"}</b></div>
                  <div><UserRoundCog size={16} /><span>Assigned</span><b>{selected.assigned_to || selected.assigned_role}</b></div>
                  <div><ShieldCheck size={16} /><span>Compliance Evidence</span><b>{selected.metadata?.evidence_status || "Ready"}</b></div>
                  <div><Clock3 size={16} /><span>E-Signature</span><b>{selected.metadata?.signature_status || (selected.status === "APPROVED" ? "Signed" : "Pending")}</b></div>
                </div>

                <div className="case-evidence-grid">
                  <div><b>Rule Evaluations</b><span>{selected.denial_reason || "Payer, CPT, ICD, and coverage rules available for reviewer."}</span></div>
                  <div><b>Compliance Evidence</b><span>{selected.description || "Evidence bundle attached to case record."}</span></div>
                  <div><b>Denial Reasoning</b><span>{selected.ai_suggestion || "AI recommendation pending."}</span></div>
                  <div><b>Approval History</b><span>{selected.status === "APPROVED" ? "Approved and ready to resume pipeline." : "Awaiting reviewer approval."}</span></div>
                </div>

                <div className="comment-panel">
                  <h4><MessageSquare size={16} /> Activity Feed</h4>
                  <div className="comment-list">
                    {(selected.comments || []).map((item) => (
                      <p key={item.id}><b>{item.author}</b> {item.comment}<small>{new Date(item.created_at).toLocaleString()}</small></p>
                    ))}
                    {(selected.audit_logs || []).slice(-6).map((item) => (
                      <p key={`audit-${item.id}`}><b>{item.actor}</b> {item.action}<small>{new Date(item.created_at).toLocaleString()}</small></p>
                    ))}
                  </div>
                  <div className="comment-compose">
                    <input value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Add reviewer note" />
                    <button onClick={handleComment}>Post</button>
                  </div>
                </div>
              </>
            ) : (
              <div className="empty-state">Select a case to review timeline, audit, comments, and AI guidance.</div>
            )}
          </aside>
        </div>

        {exceptionClaims.length > 0 && (
          <div className="legacy-exceptions">
            <h4>Live Pipeline Exceptions</h4>
            {exceptionClaims.map((claim) => (
              <div key={claim.claimId} className="case-exception-row">
                <div>
                  <b>{claim.claimId}</b>
                  <p>Agent: {claim.currentAgent || claim.currentStep || "Review"} | Validation: {claim.validationStatus || "PENDING"}</p>
                </div>
                <button className="case-action" onClick={() => { window.location.href = `/case/${claim.claimId}`; }}>Open Claim</button>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  if (loading) return <div className="case-page">Loading case data...</div>;
  if (error) return <div className="case-page error">{error}</div>;
  if (!data) return <div className="case-page">No data found</div>;

  const claim = data?.claim || {};
  const patient = claim?.patient || {};
  const provider = claim?.provider || {};
  const pipeline = data?.pipeline || {};
  const validation = data?.validation || {};
  const compliance = data?.compliance || {};
  const financials = data?.financials || {};
  const caseData = data?.case || data;
  const isApproved = approvedState || caseData?.status === "APPROVED" || caseData?.approval?.status === "APPROVED";
  const isValid = Boolean(formData?.patient?.dob && formData?.provider?.npi) && !isApproved;

  return (
    <div className="case-page">
      <div className="case-header">
        <h2>Case Orchestration</h2>
        <p>Claim ID: {data?.claim_id || claimId}</p>
      </div>

      <div className="case-grid">
        <div className="case-card">
          <h4>Claim Info</h4>
          <p><b>Patient:</b> {editMode ? <input value={formData?.patient?.name || ""} onChange={(e) => setFormData({ ...formData, patient: { ...formData.patient, name: e.target.value } })} /> : patient.name || "N/A"}</p>
          <p><b>DOB:</b> {editMode ? <input value={formData?.patient?.dob || ""} onChange={(e) => setFormData({ ...formData, patient: { ...formData.patient, dob: e.target.value } })} /> : patient.dob || "N/A"}</p>
          <p><b>Provider:</b> {editMode ? <input value={formData?.provider?.name || ""} onChange={(e) => setFormData({ ...formData, provider: { ...formData.provider, name: e.target.value } })} /> : provider.name || "N/A"}</p>
          <p><b>NPI:</b> {editMode ? <input value={formData?.provider?.npi || ""} onChange={(e) => setFormData({ ...formData, provider: { ...formData.provider, npi: e.target.value } })} /> : provider.npi || "N/A"}</p>
          {editMode && <button className="btn success" onClick={handleSave}>Save Changes</button>}
        </div>

        <div className="case-card"><h4>Failure Triage</h4><p><b>Validation:</b> <ClaimStatusBadge status={liveClaim?.validationStatus || validation?.status} /></p><p><b>Compliance:</b> <ClaimStatusBadge status={liveClaim?.complianceStatus || compliance?.status} /></p><p><b>Submission:</b> <ClaimStatusBadge status={liveClaim?.submissionStatus || pipeline?.stage} /></p></div>
        <div className="case-card"><h4>Financial</h4><p><b>Expected:</b> ${financials?.expected || 0}</p><p><b>Received:</b> ${financials?.received || 0}</p><p><b>Status:</b> {financials?.status || "N/A"}</p></div>
        <div className="case-card">
          <h4>Retry Actions</h4>
          {isApproved && <div className="approval-success"><b>Approved Successfully</b><span>Pipeline Resumed</span></div>}
          <button className="btn primary" disabled={isApproved} onClick={() => setEditMode(true)}>Edit</button>
          <button className="btn success" disabled={isApproved} onClick={() => postAction(`${API_URL}/api/case/${claimId}/sign?user_id=Kiran`)}>Sign</button>
          <button className="btn success" disabled={!isValid || caseBusy === "approve"} onClick={handleApprove}>{caseBusy === "approve" ? "Approving..." : "Approve"}</button>
          <button className="btn primary" disabled={isApproved} onClick={() => postAction(`${API_URL}/api/rcm/start-pipeline/${claimId}`)}>Retry</button>
          <button className="btn danger" disabled={isApproved} onClick={() => postAction(`${API_URL}/api/case/${claimId}/escalate`)}>Reject</button>
        </div>

        <div className="case-card full">
          <h4>AI-Assisted Denial Review</h4>
          <p><b>Root Cause:</b> {denialAi.root_cause || denialAi.denial_reason || "No denial analysis yet"}</p>
          <p><b>Retry Probability:</b> {Math.round(Number(denialAi.retry_probability || 0) * 100)}%</p>
          <p><b>Strategy:</b> {denialAi.resubmission_strategy || "Generate appeal or analyze denial to view strategy"}</p>
          <div className="case-ai-actions">
            <button className="btn success" disabled={Boolean(caseBusy)} onClick={handleApproveSuggestion}>{caseBusy === "approve-suggestion" ? "Applying..." : "Approve Suggestion"}</button>
            <button className="btn danger" disabled={Boolean(caseBusy)} onClick={() => setDenialAi({ ...denialAi, reviewer_decision: "REJECTED" })}>Reject Suggestion</button>
            <button className="btn primary" disabled={Boolean(caseBusy)} onClick={handleGenerateAppeal}>{caseBusy === "appeal" ? "Generating..." : "Generate Appeal"}</button>
            <button className="btn primary" disabled={Boolean(caseBusy)} onClick={handleApproveSuggestion}>Resubmit Claim</button>
          </div>
        </div>

        <div className="case-card full"><h4>Live Pipeline Visualization</h4><PipelineTimeline pipeline={pipeline} liveState={liveClaim} /></div>
        <div className="case-card full"><h4>Case Details</h4><p><b>Case ID:</b> {caseData.case_id || "N/A"}</p><p><b>Status:</b> {caseData.status || "PENDING"}</p><p><b>Assigned To:</b> {caseData.assigned_to || "Unassigned"}</p><p><b>SLA Due:</b> {caseData.sla_due || "N/A"}</p></div>
      </div>

      <RealtimeAgentFeed events={claimEvents} title="Case Event Feed" />
    </div>
  );
}
