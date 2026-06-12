import { displayText } from "../../../utils/claimSync";

export const isValidClaimId = (value?: string | null) => {
  if (!value) return false;
  return /^CLM-[a-f0-9]{10}$/i.test(String(value).trim()) || /^CLM-/i.test(String(value).trim());
};

export const getClaim = (item: any) =>
  item?.claim || item?.payload?.claim || item?.payload || item || {};

export const getClaimId = (item: any) =>
  item?.claim_id ||
  item?.claimId ||
  item?.payload?.claim_id ||
  item?.payload?.claimId ||
  item?.payload?.claim?.claim_id ||
  item?.payload?.claim?.claimId ||
  item?.claim?.claim_id ||
  item?.claim?.claimId ||
  item?.data?.claim_id ||
  item?.data?.claim?.claim_id;

export const getUploadSessionId = (item: any) =>
  item?.upload_session_id || item?.uploadSessionId || item?.payload?.upload_session_id;

export const getTempId = (item: any) =>
  item?.temp_id || item?.tempId || item?.payload?.temp_id;

export const getCreatedAt = (item: any) =>
  item?.created_at ||
  item?.createdAt ||
  item?.payload?.created_at ||
  item?.payload?.claim?.created_at ||
  item?.claim?.created_at;

export const getUploadedAt = (item: any) =>
  item?.uploaded_at ||
  item?.uploadedAt ||
  item?.payload?.uploaded_at ||
  item?.payload?.claim?.uploaded_at ||
  item?.claim?.uploaded_at ||
  getCreatedAt(item);

export const getLastActivityAt = (item: any) =>
  item?.last_activity_at ||
  item?.lastActivityAt ||
  item?.updatedAt ||
  item?.updated_at ||
  item?.payload?.last_activity_at ||
  item?.payload?.claim?.last_activity_at ||
  item?.claim?.last_activity_at ||
  getUploadedAt(item);

export const isNewUploadFlag = (item: any) =>
  Boolean(item?.is_new_upload || item?.isNewUpload || item?.payload?.is_new_upload);

export const getPatientName = (item: any) =>
  displayText(
    getClaim(item)?.patient?.name ||
      item?.payload?.patient?.name ||
      item?.patient ||
      item?.patient_name ||
      item?.patientName,
    "Not reported"
  );

export const getPatientDob = (item: any) =>
  displayText(
    getClaim(item)?.patient?.dob ||
      item?.patient_dob ||
      item?.dob ||
      item?.payload?.patient_dob,
    ""
  );

export const getGender = (item: any) =>
  displayText(getClaim(item)?.patient?.gender || item?.gender || item?.patient_gender, "");

export const getMemberId = (item: any) =>
  displayText(
    getClaim(item)?.member_id ||
      getClaim(item)?.patient?.member_id ||
      item?.member_id ||
      item?.subscriber_id,
    ""
  );

export const getPayer = (item: any) =>
  displayText(
    getClaim(item)?.payer?.name ||
      getClaim(item)?.payer_name ||
      item?.payer ||
      item?.payer_name ||
      item?.insurance,
    "Not reported"
  );

export const getDos = (item: any) =>
  displayText(getClaim(item)?.date_of_service || item?.date_of_service || item?.dos, "");

export const getAmount = (item: any) =>
  Number(
    getClaim(item)?.total_charge ??
      item?.total_charge ??
      item?.claim_amount ??
      item?.amount ??
      0
  );

export const getProvider = (item: any) =>
  displayText(
    getClaim(item)?.provider?.name ||
      getClaim(item)?.provider_name ||
      item?.provider ||
      item?.provider_name,
    "Not reported"
  );

export const getFileType = (item: any) =>
  String(item?.file_type || item?.document_type || item?.upload_source || "").toUpperCase();

export const normalizeClaimType = (value?: string | null) =>
  String(value || "")
    .trim()
    .toUpperCase()
    .replace(/[-_\s]/g, "");

export const getClaimType = (item: any) =>
  normalizeClaimType(
    item?.claim_type ||
      item?.claimType ||
      item?.payload?.claim_type ||
      item?.payload?.claim?.claim_type ||
      item?.claim?.claim_type ||
      item?.form_type ||
      item?.document_type
  );

export const getSupportedForms = (item: any) => {
  const type = getClaimType(item);

  if (type === "BOTH" || type === "CMS1500UB04" || type === "UB04CMS1500") {
    return ["CMS1500", "UB04"] as const;
  }

  if (type === "CMS1500" || type === "CMS") return ["CMS1500"] as const;
  if (type === "UB04" || type === "UB") return ["UB04"] as const;

  return [] as const;
};

export const getUploadMode = (item: any) => {
  const raw =
    item?.upload_mode ||
    item?.uploadMode ||
    item?.metadata?.upload_mode ||
    item?.payload?.upload_mode ||
    item?.claim?.upload_mode;

  const mode = String(raw || "").toLowerCase();

  if (mode === "bulk" || mode === "single") return mode;

  const source = String(item?.source || item?.payload?.source || item?.claim?.source || "").toUpperCase();

  return source === "EXCEL" || source === "CSV" || source === "BULK" ? "bulk" : "single";
};

export const getUploadSource = (item: any) => {
  const raw =
    item?.upload_source ||
    item?.uploadSource ||
    item?.source ||
    item?.metadata?.source ||
    item?.payload?.source ||
    item?.claim?.source;

  const source = String(raw || "").toUpperCase();

  if (source.includes("EXCEL") || source.includes("CSV") || source === "BULK") return "BULK";
  if (source.includes("PDF")) return "PDF";
  if (["PNG", "JPG", "JPEG", "WEBP", "IMAGE", "TIFF"].some((value) => source.includes(value))) return "IMAGE";

  return getUploadMode(item) === "bulk" ? "BULK" : "Not reported";
};

export const getRiskScore = (item: any) => {
  const raw =
    item?.risk_score ??
    item?.claim?.denial_risk?.risk_score ??
    item?.payload?.denial_risk?.risk_score ??
    item?.payload?.denial_ai?.risk_score ??
    item?.denial_risk?.risk_score;

  if (raw === undefined || raw === null || raw === "") return null;

  const score = Number(raw);

  return Number.isFinite(score) ? score : null;
};

export const getExtraction = (item: any) =>
  item?.extraction || item?.payload?.extraction || item?.claim?.extraction || {};

export const getPipelineSteps = (item: any) =>
  item?.pipeline_steps || item?.pipeline?.steps || item?.payload?.pipeline_steps || [];

export const getBackendPipeline = (item: any) =>
  item?.pipeline || item?.payload?.pipeline || item?.claim?.pipeline || {};

export const getBackendClaim = (item: any) =>
  item?.claim || item?.payload?.claim || item;

export const getBackendField = (item: any, field: string) =>
  getBackendClaim(item)?.[field] ?? item?.[field] ?? item?.payload?.[field];

export const getComplianceResult = (item: any) =>
  item?.compliance || item?.payload?.compliance || item?.claim?.compliance || {};

export const getNestedValue = (source: any, path: string) => {
  if (!source || !path) return undefined;

  return path.split(".").reduce((current, key) => current?.[key], source);
};

export const toList = (value: any) => {
  if (!value) return [];
  return Array.isArray(value) ? value : [value];
};

export const compactUnique = <T,>(items: T[]) =>
  Array.from(new Set(items.filter(Boolean)));

export const pickFirst = (...values: any[]) =>
  values.find((value) => value !== undefined && value !== null && value !== "");
