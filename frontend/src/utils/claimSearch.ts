const textValue = (value: any): string => {
  if (value === undefined || value === null || value === "") return "";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) {
    return value.map(textValue).filter(Boolean).join(" ");
  }
  if (typeof value === "object") {
    return textValue(
      value.name ||
        value.full_name ||
        value.patient_name ||
        value.payer_name ||
        value.provider_name ||
        value.member_id ||
        value.id ||
        value.value ||
        value.label
    );
  }
  return "";
};

export const buildClaimSearchText = (claim: any) => {
  const nestedClaim = claim?.claim || claim?.payload?.claim || claim?.data?.claim || {};
  const payload = claim?.payload || {};
  const pipeline = claim?.pipeline || payload?.pipeline || nestedClaim?.pipeline || {};
  const patient = claim?.patient || nestedClaim?.patient || payload?.patient || {};
  const payer = claim?.payer || nestedClaim?.payer || payload?.payer || {};
  const provider = claim?.provider || nestedClaim?.provider || payload?.provider || {};
  const insurance = claim?.insurance || nestedClaim?.insurance || payload?.insurance || {};

  const searchableText = [
    claim?.claim_id,
    claim?.claimId,
    claim?.id,
    nestedClaim?.claim_id,
    nestedClaim?.claimId,
    payload?.claim_id,
    payload?.claimId,
    patient?.name,
    claim?.patient_name,
    claim?.patientName,
    nestedClaim?.patient_name,
    nestedClaim?.patientName,
    payer?.name,
    claim?.payer_name,
    claim?.payer,
    nestedClaim?.payer_name,
    nestedClaim?.payer,
    insurance?.payer,
    insurance?.payer_name,
    provider?.name,
    claim?.provider_name,
    claim?.provider,
    nestedClaim?.provider_name,
    nestedClaim?.provider,
    claim?.member_id,
    claim?.subscriber_id,
    nestedClaim?.member_id,
    nestedClaim?.subscriber_id,
    patient?.member_id,
    insurance?.member_id,
    insurance?.subscriber_id,
    claim?.status,
    nestedClaim?.status,
    claim?.stage,
    claim?.current_stage,
    claim?.current_agent,
    claim?.active_step,
    pipeline?.current_stage,
    pipeline?.current_agent,
    pipeline?.active_step,
    claim?.pipeline_state,
    claim?.pipeline_status,
    pipeline?.pipeline_state,
    pipeline?.pipeline_status,
    claim?.form_type,
    claim?.claim_type,
    nestedClaim?.form_type,
    nestedClaim?.claim_type,
    claim?.document_type,
    nestedClaim?.document_type,
    claim?.source,
    claim?.upload_source,
    payload?.source,
  ];

  return searchableText.map(textValue).filter(Boolean).join(" ").toLowerCase();
};

export const claimMatchesSearch = (claim: any, query: string) => {
  const normalizedQuery = String(query || "").trim().toLowerCase();
  return !normalizedQuery || buildClaimSearchText(claim).includes(normalizedQuery);
};
