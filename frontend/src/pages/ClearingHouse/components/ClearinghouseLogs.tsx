import React from "react";

const ClearinghouseLogs = ({ logs = [] }: any) => {
  return (
    <div className="bg-white rounded-xl shadow p-5">
      <h2 className="font-semibold mb-4">Processing Logs</h2>

      <div className="space-y-2 text-sm max-h-[300px] overflow-y-auto">
        {logs.length === 0 && <div>No logs yet</div>}

        {logs.map((log: any, index: number) => (
          <div key={index} className="border-b pb-1">
            <span className="text-gray-500 mr-2">
              {log.time}
            </span>
            {log.message}
          </div>
        ))}
      </div>
    </div>
  );
};

export default ClearinghouseLogs;