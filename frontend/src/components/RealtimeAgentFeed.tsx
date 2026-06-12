import React from "react";
import { PipelineEvent } from "../services/websocket";
import ClaimStatusBadge from "./ClaimStatusBadge";

type Props = {
  events: PipelineEvent[];
  title?: string;
};

const RealtimeAgentFeed: React.FC<Props> = ({ events, title = "Live Agent Feed" }) => (
  <section className="profile-card">
    <h3>{title}</h3>
    <div className="space-y-2 max-h-72 overflow-auto">
      {events.slice(0, 20).map((event, index) => (
        <div key={`${event.timestamp}-${index}`} className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs">
          <div className="flex items-center justify-between gap-3">
            <strong className="text-slate-800">{event.agent || event.step || event.type}</strong>
            <ClaimStatusBadge status={event.status} />
          </div>
          <div className="mt-1 text-slate-500">
            {event.claim_id || event.data?.claim_id || "global"} - {event.timestamp ? new Date(event.timestamp).toLocaleString() : "now"}
          </div>
        </div>
      ))}
      {events.length === 0 && <div className="text-sm text-slate-500">Waiting for websocket activity...</div>}
    </div>
  </section>
);

export default RealtimeAgentFeed;
