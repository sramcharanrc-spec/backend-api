import React, { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  BadgeCheck,
  BarChart3,
  Bot,
  BrainCircuit,
  Clock3,
  Copy,
  Download,
  DollarSign,
  ExternalLink,
  FileCheck2,
  FileText,
  Gauge,
  GitBranch,
  HeartPulse,
  Printer,
  Search,
  ShieldAlert,
  Sparkles,
  TimerReset,
  TrendingUp,
  Users,
  X,
  Zap,
} from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  RadialBar,
  RadialBarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import RealtimeAgentFeed from "../../components/RealtimeAgentFeed";
import { API_URL } from "../../config";
import { usePipeline } from "../../hooks/usePipeline";
import { getRecords } from "../../services/rcmApi";
import { addConnectionHealthListener, addPipelineEventListener, type WebSocketHealth } from "../../services/websocket";
import { displayText, mergeClaims, normalizeClaimsResponse } from "../../utils/claimSync";
import { clearClaimCache } from "../../utils/cacheUtils";
import { calculateTrend, getClaimTrendPeriods } from "../../utils/kpiTrends";
import "../Analytics/Analytics.css";

type RecordType = Record<string, any>;
type ClaimLifecycle = "ACTIVE" | "REVIEW" | "COMPLETED" | "COMMAND_CENTER";
type ClaimStores = {
  activeClaims: RecordType[];
  reviewClaims: RecordType[];
  completedClaims: RecordType[];
  commandCenterClaims: RecordType[];
};
type ClaimStoresAction =
  | { type: "SET_ACTIVE_SOURCE"; claims: RecordType[] }
  | { type: "UPSERT_ACTIVE_SOURCE"; claims: RecordType[] }
  | { type: "SET_COMPLETED_SOURCE"; claims: RecordType[] }
  | { type: "MERGE_COMPLETED"; claims: RecordType[] }
  | { type: "MOVE_TO_COMMAND_CENTER"; claim: RecordType };

const COMPLETED_CACHE_KEY = "ehr-command-center-completed-claims-v1";
const LIVE_CLAIM_EVENT_TYPES = new Set([
  "claim_created",
  "claim_updated",
  "claim_processing",
  "claim_completed",

  "agent_update",
  "pipeline_update",
  "pipeline_started",
  "pipeline_resumed",
  "pipeline_completed",

  "manual_review_required",
  "hitl_required",
  "case_created",
  "case_assigned",
  "case_escalated",

  "clearinghouse_queued",
  "clearinghouse_accepted",
  "payment_completed",
  "denial_analyzed",
]);

const palette = ["#2563eb", "#14b8a6", "#f97316", "#8b5cf6", "#ef4444", "#22c55e"];
const COMPLETED_KPI_STATUSES = new Set(["COMPLETED", "PAID", "COMMAND_CENTER"]);
const HITL_KPI_STATUSES = new Set(["HITL_REQUIRED", "MANUAL_REVIEW_REQUIRED", "WAITING_FOR_REVIEW"]);

const money = (value: number) =>
  Number(value || 0).toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

const pct = (value: number) => `${Math.round(value)}%`;
const statusOf = (item: any) => {
  const rawStatus = String(item?.status || item?.claim?.status || item?.payload?.claim?.status || "").toUpperCase();
  const lifecycle = String(item?.lifecycle_status || item?.lifecycle || item?.workspace || item?.payload?.lifecycle_status || "").toUpperCase();
  if (rawStatus) return rawStatus;
  if (item?.command_center === true || item?.pipeline_completed === true || lifecycle === "COMMAND_CENTER") return "COMMAND_CENTER";
  return "PENDING";
};
const claimOf = (item: any) => item?.claim || item?.payload?.claim || item?.payload || item || {};
const pipelineOf = (item: any) =>
  item?.pipeline?.steps ||
  item?.data?.pipeline?.steps ||
  item?.payload?.pipeline?.steps ||
  item?.metadata?.pipeline?.steps ||
  item?.pipelineSteps ||
  {};
const progressOf = (item: any) => {
  const raw =
    item?.progress ??
    item?.payload?.progress ??
    item?.pipeline?.progress;

  if (raw !== undefined && raw !== null) {
    return Math.min(
      100,
      Math.max(
        0,
        Math.round(Number(raw))
      )
    );
  }

  const status = String(
    item?.status || ""
  ).toUpperCase();

  const stage = String(
    item?.stage ||
      item?.current_stage ||
      ""
  ).toUpperCase();

  if (
    status === "PAID" ||
    status === "COMPLETED" ||
    stage === "FINISH" ||
    stage === "COMPLETED"
  ) {
    return 100;
  }

  return 0;
};

const isCommandCenterClaim = (item: any) => {
  const status = statusOf(item);

  const stage = String(
    item?.stage ||
      item?.current_stage ||
      ""
  ).toUpperCase();

  return (
    item?.pipeline_completed === true ||
    item?.command_center === true ||
    COMPLETED_KPI_STATUSES.has(status) ||
    status === "APPROVED" ||
    stage === "FINISH" ||
    stage === "COMPLETED"
  );
};
const isCompletedCommandCenterClaim = (item: any) => {
  const status = statusOf(item);

  const stage = String(
    item?.stage ||
      item?.current_stage ||
      item?.payload?.stage ||
      item?.pipeline?.current_stage ||
      ""
  ).toUpperCase();

  return (
    COMPLETED_KPI_STATUSES.has(status) ||
    status === "APPROVED" ||
    ["FINISH", "COMPLETED"].includes(stage) ||
    item?.pipeline_completed === true ||
    item?.command_center === true
  );
};
const amountOf = (item: any) => Number(item?.total_charge || claimOf(item)?.total_charge || item?.payment_amount || item?.payment?.paid_amount || item?.payment?.expected || 0);
const payerOf = (item: any) => displayText(claimOf(item)?.payer?.name || item?.payer || item?.payer_name, "Unknown");
const patientNameOf = (item: any) => displayText(item?.patient?.name || claimOf(item)?.patient?.name || item?.patient || item?.patient_name, "Unknown Patient");
const completedAtOf = (item: any) => item?.completed_at || item?.finalized_at || item?.updated_at || "";
const docUrl = (url?: string) => (!url ? "" : url.startsWith("http") ? url : `${API_URL}${url}`);
const riskOf = (item: any) => {
  const raw = item?.risk_score ?? item?.payload?.denial_ai?.risk_score ?? item?.denial_ai?.risk_score ?? claimOf(item)?.risk_score ?? 0;
  const value = Number(raw || 0);
  return value <= 1 ? value * 100 : value;
};
const extractionOf = (item: any) => claimOf(item)?.extraction || item?.payload?.extraction || item?.extraction || {};

const claimIdOf = (item: any) => item?.claim_id || item?.claimId || item?.claim?.claim_id || item?.payload?.claim_id || item?.payload?.claim?.claim_id;
const claimIdsHash = (claims: RecordType[]) => JSON.stringify(claims.map((claim) => claimIdOf(claim)));

const recordsFromResponse = (response: any): RecordType[] =>
  normalizeClaimsResponse(response?.data ?? response);

const recordFromClaimEvent = (event: any): RecordType | null => {
  const eventType = String(event?.type || event?.event || "").toLowerCase();
  if (!LIVE_CLAIM_EVENT_TYPES.has(eventType)) return null;

  const data = event?.data && typeof event.data === "object" ? event.data : {};
  const snapshot = event?.claim || data?.claim || event?.payload?.claim || event?.payload || {};
  const id =
    event?.claim_id ||
    event?.claimId ||
    data?.claim_id ||
    data?.claimId ||
    snapshot?.claim_id ||
    snapshot?.claimId;

  if (!id) return null;

  return {
    ...snapshot,
    ...data,
    ...event,
    claim_id: id,
  };
};

