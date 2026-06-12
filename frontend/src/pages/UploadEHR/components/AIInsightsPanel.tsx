import React, { useMemo, useState } from "react";

type AIInsightsPanelProps = {
  item?: any;
  riskScore?: number | string | null;
  validationScore?: number | string | null;
  confidence?: number | string | null;
  denialProbability?: number | string | null;
  ocrQuality?: number | string | null;
  completeness?: number | string | null;
  suggestions?: any[];
  onOpenSuggestions?: () => void;
};

type InsightMetric = {
  key: string;
  label: string;
  value: number | null;
  display: string;
  tone: "good" | "warning" | "danger" | "neutral";
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

const clampPercent = (value: number) => Math.max(0, Math.min(100, value));

const normalizePercentNumber = (value: any): number | null => {
  if (value === undefined || value === null || value === "") return null;

  const parsed =
    typeof value === "string"
      ? Number(value.replace("%", "").trim())
      : Number(value);

  if (!Number.isFinite(parsed)) return null;

  const normalized = parsed <= 1 && parsed > 0 ? parsed * 100 : parsed;
  return clampPercent(Math.round(normalized));
};

const displayPercent = (value: any) => {
  const normalized = normalizePercentNumber(value);
  return normalized === null ? "Not reported" : `${Math.round(normalized)}%`;
};

const firstValue = (...values: any[]) => {
  return values.find(
    (value) => value !== undefined && value !== null && value !== ""
  );
};

const getClaimPayload = (item: any) => {
  return item?.claim || item?.payload?.claim || item?.payload || item || {};
};

const getNestedValue = (root: any, path: string) => {
  if (!root || !path) return undefined;

  return path.split(".").reduce((acc, key) => {
    if (acc === undefined || acc === null) return undefined;
    return acc?.[key];
  }, root);
};

const getFirstPathValue = (item: any, paths: string[]) => {
  const claim = getClaimPayload(item);

  const roots = [
    item,
    item?.payload,
    item?.claim,
    item?.payload?.claim,
    claim,
  ].filter(Boolean);

  for (const path of paths) {
    for (const root of roots) {
      const value = getNestedValue(root, path);
      if (value !== undefined && value !== null && value !== "") {
        return value;
      }
    }
  }

  return undefined;
};

const getSuggestionText = (suggestion: any) => {
  if (typeof suggestion === "string") return suggestion;

  return (
    suggestion?.message ||
    suggestion?.suggestion ||
    suggestion?.recommendation ||
    suggestion?.action ||
    suggestion?.description ||
    suggestion?.reason ||
    JSON.stringify(suggestion)
  );
};

const getSuggestionTitle = (suggestion: any, index: number) => {
  if (typeof suggestion === "string") return `Suggestion ${index + 1}`;

  return (
    suggestion?.category ||
    suggestion?.field ||
    suggestion?.type ||
    suggestion?.agent ||
    suggestion?.label ||
    `Suggestion ${index + 1}`
  );
};

const getSuggestionTone = (suggestion: any) => {
  const raw = String(
    suggestion?.severity ||
      suggestion?.priority ||
      suggestion?.risk ||
      suggestion?.level ||
      ""
  ).toUpperCase();

  if (["HIGH", "CRITICAL", "DANGER", "ERROR"].includes(raw)) return "danger";
  if (["MEDIUM", "WARNING", "WARN"].includes(raw)) return "warning";
  if (["LOW", "INFO"].includes(raw)) return "neutral";

  return "neutral";
};

const statusOf = (item: any) => {
  const claim = getClaimPayload(item);

  return String(
    item?.status ||
      item?.pipeline_status ||
      item?.current_stage ||
      claim?.status ||
      claim?.pipeline_status ||
      claim?.current_stage ||
      ""
  ).toUpperCase();
};

const buildDynamicSuggestions = (item: any, providedSuggestions?: any[]) => {
  const claim = getClaimPayload(item);

  const analysis = item?.analysis || claim?.analysis || item?.denial_ai || claim?.denial_ai || {};
  const compliance = item?.compliance || claim?.compliance || {};

  const candidates = [
    providedSuggestions,
    item?.suggestions,
    item?.ai_suggestions,
    item?.recommendations,
    item?.insights?.suggestions,
    item?.analytics?.suggestions,
    item?.payload?.suggestions,
    item?.payload?.ai_suggestions,
    item?.payload?.analytics?.suggestions,
    claim?.suggestions,
    claim?.ai_suggestions,
    claim?.recommendations,
    claim?.analytics?.suggestions,
    analysis?.suggested_corrections,
    analysis?.suggestions,
    analysis?.denial_prevention_tips,
    compliance?.issues,
    compliance?.failed_rules,
  ];

  for (const candidate of candidates) {
    if (Array.isArray(candidate) && candidate.length > 0) {
      return candidate;
    }
  }

  const generated: any[] = [];

  const providerNpi =
    item?.provider_npi ||
    item?.provider?.npi ||
    claim?.provider_npi ||
    claim?.provider?.npi;

  const memberId =
    item?.member_id ||
    item?.patient?.member_id ||
    item?.insurance?.member_id ||
    claim?.member_id ||
    claim?.patient?.member_id ||
    claim?.insurance?.member_id;

  const payer =
    item?.payer ||
    item?.payer_name ||
    claim?.payer ||
    claim?.payer_name ||
    claim?.insurance?.payer ||
    claim?.payer?.name;

  const status = statusOf(item);

  if (!providerNpi) {
    generated.push({
      category: "Provider NPI",
      severity: "HIGH",
      message:
        "Provider NPI is missing. Verify provider directory data and update the claim before submission.",
    });
  }

  if (!memberId) {
    generated.push({
      category: "Member ID",
      severity: "MEDIUM",
      message:
        "Member ID is missing or unavailable. Confirm patient insurance eligibility before resubmission.",
    });
  }

  if (!payer) {
    generated.push({
      category: "Payer",
      severity: "MEDIUM",
      message: "Payer information is incomplete. Confirm payer name and payer ID.",
    });
  }

  if (status.includes("HARD_REJECT") || status.includes("REJECTED")) {
    generated.push({
      category: "Rejected Claim",
      severity: "HIGH",
      message:
        "Claim is rejected. Review compliance errors, correct extracted fields, and resubmit if allowed.",
    });
  }

  if (
    status.includes("WAITING_FOR_APPROVAL") ||
    claim?.pipeline_paused === true ||
    claim?.approval_required === true
  ) {
    generated.push({
      category: "Clearinghouse Approval",
      severity: "MEDIUM",
      message:
        "Claim is waiting for clearinghouse approval. Review acknowledgment details before downstream processing.",
    });
  }

  if (claim?.compliance?.failed_rules?.length > 0) {
    generated.push({
      category: "Compliance",
      severity: "HIGH",
      message:
        claim.compliance.reason ||
        claim.compliance.failed_rules[0]?.message ||
        "Compliance failed. Review failed rules before submission.",
    });
  }

  if (generated.length === 0) {
    generated.push({
      category: "No Critical Issues",
      severity: "LOW",
      message: "No blocking AI suggestions were reported by backend agents.",
    });
  }

  return generated;
};

const metricTone = (
  label: string,
  value: number | null
): InsightMetric["tone"] => {
  if (value === null) return "neutral";

  const normalizedLabel = label.toLowerCase();

  if (normalizedLabel.includes("risk") || normalizedLabel.includes("denial")) {
    if (value >= 70) return "danger";
    if (value >= 35) return "warning";
    return "good";
  }

  if (value >= 85) return "good";
  if (value >= 60) return "warning";
  return "danger";
};

const getMetric = (
  item: any,
  label: string,
  explicitValue: any,
  preferredPaths: string[],
  fallbackPaths: string[] = []
): InsightMetric => {
  const preferredValue = getFirstPathValue(item, preferredPaths);
  const fallbackValue = getFirstPathValue(item, fallbackPaths);

  // Important:
  // Prefer final backend agent values first.
  // Use explicit prop second.
  // Use extraction fallback last because extraction may contain stale UniversalMapper scores.
  const backendValue = firstValue(preferredValue, explicitValue, fallbackValue);
  const value = normalizePercentNumber(backendValue);

  return {
    key: label.toLowerCase().replace(/\s+/g, "_"),
    label,
    value,
    display: displayPercent(backendValue),
    tone: metricTone(label, value),
  };
};

const scoreForAverage = (metric: InsightMetric) => {
  if (metric.value === null) return null;

  const label = metric.label.toLowerCase();

  // For risk-like metrics, lower is better, so invert them for the average badge.
  if (label.includes("risk") || label.includes("denial")) {
    return 100 - metric.value;
  }

  return metric.value;
};

const AIInsightsPanel = ({
  item = {},
  riskScore,
  validationScore,
  confidence,
  denialProbability,
  ocrQuality,
  completeness,
  suggestions,
  onOpenSuggestions,
}: AIInsightsPanelProps) => {
  const [showAll, setShowAll] = useState(false);

  const metrics = useMemo(
    () => [
      getMetric(
        item,
        "Validation Score",
        validationScore,
        [
          "validation.validation_score",
          "validation.score",
          "validation_result.validation_score",
          "agents.validation.output.validation_score",
          "agents.validation.output.score",
          "agents.validation.score",
          "compliance.validation_score_percent",
          "validation_score",
        ],
        [
          "extraction.validation_score",
          "extraction.validation_score_percent",
          "payload.extraction.validation_score",
          "claim.extraction.validation_score",
        ]
      ),

      getMetric(
        item,
        "Risk Score",
        riskScore,
        [
          "compliance.risk_score_percent",
          "compliance_risk_score_percent",
          "validation.risk_score",
          "validation_result.risk_score",
          "agents.validation.output.risk_score",
          "agents.compliance.output.risk_score_percent",
          "risk_score",
        ],
        [
          "extraction.risk_score",
          "payload.extraction.risk_score",
          "claim.extraction.risk_score",
        ]
      ),

      getMetric(
        item,
        "Confidence",
        confidence,
        [
          "confidence",
          "extraction_confidence",
          "extraction.extraction_confidence",
          "extraction_metadata.confidence",
          "agents.extraction.output.extraction_confidence",
        ],
        [
          "extraction.confidence",
          "payload.confidence",
          "payload.extraction.confidence",
          "claim.confidence",
        ]
      ),

      getMetric(
        item,
        "Denial Probability",
        denialProbability,
        [
          "analysis.denial_probability",
          "analysis.retry_probability_percent",
          "analysis.retry_probability",
          "denial.risk_score_percent",
          "denial.risk_score",
          "denial_risk.risk_score_percent",
          "denial_risk.risk_score",
          "denial_ai.denial_probability",
          "denial_ai.retry_probability",
          "agents.denial.output.risk_score_percent",
          "agents.denial.output.risk_score",
        ],
        [
          "denial_probability",
          "payload.denial_probability",
          "claim.denial_probability",
        ]
      ),

      getMetric(
        item,
        "OCR Quality",
        ocrQuality,
        [
          "ocr_confidence",
          "ocr_quality",
          "extraction.ocr_quality",
          "extraction_metadata.ocr_quality",
          "agents.extraction.output.ocr_quality",
        ],
        [
          "payload.ocr_quality",
          "payload.extraction.ocr_quality",
          "claim.ocr_quality",
        ]
      ),

      getMetric(
        item,
        "Completeness",
        completeness,
        [
          "completeness_score",
          "extraction.field_completion",
          "field_completion",
          "validation.field_completion",
          "validation_result.field_completion",
          "agents.validation.output.field_completion",
        ],
        [
          "completeness",
          "validation.completeness",
          "payload.completeness",
          "payload.validation.completeness",
          "claim.completeness",
        ]
      ),
    ],
    [
      item,
      riskScore,
      validationScore,
      confidence,
      denialProbability,
      ocrQuality,
      completeness,
    ]
  );

  const dynamicSuggestions = useMemo(
    () => buildDynamicSuggestions(item, suggestions),
    [item, suggestions]
  );

  const visibleSuggestions = showAll
    ? dynamicSuggestions
    : dynamicSuggestions.slice(0, 4);

  const averageScore = useMemo(() => {
    const reported = metrics
      .map(scoreForAverage)
      .filter((value): value is number => value !== null);

    if (reported.length === 0) return null;

    return Math.round(
      reported.reduce((sum, value) => sum + value, 0) / reported.length
    );
  }, [metrics]);

  return (
    <section className="cw-panel cw-ai-panel cw-insights-panel">
      <div className="cw-panel-title">
        <div>
          <h3>AI Insights</h3>
          <p>Backend risk, confidence, validation, and agent recommendations</p>
        </div>

        <div className="cw-ai-title-actions">
          {averageScore !== null && (
            <span
              className={`cw-ai-score ${metricTone(
                "Validation Score",
                averageScore
              )}`}
            >
              Avg {averageScore}%
            </span>
          )}

          {dynamicSuggestions.length > 0 && (
            <span className="cw-ai-suggestion-count">
              {dynamicSuggestions.length} suggestions
            </span>
          )}
        </div>
      </div>

      <div className="cw-ai-metric-list">
        {metrics.map((metric) => (
          <div className={`cw-ai-metric ${metric.tone}`} key={metric.key}>
            <div className="cw-ai-metric-head">
              <span>{metric.label}</span>
              <strong>{metric.display}</strong>
            </div>

            <div className="cw-ai-bar">
              <i style={{ width: `${metric.value ?? 0}%` }} />
            </div>
          </div>
        ))}
      </div>

      <div className="cw-ai-summary-box">
        <strong>AI Summary</strong>
        <p>
          {safeText(
            item?.analytics?.summary ||
              item?.payload?.analytics?.summary ||
              item?.claim?.analytics?.summary ||
              item?.ai_summary ||
              item?.summary ||
              item?.analysis?.appeal_summary ||
              item?.denial_ai?.appeal_summary,
            "No AI summary was reported by backend agents."
          )}
        </p>
      </div>

      <div className="cw-suggestion-list">
        <div className="cw-suggestion-list-head">
          <strong>Top Suggestions</strong>
          {dynamicSuggestions.length > 4 && (
            <button type="button" onClick={() => setShowAll((prev) => !prev)}>
              {showAll ? "Show Less" : `Show All ${dynamicSuggestions.length}`}
            </button>
          )}
        </div>

        {visibleSuggestions.map((suggestion, index) => (
          <div
            className={`cw-suggestion ${getSuggestionTone(suggestion)}`}
            key={`${getSuggestionTitle(suggestion, index)}-${index}`}
          >
            <strong>{getSuggestionTitle(suggestion, index)}</strong>
            <span>{getSuggestionText(suggestion)}</span>
          </div>
        ))}
      </div>

      {onOpenSuggestions && (
        <button
          type="button"
          className="cw-btn secondary"
          onClick={onOpenSuggestions}
        >
          View AI Suggestions
        </button>
      )}
    </section>
  );
};

export default AIInsightsPanel;
