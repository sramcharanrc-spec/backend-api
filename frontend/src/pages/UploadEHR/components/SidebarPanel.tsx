import React, { useMemo } from "react";

type SidebarPanelProps = {
  events: any[];
};

const getEventKey = (event: any, index: number) => {
  return (
    event.id ||
    event.event_id ||
    event.trace_id ||
    `${event.type || "event"}-${event.claim_id || "global"}-${event.stage || ""}-${event.status || ""}-${event.timestamp || index}`
  );
};

const formatEventTime = (timestamp?: string) => {
  if (!timestamp) return "now";

  const date = new Date(timestamp);

  if (Number.isNaN(date.getTime())) {
    return "now";
  }

  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
};

const formatStage = (value?: string) =>
  String(value || "")
    .replace(/_/g, " ")
    .trim();

const getEventTitle = (event: any) =>
  event.agent || event.current_agent || event.data?.agent || event.type || "Pipeline Agent";

const getEventDescription = (event: any) => {
  const stage = formatStage(event.stage || event.current_stage || event.active_step || event.step);
  const status = formatStage(event.status || event.pipeline_state || event.data?.status);
  const message = event.message || event.data?.message || event.step;

  return [stage, status, message].filter(Boolean).join(" - ") || "Pipeline event";
};

const SidebarPanel: React.FC<SidebarPanelProps> = ({ events }) => {
  const visibleEvents = useMemo(() => events.slice(0, 12), [events]);

  return (
    <aside className="cw-activity-card">
      <div className="cw-activity-head">
        <h3>Activity Feed</h3>
        <button>View All</button>
      </div>

      <div className="cw-activity-list">
        {visibleEvents.map((event, index) => (
          <div className="cw-activity" key={getEventKey(event, index)}>
            <span />
            <time>{formatEventTime(event.timestamp)}</time>
            <strong>{getEventTitle(event)}</strong>
            <p>{getEventDescription(event)}</p>
          </div>
        ))}

        {visibleEvents.length === 0 && (
          <p className="cw-empty">Waiting for websocket activity.</p>
        )}
      </div>
    </aside>
  );
};

export default React.memo(SidebarPanel);
