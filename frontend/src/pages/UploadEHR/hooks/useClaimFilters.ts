import { useMemo, useState } from "react";

import {
  getAmount,
  getClaimId,
  getCurrentAgent,
  getDos,
  getPatientName,
  getPayer,
  getReviewStatus,
  getUploadMode,
  getWorkspaceStatus,
} from "../utils";

import type { ProcessingMode } from "../utils/claimTypes";

export type ClaimTab =
  | "latest"
  | "all"
  | "bulk"
  | "single"
  | "live"
  | "review"
  | "rejected"
  | "completed";

type UseClaimFiltersOptions = {
  items: any[];
  processingMode: ProcessingMode;
  claimModeOverrides: Record<string, ProcessingMode>;
};

const normalizeStatus = (value: any) =>
  String(value || "")
    .trim()
    .toUpperCase()
    .replace(/[\s-]+/g, "_");

const safeText = (value: any) => {
  if (value === undefined || value === null) return "";
  return String(value).toLowerCase();
};

const getNestedPipeline = (item: any) =>
  item?.pipeline ||
  item?.payload?.pipeline ||
  item?.payload?.claim?.pipeline ||
  item?.claim?.pipeline ||
  {};

const getStage = (item: any) =>
  item?.stage ||
  item?.current_stage ||
  item?.payload?.stage ||
  item?.payload?.current_stage ||
  item?.payload?.claim?.stage ||
  item?.payload?.claim?.current_stage ||
  item?.claim?.stage ||
  item?.claim?.current_stage ||
  getNestedPipeline(item)?.current_stage ||
  getNestedPipeline(item)?.active_step;

const getPipelineState = (item: any) =>
  item?.pipeline_state ||
  item?.pipeline_status ||
  item?.payload?.pipeline_state ||
  item?.payload?.pipeline_status ||
  item?.payload?.claim?.pipeline_state ||
  item?.payload?.claim?.pipeline_status ||
  item?.claim?.pipeline_state ||
  item?.claim?.pipeline_status ||
  getNestedPipeline(item)?.pipeline_state ||
  getNestedPipeline(item)?.pipeline_status;

const getLastActivityAt = (item: any) =>
  item?.last_activity_at ||
  item?.lastActivityAt ||
  item?.updatedAt ||
  item?.updated_at ||
  item?.uploaded_at ||
  item?.created_at ||
  item?.timestamp ||
  item?.payload?.last_activity_at ||
  item?.payload?.updated_at ||
  item?.payload?.claim?.last_activity_at ||
  item?.payload?.claim?.updated_at ||
  item?.claim?.last_activity_at ||
  item?.claim?.updated_at;

const timestampOf = (item: any) => {
  const timestamp = new Date(getLastActivityAt(item) || 0).getTime();
  return Number.isFinite(timestamp) ? timestamp : 0;
};

const getClaimMode = (
  item: any,
  claimModeOverrides: Record<string, ProcessingMode>,
  defaultMode: ProcessingMode
): ProcessingMode => {
  const claimId = getClaimId(item);

  return (
    claimModeOverrides[claimId] ||
    item?.clearinghouse_processing_mode ||
    item?.processing_mode ||
    item?.payload?.clearinghouse_processing_mode ||
    item?.payload?.processing_mode ||
    item?.payload?.claim?.clearinghouse_processing_mode ||
    item?.payload?.claim?.processing_mode ||
    item?.claim?.clearinghouse_processing_mode ||
    item?.claim?.processing_mode ||
    defaultMode
  );
};

const isValidWorkspaceClaim = (item: any) => {
  const claimId = getClaimId(item);

  if (!claimId) return false;

  // Keep real claim records and ignore temporary upload/session rows.
  return String(claimId).startsWith("CLM-") || String(claimId).startsWith("uploads-");
};

const isLatestUpload = (item: any) => {
  return Boolean(
    item?.is_new_upload ||
      item?.payload?.is_new_upload ||
      item?.claim?.is_new_upload ||
      item?.payload?.claim?.is_new_upload
  );
};

const isClearinghouseWaitingClaim = (item: any) => {
  const status = normalizeStatus(getWorkspaceStatus(item));
  const stage = normalizeStatus(getStage(item));
  const pipelineState = normalizeStatus(getPipelineState(item));

  return (
    stage === "CLEARINGHOUSE" &&
    (status === "WAITING_FOR_APPROVAL" ||
      status === "PENDING_CLEARINGHOUSE" ||
      pipelineState === "WAITING_FOR_APPROVAL" ||
      pipelineState === "PENDING_CLEARINGHOUSE")
  );
};

