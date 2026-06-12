import React, { useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import type { WebSocketHealth } from "../../../services/websocket";

type ProcessingClaim = {
  stage?: string;
  status?: string;
  progress?: number | null;
  current_stage?: string;
  current_agent?: string;
  active_step?: string;
  pipeline_state?: string;
  pipeline_status?: string;
  review_required?: boolean;
  approval_required?: boolean;
  pipeline_paused?: boolean;
};

type RealtimeSyncManagerProps = {
  wsHealth: WebSocketHealth;
  backendHealthy: boolean | null;
  pollingFallbackActive: boolean;
  pollingFallbackStopped: boolean;
  visibleProcessingClaims: ProcessingClaim[];
};

const normalizeText = (value?: string | null) =>
  String(value || "")
    .replace(/_/g, " ")
    .replace(/\s+/g, " ")
    .trim();

const normalizeUpper = (value?: string | null) =>
  String(value || "")
    .trim()
    .toUpperCase()
    .replace(/\s+/g, "_")
    .replace(/-/g, "_");

const getClaimStage = (claim: any) =>
  claim?.current_stage ||
  claim?.pipeline?.current_stage ||
  claim?.stage ||
  claim?.active_step ||
  claim?.pipeline?.active_step ||
  claim?.current_agent ||
  claim?.pipeline?.current_agent ||
  "Not reported";

const getClaimStatus = (claim: any) =>
  claim?.status ||
  claim?.pipeline_status ||
  claim?.pipeline?.pipeline_status ||
  claim?.pipeline_state ||
  claim?.pipeline?.pipeline_state ||
  "Not reported";

const getClaimProgress = (claim?: ProcessingClaim) => {
  const explicit = claim?.progress;

  if (typeof explicit === "number" && Number.isFinite(explicit)) {
    return Math.max(0, Math.min(100, explicit));
  }

  const stage = normalizeUpper(
    claim?.current_stage || claim?.stage || claim?.active_step
  );

  const status = normalizeUpper(
    claim?.pipeline_state || claim?.pipeline_status || claim?.status
  );

  if (
    status === "WAITING_FOR_APPROVAL" ||
    status === "PENDING_CLEARINGHOUSE" ||
    stage === "CLEARINGHOUSE"
  ) {
    return 70;
  }

  const progressByStage: Record<string, number> = {
    EXTRACT: 15,
    EXTRACTION: 15,
    OCR: 15,
    ELIGIBILITY: 25,
    VALIDATION: 40,
    COMPLIANCE: 55,
    SUBMISSION: 65,
    CLEARINGHOUSE: 70,
    ACKNOWLEDGMENT: 74,
    ACKNOWLEDGEMENT: 74,
    PAYER_ACKNOWLEDGMENT: 74,
    PAYER_ACKNOWLEDGEMENT: 74,
    PAYER: 74,
    DENIAL: 80,
    DENIAL_AI: 80,
    PAYMENT: 88,
    LEARNING: 94,
    ANALYTICS: 98,
    FINISH: 100,
    COMPLETED: 100,
  };

  return progressByStage[stage] ?? 10;
};

const isWaitingForClearinghouse = (claim?: ProcessingClaim) => {
  const stage = normalizeUpper(claim?.current_stage || claim?.stage);
  const state = normalizeUpper(
    claim?.pipeline_state || claim?.pipeline_status || claim?.status
  );

  return (
    stage === "CLEARINGHOUSE" ||
    state === "WAITING_FOR_APPROVAL" ||
    state === "PENDING_CLEARINGHOUSE" ||
    claim?.review_required === true ||
    claim?.approval_required === true ||
    claim?.pipeline_paused === true
  );
};

const RealtimeSyncManager: React.FC<RealtimeSyncManagerProps> = ({
  wsHealth,
  backendHealthy,
  pollingFallbackActive,
  pollingFallbackStopped,
  visibleProcessingClaims,
}) => {
  const connectionIssue = useMemo(
    () =>
      !wsHealth.connected ||
      backendHealthy === false ||
      pollingFallbackActive ||
      pollingFallbackStopped,
    [
      wsHealth.connected,
      backendHealthy,
      pollingFallbackActive,
      pollingFallbackStopped,
    ]
  );

  const [showConnectionBanner, setShowConnectionBanner] = useState(false);

  useEffect(() => {
    if (!connectionIssue) {
      setShowConnectionBanner(false);
      return;
    }

    const timer = window.setTimeout(() => {
      setShowConnectionBanner(true);
    }, 600);

    return () => window.clearTimeout(timer);
  }, [connectionIssue]);

  const bannerClassName = useMemo(() => {
    if (pollingFallbackStopped || wsHealth.status === "DEGRADED") {
      return "cw-connection-banner degraded";
    }

    if (pollingFallbackActive) {
      return "cw-connection-banner polling";
    }

    return "cw-connection-banner recovering";
  }, [pollingFallbackStopped, pollingFallbackActive, wsHealth.status]);

  const bannerTitle = useMemo(() => {
    if (pollingFallbackStopped || wsHealth.status === "DEGRADED") {
      return "Realtime connection unavailable.";
    }

    if (pollingFallbackActive) {
      return "Polling fallback active.";
    }

    return "Attempting realtime recovery...";
  }, [pollingFallbackStopped, pollingFallbackActive, wsHealth.status]);

  const bannerMessage = useMemo(() => {
    if (backendHealthy === false) {
      return "Backend is not reachable. Local claim cache is cleared until recovery.";
    }

    if (pollingFallbackActive) {
      return "Safely syncing claims with capped retries while websocket reconnects.";
    }

    return wsHealth.reason || "Connection recovery in progress.";
  }, [backendHealthy, pollingFallbackActive, wsHealth.reason]);

  const firstProcessingClaim = visibleProcessingClaims[0];
  const waitingForClearinghouse = isWaitingForClearinghouse(firstProcessingClaim);

  const maxProgress = useMemo(() => {
    if (!visibleProcessingClaims.length) return 0;

    return Math.min(
      100,
      Math.max(
        10,
        ...visibleProcessingClaims.map((claim) => getClaimProgress(claim))
      )
    );
  }, [visibleProcessingClaims]);

  const title = waitingForClearinghouse
    ? "Waiting for clearinghouse approval..."
    : "Processing claim intake...";

  const helperText = waitingForClearinghouse
    ? "Review and accept the clearinghouse response to continue the pipeline."
    : "Please wait while the claim is extracted, validated, and saved.";

    return (
      <>
        {showConnectionBanner && (
          <div className={bannerClassName}>
            <strong>{bannerTitle}</strong>
            <span>{bannerMessage}</span>
          </div>
        )}

        {visibleProcessingClaims.length > 0 && (
          <div className="cw-intake-loader" aria-live="polite">
            <div className="cw-intake-spinner">
              <Loader2 size={18} />
            </div>

            <div className="cw-intake-content">
              <strong>{title}</strong>

              <span>
                Current Stage: {getClaimStage(firstProcessingClaim)}{" "}
                &middot; Status: {getClaimStatus(firstProcessingClaim)}
              </span>

              <small>{helperText}</small>
            </div>

            <div className="cw-intake-progress">
              <i style={{ width: `${maxProgress}%` }} />
            </div>
          </div>
        )}
      </>
    );
};

export default React.memo(RealtimeSyncManager);
