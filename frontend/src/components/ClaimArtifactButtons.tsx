import React, { useState } from "react";
import { downloadCMS1500, downloadEDI, downloadUB04 } from "../services/rcmApi";

type Props = {
  claimId: string;
};

const ClaimArtifactButtons: React.FC<Props> = ({ claimId }) => {
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState("");

  const run = async (type: string, action: (id: string) => Promise<void>) => {
    try {
      setError("");
      setLoading(type);
      await action(claimId);
    } catch (err: any) {
      setError(err?.message || `Failed to download ${type}`);
    } finally {
      setLoading(null);
    }
  };

  return (
    <section className="profile-card">
      <h3>Claim Artifacts</h3>
      <div className="flex flex-wrap gap-2">
        <button disabled={loading !== null} onClick={() => run("CMS1500", downloadCMS1500)}>
          {loading === "CMS1500" ? "Downloading..." : "Download CMS1500"}
        </button>
        <button disabled={loading !== null} onClick={() => run("UB04", downloadUB04)}>
          {loading === "UB04" ? "Downloading..." : "Download UB04"}
        </button>
        <button disabled={loading !== null} onClick={() => run("EDI", downloadEDI)}>
          {loading === "EDI" ? "Downloading..." : "Download EDI"}
        </button>
      </div>
      {error && <p className="mt-2 text-sm text-rose-600">{error}</p>}
    </section>
  );
};

export default ClaimArtifactButtons;
