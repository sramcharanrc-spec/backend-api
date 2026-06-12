import React, { useState } from "react";
import { generateClaim, runRCMPipeline } from "../../api/claims";

const ClaimGeneration: React.FC = () => {
  const [patientId, setPatientId] = useState("");
  const [message, setMessage] = useState("");

  const handleGenerateClaim = async () => {
    try {
      setMessage("Generating claim...");

      // Step 1: Generate claim via AWS API
      const claimResponse = await generateClaim(patientId);

      if (claimResponse.status === "success") {
        setMessage("Claim generated successfully. Starting RCM pipeline...");

        // Step 2: Start RCM pipeline
        const pipelineResponse = await runRCMPipeline(patientId);

        console.log("Pipeline response:", pipelineResponse);

        setMessage("RCM Pipeline started successfully.");
      } else {
        setMessage(claimResponse.message || "Claim generation failed.");
      }
    } catch (error) {
      console.error(error);
      setMessage("Error occurred while generating claim.");
    }
  };

  return (
    <div style={{ padding: "20px" }}>
      <h2>Claim Generation</h2>

      <input
        type="text"
        placeholder="Enter Patient ID (e.g., P001)"
        value={patientId}
        onChange={(e) => setPatientId(e.target.value)}
        style={{ padding: "8px", marginRight: "10px" }}
      />

      <button onClick={handleGenerateClaim} style={{ padding: "8px 16px" }}>
        Generate Claim
      </button>

      {message && (
        <p style={{ marginTop: "20px", color: "blue" }}>
          {message}
        </p>
      )}
    </div>
  );
};

export default ClaimGeneration;