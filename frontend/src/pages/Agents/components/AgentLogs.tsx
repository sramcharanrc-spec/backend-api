export default function AgentLogs({ logs }: any) {

  return (
    <div className="logs-panel">

      <div className="logs-title">
        Agent Execution Logs
      </div>

      <div className="logs">

        {logs.length === 0 && (
          <div className="log-line">
            No logs yet
          </div>
        )}

        {logs.map((log: string, i: number) => (
          <div key={i} className="log-line">
            {log}
          </div>
        ))}

      </div>

    </div>
  );
}