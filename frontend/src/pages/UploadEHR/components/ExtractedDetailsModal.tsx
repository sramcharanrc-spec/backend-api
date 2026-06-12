import React, { useEffect, useMemo, useState } from "react";

type ExtractedDetailsModalProps = {
  open: boolean;
  item: any;
  editable: boolean;
  onClose: () => void;
  onSave?: (corrections: any) => Promise<void> | void;
};

type CorrectionSection = Record<string, string>;

type CorrectionForm = {
  patient: CorrectionSection;
  provider: CorrectionSection;
  payer: CorrectionSection;
  claim: CorrectionSection;
};

const safeText = (value: any, fallback = "") => {
  if (value === undefined || value === null) return fallback;
  return String(value);
};

const asObject = (value: any) =>
  value && typeof value === "object" && !Array.isArray(value) ? value : {};

const firstValue = (...values: any[]) =>
  values.find((value) => value !== undefined && value !== null && value !== "") ?? "";

const getClaimPayload = (item: any) => item?.claim || item?.payload?.claim || item?.payload || item || {};

const objectFromMaybeName = (value: any) =>
  typeof value === "string" ? { name: value } : asObject(value);

const getInitialCorrections = (item: any): CorrectionForm => {
  const claim = getClaimPayload(item);
  const patient = asObject(item?.patient);
  const claimPatient = asObject(claim?.patient);
  const provider = asObject(item?.provider);
  const claimProvider = asObject(claim?.provider);
  const payer = objectFromMaybeName(item?.payer);
  const claimPayer = objectFromMaybeName(claim?.payer);
  const itemInsurance = objectFromMaybeName(item?.insurance);
  const claimInsurance = objectFromMaybeName(claim?.insurance);

  return {
    patient: {
      name: safeText(firstValue(item?.patient_name, patient?.name, claim?.patient_name, claimPatient?.name)),
      dob: safeText(firstValue(item?.patient_dob, patient?.dob, claim?.patient_dob, claimPatient?.dob)),
      gender: safeText(firstValue(item?.gender, patient?.gender, claim?.gender, claimPatient?.gender)),
      member_id: safeText(
        firstValue(
          item?.member_id,
          patient?.member_id,
          itemInsurance?.member_id,
          claim?.member_id,
          claimPatient?.member_id,
          claimInsurance?.member_id
        )
      ),
      address: safeText(firstValue(item?.patient_address, patient?.address, claim?.patient_address, claimPatient?.address)),
      phone: safeText(firstValue(item?.patient_phone, patient?.phone, claim?.patient_phone, claimPatient?.phone)),
    },
    provider: {
      name: safeText(firstValue(item?.provider_name, provider?.name, claim?.provider_name, claimProvider?.name)),
      npi: safeText(firstValue(item?.provider_npi, provider?.npi, claim?.provider_npi, claimProvider?.npi)),
      tax_id: safeText(firstValue(item?.provider_tax_id, provider?.tax_id, claim?.provider_tax_id, claimProvider?.tax_id)),
      specialty: safeText(firstValue(item?.provider_specialty, provider?.specialty, claim?.provider_specialty, claimProvider?.specialty)),
      address: safeText(firstValue(item?.provider_address, provider?.address, claim?.provider_address, claimProvider?.address)),
      phone: safeText(firstValue(item?.provider_phone, provider?.phone, claim?.provider_phone, claimProvider?.phone)),
    },
    payer: {
      name: safeText(firstValue(item?.payer_name, payer?.name, itemInsurance?.payer, claim?.payer_name, claimPayer?.name, claimInsurance?.payer)),
      payer_id: safeText(firstValue(item?.payer_id, payer?.payer_id, payer?.id, itemInsurance?.payer_id, claim?.payer_id, claimPayer?.payer_id, claimPayer?.id, claimInsurance?.payer_id)),
      plan_name: safeText(firstValue(item?.plan_name, payer?.plan_name, itemInsurance?.plan_name, claim?.plan_name, claimPayer?.plan_name, claimInsurance?.plan_name)),
      group_number: safeText(firstValue(item?.group_number, payer?.group_number, itemInsurance?.group_number, claim?.group_number, claimPayer?.group_number, claimInsurance?.group_number)),
      policy_number: safeText(firstValue(item?.policy_number, payer?.policy_number, itemInsurance?.policy_number, claim?.policy_number, claimPayer?.policy_number, claimInsurance?.policy_number)),
      authorization_number: safeText(firstValue(item?.authorization_number, payer?.authorization_number, itemInsurance?.authorization_number, claim?.authorization_number, claimPayer?.authorization_number, claimInsurance?.authorization_number)),
    },
    claim: {
      form_type: safeText(firstValue(item?.form_type, claim?.form_type, item?.document_type, claim?.document_type)),
      date_of_service: safeText(firstValue(item?.date_of_service, item?.dos, claim?.date_of_service, claim?.dos)),
      place_of_service: safeText(firstValue(item?.place_of_service, claim?.place_of_service)),
      total_charge: safeText(firstValue(item?.total_charge, item?.claim_amount, item?.amount, claim?.total_charge, claim?.claim_amount, claim?.amount)),
      status: safeText(firstValue(item?.status, claim?.status, item?.payload?.status)),
      stage: safeText(firstValue(item?.stage, item?.current_stage, item?.active_step, claim?.stage, claim?.current_stage)),
    },
  };
};

