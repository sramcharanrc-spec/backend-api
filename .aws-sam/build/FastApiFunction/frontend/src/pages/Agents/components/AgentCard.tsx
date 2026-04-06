// src/components/AgentCard.tsx
import React, { useState } from 'react';
import useAgents from '../hooks/useAgents';

type Props = {
  patientId: string;
};

export default function AgentCard({ patientId }: Props) {
  // expecting useAgents to be a default export returning { job, startJob, ... }
  const { job = {}, startJob } = useAgents();
  const [file, setFile] = useState<File | null>(null);
  const [formValues, setFormValues] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(false);

  async function handleStart() {
    try {
      setLoading(true);
      // startJob should accept payload and optional file; adjust if your hook expects different args
      await startJob({ patientId, ...formValues }, file ?? undefined);
    } catch (err) {
      console.error(err);
      alert('Failed to start job');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ border: '1px solid #ddd', padding: 12, borderRadius: 8 }}>
      <h4>Start Claim for {patientId}</h4>

      <div style={{ marginBottom: 8 }}>
        <input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </div>

      {/* Add inputs for formValues here if needed */}
      <button onClick={handleStart} disabled={loading}>
        {loading ? 'Starting...' : 'Start Claim'}
      </button>

      {job && (job as any).jobId && (
        <div style={{ marginTop: 12 }}>
          <strong>Job:</strong> {(job as any).jobId} <br />
          <strong>Status:</strong> {(job as any).status ?? 'N/A'} {(job as any).progress ? `(${(job as any).progress}%)` : null}
        </div>
      )}
    </div>
  );
}