const isLiveClaim = (item: any) => {
  const status = normalizeStatus(getWorkspaceStatus(item));
  const stage = normalizeStatus(getStage(item));
  const pipelineState = normalizeStatus(getPipelineState(item));

  if (isCompletedClaim(item) || isDeniedClaim(item)) return false;

  return (
    isClearinghouseWaitingClaim(item) ||
    [
      "PROCESSING",
      "RUNNING",
      "ACTIVE",
      "QUEUED",
      "PENDING",
      "AUTO_APPROVED",
      "VALIDATION_REQUIRED",
      "OCR_COMPLETED",
      "VALIDATION_COMPLETED",
      "COMPLIANCE_COMPLETED",
      "SUBMISSION_COMPLETED",
    ].includes(status) ||
    [
      "PROCESSING",
      "RUNNING",
      "ACTIVE",
      "QUEUED",
      "PENDING",
      "WAITING_FOR_APPROVAL",
    ].includes(pipelineState) ||
    [
      "EXTRACTION",
      "EXTRACT",
      "OCR",
      "ELIGIBILITY",
      "VALIDATION",
      "COMPLIANCE",
      "SUBMISSION",
      "CLEARINGHOUSE",
      "ACKNOWLEDGMENT",
      "PAYER",
      "DENIAL_AI",
      "PAYMENT",
      "LEARNING",
      "ANALYTICS",
    ].includes(stage)
  );
};

const isReviewClaim = (item: any) => {
  const status = normalizeStatus(getWorkspaceStatus(item));
  const stage = normalizeStatus(getStage(item));
  const pipelineState = normalizeStatus(getPipelineState(item));

  return (
    isClearinghouseWaitingClaim(item) ||
    [
      "HITL_REQUIRED",
      "HUMAN_REVIEW_REQUIRED",
      "MANUAL_REVIEW_REQUIRED",
      "WAITING_FOR_REVIEW",
      "NEEDS_REVIEW",
      "HUMAN_REVIEW",
      "WAITING_FOR_APPROVAL",
      "PENDING_APPROVAL",
      "PENDING_CLEARINGHOUSE",
    ].includes(status) ||
    ["HUMAN_REVIEW", "MANUAL_REVIEW"].includes(stage) ||
    ["WAITING_FOR_APPROVAL", "PENDING_APPROVAL"].includes(pipelineState)
  );
};

const isDeniedClaim = (item: any) => {
  const status = normalizeStatus(getWorkspaceStatus(item));

  return [
    "HARD_REJECT",
    "HARD_REJECTED",
    "REJECTED",
    "DENIED",
    "FAILED",
    "ERROR",
  ].includes(status);
};

const isCompletedClaim = (item: any) => {
  const status = normalizeStatus(getWorkspaceStatus(item));
  const stage = normalizeStatus(getStage(item));
  const pipelineState = normalizeStatus(getPipelineState(item));

  // Manual clearinghouse waiting is not completed, even if one event says COMPLETED.
  if (isClearinghouseWaitingClaim(item)) return false;

  return (
    [
      "PAID",
      "COMPLETED",
      "COMMAND_CENTER",
      "ACCEPTED",
      "LEARNING_COMPLETED",
      "VALIDATION_COMPLETED",
      "COMPLIANCE_COMPLETED",
      "ANALYTICS_COMPLETED",
    ].includes(status) ||
    ["FINISH", "COMPLETED"].includes(stage) ||
    ["COMPLETED", "PAID", "SUCCESS"].includes(pipelineState)
  );
};

const matchesSearch = (item: any, search: string) => {
  const query = search.trim().toLowerCase();

  if (!query) return true;

  const values = [
    getClaimId(item),
    getPatientName(item),
    getPayer(item),
    getDos(item),
    getAmount(item),
    getWorkspaceStatus(item),
    getCurrentAgent(item),
    item?.member_id,
    item?.patient?.member_id,
    item?.insurance?.member_id,
    item?.provider?.name,
    item?.provider_name,
    item?.provider?.npi,
    item?.provider_npi,
    item?.payload?.claim?.patient?.name,
    item?.payload?.claim?.payer?.name,
    item?.payload?.claim?.provider?.name,
    item?.payload?.claim?.provider?.npi,
  ];

  return values.some((value) => safeText(value).includes(query));
};

const getRiskValue = (item: any) => {
  const raw =
    item?.risk_score ??
    item?.denial_probability ??
    item?.payload?.risk_score ??
    item?.payload?.claim?.risk_score ??
    item?.claim?.risk_score ??
    item?.analytics?.risk_score ??
    item?.denial_ai?.risk_score;

  const value = Number(raw);

  if (!Number.isFinite(value)) return null;

  return value <= 1 && value > 0 ? value * 100 : value;
};

