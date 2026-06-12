import React, { useCallback, useMemo, useState } from "react";
import {
  AlertTriangle,
  Bell,
  CircleDollarSign,
  ClipboardCheck,
  FileCheck2,
  RefreshCw,
  Send,
  UploadCloud,
  User,
} from "lucide-react";

import DashboardCards from "./DashboardCards";
import ClaimTabs from "./ClaimTabs";
import ClaimFilters from "./ClaimFilters";
import FormPreviewModal from "./FormPreviewModal";
import ToastStack from "./ToastStack";
import DeleteClaimModal from "./DeleteClaimModal";
import ClaimProfileDrawer from "./ClaimProfileDrawer";
import ExpandedClaimWorkspace from "./ExpandedClaimWorkspace";
import RealtimeSyncManager from "./RealtimeSyncManager";
import {
  useClaimRecords,
  useClaimUpload,
  useClaimRealtimeSync,
  useClaimFilters,
  useClaimActions,
  useFormPreview,
  useHitlCases,
} from "../hooks";

import {
  getClaimId,
  getPatientName,
  getPayer,
  getDos,
  getAmount,
  getCurrentAgent,
  getSupportedForms,
  getBackendProcessingMode,
  getReviewStatus,
  getWorkspaceStatus,
  isCompletedWorkspaceClaim,
  displayStatus,
  mergePipeline,
} from "../utils";

import {
  approveClearinghouseClaim,
  rejectClaim,
  retryClaimValidation,
  updateClearinghouseMode,
  runClearinghouseAutoReview,
} from "../services";

import {
  HitlCasePanel
} from "./";

import type { ProcessingMode } from "../utils/claimTypes";
import { calculateTrend, getClaimTrendPeriods } from "../../../utils/kpiTrends";

type UploadEHRContainerProps = {
  onUpload?: (data: any) => void;
};

type ToastMessage = {
  id: string;
  tone: "success" | "info" | "warning";
  title: string;
  message: string;
};

const money = (value: number) =>
  value
    ? `$${value.toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })}`
    : "-";

let toastSequence = 0;

const createToastId = () => {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return `toast-${crypto.randomUUID()}`;
  }

  toastSequence += 1;
  return `toast-${Date.now()}-${toastSequence}`;
};

const getPipelineProgress = (item: any) => {
  const raw =
    item?.progress ??
    item?.payload?.progress ??
    item?.payload?.claim?.progress ??
    item?.pipeline?.progress;

  const progress = Number(raw);

  if (!Number.isFinite(progress)) {
    if (isCompletedWorkspaceClaim(item)) return 100;
    return null;
  }

  return Math.min(100, Math.max(0, Math.round(progress)));
};

