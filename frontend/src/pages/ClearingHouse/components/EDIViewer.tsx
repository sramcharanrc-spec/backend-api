import React, { useState } from "react";

interface Props {
  ediData?: string;
  denialData?: any;
}

export default function EDIViewer({ ediData, denialData }: Props) {

  const [view, setView] = useState<"raw" | "parsed">("parsed");

  const defaultEDI = `
ISA*00*          *00*          *ZZ*AGENTICAI      *ZZ*BCBS
GS*HC*AGENTICAI*BCBS
ST*837*0001
NM1*41*2*AGENTICAI CLINIC
CLM*CLM12345*500
SE*23*0001
`;

  const edi = ediData || defaultEDI;

  /* ---------- DUPLICATE CHECK ---------- */
  const isDuplicate = (value: string) => {
    return denialData?.duplicates?.includes(value);
  };

  /* ---------- RISK COLOR ---------- */
  const getColor = () => {
    if (denialData?.risk_score > 0.7) return "bg-red-900";
    if (denialData?.risk_score > 0.4) return "bg-yellow-800";
    return "bg-green-800";
  };

  /* ---------- LABEL MAP ---------- */
  const fieldLabels: any = {
    ISA: ["Auth Info", "Security Info", "Sender", "Receiver"],
    GS: ["Functional ID", "Sender", "Receiver"],
    ST: ["Transaction Set", "Control Number"],
    NM1: ["Entity ID", "Type", "Name"],
    CLM: ["Claim ID", "Total Charge"],
    SE: ["Segment Count", "Control Number"]
  };

  /* ---------- SECTION MAP ---------- */
  const sectionMap: any = {
    ISA: "Header",
    GS: "Header",
    ST: "Transaction",
    NM1: "Provider",
    CLM: "Claim",
    SE: "Trailer"
  };

  /* ---------- PARSER ---------- */
  const parseEDI = (edi: string) => {
    const lines = edi.trim().split("\n");

    return lines.map((line) => {
      const parts = line.split("*");

      return {
        segment: parts[0],
        elements: parts.slice(1),
        section: sectionMap[parts[0]] || "Other"
      };
    });
  };

  const parsed = parseEDI(edi);

  return (
    <div className="bg-gray-900 text-white p-4 rounded-lg text-sm">

      {/* HEADER */}
      <div className="flex justify-between items-center mb-4">
        <h3 className="font-semibold text-green-400">
          📄 EDI 837 Viewer
        </h3>

        <button
          onClick={() => setView(view === "raw" ? "parsed" : "raw")}
          className="bg-green-500 text-black px-3 py-1 rounded text-xs"
        >
          {view === "raw" ? "Parsed View" : "Raw View"}
        </button>
      </div>

      {/* RAW VIEW */}
      {view === "raw" && (
        <pre className="bg-black text-green-400 p-4 rounded text-xs whitespace-pre-wrap">
          {edi}
        </pre>
      )}

      {/* PARSED VIEW */}
      {view === "parsed" && (

        <div className="space-y-4">

          {["Header", "Transaction", "Provider", "Claim", "Trailer"].map((section) => {

            const sectionSegments = parsed.filter(s => s.section === section);

            if (sectionSegments.length === 0) return null;

            return (
              <div key={section}>

                {/* SECTION TITLE */}
                <div className="text-blue-400 font-semibold mb-2">
                  {section}
                </div>

                {sectionSegments.map((seg, idx) => (

                  <div
                    key={idx}
                    className="bg-gray-800 p-3 rounded border border-gray-700 mb-2"
                  >

                    {/* Segment Name */}
                    <div className="text-green-400 font-bold">
                      {seg.segment}
                    </div>

                    {/* Fields */}
                    <div className="grid grid-cols-2 gap-2 mt-2 text-xs">

                      {seg.elements.map((el: any, i: number) => {

                        const label =
                          fieldLabels[seg.segment]?.[i] || `Field ${i + 1}`;

                        const highlight =
                          isDuplicate(el)
                            ? "bg-red-800 border border-red-400"
                            : seg.segment === "CLM" && i === 0
                            ? "bg-blue-900"
                            : seg.segment === "CLM" && i === 1
                            ? "bg-green-900"
                            : "bg-gray-700";

                        return (
                          <div key={i} className={`p-2 rounded ${highlight}`}>
                            <span className="text-gray-400">{label}</span>
                            <div className="font-medium">{el || "-"}</div>
                          </div>
                        );
                      })}

                    </div>

                  </div>

                ))}

              </div>
            );

          })}

        </div>
      )}

      {/* ✅ AI DENIAL PANEL (CORRECT POSITION) */}
      {denialData && (
        <div className={`${getColor()} text-white p-4 rounded mt-4`}>
          <h4 className="font-semibold">🚨 AI Denial Analysis</h4>
          <p><b>Risk Score:</b> {denialData.risk_score}</p>
          <p><b>Reason:</b> {denialData.reason}</p>
          <p><b>Suggestion:</b> {denialData.suggestion}</p>
        </div>
      )}

    </div>
  );
}