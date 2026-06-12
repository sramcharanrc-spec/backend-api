import { API_URL } from "@/config";

export type HitlCase = {
  case_id: string;
  claim_id?: string;
  title: string;
  description?: string;
  status: string;
  priority: string;
  assigned_role: string;
  assigned_to?: string;
  escalation_level: number;
  sla_due_at?: string;
  sla_status: string;
  denial_reason?: string;
  ai_suggestion?: string;
  risk_score: number;
  confidence: number;
  corrected_fields?: Array<Record<string, any>>;
  template_name?: string;
  confidence_score?: number;
  extraction_quality?: string;
  metadata?: Record<string, any>;
  comments?: Array<Record<string, any>>;
  assignments?: Array<Record<string, any>>;
  audit_logs?: Array<Record<string, any>>;
  escalations?: Array<Record<string, any>>;
  created_at?: string;
  updated_at?: string;
};

const jsonFetch = async <T>(url: string, init?: RequestInit): Promise<T> => {
  const response = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
};

export const caseService = {
  list: (params: Record<string, string> = {}) => {
    const query = new URLSearchParams(params);
    return jsonFetch<HitlCase[]>(`${API_URL}/cases${query.size ? `?${query}` : ""}`);
  },
  dashboard: () => jsonFetch<Record<string, any>>(`${API_URL}/cases/dashboard`),
  get: (caseId: string) => jsonFetch<HitlCase>(`${API_URL}/cases/${caseId}`),
  createDemo: () =>
    jsonFetch<HitlCase>(`${API_URL}/cases`, {
      method: "POST",
      body: JSON.stringify({
        claim_id: `CLM-DEMO-${Date.now().toString().slice(-5)}`,
        title: "Demo denial review",
        description: "Modifier and diagnosis review routed from DEV-stage denial intelligence.",
        priority: "HIGH",
        assigned_role: "MA Team",
        denial_reason: "Modifier 25 missing for CPT 99213",
        ai_suggestion: "Review documentation and apply modifier 25 if a separately identifiable E/M service is supported.",
        risk_score: 78,
        confidence: 0.89,
        template_name: "CMS-1500",
        confidence_score: 0.72,
        extraction_quality: "medium",
      }),
    }),
  assign: (caseId: string, assigned_role: string, assigned_to = "Queue Owner") =>
    jsonFetch<HitlCase>(`${API_URL}/cases/${caseId}/assign`, {
      method: "PUT",
      body: JSON.stringify({ assigned_role, assigned_to, assigned_by: "Kiran", reason: "Manual queue routing" }),
    }),
  status: (caseId: string, status: string) =>
    jsonFetch<HitlCase>(`${API_URL}/cases/${caseId}/status`, {
      method: "PUT",
      body: JSON.stringify({ status, actor: "Kiran", reason: "Reviewer action" }),
    }),
  comment: (caseId: string, comment: string) =>
    jsonFetch<HitlCase>(`${API_URL}/cases/${caseId}/comment`, {
      method: "POST",
      body: JSON.stringify({ author: "Kiran", role: "Admin", comment }),
    }),
  escalate: (caseId: string) =>
    jsonFetch<HitlCase>(`${API_URL}/cases/${caseId}/escalate?reason=Manual%20escalation&actor=Kiran`, {
      method: "POST",
    }),
};

