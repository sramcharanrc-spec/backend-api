import { api } from "@/lib/api";

export type StageStatus = "idle" | "running" | "ok" | "warn" | "error";
export type StageKey =
  | "claimGeneration"
  | "claimScrubbing"
  | "submission"
  | "acknowledgment"
  | "denialManagement"
  | "paymentPosting"
  | "reporting";

export interface BatchRCMStatus {
  batchId: string;
  lastUpdatedISO?: string;
  stages: Record<
    StageKey,
    { status: StageStatus; kpis: Record<string, string | number> }
  >;
}

export async function getRCMBatch(batchId: string) {
  const res = await api.get<BatchRCMStatus>(`/api/rcm/batch/${batchId}`);
  return res.data;
}
