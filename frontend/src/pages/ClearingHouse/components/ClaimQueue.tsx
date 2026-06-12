import React, { useEffect, useState } from "react";
import { API_URL } from "../../../config";
import { mergeClaims, normalizeClaimsResponse } from "../../../utils/claimSync";

interface Props {
  onSelect?: (claim: any) => void;
  refresh?: number;
  selectedClaim?: any; // ✅ ADD THIS
}

const ClaimQueue: React.FC<Props> = ({
  onSelect,
  refresh,
  selectedClaim, // ✅ RECEIVE PROP
}) => {
  const [claims, setClaims] = useState<any[]>([]);

  const loadClaims = async () => {
    try {
      const res = await fetch(`${API_URL}/records?summary=true`);
      const data = await res.json();

      const records = normalizeClaimsResponse(data);

      const pending = records.filter(
        (item: any) => item.status === "PENDING_APPROVAL"
      );

      setClaims((prev) => mergeClaims(prev, pending));
    } catch (err) {
      console.error("❌ Failed to load claims:", err);
    }
  };

  useEffect(() => {
    loadClaims();
  }, [refresh]);

  // ✅ AUTO SELECT FIRST CLAIM
  useEffect(() => {
    if (claims.length > 0 && onSelect && !selectedClaim) {
      onSelect(claims[0]);
    }
  }, [claims]);

  return (
    <table className="w-full text-sm">
      <thead className="bg-gray-50 text-xs">
        <tr>
          <th className="p-3 text-left">Claim</th>
          <th className="p-3 text-left">Status</th>
          <th className="p-3 text-left">Created</th>
        </tr>
      </thead>

      <tbody>
        {claims.length === 0 ? (
          <tr>
            <td colSpan={3} className="text-center p-6 text-gray-400">
              🎉 No pending claims — all caught up!
            </td>
          </tr>
        ) : (
          claims.map((c) => (
            <tr
              key={c.claim_id}
              className={`border-t cursor-pointer ${
                selectedClaim?.claim_id === c.claim_id
                  ? "bg-blue-100"
                  : "hover:bg-gray-100"
              }`}
              onClick={() => onSelect && onSelect(c)}
            >
              <td className="p-3">{c.claim_id}</td>
              <td className="p-3 text-orange-600">{c.status}</td>
              <td className="p-3">{c.created_at || "-"}</td>
            </tr>
          ))
        )}
      </tbody>
    </table>
  );
};

export default ClaimQueue;
