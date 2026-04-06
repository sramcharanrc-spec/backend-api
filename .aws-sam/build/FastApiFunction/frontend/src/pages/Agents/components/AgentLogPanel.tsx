// src/components/AgentLogPanel.tsx
import React from 'react';

type Props = {
  logs?: string[];
};

export default function AgentLogPanel({ logs = [] }: Props) {
  return (
    <div style={{ background: '#fafafa', padding: 8, borderRadius: 6, maxHeight: 200, overflow: 'auto' }}>
      <h5>Agent Logs</h5>
      {logs.length === 0 ? (
        <div style={{ color: '#666' }}>No logs yet</div>
      ) : (
        logs.map((l, i) => (
          <div key={i} style={{ fontFamily: 'monospace', fontSize: 13, marginBottom: 6 }}>
            {l}
          </div>
        ))
      )}
    </div>
  );
}
