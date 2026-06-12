import React, { useState } from "react";
import { postPayment } from "../../services/rcmApi";

const Payments: React.FC = () => {
  const [submissionId, setSubmissionId] = useState("");
  const [expected, setExpected] = useState("");
  const [paid, setPaid] = useState("");
  const [result, setResult] = useState<any>(null);

  const handlePayment = async () => {
    const data = await postPayment(
      submissionId,
      Number(expected),
      Number(paid)
    );
    setResult(data);
  };

  return (
    <div>
      <h2>Post Payment</h2>

      <input
        placeholder="Submission ID"
        onChange={(e) => setSubmissionId(e.target.value)}
      />

      <input
        placeholder="Expected"
        onChange={(e) => setExpected(e.target.value)}
      />

      <input
        placeholder="Paid"
        onChange={(e) => setPaid(e.target.value)}
      />

      <button onClick={handlePayment}>Submit Payment</button>

      {result && <pre>{JSON.stringify(result, null, 2)}</pre>}
    </div>
  );
};

export default Payments;