const UploadEHRContainer: React.FC<UploadEHRContainerProps> = ({ onUpload }) => {
  const [processingMode, setProcessingMode] = useState<ProcessingMode>("MANUAL");
  const [claimModeOverrides, setClaimModeOverrides] = useState<Record<string, ProcessingMode>>({});
  const [highlightedClaims, setHighlightedClaims] = useState<Set<string>>(() => new Set());
  const [toastMessages, setToastMessages] = useState<ToastMessage[]>([]);

  const pushToast = useCallback((toast: Omit<ToastMessage, "id">) => {
    const id = createToastId();

    setToastMessages((prev) => [...prev.slice(-3), { id, ...toast }]);

    window.setTimeout(() => {
      setToastMessages((prev) => prev.filter((entry) => entry.id !== id));
    }, 6500);
  }, []);

  const records = useClaimRecords({
    autoLoad: true,
    page: 1,
    limit: 200,
  });

  const markClaimAsNew = useCallback(
    (claimId: string) => {
      if (!claimId) return;

      setHighlightedClaims((prev) => new Set(prev).add(claimId));

      window.setTimeout(() => {
        setHighlightedClaims((prev) => {
          const next = new Set(prev);
          next.delete(claimId);
          return next;
        });
      }, 30000);

      pushToast({
        tone: "success",
        title: "New claim received",
        message: claimId,
      });
    },
    [pushToast]
  );

  const upload = useClaimUpload({
    processingMode,
    onUpload,
    refreshClaims: records.refreshClaims,
    mergeItems: records.mergeItems,
    markClaimAsNew,
  });

  const realtime = useClaimRealtimeSync({
    mergeItems: records.mergeItems,
    onCompleted: (claimId) => {
      records.refreshClaims();

      pushToast({
        tone: "success",
        title: "Claim completed",
        message: claimId,
      });
    },
  });

  const filters = useClaimFilters({
    items: records.items,
    processingMode,
    claimModeOverrides,
  });
  
  const visibleProcessingClaims = useMemo(() => {
    return records.items
      .filter((item: any) => {
        const status = String(
          item?.pipeline_state ||
            item?.pipeline_status ||
            item?.status ||
            ""
        )
          .toUpperCase()
          .replace(/\s+/g, "_");

        const stage = String(
          item?.current_stage ||
            item?.stage ||
            item?.active_step ||
            ""
        )
          .toUpperCase()
          .replace(/\s+/g, "_");

      return (
        status.includes("RUNNING") ||
        status.includes("PROCESSING") ||
        status === "WAITING_FOR_APPROVAL" ||
        status === "PENDING_CLEARINGHOUSE" ||
        status === "PENDING_APPROVAL" ||
        stage === "CLEARINGHOUSE" ||
        stage === "ACKNOWLEDGMENT" ||
        stage === "PAYER_ACKNOWLEDGMENT" ||
        stage === "PAYER"
      );
      })
      .map((item: any) => ({
        stage:
          item?.current_stage ||
          item?.stage ||
          item?.active_step ||
          "Starting",
        status:
          item?.pipeline_state ||
          item?.pipeline_status ||
          item?.status ||
          "Processing",
        progress:
          getPipelineProgress(item) ??
          item?.progress ??
          item?.pipeline?.progress ??
          10,
        current_stage: item?.current_stage,
        current_agent: item?.current_agent,
        active_step: item?.active_step,
        pipeline_state: item?.pipeline_state,
        pipeline_status: item?.pipeline_status,
        review_required: item?.review_required,
        approval_required: item?.approval_required,
        pipeline_paused: item?.pipeline_paused,
      }));
  }, [records.items]);

  const actions = useClaimActions({
    items: records.items,
    setItems: records.setItems,
    mergeItems: records.mergeItems,
    removeClaim: records.removeClaim,
    refreshClaims: records.refreshClaims,
  });

  const forms = useFormPreview();

  const hitl = useHitlCases({
    mergeItems: records.mergeItems,
    setActionMessage: actions.setActionMessage,
  });

  const workspaceMetrics = useMemo(() => {
    const workspaceItems = filters.workspaceItems;
    const totalRevenue = workspaceItems.reduce((sum, item) => sum + getAmount(item), 0);
    const { currentWeekClaims, previousWeekClaims } = getClaimTrendPeriods(workspaceItems);

    const countPeriodBy = (claims: any[], predicate: (item: any) => boolean) =>
      claims.filter(predicate).length;

    const currentRevenue = currentWeekClaims.reduce((sum, item) => sum + getAmount(item), 0);
    const previousRevenue = previousWeekClaims.reduce((sum, item) => sum + getAmount(item), 0);

    const isInProgress = (item: any) => {
      const status = getWorkspaceStatus(item);
      return ["PROCESSING", "ACTIVE", "RUNNING", "QUEUED", "PENDING"].includes(status);
    };

    const isPendingReview = (item: any) => {
      const status = getWorkspaceStatus(item);
      return [
        "HITL_REQUIRED",
        "HUMAN_REVIEW_REQUIRED",
        "MANUAL_REVIEW_REQUIRED",
        "WAITING_FOR_REVIEW",
        "NEEDS_REVIEW",
        "HUMAN_REVIEW",
        "WAITING_FOR_APPROVAL",
      ].includes(status);
    };

    const isDenied = (item: any) => {
      const status = getWorkspaceStatus(item);
      return ["DENIED", "REJECTED", "HARD_REJECT", "FAILED", "ERROR"].includes(status);
    };

    const isPaid = (item: any) => {
      const status = getWorkspaceStatus(item);
      const paymentStatus = String(item?.payment_status || item?.payment?.status || "").toUpperCase();

      return (
        ["PAID", "COMPLETED", "COMMAND_CENTER"].includes(status) ||
        paymentStatus === "PAID"
      );
    };

    return [
      {
        label: "Total Claims",
        value: workspaceItems.length,
        trend: calculateTrend(currentWeekClaims.length, previousWeekClaims.length),
        icon: FileCheck2,
        tone: "blue",
      },
      {
        label: "In Progress",
        value: workspaceItems.filter(isInProgress).length,
        trend: calculateTrend(
          countPeriodBy(currentWeekClaims, isInProgress),
          countPeriodBy(previousWeekClaims, isInProgress)
        ),
        icon: User,
        tone: "orange",
      },
      {
        label: "Pending Review",
        value: workspaceItems.filter(isPendingReview).length,
        trend: calculateTrend(
          countPeriodBy(currentWeekClaims, isPendingReview),
          countPeriodBy(previousWeekClaims, isPendingReview)
        ),
        icon: ClipboardCheck,
        tone: "purple",
      },
      {
        label: "Denied",
        value: workspaceItems.filter(isDenied).length,
        trend: calculateTrend(
          countPeriodBy(currentWeekClaims, isDenied),
          countPeriodBy(previousWeekClaims, isDenied)
        ),
        icon: AlertTriangle,
        tone: "red",
      },
      {
        label: "Paid",
        value: workspaceItems.filter(isPaid).length,
        trend: calculateTrend(
          countPeriodBy(currentWeekClaims, isPaid),
          countPeriodBy(previousWeekClaims, isPaid)
        ),
        icon: Send,
        tone: "green",
      },
      {
        label: "Total Claim Amount",
        value: totalRevenue ? `$${totalRevenue.toLocaleString()}` : "-",
        trend: calculateTrend(currentRevenue, previousRevenue),
        icon: CircleDollarSign,
        tone: "emerald",
      },
    ];
  }, [filters.workspaceItems]);

  const handleProcessingModeChange = useCallback(
    async (mode: ProcessingMode) => {
      setProcessingMode(mode);

      pushToast({
        tone: "info",
        title: "Processing mode changed",
        message: `Default clearinghouse mode is now ${mode}.`,
      });
    },
    [pushToast]
  );

  const handleClaimModeChange = useCallback(
    async (claimId: string, mode: ProcessingMode) => {
      setClaimModeOverrides((prev) => ({
        ...prev,
        [claimId]: mode,
      }));

      try {
        const data = await updateClearinghouseMode(claimId, mode);

        records.mergeItems([
          {
            ...(data.claim || data),
            claim_id: claimId,
            clearinghouse_processing_mode: mode,
            processing_mode: mode,
            updatedAt: new Date().toISOString(),
          },
        ]);

        pushToast({
          tone: "success",
          title: "Claim mode updated",
          message: `${claimId} set to ${mode}.`,
        });
      } catch (error: any) {
        pushToast({
          tone: "warning",
          title: "Mode update failed",
          message: error?.message || "Could not update processing mode.",
        });
      }
    },
    [pushToast, records]
  );
  const handleAcceptClearinghouse = useCallback(
    async (claimId: string) => {
      try {
        actions.setActionMessage("Accepting clearinghouse approval...");

        const data = await approveClearinghouseClaim(claimId);

        const nextClaim =
          data.resumed?.claim ||
          data.claim ||
          data.queued?.claim ||
          data.queued ||
          data;

        const nextPipeline =
          data.resumed?.pipeline ||
          data.pipeline ||
          data.queued?.pipeline ||
          nextClaim?.pipeline ||
          {};

        const rawStatus =
          data.resumed?.status ||
          data.status ||
          nextClaim?.status ||
          "PROCESSING";

        const nextStatus = [
          "WAITING_FOR_APPROVAL",
          "PENDING_CLEARINGHOUSE",
          "PENDING_APPROVAL",
        ].includes(String(rawStatus || "").toUpperCase())
          ? "PROCESSING"
          : rawStatus;

        const nextStage =
          data.resumed?.current_stage ||
          nextPipeline?.current_stage ||
          data.current_stage ||
          nextClaim?.current_stage ||
          nextClaim?.stage ||
          "ACKNOWLEDGMENT";

        const nextAgent =
          nextPipeline?.current_agent ||
          data.current_agent ||
          nextClaim?.current_agent ||
          "PAYER_ACKNOWLEDGMENT";

        const nextProgress =
          data.progress ??
          nextClaim?.progress ??
          nextPipeline?.progress ??
          74;

        const mergedClaim = {
          ...nextClaim,
          claim_id: claimId,
          status: nextStatus,
          stage: nextStage,
          current_stage: nextStage,
          current_agent: nextAgent,
          active_step:
            data.active_step ||
            nextClaim?.active_step ||
            nextPipeline?.active_step ||
            String(nextStage || "acknowledgment").toLowerCase(),
          pipeline_state:
            data.pipeline_state ||
            nextClaim?.pipeline_state ||
            nextPipeline?.pipeline_state ||
            "PIPELINE_RESUMED",
          pipeline_status:
            data.pipeline_status ||
            nextClaim?.pipeline_status ||
            nextPipeline?.pipeline_status ||
            "RUNNING",
          progress: nextProgress,
          pipeline: nextPipeline,
          approval_required: false,
          review_required: false,
          pipeline_paused: false,
          clearinghouse_accepted: true,
          clearinghouse_approved: true,
          updatedAt: new Date().toISOString(),
        };

        records.mergeItems([mergedClaim]);

        actions.setPipelineData((prev) => ({
          ...prev,
          [claimId]: mergePipeline({ pipeline: prev[claimId] }, { pipeline: nextPipeline }),
        }));

        actions.setActionMessage("Clearinghouse accepted. Pipeline resumed.");

        pushToast({
          tone: "success",
          title: "Clearinghouse accepted",
          message: `${claimId} resumed to next pipeline stage.`,
        });

        // Important: backend continuation runs async after accept.
        // These refreshes pull the latest DB state without manual browser refresh.
        window.setTimeout(() => records.refreshClaims(), 500);
        window.setTimeout(() => records.refreshClaims(), 1500);
        window.setTimeout(() => records.refreshClaims(), 3000);
        window.setTimeout(() => records.refreshClaims(), 6000);
      } catch (error: any) {
        actions.setActionMessage(error?.message || "Clearinghouse accept failed.");

        pushToast({
          tone: "warning",
          title: "Clearinghouse accept failed",
          message: error?.message || "Could not accept clearinghouse approval.",
        });
      }
    },
    [actions, pushToast, records]
  );
    
    const handleApprove = useCallback(
    async (claimId: string) => {
      try {
        actions.setActionMessage("Approving claim...");

        const data = await approveClearinghouseClaim(claimId);

        const nextClaim =
          data.resumed?.claim ||
          data.claim ||
          data.queued?.claim ||
          data.queued ||
          data;

        const nextPipeline =
          data.resumed?.pipeline ||
          data.pipeline ||
          data.queued?.pipeline ||
          nextClaim?.pipeline ||
          {};

        const nextStage =
          data.resumed?.current_stage ||
          nextPipeline?.current_stage ||
          data.current_stage ||
          nextClaim?.current_stage ||
          nextClaim?.stage ||
          "ACKNOWLEDGMENT";

        const nextAgent =
          nextPipeline?.current_agent ||
          data.current_agent ||
          nextClaim?.current_agent ||
          "PAYER_ACKNOWLEDGMENT";

        records.mergeItems([
          {
            ...nextClaim,
            claim_id: claimId,
            status: "PROCESSING",
            stage: nextStage,
            current_stage: nextStage,
            current_agent: nextAgent,
            active_step:
              data.active_step ||
              nextClaim?.active_step ||
              nextPipeline?.active_step ||
              String(nextStage || "acknowledgment").toLowerCase(),
            pipeline_state:
              data.pipeline_state ||
              nextClaim?.pipeline_state ||
              nextPipeline?.pipeline_state ||
              "PIPELINE_RESUMED",
            pipeline_status:
              data.pipeline_status ||
              nextClaim?.pipeline_status ||
              nextPipeline?.pipeline_status ||
              "RUNNING",
            progress:
              data.progress ??
              nextClaim?.progress ??
              nextPipeline?.progress ??
              74,
            pipeline: nextPipeline,
            approval_required: false,
            review_required: false,
            pipeline_paused: false,
            clearinghouse_accepted: true,
            clearinghouse_approved: true,
            updatedAt: new Date().toISOString(),
          },
        ]);

        actions.setPipelineData((prev) => ({
          ...prev,
          [claimId]: mergePipeline({ pipeline: prev[claimId] }, { pipeline: nextPipeline }),
        }));

        actions.setActionMessage("Claim approved. Pipeline resumed.");

        pushToast({
          tone: "success",
          title: "Claim approved",
          message: claimId,
        });

        window.setTimeout(() => records.refreshClaims(), 500);
        window.setTimeout(() => records.refreshClaims(), 1500);
        window.setTimeout(() => records.refreshClaims(), 3000);
        window.setTimeout(() => records.refreshClaims(), 6000);
      } catch (error: any) {
        actions.setActionMessage(error?.message || "Approval failed.");

        pushToast({
          tone: "warning",
          title: "Approval failed",
          message: error?.message || "Could not approve claim.",
        });
      }
    },
    [actions, pushToast, records]
  );
      const handleAutoReview = useCallback(
        async (claimId: string) => {
          try {
            actions.setActionMessage("Running clearinghouse auto review...");

            const data = await runClearinghouseAutoReview(claimId);

            records.mergeItems([
              {
                ...(data.claim || data),
                claim_id: claimId,
                status: data.status || data.claim?.status || "PROCESSING",
                updatedAt: new Date().toISOString(),
              },
            ]);

            actions.setActionMessage("Auto review completed.");

            pushToast({
              tone: "success",
              title: "Auto review completed",
              message: claimId,
            });
          } catch (error: any) {
            actions.setActionMessage(error?.message || "Auto review failed.");

            pushToast({
              tone: "warning",
              title: "Auto review failed",
              message: error?.message || "Could not run auto review.",
            });
          }
        },
        [actions, pushToast, records]
      );

    const handleReject = useCallback(
      async (claimId: string) => {
        try {
          actions.setActionMessage("Rejecting claim...");

          const data = await rejectClaim(claimId);

          records.mergeItems([
            {
              ...(data.claim || data),
              claim_id: claimId,
              status: data.status || data.claim?.status || "REJECTED",
              updatedAt: new Date().toISOString(),
            },
          ]);

          actions.setActionMessage("Claim rejected.");

          pushToast({
            tone: "success",
            title: "Claim rejected",
            message: claimId,
          });
        } catch (error: any) {
          actions.setActionMessage(error?.message || "Reject failed.");

          pushToast({
            tone: "warning",
            title: "Reject failed",
            message: error?.message || "Could not reject claim.",
          });
        }
      },
      [actions, pushToast, records]
    );

  const handleRetry = useCallback(
    async (claimId: string) => {
      try {
        actions.setActionMessage("Retrying validation...");

        const data = await retryClaimValidation(claimId);

        records.mergeItems([
          {
            ...(data.claim || data),
            claim_id: claimId,
            status: data.status || data.claim?.status || "PROCESSING",
            updatedAt: new Date().toISOString(),
          },
        ]);

        actions.setActionMessage("Validation retry started.");

        pushToast({
          tone: "success",
          title: "Retry started",
          message: claimId,
        });
      } catch (error: any) {
        actions.setActionMessage(error?.message || "Retry failed.");

        pushToast({
          tone: "warning",
          title: "Retry failed",
          message: error?.message || "Could not retry validation.",
        });
      }
    },
    [actions, pushToast, records]
  );

  const handleViewClaim = useCallback(
    async (claimId: string) => {
      await actions.handleViewClaim(claimId);
    },
    [actions]
  );

  const handleExpandedApprove = useCallback(
    async (claimId: string, item: any) => {
      const status = getWorkspaceStatus(item);
      const normalizedStatus = String(status || "").toUpperCase();

      const isHitl =
        normalizedStatus.includes("HITL") ||
        normalizedStatus.includes("HUMAN_REVIEW") ||
        normalizedStatus.includes("MANUAL_REVIEW");

      if (isHitl && (hitl as any)?.approveHitlCase) {
        await (hitl as any).approveHitlCase(claimId);
        return;
      }

      await handleApprove(claimId);
    },
    [handleApprove, hitl]
  );

  const handleExpandedRouteCase = useCallback(
    async (claimId: string, assignedRole: string) => {
      if ((hitl as any)?.routeCase) {
        await (hitl as any).routeCase(claimId, assignedRole);
        return;
      }

      pushToast({
        tone: "info",
        title: "Routing action",
        message: `${claimId} should be routed to ${assignedRole}.`,
      });
    },
    [hitl, pushToast]
  );

  const handleExpandedEscalate = useCallback(
    async (claimId: string) => {
      if ((hitl as any)?.escalateHitlCase) {
        await (hitl as any).escalateHitlCase(claimId);
        return;
      }

      pushToast({
        tone: "info",
        title: "Escalation action",
        message: `${claimId} escalation requested.`,
      });
    },
    [hitl, pushToast]
  );

  const renderFormButtons = (item: any) => {
    const formsForClaim = getSupportedForms(item);

    return (
      <div className="cw-form-actions">
        {formsForClaim.includes("CMS1500") && (
          <button
            className="cw-form-btn"
            type="button"
            onClick={() => forms.openFormPreview(item, "CMS1500")}
          >
            CMS1500
          </button>
        )}

        {formsForClaim.includes("UB04") && (
          <button
            className="cw-form-btn purple"
            type="button"
            onClick={() => forms.openFormPreview(item, "UB04")}
          >
            UB04
          </button>
        )}

        {formsForClaim.length === 0 && <span className="forms-empty">Forms pending</span>}
      </div>
    );
  };

  return (
    <div className="claim-workspace-page">
      <form className="cw-hidden-upload" onSubmit={upload.handleUpload} style={{ display: "none" }}>
        <input
          ref={upload.fileInputRef}
          type="file"
          onChange={(event) => upload.handleFileChange(event.target.files?.[0] || null)}
        />
      </form>

      <header className="cw-page-header">
        <div>
          <div className="cw-breadcrumb">Workspace / Claim Workspace</div>
          <h1>Claim Workspace</h1>
          <p>End-to-end claim orchestration and real-time AI agent monitoring</p>
        </div>

        <div className="cw-header-actions">
          <span
            className={`cw-ws-status ${realtime.wsHealth.connected ? "connected" : "disconnected"}`}
            title={realtime.wsHealth.reason || realtime.wsHealth.status}
          >
            {realtime.wsHealth.connected
              ? "Realtime connected"
              : realtime.wsHealth.status === "CONNECTING"
              ? "Realtime connecting"
              : "Realtime disconnected"}
          </span>

          <div className="cw-mode-toggle" role="group" aria-label="Clearinghouse processing mode">
            <button
              className={processingMode === "AUTO" ? "active" : ""}
              onClick={() => handleProcessingModeChange("AUTO")}
              type="button"
            >
              Auto Process
            </button>

            <button
              className={processingMode === "MANUAL" ? "active" : ""}
              onClick={() => handleProcessingModeChange("MANUAL")}
              type="button"
            >
              Manual Review
            </button>
          </div>

          <button
            className="cw-primary"
            type="button"
            onClick={(event) =>
              upload.file ? upload.handleUpload(event as any) : upload.openFilePicker()
            }
            disabled={upload.loading}
          >
            <UploadCloud size={17} />
            {upload.loading ? "Uploading..." : upload.file ? "Start Upload" : "Upload Claim"}
          </button>

          <button
            className="cw-filter"
            type="button"
            onClick={() => records.refreshClaims()}
            disabled={records.isRefreshing || upload.loading}
            title="Refresh Claims"
          >
            <RefreshCw size={16} className={records.isRefreshing ? "spin" : ""} />
          </button>
        </div>
      </header>

      <RealtimeSyncManager
        wsHealth={realtime.wsHealth}
        backendHealthy={records.backendHealthy}
        pollingFallbackActive={realtime.pollingFallbackActive}
        pollingFallbackStopped={realtime.pollingFallbackStopped}
        visibleProcessingClaims={visibleProcessingClaims}
      />

      {(upload.uploadStatus !== "idle" || upload.file) && (
        <div className={`cw-upload-status ${upload.uploadStatus}`}>
          <strong>
            {upload.file
              ? upload.file.name
              : upload.uploadStatus === "success"
              ? "Upload complete"
              : "Upload status"}
          </strong>
          <span>{upload.uploadMessage || "Ready to upload"}</span>
        </div>
      )}

      <DashboardCards metrics={workspaceMetrics} />

      <section className="cw-workspace-card">
        <div className="cw-workspace-toolbar">
          <div>
            <h2>Claim Queue</h2>
            <p>{filters.renderedItems.length} claims visible</p>
          </div>

          <div className="cw-toolbar-note">
            <Bell size={16} />
            <span>
              {realtime.wsHealth.connected
                ? "Live updates enabled"
                : realtime.pollingFallbackActive
                ? "Polling fallback active"
                : "Realtime unavailable"}
            </span>
          </div>
        </div>

        <ClaimTabs
          activeTab={filters.activeTab}
          setActiveTab={filters.setActiveTab}
          tabCounts={filters.tabCounts}
        />

        <ClaimFilters
          search={filters.search}
          setSearch={filters.setSearch}
          filter={filters.filter}
          setFilter={filters.setFilter}
          riskFilter={filters.riskFilter}
          setRiskFilter={filters.setRiskFilter}
          uploadTypeFilter={filters.uploadTypeFilter}
          setUploadTypeFilter={filters.setUploadTypeFilter}
          payerFilter={filters.payerFilter}
          setPayerFilter={filters.setPayerFilter}
          agentFilter={filters.agentFilter}
          setAgentFilter={filters.setAgentFilter}
          dateFilter={filters.dateFilter}
          setDateFilter={filters.setDateFilter}
          validationFilter={filters.validationFilter}
          setValidationFilter={filters.setValidationFilter}
          modeFilter={filters.modeFilter}
          setModeFilter={filters.setModeFilter}
          reviewFilter={filters.reviewFilter}
          setReviewFilter={filters.setReviewFilter}
          latestFilter={filters.latestFilter}
          setLatestFilter={filters.setLatestFilter}
          payerOptions={filters.payerOptions}
          agentOptions={filters.agentOptions}
          activeTab={filters.activeTab}
        />

        <div className="cw-table-wrap">
          <table className="cw-table">
            <thead>
              <tr>
                <th>Claim ID</th>
                <th>Patient</th>
                <th>Payer</th>
                <th>DOS</th>
                <th>Amount</th>
                <th>Status</th>
                <th>Agent</th>
                <th>Progress</th>
                <th>Review</th>
                <th>Actions</th>
              </tr>
            </thead>

            <tbody>
              {filters.renderedItems.length === 0 && (
                <tr>
                  <td colSpan={10}>
                    <div className="cw-empty-state">No claims found.</div>
                  </td>
                </tr>
              )}

              {filters.renderedItems.map((item) => {
                const claimId = getClaimId(item);
                const livePipeline = actions.pipelineData?.[claimId] || {};

                const latestItem = {
                  ...item,

                  // Keep top-level live fields if pipelineData carries them.
                  status:
                    livePipeline?.status ||
                    livePipeline?.pipeline_status ||
                    item?.status,

                  current_stage:
                    livePipeline?.current_stage ||
                    livePipeline?.stage ||
                    item?.current_stage ||
                    item?.stage,

                  current_agent:
                    livePipeline?.current_agent ||
                    livePipeline?.agent ||
                    item?.current_agent ||
                    item?.agent,

                  active_step:
                    livePipeline?.active_step ||
                    item?.active_step,

                  progress:
                    livePipeline?.progress ??
                    item?.progress,

                  pipeline_state:
                    livePipeline?.pipeline_state ||
                    item?.pipeline_state,

                  pipeline_status:
                    livePipeline?.pipeline_status ||
                    item?.pipeline_status,

                  review_required:
                    livePipeline?.review_required ??
                    item?.review_required,

                  approval_required:
                    livePipeline?.approval_required ??
                    item?.approval_required,

                  pipeline_paused:
                    livePipeline?.pipeline_paused ??
                    item?.pipeline_paused,

                  pipeline: {
                    ...(item?.pipeline || {}),
                    ...(item?.claim?.pipeline || {}),
                    ...(livePipeline || {}),
                    steps: {
                      ...(item?.pipeline?.steps || {}),
                      ...(item?.claim?.pipeline?.steps || {}),
                      ...(livePipeline?.steps || {}),
                    },
                    stage_status: {
                      ...(item?.pipeline?.stage_status || {}),
                      ...(item?.claim?.pipeline?.stage_status || {}),
                      ...(livePipeline?.stage_status || {}),
                    },
                    agents: {
                      ...(item?.pipeline?.agents || {}),
                      ...(item?.claim?.pipeline?.agents || {}),
                      ...(livePipeline?.agents || {}),
                    },
                  },

                  claim: {
                    ...(item?.claim || {}),
                    pipeline: {
                      ...(item?.claim?.pipeline || {}),
                      ...(item?.pipeline || {}),
                      ...(livePipeline || {}),
                      steps: {
                        ...(item?.claim?.pipeline?.steps || {}),
                        ...(item?.pipeline?.steps || {}),
                        ...(livePipeline?.steps || {}),
                      },
                    },
                  },
                };

                const status = getWorkspaceStatus(latestItem);
                const progress = getPipelineProgress(latestItem);
                const mode = getBackendProcessingMode(
                  latestItem,
                  claimModeOverrides,
                  processingMode
                );
                const reviewStatus = getReviewStatus(latestItem, mode);
                const isExpanded = actions.expandedRow === claimId;
                const isHighlighted = highlightedClaims.has(claimId);

                return (
                  <React.Fragment key={claimId}>
                    <tr className={`cw-row ${isHighlighted ? "highlight" : ""}`}>
                      <td>
                        <strong>{claimId}</strong>
                      </td>

                      <td>{getPatientName(latestItem)}</td>

                      <td>{getPayer(latestItem)}</td>

                      <td>{getDos(latestItem) || "Not reported"}</td>

                      <td>{money(getAmount(latestItem))}</td>

                      <td>
                        <span className={`cw-status ${status.toLowerCase()}`}>
                          {displayStatus(status)}
                        </span>
                      </td>

                      <td>{getCurrentAgent(latestItem)}</td>

                      <td>{progress ?? "-"}</td>

                      <td>{reviewStatus}</td>

                      <td>
                        <div className="cw-row-actions">
                          <button
                            type="button"
                            className="cw-btn secondary"
                            onClick={() => handleViewClaim(claimId)}
                          >
                            {isExpanded ? "Hide" : "View"}
                          </button>

                          <button
                            type="button"
                            className="cw-btn secondary"
                            onClick={() => actions.openClaimProfile(claimId)}
                          >
                            Profile
                          </button>

                          <button
                            type="button"
                            className="cw-btn danger"
                            onClick={() => actions.handleDeleteRequest(latestItem)}
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>

                    {isExpanded && (
                      <tr className="cw-expanded-row">
                        <td colSpan={10}>
                          <ExpandedClaimWorkspace
                            item={latestItem}
                            pipelineData={latestItem.pipeline}
                            events={realtime.events}
                            processingMode={processingMode}
                            claimModeOverrides={claimModeOverrides}
                            onOpenProfile={actions.openClaimProfile}
                            onDeleteRequest={actions.handleDeleteRequest}
                            onModeChange={handleClaimModeChange}
                            onApprove={handleExpandedApprove}
                            onAcceptClearinghouse={handleAcceptClearinghouse}
                            onReject={handleReject}
                            onEscalate={handleExpandedEscalate}
                            onRouteCase={handleExpandedRouteCase}
                          />
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <FormPreviewModal
        formPreview={forms.formPreview}
        pdfLoading={forms.pdfLoading}
        pdfError={forms.pdfError}
        pdfZoom={forms.pdfZoom}
        setPdfZoom={forms.setPdfZoom}
        setFormPreview={forms.setFormPreview}
        printPdfPreview={forms.printPdfPreview}
        pdfFrameRef={forms.pdfFrameRef}
      />

      <ClaimProfileDrawer
        profileOpen={actions.profileOpen}
        profileData={actions.profileData}
        onClose={() => actions.setProfileOpen(null)}
      />

      <DeleteClaimModal
        deleteTarget={actions.deleteTarget}
        deletingClaim={actions.deletingClaim}
        onCancel={() => actions.setDeleteTarget(null)}
        onConfirm={actions.handleDeleteClaim}
      />

      <ToastStack toastMessages={toastMessages} />
    </div>
  );
};

export default UploadEHRContainer;
