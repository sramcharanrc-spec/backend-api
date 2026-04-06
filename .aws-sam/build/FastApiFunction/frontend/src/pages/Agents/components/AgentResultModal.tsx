// src/components/AgentResultModal.tsx
import React, { useState } from 'react';
// corrected import to point to apiAgent folder in src/
import { getResultPresign } from "../api/agentApi";

type Props = {
  jobId?: string | null;
  onClose?: () => void;
  open: boolean;
};

export default function AgentResultModal({ jobId = null, onClose, open }: Props) {
  const [url, setUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  if (!open) return null;

  async function handleFetch() {
    if (!jobId) {
      alert('No job id provided');
      return;
    }
    setLoading(true);
    try {
      const resp = await getResultPresign(jobId);
      // defensive: ensure resp has url
      if (resp && typeof resp.url === 'string') {
        setUrl(resp.url);
      } else {
        console.error('Unexpected response from getResultPresign', resp);
        alert('No download url returned');
      }
    } catch (err) {
      console.error(err);
      alert('Failed to fetch result');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ background: '#fff', padding: 20, borderRadius: 8, width: 520 }}>
        <h3>Result</h3>

        <div style={{ marginBottom: 12 }}>
          Job: <strong>{jobId ?? '—'}</strong>
        </div>

        <div style={{ marginBottom: 12 }}>
          <button onClick={handleFetch} disabled={loading || !jobId}>
            {loading ? 'Fetching...' : 'Get Download Link'}
          </button>

          {url && (
            <div style={{ marginTop: 8 }}>
              <a href={url} target="_blank" rel="noreferrer">Download EDI</a>
            </div>
          )}
        </div>

        <div style={{ textAlign: 'right' }}>
          <button onClick={() => { setUrl(null); onClose?.(); }}>Close</button>
        </div>
      </div>
    </div>
  );
}
