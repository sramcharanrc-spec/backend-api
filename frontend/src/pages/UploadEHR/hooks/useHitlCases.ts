import { useCallback, useRef, useState } from "react";
import { API_URL } from "../../../config";

type UseHitlCasesOptions = {
  mergeItems?: (claims: any[]) => void;
  setActionMessage?: (message: string) => void;
};

const getNestedCase = (value: any) => {
  if (!value) return null;

  return (
    value?.case ||
    value?.hitl_case ||
    value?.hitlCase ||
    value?.caseRecord ||
    value?.review_case ||
    value?.payload?.case ||
    value?.payload?.hitl_case ||
    value?.claim?.case ||
    value?.claim?.hitl_case ||
    value?.pipeline?.case ||
    null
  );
};

const normalizeCase = (value: any, claimId: string) => {
  const nested = getNestedCase(value) || value;

  if (!nested) return null;

  const caseId =
    nested?.case_id ||
    nested?.id ||
    value?.case_id ||
    value?.hitl_case_id ||
    value?.pipeline?.case_id;

  if (!caseId) return null;

  return {
    ...nested,
    case_id: caseId,
    claim_id: nested?.claim_id || claimId,
  };
};

const isPlainObject = (value: any) =>
  Boolean(value && typeof value === "object" && !Array.isArray(value));

const hasKeys = (value: any) =>
  isPlainObject(value) && Object.keys(value).length > 0;

const getResponseClaim = (value: any) =>
  value?.claim || value?.payload?.claim || value?.resumed?.claim || {};

const getResponsePipeline = (value: any) =>
  value?.pipeline ||
  value?.payload?.pipeline ||
  value?.resumed?.pipeline ||
  value?.claim?.pipeline ||
  value?.payload?.claim?.pipeline;

const mergeCaseUpdate = (
  mergeItems: UseHitlCasesOptions["mergeItems"],
  update: any
) => {
  // mergeItems applies the shared deep pipeline merge, so sparse case payloads do not erase steps.
  mergeItems?.([update]);
};