const lifecycleOf = (item: any): ClaimLifecycle => {
  if (isCompletedCommandCenterClaim(item)) return "COMMAND_CENTER";
  const status = statusOf(item);
  if (["HITL_REQUIRED", "MANUAL_REVIEW_REQUIRED", "FAILED", "WAITING_FOR_REVIEW"].includes(status)) return "REVIEW";
  return "ACTIVE";
};

const withLifecycle = (item: RecordType, lifecycle?: ClaimLifecycle): RecordType => {
  const nextLifecycle = lifecycle || lifecycleOf(item);
  return {
    ...item,
    claim_id: claimIdOf(item),
    lifecycle: nextLifecycle,
    lifecycle_status: nextLifecycle === "COMMAND_CENTER" ? "COMMAND_CENTER" : item.lifecycle_status,
    command_center: nextLifecycle === "COMMAND_CENTER" ? true : item.command_center,
    pipeline_completed: nextLifecycle === "COMMAND_CENTER" ? true : item.pipeline_completed,
    progress: nextLifecycle === "COMMAND_CENTER" ? 100 : progressOf(item),
  };
};

const mergeByClaimId = (current: RecordType[] = [], incoming: RecordType[] = []) => {
  return mergeClaims(current, incoming);
};

const removeClaims = (claims: RecordType[], ids: Set<string>) => claims.filter((claim) => !ids.has(claimIdOf(claim)));

const loadCompletedCache = (): RecordType[] => {
  if (typeof window === "undefined") return [];
  try {
    window.localStorage.removeItem(COMPLETED_CACHE_KEY);
    window.sessionStorage.removeItem(COMPLETED_CACHE_KEY);
  } catch {
  }
  return [];
};

const claimStoresReducer = (state: ClaimStores, action: ClaimStoresAction): ClaimStores => {
  if (action.type === "SET_ACTIVE_SOURCE") {
    const nonCompleted = action.claims.filter((claim) => !isCompletedCommandCenterClaim(claim));
    return {
      ...state,
      activeClaims: nonCompleted
        .filter((claim) => lifecycleOf(claim) === "ACTIVE")
        .map((claim) => withLifecycle(claim, "ACTIVE")),
      reviewClaims: nonCompleted
        .filter((claim) => lifecycleOf(claim) === "REVIEW")
        .map((claim) => withLifecycle(claim, "REVIEW")),
    };
  }

  if (action.type === "UPSERT_ACTIVE_SOURCE") {
    const nonCompleted = action.claims.filter((claim) => !isCompletedCommandCenterClaim(claim));
    return {
      ...state,
      activeClaims: mergeByClaimId(
        state.activeClaims,
        nonCompleted
          .filter((claim) => lifecycleOf(claim) === "ACTIVE")
          .map((claim) => withLifecycle(claim, "ACTIVE"))
      ),
      reviewClaims: mergeByClaimId(
        state.reviewClaims,
        nonCompleted
          .filter((claim) => lifecycleOf(claim) === "REVIEW")
          .map((claim) => withLifecycle(claim, "REVIEW"))
      ),
    };
  }

  if (action.type === "SET_COMPLETED_SOURCE") {
    const completed = action.claims
      .filter((claim) => isCompletedCommandCenterClaim(claim))
      .map((claim) => withLifecycle(claim, "COMMAND_CENTER"));
    return {
      ...state,
      completedClaims: completed,
      commandCenterClaims: completed,
    };
  }

  if (action.type === "MERGE_COMPLETED") {
    const completedIncoming = action.claims
      .filter((claim) => isCompletedCommandCenterClaim(claim))
      .map((claim) => withLifecycle(claim, "COMMAND_CENTER"));
    if (!completedIncoming.length) return state;
    const ids = new Set(completedIncoming.map(claimIdOf).filter(Boolean));
    const completed = mergeByClaimId(state.completedClaims, completedIncoming);
    return {
      activeClaims: removeClaims(state.activeClaims, ids),
      reviewClaims: removeClaims(state.reviewClaims, ids),
      completedClaims: completed,
      commandCenterClaims: mergeByClaimId(state.commandCenterClaims, completedIncoming),
    };
  }

  if (action.type === "MOVE_TO_COMMAND_CENTER") {
    const completed = withLifecycle(action.claim, "COMMAND_CENTER");
    if (!isCompletedCommandCenterClaim(completed)) return state;
    const claimId = claimIdOf(completed);
    if (!claimId) return state;
    const ids = new Set([claimId]);
    return {
      activeClaims: removeClaims(state.activeClaims, ids),
      reviewClaims: removeClaims(state.reviewClaims, ids),
      completedClaims: mergeByClaimId(state.completedClaims, [completed]),
      commandCenterClaims: mergeByClaimId(state.commandCenterClaims, [completed]),
    };
  }

  return state;
};

const filterClaimsByStatus = (claims: RecordType[], selectedStatus: string) => {
  const queryStatus = String(selectedStatus || "ALL").toUpperCase();
  const commandCenterClaims = claims.filter(isCompletedCommandCenterClaim);
  const nonCommandCenterClaims = claims.filter((claim) => !isCompletedCommandCenterClaim(claim));

  if (queryStatus === "COMPLETED") {
    return commandCenterClaims.filter((claim) => progressOf(claim) === 100);
  }

  if(queryStatus==="ALL")
   return claims;

  return nonCommandCenterClaims.filter((claim) => statusOf(claim) === queryStatus);
};

const trend = (base: number, offset = 0) => {
  const value = Number(base || 0);
  if (value <= 0) return Array.from({ length: 8 }, () => 0);
  return Array.from({ length: 8 }, (_, index) => Math.max(1, Math.round(value * (0.65 + index * 0.055) + ((index + offset) % 3) * 4)));
};

