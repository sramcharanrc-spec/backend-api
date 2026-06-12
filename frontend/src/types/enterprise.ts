export interface ExtractionSummary {
  claim_id: string;
  uploaded_file?: string;
  detected_form_type?: string;
  form_type?: string;
  confidence_score?: number | null;
  confidence_threshold?: number;
  extraction_status?: string;
  hitl_required?: boolean;
  hitl_reason?: string[];
  ocr_confidence?: number | null;
  extracted_field_count?: number;
  extracted_services_count?: number;
  processing_duration?: number | string | null;
}

export interface OcrPreview {
  claim_id: string;
  text: string;
}

export interface ValidationSummary {
  claim_id: string;
  validation_result: {
    cpt_valid?: boolean;
    icd_valid?: boolean;
    drug_match?: boolean;
    coverage_valid?: boolean;
    missing_fields?: string[];
    warnings?: string[];
    explanation?: string[];
    rules_evaluated?: any[];
  };
  hitl_reason?: string[];
}

export interface CaseOrchestrationSummary {
  claim_id: string;
  case?: any;
  routing?: any;
  case_id?: string | null;
  current_owner?: string | null;
  priority?: string;
  next_stage?: string;
  sla_deadline?: string;
  escalation_level?: number;
}

export interface AuditEvidence {
  claim_id: string;
  timeline: {
    timestamp?: string;
    event: string;
    detail?: string;
    source?: string;
  }[];
  decision_logs?: any[];
  agent_events?: any[];
  compliance?: any[];
}

export interface EnterpriseAnalytics {
  summary: {
    total_claims?: number;
    average_processing_time_ms?: number;
    average_payment_time_ms?: number;
    top_denial_reason?: string | null;
    best_payer?: string | null;
    worst_payer?: string | null;
    sla_compliance?: number;
    claim_success_ratio?: number;
    open_cases?: number;
    decision_log_count?: number;
    metric_count?: number;
  };
  claim_trends: any[];
  payer_ranking: any[];
  denial_reasons: any[];
  agent_performance: any[];
  cycle_time?: any;
  sla_metrics?: any;
}
