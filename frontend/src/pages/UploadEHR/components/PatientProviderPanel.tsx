import React, { useMemo, useState } from "react";
import ExtractedDetailsModal from "./ExtractedDetailsModal";

type PatientProviderPanelProps = {
  item: any;
};

const safeText = (value: any, fallback = "Not reported") => {
  if (value === undefined || value === null || value === "") return fallback;
  if (typeof value === "object") {
    const text =
      value.summary ||
      value.status ||
      value.message ||
      value.label ||
      value.name ||
      value.value ||
      value.code;

    if (text !== undefined && text !== null && text !== "") return String(text);

    try {
      return JSON.stringify(value);
    } catch {
      return fallback;
    }
  }

  return String(value);
};

const formatDate = (value: any) => {
  if (!value) return "Not reported";

  const raw = String(value).trim();

  if (/^\d{4}-\d{2}-\d{2}/.test(raw)) {
    const date = new Date(raw);
    if (!Number.isNaN(date.getTime())) {
      return date.toLocaleDateString();
    }
  }

  return raw;
};
const normalizeStatus = (value: any) =>
  String(value || "")
    .trim()
    .toUpperCase()
    .replace(/[\s-]+/g, "_");

const formatMoney = (value: any) => {
  const amount = Number(value);

  if (!Number.isFinite(amount)) return "Not reported";

  return amount.toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
};

const getClaimPayload = (item: any) => {
  return item?.claim || item?.payload?.claim || item?.payload || item || {};
};

const getPatient = (item: any) => {
  const claim = getClaimPayload(item);

  return {
    ...(claim?.patient || {}),
    ...(item?.patient || {}),
    name:
      item?.patient_name ||
      claim?.patient_name ||
      item?.patient?.name ||
      claim?.patient?.name,
    dob:
      item?.patient_dob ||
      claim?.patient_dob ||
      item?.patient?.dob ||
      claim?.patient?.dob,
    gender:
      item?.gender ||
      claim?.gender ||
      item?.patient?.gender ||
      claim?.patient?.gender,
    member_id:
      item?.member_id ||
      claim?.member_id ||
      item?.patient?.member_id ||
      claim?.patient?.member_id ||
      item?.insurance?.member_id ||
      claim?.insurance?.member_id,
  };
};

const getProvider = (item: any) => {
  const claim = getClaimPayload(item);

  return {
    ...(claim?.provider || {}),
    ...(item?.provider || {}),
    name:
      item?.provider_name ||
      claim?.provider_name ||
      item?.provider?.name ||
      claim?.provider?.name,
    npi:
      item?.provider_npi ||
      claim?.provider_npi ||
      item?.provider?.npi ||
      claim?.provider?.npi,
    tax_id:
      item?.provider_tax_id ||
      claim?.provider_tax_id ||
      item?.provider?.tax_id ||
      claim?.provider?.tax_id,
    address:
      item?.provider_address ||
      claim?.provider_address ||
      item?.provider?.address ||
      claim?.provider?.address,
  };
};

const getPayer = (item: any) => {
  const claim = getClaimPayload(item);

  const payer =
    typeof item?.payer === "string"
      ? { name: item.payer }
      : typeof claim?.payer === "string"
      ? { name: claim.payer }
      : {
          ...(claim?.payer || {}),
          ...(item?.payer || {}),
        };

  return {
    ...payer,
    name:
      item?.payer_name ||
      claim?.payer_name ||
      payer?.name ||
      item?.insurance?.payer ||
      claim?.insurance?.payer,
    payer_id:
      item?.payer_id ||
      claim?.payer_id ||
      payer?.payer_id ||
      payer?.id ||
      item?.insurance?.payer_id ||
      claim?.insurance?.payer_id,
    group_number:
      item?.group_number ||
      claim?.group_number ||
      item?.insurance?.group_number ||
      claim?.insurance?.group_number,
    plan_name:
      item?.plan_name ||
      claim?.plan_name ||
      item?.insurance?.plan_name ||
      claim?.insurance?.plan_name,
  };
};

const getServices = (item: any) => {
  const claim = getClaimPayload(item);

  const services =
    item?.services ||
    claim?.services ||
    item?.service_lines ||
    claim?.service_lines ||
    item?.payload?.services ||
    [];

  return Array.isArray(services) ? services : [];
};

const getDiagnosisCodes = (item: any) => {
  const claim = getClaimPayload(item);

  const codes =
    item?.diagnosis_codes ||
    claim?.diagnosis_codes ||
    item?.icd_codes ||
    claim?.icd_codes ||
    item?.icd10_codes ||
    claim?.icd10_codes ||
    [];

  return Array.isArray(codes) ? codes : codes ? [codes] : [];
};