const Sparkline = ({ data, color = "#2563eb" }: { data: number[]; color?: string }) => {
  const max = Math.max(...data, 1);
  const points = data
    .map((value, index) => `${(index / Math.max(data.length - 1, 1)) * 96 + 2},${34 - (value / max) * 28}`)
    .join(" ");
  return (
    <svg className="ec-spark" viewBox="0 0 100 40" preserveAspectRatio="none">
      <polyline points={points} fill="none" stroke={color} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
};

const ClaimTableSkeleton = () => (
  <div className="ec-page">
    <section className="ec-panel cc-repository">
      <div className="ec-panel-title">
        <div>
          <h2>Loading claims</h2>
          <p>Hydrating claim records from the API.</p>
        </div>
      </div>
      <div className="cc-repository-table">
        <div className="cc-repository-head">
          <span>Claim ID</span><span>Patient</span><span>Payer</span><span>DOS</span><span>Status</span><span>Payment</span><span>Denial</span><span>Completed</span><span>Duration</span><span>Actions</span>
        </div>
        {Array.from({ length: 5 }, (_, index) => (
          <div className="cc-repository-row" key={index}>
            {Array.from({ length: 10 }, (_, cellIndex) => (
              <span key={cellIndex} className="cc-empty-doc">Loading...</span>
            ))}
          </div>
        ))}
      </div>
    </section>
  </div>
);

const Dashboard: React.FC = () => {
  const [records, setRecords] = useState<RecordType[]>([]);
  const [repositoryLoading, setRepositoryLoading] = useState(false);
  const [repositoryClaims, setRepositoryClaims] = useState<RecordType[]>([]);
  const [repositorySearch, setRepositorySearch] = useState("");
  const [repositoryStatus, setRepositoryStatus] = useState("ALL");
  const [selectedClaim, setSelectedClaim] = useState<RecordType | null>(null);
  const [detailTab, setDetailTab] = useState("Overview");
  const [loading, setLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [wsHealth, setWsHealth] = useState<WebSocketHealth>({ status: "DISCONNECTED", connected: false, attempts: 0 });
  const { claims, events, bulkProgress } = usePipeline();
  const repositoryRequestRef = useRef(0);
  const repositoryLoadingRef = useRef(false);
  const recordsRequestRef = useRef(0);
  const repositoryAbortRef = useRef<AbortController | null>(null);
  const previousMerged = useRef("");
  const initialized = useRef(false);
  const [claimStores, dispatchClaimStores] = useReducer(claimStoresReducer, undefined, () => {
    const cached = loadCompletedCache();
    return {
      activeClaims: [],
      reviewClaims: [],
      completedClaims: cached,
      commandCenterClaims: cached,
    };
  });

  useEffect(() => {
    clearClaimCache();
  }, []);

  const loadRepository = useCallback(async () => {
    if (repositoryLoadingRef.current) {
      return;
    }

    repositoryLoadingRef.current = true;

    const requestId = repositoryRequestRef.current + 1;
    repositoryRequestRef.current = requestId;
    repositoryAbortRef.current?.abort();

    const controller = new AbortController();
    repositoryAbortRef.current = controller;

    setRepositoryLoading(true);

    try {
      const params = new URLSearchParams();
      if (repositorySearch.trim()) {
        params.set(
          "search",
          repositorySearch.trim()
        );
      }

      params.set(
        "status",
        "COMPLETED"
      );

      const response = await fetch(`${API_URL}/claims?${params}`, { signal: controller.signal });
      const data = await response.json();

      console.log(
        "API records",
        data.records
      );

      if (requestId !== repositoryRequestRef.current || controller.signal.aborted) return;
      const apiRecords = normalizeClaimsResponse(data);

      console.log(
        "API records:",
        apiRecords.length
      );

      const completed = apiRecords.map((claim: RecordType) => {
        const normalizedClaim = {
          ...claim,
          claim_id: claim.claim_id || claim.claimId || crypto.randomUUID(),
        };

        const finalized = isCompletedCommandCenterClaim(normalizedClaim);

        return {
          ...normalizedClaim,
          status: claim.status || claim.pipeline_status || claim.pipeline_state || "UNKNOWN",
          progress: finalized ? 100 : progressOf(normalizedClaim),
          pipeline_completed: finalized,
          command_center: finalized,
          lifecycle_status: finalized ? "COMMAND_CENTER" : claim.lifecycle_status,
          current_stage: claim.current_stage || claim.stage || (finalized ? "COMPLETED" : "UNKNOWN"),
        };
      });

      console.log(
        "completed:",
        completed.length
      );

      setRepositoryClaims(completed);
      dispatchClaimStores({ type: "SET_COMPLETED_SOURCE", claims: completed });
    } catch (error) {
      if ((error as any)?.name !== "AbortError") console.error(error);
    } finally {
      repositoryLoadingRef.current = false;
      setRepositoryLoading(false);
      setLoading(false);
    }
  }, [repositorySearch]);

  const openRepositoryClaim = async (claimId: string) => {
    try {
      const response = await fetch(`${API_URL}/api/command-center/claims/${claimId}`);
      const data = await response.json();
      setSelectedClaim(data);
      setDetailTab("Overview");
    } catch (error) {
      console.error(error);
    }
  };

  const load = useCallback(async () => {
    const requestId = recordsRequestRef.current + 1;
    recordsRequestRef.current = requestId;
    try {
      const response = await getRecords(true);
      if (requestId !== recordsRequestRef.current) return;
      const nextRecords = recordsFromResponse(response);
      setRecords((prev) => {
        if (
          claimIdsHash(prev) ===
          claimIdsHash(nextRecords)
        ) {
          return prev;
        }

        return nextRecords;
      });
      dispatchClaimStores({ type: "SET_ACTIVE_SOURCE", claims: nextRecords });
      setLastUpdated(new Date());
    } catch (error) {
      console.error(error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (
      initialized.current
    ) {
      return;
    }

    initialized.current =
      true;

    const initializeClaims = async () => {
      const requestId = recordsRequestRef.current + 1;
      recordsRequestRef.current = requestId;
      if (records.length === 0) {
        setLoading(true);
      }

      try {
        const response = await getRecords(true);
        if (requestId !== recordsRequestRef.current) return;

        const apiRecords = recordsFromResponse(response);

        setRecords((prev) => {
          if (
            claimIdsHash(prev) ===
            claimIdsHash(apiRecords)
          ) {
            return prev;
          }

          return apiRecords;
        });
        dispatchClaimStores({ type: "SET_ACTIVE_SOURCE", claims: apiRecords });
        setLastUpdated(new Date());
      } catch (error) {
        console.error(
          "[ClaimWorkspace] Initial load failed",
          error
        );
      } finally {
        setLoading(false);
      }
    };

    initializeClaims();
  }, []);

  useEffect(() => addConnectionHealthListener(setWsHealth), []);

  useEffect(() => {
    if (
      wsHealth.connected
    ) {
      return;
    }

    const timer =
      window.setInterval(
        load,
        30000
      );

    return () => {
      window.clearInterval(
        timer
      );
    };
  }, [wsHealth.connected, load]);

  useEffect(() => {
    const unsubscribe = addPipelineEventListener((event) => {
      const claimRecord = recordFromClaimEvent(event);
      if (!claimRecord) return;

      setRecords((prev) => {
        const next =
          mergeByClaimId(
            prev,
            [claimRecord]
          );

        if (
          JSON.stringify(prev) ===
          JSON.stringify(next)
        ) {
          return prev;
        }

        return next;
      });

      if (String(event.type || event.event).toLowerCase() === "claim_completed") {
        dispatchClaimStores({ type: "MERGE_COMPLETED", claims: [claimRecord] });
      } else {
        dispatchClaimStores({ type: "UPSERT_ACTIVE_SOURCE", claims: [claimRecord] });
      }

      setLastUpdated(new Date());
    });

    return unsubscribe;
  }, []);

  useEffect(() => {
    loadRepository();
    const repositoryTimer = window.setInterval(loadRepository, 30000);
    return () => {
      window.clearInterval(repositoryTimer);
      repositoryAbortRef.current?.abort();
    };
  }, [loadRepository]);

  useEffect(() => {
    try {
      window.localStorage.removeItem(COMPLETED_CACHE_KEY);
      window.sessionStorage.removeItem(COMPLETED_CACHE_KEY);
    } catch {
      // Claim caches are intentionally disabled.
    }
  }, [claimStores.completedClaims]);

  useEffect(() => {
    const completedEvents = events.filter((event: any) => {
      const steps =
        event.data?.pipeline?.steps ||
        event.pipeline?.steps ||
        {};

      const required = [
        "case_orchestrated",
        "eligibility_checked",
        "rules_validated",
        "submitted",
        "clearinghouse_queued",
        "acknowledged",
        "denial_checked",
        "paid",
        "analytics_done",
      ];

      return required.every(
        (step) => steps?.[step] === true
      );
    });

    if (!completedEvents.length) return;

    dispatchClaimStores({
      type: "MERGE_COMPLETED",
      claims: completedEvents,
    });
  }, [events]);

  useEffect(() => {
    const completedEvents = events.filter((event: any) => {
      const steps =
        event.data?.pipeline?.steps ||
        event.pipeline?.steps ||
        {};

      const required = [
        "case_orchestrated",
        "eligibility_checked",
        "rules_validated",
        "submitted",
        "clearinghouse_queued",
        "acknowledged",
        "denial_checked",
        "paid",
        "analytics_done",
      ];

      return required.every(
        (step) => steps?.[step] === true
      );
    });
    if (!completedEvents.length) return;

    completedEvents.forEach((event: any) => {
      const claimId = event.claim_id || event.data?.claim_id || event.data?.claimId || event.metadata?.claim_id;
      if (!claimId) return;
      const live = (claims as any)[claimId] || {};
      const snapshot = live.snapshot || event.claim || event.data?.claim || {};
      const steps =
        event.data?.pipeline?.steps ||
        event.pipeline?.steps ||
        snapshot.pipeline?.steps ||
        live.pipeline?.steps ||
        {};
      dispatchClaimStores({
        type: "MOVE_TO_COMMAND_CENTER",
        claim: {
          ...snapshot,
          claim_id: claimId,
          status: "COMPLETED",
          pipeline: {
            ...(snapshot.pipeline || {}),
            steps,
          },
          progress: 100,
          pipeline_completed: true,
          command_center: true,
          lifecycle_status: "COMMAND_CENTER",
          current_stage: "COMPLETED",
          completed_at: event.timestamp || live.updatedAt || new Date().toISOString(),
          finalized_at: event.timestamp || live.updatedAt || new Date().toISOString(),
          processing_duration: event.data?.processing_duration || event.metadata?.processing_duration || snapshot.processing_duration || 0,
          payment_status: snapshot.payment_status || event.data?.payment_status || "FINALIZED",
          denial_status: snapshot.denial_status || event.data?.denial_status || "CLEARED",
          analytics: snapshot.analytics || event.data?.analytics || {},
        },
      });
    });
  }, [events, claims]);

  const merged = useMemo(() => {
    const map = new Map();

    records.forEach((record) => {
      const id =
        record.claim_id ||
        record.claimId;

      if (id) {
        map.set(id, record);
      }
    });

    Object.values(claims).forEach((liveClaim: any) => {
      const id =
        liveClaim.claimId ||
        liveClaim.claim_id;

      if (!id) return;

      const previous =
        map.get(id) || {};

      map.set(
        id,
        {
          ...previous,
          ...liveClaim,
          claim_id: id
        }
      );
    });

    return Array.from(map.values());
  }, [records, claims]);

  useEffect(() => {
    const hash =
      JSON.stringify(
        merged.map(
          (c) => ({
            id: c.claim_id,
            status: c.status,
            progress: c.progress,
          })
        )
      );

    if (
      hash ===
      previousMerged.current
    ) {
      return;
    }

    previousMerged.current =
      hash;

    dispatchClaimStores({
      type: "SET_ACTIVE_SOURCE",
      claims: merged,
    });
  }, [merged]);

  const activeClaims = claimStores.activeClaims;
  const reviewClaims = claimStores.reviewClaims;
  const completedClaims = useMemo(
  () => claimStores.completedClaims,
  [claimStores.completedClaims]
  );
  const commandCenterClaims = useMemo(
  () => claimStores.commandCenterClaims,
  [claimStores.commandCenterClaims]
  );
  const displayedRepositoryClaims = useMemo(() => {
    const allClaims =
      [
        ...repositoryClaims,
        ...completedClaims,
        ...commandCenterClaims,
      ];

    const unique =
      Array.from(
        new Map(
          allClaims.map(
            (claim) => [
              claimIdOf(claim),
              claim
            ]
          )
        ).values()
      );

    return unique.filter((claim) => {
      if (repositoryStatus === "ALL") return true;

      if (repositoryStatus === "COMPLETED") return true;

      return statusOf(claim) === repositoryStatus;
    });
  }, [repositoryClaims, completedClaims, commandCenterClaims, repositoryStatus]);

  useEffect(() => {
    console.log(
      "records:",
      records.length
    );

    console.log(
      "wsClaims:",
      Object.keys(claims).length
    );

    console.log(
      "merged:",
      merged.length
    );

    console.log(
      "completedClaims",
      completedClaims
    );

    console.log(
      "repositoryClaims",
      repositoryClaims.length
    );

    console.log(
      "commandCenterClaims",
      commandCenterClaims.length
    );

    console.log(
      "displayed:",
      displayedRepositoryClaims.length
    );

    console.log(
      "activeClaims",
      activeClaims.length
    );

  }, [records, claims, repositoryClaims, completedClaims, commandCenterClaims, displayedRepositoryClaims, activeClaims, merged]);

  const allClaims = useMemo(
    () => mergeByClaimId(
      mergeByClaimId(
        mergeByClaimId(merged, completedClaims),
        commandCenterClaims
      ),
      repositoryClaims
    ),
    [merged, completedClaims, commandCenterClaims, repositoryClaims]
  );

  const kpiData = useMemo(
    () => (Array.isArray(allClaims) ? allClaims : []).map((claim) => ({
      ...claim,
      status: statusOf(claim),
    })),
    [allClaims]
  );

  useEffect(() => {
    const data = Array.isArray(allClaims) ? allClaims : [];

    console.log("KPICards data:", data);
    console.log(
      "Statuses:",
      data.map((d: any) => ({
        claim_id: d.claim_id,
        status: d.status,
        total_charge: d.total_charge,
        claim_charge: d.claim?.total_charge
      }))
    );
  }, [allClaims]);

  // const metrics = useMemo(() => {
  //   const total = kpiData.length;
  //   const active = kpiData.filter((item) => !isCompletedCommandCenterClaim(item) && ["IN_PROGRESS", "PROCESSING", "ACTIVE", "RUNNING", "QUEUED", "PENDING"].includes(item.status)).length;
  //   const hitl = kpiData.filter((item) => HITL_KPI_STATUSES.has(item.status)).length;
  //   const pendingReview = kpiData.filter((item) => !isCompletedCommandCenterClaim(item) && (item.status.includes("PENDING") || item.status.includes("REVIEW"))).length;
  //   const denied = kpiData.filter((item) => ["DENIED", "REJECTED"].includes(item.status) || pipelineOf(item).clearinghouse_rejected).length;
  //   const completed = kpiData.filter((item) => COMPLETED_KPI_STATUSES.has(item.status)).length;
  //   const paid = completed;
  //   const autoApproved = kpiData.filter((item) => pipelineOf(item).auto_accepted || item.processing_mode === "AUTO").length;
  //   const revenue = kpiData.reduce((sum, item) => sum + amountOf(item), 0);
  //   const slaBreaches = kpiData.filter((item) => String(item.sla_status || item.case?.sla_status || "").toUpperCase() === "OVERDUE").length;
  //   const denialRate = total ? (denied / total) * 100 : 0;
  //   const payerApproval = total ? (paid / total) * 100 : 0;
  //   const ocrValues = kpiData.map((item) => Number(extractionOf(item).ocr_quality || extractionOf(item).extraction_confidence || 0)).filter(Boolean);
  //   const ocrAccuracy = ocrValues.length ? ocrValues.reduce((sum, value) => sum + value, 0) / ocrValues.length : 91;
  //   const aiAccuracy = Math.max(82, Math.min(99, 96 - denialRate / 5 + autoApproved));
  //   const avgProcessing = Math.max(7, Math.round(26 - paid * 0.4 + hitl * 0.7));
  //   const avgCycleTime = `${Math.max(1, Math.round(avgProcessing / 8))}d ${avgProcessing % 8}h`;

  //   return {
  //     total,
  //     active,
  //     hitl,
  //     pendingReview,
  //     denied,
  //     completed,
  //     paid,
  //     autoApproved,
  //     revenue,
  //     avgCycleTime,
  //     slaBreaches,
  //     denialRate,
  //     aiAccuracy,
  //     ocrAccuracy,
  //     payerApproval,
  //     avgProcessing,
  //   };
  // }, [kpiData]);

  const normalizePercent = (value: any) => {
  const num = Number(value || 0);
  if (!Number.isFinite(num) || num <= 0) return 0;
  return num <= 1 ? num * 100 : num;
};

const actualPaymentStatus = (item: any) => {
  const claim = claimOf(item);
  const payment = item?.payment || claim?.payment || item?.payment_result || claim?.payment_result || {};
  const financials = item?.financials || claim?.financials || payment?.financials || {};

  return String(
    item?.payment_status ||
      claim?.payment_status ||
      payment?.payment_status ||
      financials?.payment_status ||
      financials?.status ||
      ""
  ).toUpperCase();
};

const isPaymentReconciliationClaim = (item: any) => {
  const status = statusOf(item);
  const paymentStatus = actualPaymentStatus(item);

  return (
    [
      "UNDERPAID",
      "OVERPAID",
      "PAID_WITH_ADJUSTMENT",
      "PAYMENT_RECONCILIATION_REQUIRED",
    ].includes(paymentStatus) ||
    status === "PAYMENT_RECONCILIATION_REQUIRED" ||
    item?.underpayment_alert === true ||
    item?.overpayment_alert === true ||
    item?.claim?.underpayment_alert === true ||
    item?.claim?.overpayment_alert === true
  );
};

const isPaidClaim = (item: any) => {
  const status = statusOf(item);
  const paymentStatus = actualPaymentStatus(item);

  if (isPaymentReconciliationClaim(item)) return false;

  return (
    paymentStatus === "PAID" ||
    status === "PAID" ||
    pipelineOf(item).paid === true
  );
};

const isAutoApprovedClaim = (item: any) => {
  const claim = claimOf(item);
  const status = statusOf(item);

  return (
    String(item?.confidence_status || claim?.confidence_status || "").toUpperCase() === "AUTO_APPROVED" ||
    String(item?.status || claim?.status || "").toUpperCase() === "AUTO_APPROVED" ||
    item?.auto_approved === true ||
    claim?.auto_approved === true ||
    pipelineOf(item).auto_accepted === true
  );
};

const isActiveClaim = (item: any) => {
  const status = statusOf(item);

  if (isCompletedCommandCenterClaim(item)) return false;
  if (HITL_KPI_STATUSES.has(status)) return false;

  return [
    "IN_PROGRESS",
    "PROCESSING",
    "ACTIVE",
    "RUNNING",
    "QUEUED",
    "PENDING",
    "OCR_COMPLETED",
    "VALIDATION_COMPLETED",
    "COMPLIANCE_COMPLETED",
    "SUBMITTED",
    "PENDING_CLEARINGHOUSE",
    "WAITING_FOR_APPROVAL",
    "DENIAL_AI_RUNNING",
    "DENIAL_AI_REQUIRED",
  ].includes(status);
};

const getProcessingHours = (item: any) => {
  const raw =
    item?.processing_duration ??
    item?.claim?.processing_duration ??
    item?.pipeline?.processing_duration ??
    item?.duration_seconds ??
    item?.claim?.duration_seconds;

  const seconds = Number(raw || 0);

  if (!Number.isFinite(seconds) || seconds <= 0) return null;

  // If backend already sends hours, keep it. If it sends seconds, convert.
  return seconds > 72 ? seconds / 3600 : seconds;
};

const metrics = useMemo(() => {
  const total = kpiData.length;

  const active = kpiData.filter(isActiveClaim).length;

  const hitl = kpiData.filter((item) => {
    const status = statusOf(item);
    return (
      HITL_KPI_STATUSES.has(status) ||
      item?.review_required === true ||
      item?.approval_required === true ||
      item?.pipeline_paused === true ||
      item?.case?.status === "OPEN"
    );
  }).length;

  const pendingReview = kpiData.filter((item) => {
    const status = statusOf(item);
    return (
      !isCompletedCommandCenterClaim(item) &&
      (
        status.includes("REVIEW") ||
        status.includes("HITL") ||
        item?.review_required === true ||
        item?.approval_required === true
      )
    );
  }).length;

  const denied = kpiData.filter((item) => {
    const status = statusOf(item);
    const denialStatus = String(
      item?.denial_status ||
        item?.denial_ai?.status ||
        item?.claim?.denial_status ||
        ""
    ).toUpperCase();

    return (
      ["DENIED", "REJECTED", "DENIAL_ANALYZED"].includes(status) ||
      ["DENIED", "DENIAL_ANALYZED"].includes(denialStatus) ||
      pipelineOf(item).clearinghouse_rejected === true
    );
  }).length;

  const paid = kpiData.filter(isPaidClaim).length;
  const autoApproved = kpiData.filter(isAutoApprovedClaim).length;

  const revenue = kpiData.reduce((sum, item) => sum + amountOf(item), 0);

  const slaBreaches = kpiData.filter((item) =>
    String(item.sla_status || item.case?.sla_status || "").toUpperCase() === "OVERDUE"
  ).length;

  const denialRate = total ? (denied / total) * 100 : 0;
  const payerApproval = total ? (paid / total) * 100 : 0;

  const ocrValues = kpiData
    .map((item) => {
      const extraction = extractionOf(item);
      return normalizePercent(
        extraction.ocr_quality ??
          extraction.extraction_confidence ??
          item?.ocr_quality ??
          item?.extraction_confidence ??
          item?.claim?.extraction_confidence
      );
    })
    .filter((value) => value > 0);

  const ocrAccuracy = ocrValues.length
    ? ocrValues.reduce((sum, value) => sum + value, 0) / ocrValues.length
    : 0;

  const aiValues = kpiData
    .map((item) =>
      normalizePercent(
        item?.ai_accuracy ??
          item?.analytics?.ai_accuracy ??
          item?.analytics?.ai_confidence ??
          item?.claim?.confidence ??
          item?.confidence
      )
    )
    .filter((value) => value > 0);

  const aiAccuracy = aiValues.length
    ? aiValues.reduce((sum, value) => sum + value, 0) / aiValues.length
    : 0;

  const processingHours = kpiData
    .map(getProcessingHours)
    .filter((value): value is number => value !== null);

  const avgProcessing = processingHours.length
    ? Math.round(processingHours.reduce((sum, value) => sum + value, 0) / processingHours.length)
    : 0;

  const avgCycleTime =
    avgProcessing > 0
      ? `${Math.floor(avgProcessing / 24)}d ${avgProcessing % 24}h`
      : "0d 0h";

  return {
    total,
    active,
    hitl,
    pendingReview,
    denied,
    paid,
    autoApproved,
    revenue,
    avgCycleTime,
    slaBreaches,
    denialRate,
    aiAccuracy,
    ocrAccuracy,
    payerApproval,
    avgProcessing,
  };
}, [kpiData]);

  const metricTrends = useMemo(() => {
    const { currentWeekClaims, previousWeekClaims } = getClaimTrendPeriods(kpiData);
    const countPeriodBy = (claims: RecordType[], predicate: (item: RecordType) => boolean) => claims.filter(predicate).length;
    const activePredicate = (item: RecordType) => !isCompletedCommandCenterClaim(item) && ["IN_PROGRESS", "PROCESSING", "ACTIVE", "RUNNING", "QUEUED", "PENDING"].includes(statusOf(item));
    const hitlPredicate = (item: RecordType) => HITL_KPI_STATUSES.has(statusOf(item));
    const pendingReviewPredicate = (item: RecordType) => !isCompletedCommandCenterClaim(item) && (statusOf(item).includes("PENDING") || statusOf(item).includes("REVIEW"));
    const deniedPredicate = (item: RecordType) => ["DENIED", "REJECTED"].includes(statusOf(item)) || pipelineOf(item).clearinghouse_rejected;
    const paidPredicate = (item: RecordType) => COMPLETED_KPI_STATUSES.has(statusOf(item));
    const currentRevenue = currentWeekClaims.reduce((sum, item) => sum + amountOf(item), 0);
    const previousRevenue = previousWeekClaims.reduce((sum, item) => sum + amountOf(item), 0);

    return {
      total: calculateTrend(currentWeekClaims.length, previousWeekClaims.length),
      active: calculateTrend(countPeriodBy(currentWeekClaims, activePredicate), countPeriodBy(previousWeekClaims, activePredicate)),
      hitl: calculateTrend(countPeriodBy(currentWeekClaims, hitlPredicate), countPeriodBy(previousWeekClaims, hitlPredicate)),
      pendingReview: calculateTrend(countPeriodBy(currentWeekClaims, pendingReviewPredicate), countPeriodBy(previousWeekClaims, pendingReviewPredicate)),
      denied: calculateTrend(countPeriodBy(currentWeekClaims, deniedPredicate), countPeriodBy(previousWeekClaims, deniedPredicate)),
      paid: calculateTrend(countPeriodBy(currentWeekClaims, paidPredicate), countPeriodBy(previousWeekClaims, paidPredicate)),
      revenue: calculateTrend(currentRevenue, previousRevenue),
    };
  }, [kpiData]);

  const revenueTrend = useMemo(
    () =>
      Array.from({ length: 14 }, (_, index) => ({
        day: `D${index + 1}`,
        revenue: Math.round((metrics.revenue / 14 || 0) * (0.72 + index * 0.035 + (index % 3) * 0.04)),
        claims: Math.max(1, Math.round((metrics.total || 8) * (0.4 + index * 0.035))),
        denials: Math.max(0, Math.round((metrics.denied || 1) * (0.25 + (index % 4) * 0.16))),
      })),
    [metrics]
  );

  const payerRows = useMemo(() => {
    const map: Record<string, { payer: string; total: number; denied: number; paid: number; revenue: number }> = {};

    allClaims.forEach((item) => {
      const payer = payerOf(item);
      map[payer] ||= { payer, total: 0, denied: 0, paid: 0, revenue: 0 };
      map[payer].total += 1;
      map[payer].revenue += amountOf(item);
      if (["DENIED", "REJECTED"].includes(statusOf(item))) map[payer].denied += 1;
      if (["PAID", "COMPLETED"].includes(statusOf(item)) || pipelineOf(item).paid) map[payer].paid += 1;
    });

    return Object.values(map)
      .filter((row) => row.total > 0)
      .sort((a, b) => b.total - a.total)
      .slice(0, 6);
  }, [allClaims]);

  const agentNodes = ["OCR", "Validation", "Compliance", "Submission", "Clearinghouse", "Denial AI", "Payment", "Learning", "Analytics"].map((name) => {
    const event = events.find((item) => `${item.agent} ${item.step} ${item.type}`.toLowerCase().includes(name.toLowerCase().split(" ")[0]));
    return {
      name,
      status: event?.status || (name === "OCR" ? "COMPLETED" : "MONITORING"),
      confidence: Math.round(Number(event?.data?.confidence || event?.metadata?.confidence || 0.88) * 100),
    };
  });

  const exportRepositoryCsv = () => {
    const rows = [
      ["Claim ID", "Patient", "Payer", "Status", "Payment Amount", "Completed At"],
      ...displayedRepositoryClaims.map((claim) => [
        claim.claim_id,
        patientNameOf(claim),
        typeof claim.payer === "string" ? claim.payer : claim.payer?.name || "Unknown",
        claim.status,
        claim.payment_amount || 0,
        completedAtOf(claim),
      ]),
    ];
    const csv = rows.map((row) => row.map((cell) => `"${String(cell ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "command-center-claims.csv";
    anchor.click();
    URL.revokeObjectURL(url);
  };
    const formatStatusText = (value?: string | null) => {
    if (!value) return "-";

    return String(value)
      .replace(/_/g, " ")
      .toLowerCase()
      .replace(/\b\w/g, (char) => char.toUpperCase());
  };

  const truncateText = (value: unknown, maxLength = 22) => {
    const text = value === null || value === undefined || value === "" ? "-" : String(value);

    if (text.length <= maxLength) return text;

    return `${text.slice(0, maxLength - 3)}...`;
  };
  const renderPdfTab = (title: string, url?: string) => {
    const resolvedUrl = docUrl(url);
    return (
      <div className="cc-pdf-tab">
        <div className="cc-document-toolbar">
          <strong>{title}</strong>
          <div>
            <button disabled={!resolvedUrl} onClick={() => resolvedUrl && window.open(resolvedUrl, "_blank", "noopener,noreferrer")}><ExternalLink size={15} /> Open</button>
            <a className={!resolvedUrl ? "disabled" : ""} href={resolvedUrl || undefined} download><Download size={15} /> Download</a>
            <button disabled={!resolvedUrl} onClick={() => resolvedUrl && window.open(resolvedUrl, "_blank", "noopener,noreferrer")?.print()}><Printer size={15} /> Print</button>
          </div>
        </div>
        {resolvedUrl ? <iframe title={title} src={resolvedUrl} /> : <div className="cc-empty-doc">No finalized {title} artifact is available yet.</div>}
      </div>
    );
  };

  const renderDetailTab = () => {
    if (!selectedClaim) return null;
    const claim = selectedClaim.claim || selectedClaim;
    const payment = selectedClaim.payment || {};
    const audit = selectedClaim.audit_history?.length ? selectedClaim.audit_history : selectedClaim.events || [];
    const docs = selectedClaim.documents || [];
    if (detailTab === "CMS1500") return renderPdfTab("CMS1500", selectedClaim.cms1500_pdf_url);
    if (detailTab === "UB04") return renderPdfTab("UB04", selectedClaim.ub04_pdf_url);
    if (detailTab === "EDI") {
      const ediPayload = JSON.stringify(selectedClaim.edi || {}, null, 2);
      return (
        <div className="cc-code-panel">
          <div className="cc-document-toolbar">
            <strong>837 Payload And Responses</strong>
            <button onClick={() => navigator.clipboard?.writeText(ediPayload)}><Copy size={15} /> Copy</button>
          </div>
          <pre>{ediPayload}</pre>
        </div>
      );
    }
    if (detailTab === "Payment") {
      return (
        <div className="cc-detail-grid">
          {[
            ["Billed Amount", money(Number(selectedClaim.total_charge || claim.total_charge || 0))],
            ["Allowed Amount", money(Number(payment.allowed_amount || selectedClaim.payment_amount || 0))],
            ["Paid Amount", money(Number(selectedClaim.payment_amount || payment.paid_amount || 0))],
            ["Deductible", money(Number(payment.deductible || 0))],
            ["Coinsurance", money(Number(payment.coinsurance || 0))],
            ["Patient Responsibility", money(Number(payment.patient_responsibility || 0))],
          ].map(([label, value]) => {
            const fullValue = value === null || value === undefined || value === "" ? "-" : String(value);
            const displayValue = truncateText(fullValue, 24);

            return (
              <div className="cc-info-tile" key={label} title={fullValue}>
              <span>{label}</span>
              <strong>{displayValue}</strong>
            </div>
          );
       })}
        </div>
      );
    }
    if (detailTab === "Audit Trail") {
      return (
        <div className="cc-timeline">
          {audit.map((entry: any, index: number) => (
            <div key={`${entry.timestamp || entry.started_at || index}-${index}`}>
              <i>{index + 1}</i>
              <div><strong>{entry.stage || entry.agent || entry.status || "Pipeline Event"}</strong><span>{entry.status || entry.message || "Completed"} • {entry.timestamp || entry.completed_at || entry.started_at || "timestamp pending"}</span></div>
            </div>
          ))}
          {!audit.length && <div className="cc-empty-doc">No audit events recorded.</div>}
        </div>
      );
    }
    if (detailTab === "Analytics") {
      const analytics = selectedClaim.analytics || {};
      return (
        <div className="cc-detail-grid">
          {[
            ["Processing Time", `${selectedClaim.processing_duration || 0}s`],
            ["AI Confidence", pct(Number(analytics.ai_confidence || claim.confidence || 0) <= 1 ? Number(analytics.ai_confidence || claim.confidence || 0) * 100 : Number(analytics.ai_confidence || claim.confidence || 0))],
            ["Denial Probability", pct(Number(analytics.denial_probability || 0) <= 1 ? Number(analytics.denial_probability || 0) * 100 : Number(analytics.denial_probability || 0))],
            ["Automation Score", pct(Number(analytics.automation_score || 0))],
          ].map(([label, value]) => <div className="cc-info-tile" key={label}><span>{label}</span><strong>{value}</strong></div>)}
        </div>
      );
    }
    if (detailTab === "Documents") {
      return (
        <div className="cc-doc-list">
          {docs.map((doc: any) => (
            <a href={docUrl(doc.url)} target="_blank" rel="noreferrer" key={doc.label}><FileText size={18} /><span>{doc.label}</span><Download size={16} /></a>
          ))}
        </div>
      );
    }
    return (
      <div className="cc-detail-grid">
        {[
          ["Patient", patientNameOf(selectedClaim)],
          ["Payer", typeof selectedClaim.payer === "string" ? selectedClaim.payer : selectedClaim.payer?.name || "Unknown"],
          ["Date Of Service", selectedClaim.date_of_service || claim.date_of_service || "-"],
          ["Final Status", formatStatusText(selectedClaim.status)],,
          ["Payment Status", selectedClaim.payment_status || "-"],
          ["Denial Status", selectedClaim.denial_status || "-"],
          ["Completed At", completedAtOf(selectedClaim) || "-"],
          ["Processing Duration", `${selectedClaim.processing_duration || 0}s`],
          ["Command Center", isCompletedCommandCenterClaim(selectedClaim) ? "Yes" : "No"],
          ["Pipeline Progress", `${progressOf(selectedClaim)}%`],
          ["Payment Outcome", selectedClaim.payment_status || selectedClaim.payment?.status || "-"],
          ["Final Denial Risk", `${Math.round(riskOf(selectedClaim))}%`],
          ["Analytics Summary", selectedClaim.analytics?.summary || selectedClaim.analytics_summary || "-"],
        ].map(([label, value]) => <div className="cc-info-tile" key={label}><span>{label}</span><strong>{value}</strong></div>)}
      </div>
    );
  };

  if (
    loading &&
    records.length === 0
  ) {
    return (
      <ClaimTableSkeleton />
    );
  }

  const kpis = [
    ["Total Claims", metrics.total, metricTrends.total, FileCheck2, "#2563eb", trend(metrics.total, 1)],
    ["Active Claims", metrics.active, metricTrends.active, Activity, "#14b8a6", trend(metrics.active, 2)],
    ["HITL Required", metrics.hitl, metricTrends.hitl, Users, "#f97316", trend(metrics.hitl, 3)],
    ["Pending Review", metrics.pendingReview, metricTrends.pendingReview, Clock3, "#8b5cf6", trend(metrics.pendingReview, 4)],
    ["Denied Claims", metrics.denied, metricTrends.denied, ShieldAlert, "#ef4444", trend(metrics.denied, 5)],
    ["Paid Claims", metrics.paid, metricTrends.paid, BadgeCheck, "#22c55e", trend(metrics.paid, 6)],
    ["Auto Approved", metrics.autoApproved, null, Zap, "#06b6d4", trend(metrics.autoApproved, 7)],
    ["Total Revenue Generated", money(metrics.revenue), metricTrends.revenue, DollarSign, "#16a34a", trend(metrics.revenue / 1000, 8)],
    ["Average Cycle Time", metrics.avgCycleTime, null, TimerReset, "#7c3aed", trend(metrics.avgProcessing, 9)],
    ["SLA Breaches", metrics.slaBreaches, null, AlertTriangle, "#ea580c", trend(metrics.slaBreaches, 10)],
    ["Denial Rate", pct(metrics.denialRate), null, BarChart3, "#dc2626", trend(metrics.denialRate, 11)],
    ["AI Accuracy", pct(metrics.aiAccuracy), null, BrainCircuit, "#4f46e5", trend(metrics.aiAccuracy, 12)],
    ["OCR Accuracy", pct(metrics.ocrAccuracy), null, Sparkles, "#0891b2", trend(metrics.ocrAccuracy, 13)],
    ["Payer Approval", pct(metrics.payerApproval), null, HeartPulse, "#059669", trend(metrics.payerApproval, 14)],
    ["Avg Processing", `${metrics.avgProcessing}h`, null, Gauge, "#0f766e", trend(metrics.avgProcessing, 15)],
  ];

  return (
    <div className="ec-page">
      <section className="ec-hero">
        <div>
          <p className="ec-eyebrow">Enterprise AI Healthcare Revenue Command Center</p>
          <h1>Revenue Orchestration Control Tower</h1>
          <p>Realtime claim flow, AI agent observability, clearinghouse intelligence, case routing, and revenue outcomes.</p>
        </div>
        <div className="ec-live-card">
          <span className="ec-live-dot" />
          <div>
            <strong>Realtime orchestration online</strong>
            <small>{lastUpdated ? `Refreshed ${lastUpdated.toLocaleTimeString()}` : "Waiting for telemetry"}</small>
          </div>
        </div>
      </section>

      <section className="ec-panel cc-repository">
        <div className="ec-panel-title">
          <div>
            <h2>Finalized Claim Repository</h2>
            <p>Completed claim records, healthcare forms, EDI payloads, payments, audit history, and downloadable artifacts.</p>
          </div>
          <div className="cc-repository-actions">
            <button onClick={loadRepository} disabled={repositoryLoading}>{repositoryLoading ? "Refreshing..." : "Refresh"}</button>
            <button onClick={exportRepositoryCsv}><Download size={15} /> Export CSV</button>
          </div>
        </div>
        <div className="cc-repository-filters">
          <label><Search size={15} /><input value={repositorySearch} onChange={(event) => setRepositorySearch(event.target.value)} placeholder="Search claim, patient, payer" /></label>
          <select value={repositoryStatus} onChange={(event) => setRepositoryStatus(event.target.value)}>
            <option value="ALL">All finalized</option>
            <option value="APPROVED">Approved</option>
            <option value="PAID">Paid</option>
            <option value="REJECTED">Rejected</option>
            <option value="CLOSED">Closed</option>
            <option value="COMPLETED">Completed</option>
          </select>
        </div>
        <div className="cc-repository-table">
          <div className="cc-repository-head">
            <span>Claim ID</span><span>Patient</span><span>Payer</span><span>DOS</span><span>Status</span><span>Payment</span><span>Denial</span><span>Completed</span><span>Duration</span><span>Actions</span>
          </div>
          {displayedRepositoryClaims.map((claim) => (
            <div className="cc-repository-row" key={claimIdOf(claim)}>
              <span><b>{claimIdOf(claim)}</b></span>
              <span>{patientNameOf(claim)}</span>
              <span>{payerOf(claim)}</span>
              <span>{claim.date_of_service || "-"}</span>
              <span className="cc-status-stack">
                <i className={`cc-status cc-${String(claim.status || "").toLowerCase()}`}>{isCompletedCommandCenterClaim(claim) ? "COMPLETED" : claim.status}</i>
                {isCompletedCommandCenterClaim(claim) && <i className="cc-status cc-command-center">COMMAND CENTER</i>}
              </span>
              <span>{money(Number(claim.payment_amount || 0))}</span>
              <span>{claim.denial_status || "CLEARED"}</span>
              <span>{completedAtOf(claim) ? new Date(completedAtOf(claim)).toLocaleString() : "-"}</span>
              <span>{isCompletedCommandCenterClaim(claim) ? `${progressOf(claim)}% / ${claim.processing_duration || 0}s` : `${claim.processing_duration || 0}s`}</span>
              <span><button onClick={() => openRepositoryClaim(claimIdOf(claim))}>View Record</button></span>
            </div>
          ))}
          {!displayedRepositoryClaims.length && (
            <div className="cc-empty-doc">
              {repositoryLoading
                ? "Loading finalized claims..."
                : repositoryStatus === "COMPLETED"
                ? "No completed Command Center claims are available yet."
                : "No claims match this Command Center filter."}
            </div>
          )}
        </div>
      </section>

      <section className="ec-kpi-grid">
        {kpis.map(([label, value, delta, Icon, color, points]: any) => (
          <article className="ec-kpi-card" key={label} style={{ ["--accent" as string]: color }}>
            <div className="ec-kpi-head">
              <span><Icon size={17} /> {label}</span>
              {delta !== null && (
                <em className={delta >= 0 ? "trend-up" : "trend-down"}>
                  {delta >= 0 ? "\u2191" : "\u2193"} {Math.abs(delta)}% vs last 7 days
                </em>
              )}
            </div>
            <strong>{value}</strong>
            <Sparkline data={points} color={color} />
          </article>
        ))}
      </section>

      <section className="ec-command-grid">
        <article className="ec-panel ec-wide">
          <div className="ec-panel-title">
            <div>
              <h2>Revenue And Throughput Trends</h2>
              <p>Daily streaming view of reimbursement velocity and claim volume.</p>
            </div>
            <TrendingUp size={20} />
          </div>
          <ResponsiveContainer width="100%" height={320}>
            <AreaChart data={revenueTrend}>
              <defs>
                <linearGradient id="revenueFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#2563eb" stopOpacity={0.35} />
                  <stop offset="95%" stopColor="#2563eb" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#dbeafe" />
              <XAxis dataKey="day" />
              <YAxis />
              <Tooltip />
              <Area type="monotone" dataKey="revenue" stroke="#2563eb" fill="url(#revenueFill)" strokeWidth={3} name="Revenue" />
              <Line type="monotone" dataKey="claims" stroke="#14b8a6" strokeWidth={2} name="Claims" />
              <Line type="monotone" dataKey="denials" stroke="#ef4444" strokeWidth={2} name="Denials" />
            </AreaChart>
          </ResponsiveContainer>
        </article>

        <article className="ec-panel">
          <div className="ec-panel-title">
            <div>
              <h2>Automation Health</h2>
              <p>AI accuracy, OCR confidence, payer approval.</p>
            </div>
            <Bot size={20} />
          </div>
          <ResponsiveContainer width="100%" height={295}>
            <RadialBarChart innerRadius="28%" outerRadius="95%" data={[
              { name: "AI Accuracy", value: metrics.aiAccuracy, fill: "#4f46e5" },
              { name: "OCR Accuracy", value: metrics.ocrAccuracy, fill: "#06b6d4" },
              { name: "Payer Approval", value: metrics.payerApproval, fill: "#22c55e" },
            ]}>
              <RadialBar dataKey="value" cornerRadius={8} />
              <Tooltip />
            </RadialBarChart>
          </ResponsiveContainer>
        </article>

        <article className="ec-panel">
          <div className="ec-panel-title">
            <div>
              <h2>Realtime Orchestration Map</h2>
              <p>Live stage health from websocket events.</p>
            </div>
            <GitBranch size={20} />
          </div>
          <div className="ec-agent-map">
            {agentNodes.map((agent, index) => (
              <div className="ec-agent-node" key={agent.name}>
                <i style={{ background: palette[index % palette.length] }}>{index + 1}</i>
                <div>
                  <strong>{agent.name}</strong>
                  <span>{agent.status}</span>
                </div>
                <b>{agent.confidence}%</b>
              </div>
            ))}
          </div>
        </article>

        <article className="ec-panel">
          <div className="ec-panel-title">
            <div>
              <h2>Claim State Mix</h2>
              <p>Operational distribution.</p>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={285}>
            <PieChart>
              <Pie
                data={[
                  { name: "Paid", value: metrics.paid },
                  { name: "Active", value: metrics.active },
                  { name: "HITL", value: metrics.hitl },
                  { name: "Denied", value: metrics.denied },
                ]}
                dataKey="value"
                innerRadius={58}
                outerRadius={96}
                paddingAngle={4}
              >
                {palette.map((color) => <Cell key={color} fill={color} />)}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </article>

        <article className="ec-panel ec-wide">
          <div className="ec-panel-title">
            <div>
              <h2>Payer Intelligence</h2>
              <p>Approval, denial, SLA risk, revenue, and forecast signal by payer.</p>
            </div>
          </div>
          <div className="ec-table">
            <div className="ec-table-head">
              <span>Payer</span><span>Approval %</span><span>Denial %</span><span>Avg Time</span><span>SLA Risk</span><span>Revenue</span>
            </div>
            {payerRows.length > 0 ? (
              payerRows.map((payer, index) => {
                const approval = payer.total ? (payer.paid / payer.total) * 100 : 0;
                const denial = payer.total ? (payer.denied / payer.total) * 100 : 0;

                return (
                  <div className="ec-table-row" key={payer.payer}>
                    <span>
                      <b>{payer.payer}</b>
                      <small>Forecast {denial > 25 ? "watch" : "stable"}</small>
                    </span>
                    <span>{pct(approval)}</span>
                    <span>{pct(denial)}</span>
                    <span>{18 + index * 4}h</span>
                    <span>
                      <i className={denial > 25 ? "risk-high" : "risk-low"}>
                        {denial > 25 ? "Elevated" : "Low"}
                      </i>
                    </span>
                    <span>{money(payer.revenue)}</span>
                  </div>
                );
              })
            ) : (
              <div className="ec-table-row">
                <span>
                  <b>No payer data</b>
                  <small>Backend data unavailable</small>
                </span>
                <span>0%</span>
                <span>0%</span>
                <span>0h</span>
                <span>
                  <i className="risk-low">Low</i>
                </span>
                <span>{money(0)}</span>
              </div>
            )}
          </div>
        </article>

        <article className="ec-panel">
          <div className="ec-panel-title">
            <div>
              <h2>Bottleneck Alerts</h2>
              <p>SLA and queue signals.</p>
            </div>
          </div>
          <div className="ec-alert-list">
            <div><AlertTriangle size={16} /><span>{metrics.hitl} HITL cases need routing review</span></div>
            <div><Clock3 size={16} /><span>{bulkProgress.processing} claims currently processing</span></div>
            <div><ShieldAlert size={16} /><span>{pct(metrics.denialRate)} denial rate across active population</span></div>
          </div>
        </article>

        <article className="ec-panel ec-wide">
          <RealtimeAgentFeed events={events.slice(0, 12)} title="Enterprise Activity Stream" />
        </article>
      </section>

      {selectedClaim && (
        <div className="cc-detail-backdrop" role="dialog" aria-modal="true">
          <div className="cc-detail-modal">
            <aside className="cc-detail-summary">
              <button className="cc-close" onClick={() => setSelectedClaim(null)}><X size={18} /></button>
              <p className="ec-eyebrow">Finalized Claim</p>
              <h2>{claimIdOf(selectedClaim)}</h2>
              <span className={`cc-status cc-${String(selectedClaim.status || "").toLowerCase()}`}>{selectedClaim.status}</span>
              <div className="cc-summary-list">
                <div><span>Patient</span><strong>{patientNameOf(selectedClaim)}</strong></div>
                <div><span>Payer</span><strong>{payerOf(selectedClaim)}</strong></div>
                <div><span>Total Charges</span><strong>{money(Number(selectedClaim.total_charge || 0))}</strong></div>
                <div><span>Payment</span><strong>{money(Number(selectedClaim.payment_amount || 0))}</strong></div>
                <div><span>Completed</span><strong>{completedAtOf(selectedClaim) ? new Date(completedAtOf(selectedClaim)).toLocaleString() : "-"}</strong></div>
              </div>
            </aside>
            <main className="cc-detail-main">
              <div className="cc-tabs">
                {["Overview", "CMS1500", "UB04", "EDI", "Payment", "Audit Trail", "Analytics", "Documents"].map((tab) => (
                  <button className={detailTab === tab ? "active" : ""} onClick={() => setDetailTab(tab)} key={tab}>{tab}</button>
                ))}
              </div>
              <div className="cc-tab-body">{renderDetailTab()}</div>
            </main>
          </div>
        </div>
      )}
    </div>
  );
};

export default Dashboard;