const matchesRiskFilter = (item: any, riskFilter: string) => {
  if (!riskFilter || riskFilter === "all") return true;

  const risk = getRiskValue(item);

  if (risk === null) return riskFilter === "not_reported";

  if (riskFilter === "low") return risk < 35;
  if (riskFilter === "medium") return risk >= 35 && risk < 70;
  if (riskFilter === "high") return risk >= 70;

  return true;
};

const matchesDateFilter = (item: any, dateFilter: string) => {
  if (!dateFilter || dateFilter === "any") return true;

  const timestamp = timestampOf(item);

  if (!timestamp) return false;

  const now = Date.now();
  const ageMs = now - timestamp;
  const dayMs = 24 * 60 * 60 * 1000;

  if (dateFilter === "today") return ageMs <= dayMs;
  if (dateFilter === "7d") return ageMs <= 7 * dayMs;
  if (dateFilter === "30d") return ageMs <= 30 * dayMs;

  return true;
};

const matchesValidationFilter = (item: any, validationFilter: string) => {
  if (!validationFilter || validationFilter === "any") return true;

  const validationStatus = normalizeStatus(
    item?.validation_status ||
      item?.validation?.status ||
      item?.payload?.validation_status ||
      item?.payload?.claim?.validation_status ||
      item?.claim?.validation_status
  );

  const score = Number(
    item?.validation_score ??
      item?.validation?.validation_score ??
      item?.payload?.validation_score ??
      item?.payload?.claim?.validation_score ??
      item?.claim?.validation_score
  );

  if (validationFilter === "passed") {
    return validationStatus.includes("PASS") || score >= 80;
  }

  if (validationFilter === "failed") {
    return validationStatus.includes("FAIL") || validationStatus.includes("ERROR");
  }

  if (validationFilter === "warning") {
    return validationStatus.includes("WARN") || (Number.isFinite(score) && score > 0 && score < 80);
  }

  return true;
};

const matchesModeFilter = (
  item: any,
  modeFilter: string,
  claimModeOverrides: Record<string, ProcessingMode>,
  processingMode: ProcessingMode
) => {
  if (!modeFilter || modeFilter === "all") return true;

  const mode = normalizeStatus(getClaimMode(item, claimModeOverrides, processingMode));

  return mode === normalizeStatus(modeFilter);
};

const matchesReviewFilter = (
  item: any,
  reviewFilter: string,
  claimModeOverrides: Record<string, ProcessingMode>,
  processingMode: ProcessingMode
) => {
  if (!reviewFilter || reviewFilter === "all") return true;

  const mode = getClaimMode(item, claimModeOverrides, processingMode);
  const reviewStatus = normalizeStatus(getReviewStatus(item, mode));

  if (reviewFilter === "needs_review") {
    return (
      isReviewClaim(item) ||
      reviewStatus.includes("NEEDS") ||
      reviewStatus.includes("WAITING") ||
      reviewStatus.includes("REVIEW")
    );
  }

  if (reviewFilter === "approved") {
    return reviewStatus.includes("APPROVED");
  }

  if (reviewFilter === "rejected") {
    return isDeniedClaim(item) || reviewStatus.includes("REJECT");
  }

  return true;
};

const uniqueSorted = (values: string[]) =>
  Array.from(new Set(values.filter(Boolean))).sort((a, b) => a.localeCompare(b));

