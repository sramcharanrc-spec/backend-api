type AgentExecutionDetailsProps = {
  stages: any[];
  statusClass: (status?: string) => string;
};

const AgentExecutionDetails = ({ stages, statusClass }: AgentExecutionDetailsProps) => {
  if (!stages.length) return null;

  return (
    <section className="cw-panel cw-agent-panel">
      <div className="cw-panel-title">
        <h3>Agent Execution Details</h3>
        <span className="live-badge">Live</span>
      </div>

      <div className="cw-agent-execution-list">
        {stages.map((stage) => {
          const status = stage.status || "PENDING";

          return (
            <div className={`cw-agent-execution-card ${String(status).toLowerCase()}`} key={stage.key || stage.id}>
              <div className="cw-agent-execution-head">
                <strong>{stage.label || stage.key || stage.id}</strong>
                <span className={statusClass(status)}>{String(status).replace(/_/g, " ")}</span>
              </div>

              <div className="cw-agent-execution-grid">
                <div className="cw-info-field compact">
                  <span>Agent</span>
                  <strong>{stage.agent || "Not reported"}</strong>
                </div>

                <div className="cw-info-field compact">
                  <span>Stage</span>
                  <strong>{String(stage.key || stage.id || "").replace(/_/g, " ")}</strong>
                </div>

                <div className="cw-info-field compact">
                  <span>Updated</span>
                  <strong>
                    {stage.timestamp
                      ? new Date(stage.timestamp).toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                        })
                      : "Awaiting event"}
                  </strong>
                </div>

                <div className="cw-info-field compact">
                  <span>Progress</span>
                  <strong>{stage.progress ?? "Not reported"}</strong>
                </div>
              </div>

              {stage.message && <p className="cw-agent-message">{String(stage.message)}</p>}
            </div>
          );
        })}
      </div>
    </section>
  );
};

export default AgentExecutionDetails;