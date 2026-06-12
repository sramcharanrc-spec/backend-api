import { memo, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clipboard,
  Clock3,
  Download,
  FileSearch,
  GitBranch,
  Loader2,
  Search,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import {
  exportAuditEvidence,
  getAuditEvidence,
  getCaseOrchestration,
  getExtractionSummary,
  getOcrPreview,
  getValidationSummary,
} from "../../../services/rcmApi";
import type {
  AuditEvidence,
  CaseOrchestrationSummary,
  ExtractionSummary,
  OcrPreview,
  ValidationSummary,
} from "../../../types/enterprise";
import "./EnterpriseClaimObservability.css";

interface Props {
  claimId?: string;
}

const pct = (value?: number | null) => {
  if (value === undefined || value === null || Number.isNaN(Number(value))) return "";
  const normalized = value <= 1 ? value * 100 : value;
  return `${Math.round(normalized)}%`;
};

const durationLabel = (value?: number | string | null) => {
  if (value === undefined || value === null || value === "") return "";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return String(value);
  if (numeric < 1000) return `${Math.round(numeric)}ms`;
  const seconds = numeric / 1000;
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
};

const formatTime = (value?: string) => {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleTimeString();
};

const countSearchMatches = (text: string, query: string) => {
  if (!query.trim()) return 0;
  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return (text.match(new RegExp(escaped, "gi")) || []).length;
};

const StatusCheck = ({ ok, label }: { ok?: boolean; label: string }) => (
  <div className={`eco-check ${ok ? "ok" : "bad"}`}>
    {ok ? <CheckCircle2 size={16} /> : <XCircle size={16} />}
    <span>{label}</span>
  </div>
);

function EnterpriseClaimObservability({ claimId }: Props) {
  const [extraction, setExtraction] = useState<ExtractionSummary | null>(null);
  const [ocr, setOcr] = useState<OcrPreview | null>(null);
  const [validation, setValidation] = useState<ValidationSummary | null>(null);
  const [caseSummary, setCaseSummary] = useState<CaseOrchestrationSummary | null>(null);
  const [audit, setAudit] = useState<AuditEvidence | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [ocrOpen, setOcrOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQuery(query.trim()), 220);
    return () => window.clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!claimId) return;
    let cancelled = false;
    setLoading(true);
    setError("");
    Promise.all([
      getExtractionSummary(claimId),
      getOcrPreview(claimId),
      getValidationSummary(claimId),
      getCaseOrchestration(claimId),
      getAuditEvidence(claimId),
    ])
      .then(([extractionData, ocrData, validationData, caseData, auditData]) => {
        if (cancelled) return;
        setExtraction(extractionData);
        setOcr(ocrData);
        setValidation(validationData);
        setCaseSummary(caseData);
        setAudit(auditData);
      })
      .catch((err) => {
        console.error(err);
        if (!cancelled) setError("Enterprise observability data could not be loaded for this claim.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [claimId]);

  const confidence = extraction?.confidence_score ?? null;
  const confidencePercent = confidence === null ? null : confidence <= 1 ? confidence * 100 : confidence;
  const confidenceTone = confidencePercent === null ? "empty" : confidencePercent >= 80 ? "green" : confidencePercent >= 60 ? "orange" : "red";
  const validationResult = validation?.validation_result || {};
  const ocrText = ocr?.text || "";
  const searchMatches = useMemo(() => countSearchMatches(ocrText, debouncedQuery), [debouncedQuery, ocrText]);
  const filteredTimeline = useMemo(() => (audit?.timeline || []).slice(-80), [audit?.timeline]);
  const visibleTimeline = filteredTimeline.slice(Math.max(0, filteredTimeline.length - 36));

  const slaCountdown = useMemo(() => {
    if (!caseSummary?.sla_deadline) return "";
    const deadline = new Date(caseSummary.sla_deadline).getTime();
    if (!Number.isFinite(deadline)) return "";
    const remaining = deadline - now;
    if (remaining <= 0) return "Overdue";
    const totalSeconds = Math.floor(remaining / 1000);
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    return `${hours}h ${minutes}m ${seconds}s`;
  }, [caseSummary?.sla_deadline, now]);

  if (!claimId) return null;

  return (
    <section className="eco-panel">
      <div className="eco-panel-head">
        <div>
          <p className="ao-eyebrow">Claim Observability</p>
          <h2>Enterprise workflow evidence</h2>
        </div>
        {loading && <Loader2 className="eco-spin" size={18} />}
      </div>

      {error && <div className="eco-error"><AlertTriangle size={16} />{error}</div>}

      <div className="eco-grid">
        <article className="eco-card extraction">
          <div className="eco-card-title">
            <FileSearch size={17} />
            <strong>Document Extraction Summary</strong>
          </div>
          <div className="eco-summary-grid">
            <span>File</span><strong>{extraction?.uploaded_file || ""}</strong>
            <span>Detected Form</span><strong>{extraction?.detected_form_type || extraction?.form_type || ""}</strong>
            <span>Confidence</span><strong>{pct(extraction?.confidence_score)}</strong>
            <span>Threshold</span><strong>{pct(extraction?.confidence_threshold)}</strong>
            <span>Fields</span><strong>{extraction?.extracted_field_count ?? ""}</strong>
            <span>Services</span><strong>{extraction?.extracted_services_count ?? ""}</strong>
            <span>Review</span><strong>{extraction?.hitl_required ? "Required" : extraction ? "Not required" : ""}</strong>
            <span>Duration</span><strong>{durationLabel(extraction?.processing_duration)}</strong>
          </div>
          <div className={`eco-confidence ${confidenceTone}`}>
            <i><b style={{ width: `${Math.max(0, Math.min(100, confidencePercent || 0))}%` }} /></i>
          </div>
          {extraction?.hitl_required && (
            <div className="eco-warning-list">
              <strong>Human Review Triggered</strong>
              {(extraction.hitl_reason || []).map((reason) => <span key={reason}>{reason}</span>)}
            </div>
          )}
        </article>

        <article className="eco-card">
          <div className="eco-card-title">
            <ShieldCheck size={17} />
            <strong>Validation Agent</strong>
          </div>
          <div className="eco-validation-grid">
            <StatusCheck ok={validationResult.cpt_valid} label="CPT" />
            <StatusCheck ok={validationResult.icd_valid} label="ICD" />
            <StatusCheck ok={validationResult.drug_match} label="Drug Match" />
            <StatusCheck ok={validationResult.coverage_valid} label="Coverage" />
          </div>
          {(validationResult.missing_fields || []).length > 0 && (
            <div className="eco-inline-list">
              <span>Missing</span>
              {(validationResult.missing_fields || []).map((field: string) => <b key={field}>{field}</b>)}
            </div>
          )}
          {(validationResult.explanation || []).length > 0 && (
            <div className="eco-explanation">
              {(validationResult.explanation || []).map((item: string) => <p key={item}>{item}</p>)}
            </div>
          )}
        </article>

        <article className="eco-card">
          <div className="eco-card-title">
            <GitBranch size={17} />
            <strong>Case Orchestration</strong>
          </div>
          <div className="eco-summary-grid">
            <span>Case ID</span><strong>{caseSummary?.case_id || ""}</strong>
            <span>Current owner</span><strong>{caseSummary?.current_owner || ""}</strong>
            <span>Priority</span><strong>{caseSummary?.priority || ""}</strong>
            <span>Next stage</span><strong>{caseSummary?.next_stage || ""}</strong>
            <span>SLA countdown</span><strong>{slaCountdown}</strong>
            <span>Escalation</span><strong>{caseSummary?.escalation_level ?? ""}</strong>
          </div>
        </article>

        <article className="eco-card ocr">
          <button className="eco-expand-btn" type="button" onClick={() => setOcrOpen((current) => !current)}>
            {ocrOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            OCR Preview
          </button>
          {ocrOpen && (
            <div className="eco-ocr-panel">
              <div className="eco-ocr-tools">
                <label>
                  <Search size={15} />
                  <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search OCR text" />
                </label>
                <button type="button" onClick={() => navigator.clipboard?.writeText(ocrText)} disabled={!ocrText}>
                  <Clipboard size={15} /> Copy
                </button>
              </div>
              {debouncedQuery && <small>{searchMatches} matches</small>}
              <pre>{ocrText}</pre>
            </div>
          )}
        </article>
      </div>

      <article className="eco-card compliance">
        <div className="eco-card-title">
          <Clock3 size={17} />
          <strong>Compliance Evidence Timeline</strong>
          <div className="eco-export-actions">
            {(["json", "csv", "pdf"] as const).map((format) => (
              <button type="button" key={format} onClick={() => exportAuditEvidence(claimId, format)}>
                <Download size={14} /> {format.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
        <div className="eco-timeline">
          {visibleTimeline.map((item, index) => (
            <p key={`${item.timestamp}-${item.event}-${index}`}>
              <time>{formatTime(item.timestamp)}</time>
              <strong>{item.event}</strong>
              {item.detail && <span>{item.detail}</span>}
            </p>
          ))}
          {visibleTimeline.length === 0 && <p><time>--:--:--</time><strong>No audit events recorded</strong></p>}
        </div>
      </article>
    </section>
  );
}

export default memo(EnterpriseClaimObservability);