const getProcedureCodes = (item: any) => {
  const claim = getClaimPayload(item);

  const codes =
    item?.procedure_codes ||
    claim?.procedure_codes ||
    item?.cpt_codes ||
    claim?.cpt_codes ||
    [];

  return Array.isArray(codes) ? codes : codes ? [codes] : [];
};

const getExtractedFields = (item: any) => {
  const claim = getClaimPayload(item);

  const fields =
    item?.extracted_fields ||
    claim?.extracted_fields ||
    item?.field_confidence ||
    claim?.field_confidence ||
    item?.payload?.extracted_fields ||
    {};

  if (Array.isArray(fields)) return fields;

  if (fields && typeof fields === "object") {
    return Object.entries(fields).map(([key, value]: any) => ({
      field: key,
      value: value?.value ?? value,
      confidence: value?.confidence,
      source: value?.source,
    }));
  }

  return [];
};

const DetailTile = ({
  label,
  value,
  confidence,
}: {
  label: string;
  value: any;
  confidence?: any;
}) => (
  <div className="cw-extracted-field">
    <span>{label}</span>
    <strong>{safeText(value)}</strong>
    <em>
      AI · OCR · Verified
      {confidence !== undefined && confidence !== null ? ` · ${Math.round(Number(confidence) * 100)}%` : ""}
    </em>
  </div>
);