export const useClaimFilters = ({
  items,
  processingMode,
  claimModeOverrides,
}: UseClaimFiltersOptions) => {
  const [activeTab, setActiveTab] = useState<ClaimTab>("all");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [riskFilter, setRiskFilter] = useState("all");
  const [uploadTypeFilter, setUploadTypeFilter] = useState("all");
  const [payerFilter, setPayerFilter] = useState("all");
  const [agentFilter, setAgentFilter] = useState("all");
  const [dateFilter, setDateFilter] = useState("any");
  const [validationFilter, setValidationFilter] = useState("any");
  const [modeFilter, setModeFilter] = useState("all");
  const [reviewFilter, setReviewFilter] = useState("all");
  const [latestFilter, setLatestFilter] = useState("all");

  const workspaceItems = useMemo(() => {
    return items
      .filter(isValidWorkspaceClaim)
      .map((item) => {
        if (isClearinghouseWaitingClaim(item)) {
          return {
            ...item,
            status: "WAITING_FOR_APPROVAL",
            stage: "CLEARINGHOUSE",
            current_stage: "CLEARINGHOUSE",
            current_agent: "CLEARINGHOUSE",
            active_step: "clearinghouse",
            pipeline_state: "WAITING_FOR_APPROVAL",
            pipeline_status: "WAITING_FOR_APPROVAL",
            review_required: true,
            approval_required: true,
            progress: item?.progress ?? item?.pipeline?.progress ?? 70,
          };
        }

        return item;
      });
  }, [items]);

  const completedItems = useMemo(() => {
    return workspaceItems.filter(isCompletedClaim);
  }, [workspaceItems]);

  const payerOptions = useMemo(() => {
    return uniqueSorted(workspaceItems.map((item) => String(getPayer(item) || "")));
  }, [workspaceItems]);

  const agentOptions = useMemo(() => {
    return uniqueSorted(
      workspaceItems.map((item) => String(getCurrentAgent(item) || item?.current_agent || ""))
    );
  }, [workspaceItems]);

  const tabCounts = useMemo(() => {
    return workspaceItems.reduce(
      (acc, item) => {
        const mode = getUploadMode(item);

        acc.all += 1;

        if (isLatestUpload(item)) acc.latest += 1;
        if (mode === "bulk") acc.bulk += 1;
        if (mode === "single") acc.single += 1;
        if (isLiveClaim(item)) acc.live += 1;
        if (isReviewClaim(item)) acc.review += 1;
        if (isDeniedClaim(item)) acc.rejected += 1;
        if (isCompletedClaim(item)) acc.completed += 1;

        return acc;
      },
      {
        latest: 0,
        all: 0,
        bulk: 0,
        single: 0,
        live: 0,
        review: 0,
        rejected: 0,
        completed: 0,
      } as Record<ClaimTab, number>
    );
  }, [workspaceItems]);

  const renderedItems = useMemo(() => {
    return workspaceItems
      .filter((item) => {
        const activeTabMatches = (() => {
          if (activeTab === "all") return true;
          if (activeTab === "latest") return isLatestUpload(item);
          if (activeTab === "bulk") return getUploadMode(item) === "bulk";
          if (activeTab === "single") return getUploadMode(item) === "single";
          if (activeTab === "live") return isLiveClaim(item);
          if (activeTab === "review") return isReviewClaim(item);
          if (activeTab === "rejected") return isDeniedClaim(item);
          if (activeTab === "completed") return isCompletedClaim(item);

          return true;
        })();

        if (!activeTabMatches) return false;

        if (!matchesSearch(item, search)) return false;
        if (!matchesRiskFilter(item, riskFilter)) return false;
        if (!matchesDateFilter(item, dateFilter)) return false;
        if (!matchesValidationFilter(item, validationFilter)) return false;

        if (!matchesModeFilter(item, modeFilter, claimModeOverrides, processingMode)) {
          return false;
        }

        if (!matchesReviewFilter(item, reviewFilter, claimModeOverrides, processingMode)) {
          return false;
        }

        if (filter !== "all") {
          const status = normalizeStatus(getWorkspaceStatus(item));
          if (status !== normalizeStatus(filter)) return false;
        }

        if (uploadTypeFilter !== "all") {
          if (getUploadMode(item) !== uploadTypeFilter) return false;
        }

        if (payerFilter !== "all") {
          if (String(getPayer(item) || "") !== payerFilter) return false;
        }

        if (agentFilter !== "all") {
          const agent = String(getCurrentAgent(item) || item?.current_agent || "");
          if (agent !== agentFilter) return false;
        }

        if (latestFilter === "latest" && !isLatestUpload(item)) return false;
        if (latestFilter === "older" && isLatestUpload(item)) return false;

        return true;
      })
      .sort((a, b) => timestampOf(b) - timestampOf(a));
  }, [
    workspaceItems,
    activeTab,
    search,
    riskFilter,
    dateFilter,
    validationFilter,
    modeFilter,
    reviewFilter,
    filter,
    uploadTypeFilter,
    payerFilter,
    agentFilter,
    latestFilter,
    claimModeOverrides,
    processingMode,
  ]);

  return {
    activeTab,
    setActiveTab,

    search,
    setSearch,

    filter,
    setFilter,

    riskFilter,
    setRiskFilter,

    uploadTypeFilter,
    setUploadTypeFilter,

    payerFilter,
    setPayerFilter,

    agentFilter,
    setAgentFilter,

    dateFilter,
    setDateFilter,

    validationFilter,
    setValidationFilter,

    modeFilter,
    setModeFilter,

    reviewFilter,
    setReviewFilter,

    latestFilter,
    setLatestFilter,

    workspaceItems,
    completedItems,
    renderedItems,
    tabCounts,
    payerOptions,
    agentOptions,

    isLatestUpload,
    isLiveClaim,
    isReviewClaim,
    isDeniedClaim,
    isCompletedClaim,
    isClearinghouseWaitingClaim,
  };
};