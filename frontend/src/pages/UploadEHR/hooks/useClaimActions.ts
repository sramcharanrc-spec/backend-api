import { useCallback, useState } from "react";
import { API_URL } from "../../../config";
import { fetchClaimWithFallback } from "../services";
import { mergePipeline } from "../utils";

type UseClaimActionsOptions = {
  items: any[];
  setItems: React.Dispatch<React.SetStateAction<any[]>>;
  mergeItems?: (claims: any[]) => void;
  removeClaim?: (claimId: string) => void;
  refreshClaims?: () => Promise<any[]>;
};

const getClaimId = (item: any) =>
  item?.claim_id ||
  item?.id ||
  item?.claimId ||
  item?.payload?.claim_id ||
  item?.payload?.claim?.claim_id ||
  item?.claim?.claim_id;

const unwrapClaim = (data: any) => data?.claim || data?.payload?.claim || data?.payload || data || {};

const unwrapPipeline = (data: any) =>
  data?.pipeline ||
  data?.payload?.pipeline ||
  data?.claim?.pipeline ||
  data?.payload?.claim?.pipeline ||
  {
    current_stage: data?.current_stage || data?.stage,
    current_agent: data?.current_agent || data?.agent,
    active_step: data?.active_step || data?.current_step,
    pipeline_state: data?.pipeline_state,
    pipeline_status: data?.pipeline_status || data?.status,
    progress: data?.progress,
    steps: data?.pipeline_steps,
  };

export const useClaimActions = ({
  items,
  setItems,
  mergeItems,
  removeClaim,
}: UseClaimActionsOptions) => {
  const [expandedRow, setExpandedRow] = useState<string | null>(null);
  const [editData, setEditData] = useState<any>({});
  const [pipelineData, setPipelineData] = useState<Record<string, any>>({});
  const [profileOpen, setProfileOpen] = useState<string | null>(null);
  const [profileData, setProfileData] = useState<any>(null);
  const [deleteTarget, setDeleteTarget] = useState<any | null>(null);
  const [deletingClaim, setDeletingClaim] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState("");

const handleViewClaim = useCallback(
  async (claimId: string) => {
    setExpandedRow((prev) => (prev === claimId ? null : claimId));

    try {
      const claimData = await fetchClaimWithFallback(claimId);

      if (!claimData) {
        return;
      }

      const claim = unwrapClaim(claimData);
      const pipeline = unwrapPipeline(claimData || {});

      const mergedPipeline = mergePipeline(
        { pipeline: pipelineData?.[claimId] || {} },
        { pipeline }
      );

      setEditData(claim);

      setPipelineData((prev) => ({
        ...prev,
        [claimId]: mergePipeline(
          { pipeline: prev?.[claimId] || {} },
          { pipeline: mergedPipeline }
        ),
      }));

      mergeItems?.([
        {
          ...claim,
          claim_id: claimId,

          status:
            claim?.status ||
            claimData?.status ||
            mergedPipeline?.overall_status ||
            mergedPipeline?.status ||
            mergedPipeline?.pipeline_status ||
            mergedPipeline?.pipeline_state,

          current_stage:
            claim?.current_stage ||
            claimData?.current_stage ||
            mergedPipeline?.current_stage ||
            mergedPipeline?.stage ||
            mergedPipeline?.active_step,

          current_agent:
            claim?.current_agent ||
            claimData?.current_agent ||
            mergedPipeline?.current_agent ||
            mergedPipeline?.agent,

          active_step:
            claim?.active_step ||
            claimData?.active_step ||
            mergedPipeline?.active_step ||
            mergedPipeline?.workflow_state,

          progress:
            claim?.progress ??
            claimData?.progress ??
            mergedPipeline?.progress,

          pipeline_state:
            claim?.pipeline_state ||
            claimData?.pipeline_state ||
            mergedPipeline?.pipeline_state,

          pipeline_status:
            claim?.pipeline_status ||
            claimData?.pipeline_status ||
            mergedPipeline?.pipeline_status,

          review_required:
            claim?.review_required ??
            claimData?.review_required ??
            mergedPipeline?.review_required,

          approval_required:
            claim?.approval_required ??
            claimData?.approval_required ??
            mergedPipeline?.approval_required,

          pipeline_paused:
            claim?.pipeline_paused ??
            claimData?.pipeline_paused ??
            mergedPipeline?.pipeline_paused,

          pipeline: mergedPipeline,

          claim: {
            ...claim,
            pipeline: mergedPipeline,
          },

          updatedAt:
            claimData?.updatedAt ||
            claimData?.updated_at ||
            new Date().toISOString(),
        },
      ]);
    } catch (error) {
      console.error("[claim-actions] view failed", error);
    }
  },
  [mergeItems, pipelineData]
);

  const openClaimProfile = useCallback(async (claimId: string) => {
    setProfileOpen(claimId);
    setProfileData(null);

    try {
      const claimData = await fetchClaimWithFallback(claimId);

      setProfileData({
        claim: claimData || { claim_id: claimId },
        pipeline: unwrapPipeline(claimData || {}),
      });
    } catch (error) {
      console.error("[claim-actions] profile fallback fetch failed", error);
      setProfileData({
        claim: { claim_id: claimId },
        pipeline: {},
      });
    }
  }, []);

  const handleDeleteRequest = useCallback((item: any) => {
    setDeleteTarget(item);
  }, []);

  const handleDeleteClaim = useCallback(async () => {
    if (!deleteTarget) return;

    const claimId = getClaimId(deleteTarget);

    if (!claimId) return;

    const previousItems = items;

    setDeletingClaim(claimId);
    removeClaim?.(claimId);

    if (!removeClaim) {
      setItems((prev) => prev.filter((item) => getClaimId(item) !== claimId));
    }

    try {
      const user = JSON.parse(localStorage.getItem("user") || "{}");
      const role = user.role || user.user_role || "Admin";

      const response = await fetch(`${API_URL}/api/claims/${claimId}`, {
        method: "DELETE",
        headers: {
          "Content-Type": "application/json",
          "x-user-role": role,
          "x-user-email": user.email || "admin@company.com",
        },
      });

      const result = await response.json().catch(() => ({}));

      if (response.status === 404) {
        setActionMessage("Claim was already removed.");
        setDeleteTarget(null);
        return;
      }

      if (!response.ok) {
        throw new Error(result.detail || result.message || "Claim delete failed");
      }

      setActionMessage("Claim deleted successfully.");
      setDeleteTarget(null);
    } catch (error: any) {
      setItems(previousItems);
      setActionMessage(error?.message || "Claim delete failed.");
    } finally {
      setDeletingClaim(null);
    }
  }, [deleteTarget, items, removeClaim, setItems]);

  return {
    expandedRow,
    setExpandedRow,
    editData,
    setEditData,
    pipelineData,
    setPipelineData,
    profileOpen,
    setProfileOpen,
    profileData,
    setProfileData,
    deleteTarget,
    setDeleteTarget,
    deletingClaim,
    actionMessage,
    setActionMessage,
    handleViewClaim,
    openClaimProfile,
    handleDeleteRequest,
    handleDeleteClaim,
  };
};