const sectionLabels: Record<keyof CorrectionForm, string> = {
  patient: "Patient",
  provider: "Provider",
  payer: "Payer / Insurance",
  claim: "Claim",
};

const ExtractedDetailsModal: React.FC<ExtractedDetailsModalProps> = ({
  open,
  item,
  editable,
  onClose,
  onSave,
}) => {
  const initialForm = useMemo(() => getInitialCorrections(item), [item]);
  const [form, setForm] = useState<CorrectionForm>(initialForm);

  useEffect(() => {
    if (open) setForm(initialForm);
  }, [initialForm, open]);

  if (!open) return null;

  const updateField = (section: keyof CorrectionForm, field: string, value: string) => {
    setForm((prev) => ({
      ...prev,
      [section]: {
        ...prev[section],
        [field]: value,
      },
    }));
  };

  const handleSave = async () => {
    await onSave?.(form);
  };

  return (
    <div className="cw-modal-backdrop" onClick={onClose}>
      <section className="cw-extracted-modal" onClick={(event) => event.stopPropagation()}>
        <header className="cw-extracted-modal-header">
          <div>
            <h2>Full Extracted Claim Details</h2>
            <p>{editable ? "Review and correct extracted fields." : "Read-only extracted backend data."}</p>
          </div>

          <button type="button" aria-label="Close extracted claim details" onClick={onClose}>
            x
          </button>
        </header>

        <div className="cw-extracted-modal-body">
          {(Object.keys(form) as Array<keyof CorrectionForm>).map((section) => (
            <div className="cw-edit-section" key={section}>
              <h3>{sectionLabels[section]}</h3>

              <div className="cw-edit-grid">
                {Object.entries(form[section]).map(([field, value]) => (
                  <label key={`${section}-${field}`}>
                    <span>{field.replace(/_/g, " ")}</span>
                    <input
                      value={value}
                      readOnly={!editable}
                      onChange={(event) => updateField(section, field, event.target.value)}
                    />
                  </label>
                ))}
              </div>
            </div>
          ))}

          <div className="cw-edit-section">
            <h3>Raw Backend Payload</h3>
            <pre className="cw-json-preview">{JSON.stringify(item, null, 2)}</pre>
          </div>
        </div>

        <footer className="cw-extracted-modal-footer">
          <button type="button" className="cw-btn secondary" onClick={onClose}>
            Close
          </button>

          {editable && (
            <button type="button" className="cw-btn primary" onClick={handleSave}>
              Save Corrections
            </button>
          )}
        </footer>
      </section>
    </div>
  );
};

export default ExtractedDetailsModal;
