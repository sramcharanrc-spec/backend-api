import React, { useEffect, useState } from "react";



// RCMInlineStatus.tsx (hardened)
export default function RCMInlineStatus({
  batchId,
  statusUrl = (id: string) => `http://127.0.0.1:8000/api/rcm/batch/${id}`,
  pollMs = 6000,
}: {
  batchId: string | null;
  statusUrl?: (batchId: string) => string;
  pollMs?: number;
}) {
  const [data, setData] = useState<BatchRCMStatus | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  const load = async () => {
    if (!batchId) return;
    try {
      setLoading(true);
      setErr(null);
      const url = statusUrl(batchId);
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status} @ ${url}`);
      const json: BatchRCMStatus = await res.json();
      setData(json);
    } catch (e: any) {
      console.error("[RCMInlineStatus] fetch failed:", e);
      setErr(e?.message ?? "Failed to load");
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    if (!batchId) return;
    const id = setInterval(load, pollMs);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [batchId, pollMs]);

  if (!batchId) {
    return (
      <div className="rounded-xl bg-white/5 p-4 text-sm text-blue-200">
        Upload complete? We’ll show claim processing here after we receive a <b>batchId</b>.
      </div>
    );
  }

  return (
    <section className="rounded-2xl bg-gradient-to-br from-indigo-700 to-indigo-900 text-white p-4 shadow-lg">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold">RCM Status for Batch {batchId}</h3>
          <p className="text-indigo-200 text-xs">
            Tracks this upload through claim → scrub → submit → ack → denial → payment → reporting
          </p>
        </div>
        <button
          onClick={load}
          className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 transition"
          title="Refresh"
        >
          <RefreshCcw className="w-4 h-4" />
          <span className="text-sm hidden md:inline">{loading ? "Loading…" : "Refresh"}</span>
        </button>
      </div>

      {err && (
        <div className="mt-3 text-xs bg-rose-900/40 border border-rose-700/40 rounded-lg p-2">
          <div className="font-medium text-rose-100">Couldn’t fetch batch status</div>
          <div className="text-rose-200/90">
            {err}. Ensure the endpoint is reachable and CORS is enabled.
          </div>
        </div>
      )}

      {!err && (
        <StagesGrid data={data} />
      )}

      <div className="mt-3 text-xs text-indigo-200">
        Last updated: {data?.lastUpdatedISO ? new Date(data.lastUpdatedISO).toLocaleString() : "—"}
      </div>
    </section>
  );
}

function StagesGrid({ data }: { data: BatchRCMStatus | null }) {
  const stageOrder: StageKey[] = [
    "claimGeneration",
    "claimScrubbing",
    "submission",
    "acknowledgment",
    "denialManagement",
    "paymentPosting",
    "reporting",
  ];
  return (
    <div className="mt-3 grid grid-cols-1 md:grid-cols-3 xl:grid-cols-7 gap-3">
      {stageOrder.map((key) => {
        const Icon = ICON[key];
        const st = data?.stages[key];
        const status = st?.status ?? "idle";
        const kpis = st?.kpis ?? {};
        return (
          <div key={key} className="bg-white/5 rounded-xl p-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Icon className="w-4 h-4" />
                <span className="font-medium">{label(key)}</span>
              </div>
              <span className={`px-2 py-0.5 rounded-full text-xs ${BADGE[status]}`}>
                {statusText(status)}
              </span>
            </div>
            <ul className="mt-2 space-y-1">
              {Object.entries(kpis).slice(0, 2).map(([k, v]) => (
                <li key={k} className="flex items-center justify-between text-sm">
                  <span className="text-indigo-200">{k}</span>
                  <span className="font-semibold">{v as any}</span>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
