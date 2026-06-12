import React, { useEffect, useState } from "react";
import { fetchReconciliation } from "@/services/clearinghouseService";

const ERAViewer: React.FC = () => {

  const [data, setData] = useState<any>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetchReconciliation();
        setData(res);
      } catch (err) {
        console.error("ERA load error:", err);
      }
    };

    load();
  }, []);

  if (!data) return <div>Loading payments...</div>;

  return (
    <div className="space-y-2 text-sm">

      <div>Total Claims: {data.total}</div>
      <div>Paid: {data.paid}</div>
      <div>Denied: {data.denied}</div>
      <div>Underpaid: {data.underpaid}</div>

    </div>
  );
};

export default ERAViewer;