const PatientProviderPanel: React.FC<PatientProviderPanelProps> = ({ item }) => {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const patient = useMemo(() => getPatient(item), [item]);
  const provider = useMemo(() => getProvider(item), [item]);
  const payer = useMemo(() => getPayer(item), [item]);
  const services = useMemo(() => getServices(item), [item]);
  const diagnosisCodes = useMemo(() => getDiagnosisCodes(item), [item]);
  const procedureCodes = useMemo(() => getProcedureCodes(item), [item]);
  const extractedFields = useMemo(() => getExtractedFields(item), [item]);
  const status = normalizeStatus(
    item?.status ||
      item?.claim?.status ||
      item?.payload?.claim?.status ||
      item?.payload?.status
  );
  const editable = [
    "HUMAN_REVIEW_REQUIRED",
    "HITL_REQUIRED",
    "WAITING_FOR_APPROVAL",
    "MANUAL_REVIEW_REQUIRED",
    "NEEDS_REVIEW",
    "WAITING_FOR_REVIEW",
    "HARD_REJECT",
    "HARD_REJECTED",
  ].includes(status);

  const totalCharge =
    item?.total_charge ||
    item?.claim_amount ||
    item?.amount ||
    getClaimPayload(item)?.total_charge ||
    getClaimPayload(item)?.claim_amount;

  return (
    <section className="cw-panel cw-patient-provider-panel">
      <div className="cw-panel-title">
        <div>
          <h3>Extracted Claim Data</h3>
          <p>All patient, provider, payer, service, and OCR extracted fields from backend payload</p>
        </div>
        <div className="cw-panel-title-actions">
          <span className="cw-verified-pill">Backend Data</span>
          <button type="button" className="cw-details-btn" onClick={() => setDetailsOpen(true)}>
            Open Details
          </button>
        </div>
      </div>

      <div className="cw-extracted-section">
        <div className="cw-subsection-title">
          <h4>Patient Information</h4>
        </div>
        <div className="cw-extracted-grid">
          <DetailTile label="Patient Name" value={patient.name} />
          <DetailTile label="Date of Birth" value={formatDate(patient.dob)} />
          <DetailTile label="Gender" value={patient.gender} />
          <DetailTile label="Member ID" value={patient.member_id} />
          <DetailTile label="Address" value={patient.address} />
          <DetailTile label="Phone" value={patient.phone} />
        </div>
      </div>

      <div className="cw-extracted-section">
        <div className="cw-subsection-title">
          <h4>Provider Information</h4>
        </div>

        <div className="cw-extracted-grid">
          <DetailTile label="Provider Name" value={provider.name} />
          <DetailTile label="Provider NPI" value={provider.npi} />
          <DetailTile label="Tax ID" value={provider.tax_id} />
          <DetailTile label="Specialty" value={provider.specialty} />
          <DetailTile label="Address" value={provider.address} />
          <DetailTile label="Phone" value={provider.phone} />
        </div>
      </div>

      <div className="cw-extracted-section">
        <div className="cw-subsection-title">
          <h4>Payer / Insurance</h4>
        </div>

        <div className="cw-extracted-grid">
          <DetailTile label="Payer" value={payer.name} />
          <DetailTile label="Payer ID" value={payer.payer_id} />
          <DetailTile label="Plan Name" value={payer.plan_name} />
          <DetailTile label="Group Number" value={payer.group_number} />
          <DetailTile label="Policy Number" value={payer.policy_number} />
          <DetailTile label="Authorization Number" value={payer.authorization_number} />
        </div>
      </div>

      <div className="cw-extracted-section">
        <div className="cw-subsection-title">
          <h4>Claim Summary</h4>
        </div>

        <div className="cw-extracted-grid">
          <DetailTile label="Form Type" value={item?.form_type || getClaimPayload(item)?.form_type} />
          <DetailTile label="Date of Service" value={formatDate(item?.date_of_service || getClaimPayload(item)?.date_of_service)} />
          <DetailTile label="Place of Service" value={item?.place_of_service || getClaimPayload(item)?.place_of_service} />
          <DetailTile label="Total Charge" value={totalCharge ? formatMoney(totalCharge) : "Not reported"} />
          <DetailTile label="Status" value={item?.status || getClaimPayload(item)?.status} />
          <DetailTile label="Stage" value={item?.stage || item?.current_stage || getClaimPayload(item)?.stage} />
        </div>
      </div>

      <div className="cw-extracted-section">
        <div className="cw-subsection-title">
          <h4>Diagnosis Codes</h4>
        </div>

        {diagnosisCodes.length > 0 ? (
          <div className="cw-code-list">
            {diagnosisCodes.map((code: any, index: number) => (
              <span key={`dx-${index}`}>
                {safeText(typeof code === "string" ? code : code?.code || code?.icd_code)}
              </span>
            ))}
          </div>
        ) : (
          <p className="cw-empty-state small">No diagnosis codes extracted.</p>
        )}
      </div>

      <div className="cw-extracted-section">
        <div className="cw-subsection-title">
          <h4>Procedure Codes</h4>
        </div>

        {procedureCodes.length > 0 ? (
          <div className="cw-code-list">
            {procedureCodes.map((code: any, index: number) => (
              <span key={`cpt-${index}`}>
                {safeText(typeof code === "string" ? code : code?.code || code?.cpt_code)}
              </span>
            ))}
          </div>
        ) : (
          <p className="cw-empty-state small">No procedure codes extracted.</p>
        )}
      </div>

      <div className="cw-extracted-section">
        <div className="cw-subsection-title">
          <h4>Service Lines</h4>
        </div>

        {services.length > 0 ? (
          <div className="cw-service-table-wrap">
            <table className="cw-service-table">
              <thead>
                <tr>
                  <th>DOS</th>
                  <th>CPT</th>
                  <th>Modifier</th>
                  <th>Diagnosis</th>
                  <th>Units</th>
                  <th>Charge</th>
                </tr>
              </thead>
              <tbody>
                {services.map((service: any, index: number) => (
                  <tr key={`service-${index}`}>
                    <td>{formatDate(service.date_of_service || service.dos)}</td>
                    <td>{safeText(service.cpt_code || service.procedure_code || service.code)}</td>
                    <td>{safeText(service.modifier || service.modifiers?.join?.(", "))}</td>
                    <td>{safeText(service.diagnosis_code || service.icd_code || service.dx_pointer)}</td>
                    <td>{safeText(service.units || service.quantity)}</td>
                    <td>{service.charge_amount || service.amount ? formatMoney(service.charge_amount || service.amount) : "Not reported"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="cw-empty-state small">No service lines extracted.</p>
        )}
      </div>

      <div className="cw-extracted-section">
        <div className="cw-subsection-title">
          <h4>Raw Extracted Fields</h4>
        </div>

        {extractedFields.length > 0 ? (
          <div className="cw-raw-field-list">
            {extractedFields.slice(0, 24).map((field: any, index: number) => (
              <DetailTile
                key={`raw-field-${field.field || index}`}
                label={String(field.field || field.name || `Field ${index + 1}`)}
                value={field.value}
                confidence={field.confidence}
              />
            ))}
          </div>
        ) : (
          <p className="cw-empty-state small">No raw OCR field-confidence rows reported.</p>
        )}
      </div>

      <ExtractedDetailsModal
        open={detailsOpen}
        item={item}
        editable={editable}
        onClose={() => setDetailsOpen(false)}
        onSave={async (corrections) => {
          // TODO: call backend corrections/resume API here.
          console.log("Save corrections", corrections);
          setDetailsOpen(false);
        }}
      />
    </section>
  );
};

export default PatientProviderPanel;