export const useHitlCases = ({
  mergeItems,
  setActionMessage,
}: UseHitlCasesOptions = {}) => {
  const [caseMap, setCaseMap] = useState<Record<string, any>>({});

  const missingCaseIdsRef = useRef<Set<string>>(new Set());
  const caseFetchInFlightRef = useRef<Record<string, Promise<any | null>>>({});

  const fetchCaseByClaim = useCallback(
    async (claimId: string, options: { force?: boolean } = {}) => {
      if (!claimId) return null;

      if (!options.force && missingCaseIdsRef.current.has(claimId)) {
        return null;
      }

      if (caseFetchInFlightRef.current[claimId]) {
        return caseFetchInFlightRef.current[claimId];
      }

      const request = (async () => {
        try {
          const response = await fetch(`${API_URL}/cases/by-claim/${claimId}`);

          if (response.status === 404) {
            missingCaseIdsRef.current.add(claimId);
            return null;
          }

          const data = await response.json().catch(() => ({}));

          if (!response.ok) {
            console.warn("[cases] optional case fetch failed", data?.detail || response.status);
            return null;
          }

          const resolved = normalizeCase(data, claimId) || data;

          missingCaseIdsRef.current.delete(claimId);
          setCaseMap((prev) => ({ ...prev, [claimId]: resolved }));

          return resolved;
        } catch (error) {
          console.warn("[cases] fetch failed", error);
          return null;
        } finally {
          delete caseFetchInFlightRef.current[claimId];
        }
      })();

      caseFetchInFlightRef.current[claimId] = request;
      return request;
    },
    []
  );

  const ensureHitlCase = useCallback(
    async (
      claimId: string,
      reason = "Manual review required",
      assignedRole = "MA Team",
      source?: any
    ) => {
      if (!claimId) {
        throw new Error("Missing claim ID");
      }

      const sourceCase = normalizeCase(source, claimId);

      if (sourceCase?.case_id) {
        missingCaseIdsRef.current.delete(claimId);
        setCaseMap((prev) => ({ ...prev, [claimId]: sourceCase }));
        return sourceCase;
      }

      if (caseMap[claimId]?.case_id) {
        return caseMap[claimId];
      }

      const existing = await fetchCaseByClaim(claimId, { force: true });

      if (existing?.case_id) {
        return existing;
      }

      const response = await fetch(`${API_URL}/api/claims/${claimId}/hitl-case`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reason,
          assigned_role: assignedRole,
          assigned_team: assignedRole,
          created_by: "Claim Workspace",
        }),
      });

      const createdRaw = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(createdRaw.detail || createdRaw.message || "HITL case creation failed");
      }

      const created = normalizeCase(createdRaw.case || createdRaw, claimId) || createdRaw.case || createdRaw;
      const createdClaim = createdRaw.claim || created.claim || {};
      const createdPipeline = getResponsePipeline(createdRaw);

      missingCaseIdsRef.current.delete(claimId);
      setCaseMap((prev) => ({ ...prev, [claimId]: created }));

      mergeCaseUpdate(mergeItems, {
        ...createdClaim,
        claim_id: claimId,
        status: createdClaim.status || createdRaw.status || created.status || "HITL_REQUIRED",
        case: created,
        hitl_case: created,
        case_id: created.case_id,
        ...(hasKeys(createdPipeline) ? { pipeline: createdPipeline } : {}),
        review_required: true,
        approval_required: true,
        pipeline_paused: true,
        updatedAt: created.updated_at || createdRaw.updated_at || new Date().toISOString(),
      });

      return created;
    },
    [caseMap, fetchCaseByClaim, mergeItems]
  );

  const routeCase = useCallback(
    async (claimId: string, assignedRole: string, source?: any) => {
      const hitlCase = await ensureHitlCase(
        claimId,
        `Routed to ${assignedRole}`,
        assignedRole,
        source
      );

      const response = await fetch(`${API_URL}/cases/${hitlCase.case_id}/assign`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          assigned_role: assignedRole,
          assigned_team: assignedRole,
          assigned_to: "Queue Owner",
          assigned_by: "Claim Workspace",
          reason: "Inline workspace routing",
        }),
      });

      const updatedRaw = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(updatedRaw.detail || updatedRaw.message || "Case routing failed");
      }

      const updated = normalizeCase(updatedRaw.case || updatedRaw, claimId) || updatedRaw.case || updatedRaw;
      const updatedClaim = getResponseClaim(updatedRaw);
      const updatedPipeline = getResponsePipeline(updatedRaw);

      setCaseMap((prev) => ({ ...prev, [claimId]: updated }));

      mergeCaseUpdate(mergeItems, {
        ...updatedClaim,
        claim_id: claimId,
        case: updated,
        hitl_case: updated,
        case_id: updated.case_id,
        assigned_to: updated.assigned_to,
        assigned_role: updated.assigned_role,
        ...(hasKeys(updatedPipeline) ? { pipeline: updatedPipeline } : {}),
        review_required: true,
        approval_required: true,
        pipeline_paused: true,
        updatedAt: updatedClaim.updated_at || updated.updated_at || updatedRaw.updated_at || new Date().toISOString(),
      });

      setActionMessage?.(updatedRaw.message || `Routed to ${updated.assigned_role || assignedRole}.`);

      return updated;
    },
    [ensureHitlCase, mergeItems, setActionMessage]
  );

  const approveHitlCase = useCallback(
    async (claimId: string) => {
      setActionMessage?.("Approving HITL case and resuming submission...");

      const response = await fetch(`${API_URL}/api/case/${claimId}/approve?user_id=Claim%20Workspace`, {
        method: "POST",
      });

      const approval = await response.json().catch(() => ({}));

      if (!response.ok && !String(approval?.detail || "").toLowerCase().includes("already approved")) {
        throw new Error(approval?.detail || approval?.message || "Approval failed");
      }

      const resumed = approval.resumed || {};
      const nextClaim = approval.claim || resumed.claim || {};
      const nextPipeline = getResponsePipeline(approval);
      const nextCase = normalizeCase(approval.case || nextClaim.case || nextClaim.hitl_case, claimId);

      if (nextCase?.case_id) {
        setCaseMap((prev) => ({ ...prev, [claimId]: nextCase }));
      }

      mergeCaseUpdate(mergeItems, {
        ...nextClaim,
        claim_id: claimId,
        status:
          nextClaim.status ||
          resumed.status ||
          approval.pipeline_state ||
          approval.status ||
          "WAITING_FOR_APPROVAL",
        ...(hasKeys(nextPipeline) ? { pipeline: nextPipeline } : {}),
        case: nextCase,
        hitl_case: nextCase,
        case_id: nextCase?.case_id,
        review_required: false,
        approval_required: false,
        pipeline_paused: false,
        updatedAt: nextClaim.updated_at || approval.updated_at || new Date().toISOString(),
      });

      setActionMessage?.("HITL approved. Backend response merged.");

      return approval;
    },
    [mergeItems, setActionMessage]
  );

  const escalateHitlCase = useCallback(
    async (claimId: string, source?: any) => {
      const hitlCase = await ensureHitlCase(
        claimId,
        "Escalated from Claim Workspace",
        "MA Team",
        source
      );

      const response = await fetch(
        `${API_URL}/cases/${hitlCase.case_id}/escalate?reason=Claim%20Workspace%20escalation&actor=Claim%20Workspace`,
        { method: "POST" }
      );

      const updatedRaw = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(updatedRaw.detail || updatedRaw.message || "Case escalation failed");
      }

      const updated = normalizeCase(updatedRaw.case || updatedRaw, claimId) || updatedRaw.case || updatedRaw;
      const updatedClaim = getResponseClaim(updatedRaw);
      const updatedPipeline = getResponsePipeline(updatedRaw);

      setCaseMap((prev) => ({ ...prev, [claimId]: updated }));

      mergeCaseUpdate(mergeItems, {
        ...updatedClaim,
        claim_id: claimId,
        case: updated,
        hitl_case: updated,
        case_id: updated.case_id,
        escalation_level: updated.escalation_level,
        priority: updated.priority,
        ...(hasKeys(updatedPipeline) ? { pipeline: updatedPipeline } : {}),
        review_required: true,
        approval_required: true,
        pipeline_paused: true,
        updatedAt: updatedClaim.updated_at || updated.updated_at || updatedRaw.updated_at || new Date().toISOString(),
      });

      setActionMessage?.("Case escalated.");

      return updated;
    },
    [ensureHitlCase, mergeItems, setActionMessage]
  );

  return {
    caseMap,
    setCaseMap,
    fetchCaseByClaim,
    ensureHitlCase,
    routeCase,
    approveHitlCase,
    escalateHitlCase,
  };
};
