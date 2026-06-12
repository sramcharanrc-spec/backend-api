import { useCallback, useEffect, useRef, useState } from "react";
import { API_URL } from "../../../config";
import { normalizeClaimsResponse } from "../../../utils/claimSync";
import { timestampOf } from "../utils/claimDates";
import { getClaimId } from "../utils/claimGetters";
import { hydrateClaim } from "../utils/claimHydration";
import { mergeClaimLists } from "../utils/claimMerge";

const isQueuedPlaceholder = (item: any) => {
  const status = String(item?.status || item?.pipeline_state || "").toUpperCase();
  return Boolean(item?.__queued_placeholder || status === "QUEUED");
};

const shouldKeepQueuedPlaceholder = (item: any) => {
  if (!isQueuedPlaceholder(item)) return false;

  const timestamp = timestampOf(item);
  if (!timestamp) return true;

  return Date.now() - timestamp < 2 * 60 * 1000;
};

type UseClaimRecordsOptions = {
  autoLoad?: boolean;
  page?: number;
  limit?: number;
};

export const useClaimRecords = ({
  autoLoad = true,
  page = 1,
  limit = 200,
}: UseClaimRecordsOptions = {}) => {
  const [items, setItems] = useState<any[]>([]);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [backendHealthy, setBackendHealthy] = useState<boolean | null>(null);

  const itemsRef = useRef<any[]>([]);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    itemsRef.current = items;
  }, [items]);

  const mergeItems = useCallback((incoming: any[]) => {
    setItems((prev) => mergeClaimLists(prev, incoming));
  }, []);

  const removeClaim = useCallback((claimId: string) => {
    setItems((prev) => prev.filter((item) => getClaimId(item) !== claimId));
  }, []);

  const refreshClaims = useCallback(async () => {
    abortRef.current?.abort();

    const controller = new AbortController();
    abortRef.current = controller;

    setIsRefreshing(true);

    try {
      const response = await fetch(`${API_URL}/records?page=${page}&limit=${limit}`, {
        signal: controller.signal,
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(data?.detail || data?.message || `Records request failed (${response.status})`);
      }

      const claims = normalizeClaimsResponse(data)
        .map((item: any) => hydrateClaim(item))
        .filter((item: any) => getClaimId(item));

      let nextItems: any[] = [];

      setItems((prev) => {
        const serverIds = new Set(claims.map((item: any) => getClaimId(item)).filter(Boolean));
        const queuedPlaceholders = prev.filter((item) => {
          const id = getClaimId(item);
          return id && !serverIds.has(id) && shouldKeepQueuedPlaceholder(item);
        });

        nextItems = mergeClaimLists(queuedPlaceholders, claims);
        return nextItems;
      });

      itemsRef.current = nextItems;
      setBackendHealthy(true);

      return nextItems;
    } catch (error: any) {
      if (error?.name !== "AbortError") {
        console.error("[claims] refresh failed", error);
        setBackendHealthy(false);
      }

      return [];
    } finally {
      setIsRefreshing(false);

      if (abortRef.current === controller) {
        abortRef.current = null;
      }
    }
  }, [page, limit]);

  useEffect(() => {
    if (!autoLoad) return;
    void refreshClaims();

    return () => {
      abortRef.current?.abort();
    };
  }, [autoLoad, refreshClaims]);

  return {
    items,
    setItems,
    itemsRef,
    isRefreshing,
    backendHealthy,
    refreshClaims,
    mergeItems,
    removeClaim,
    getClaimId,
  };
};
