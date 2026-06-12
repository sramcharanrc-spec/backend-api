import axios from "axios";

const API_ROOT =
  "https://zwht8u3a0e.execute-api.us-east-1.amazonaws.com/prod";

const CLAIM_API = `${API_ROOT}/generateClaim`;
const VIEW_FORM_API = `${API_ROOT}/viewForm`;

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
const RCM_API = API_URL;

/* =========================
   GENERATE CLAIM (AWS)
========================= */
export async function generateClaim(patientId: string) {
  const res = await axios.post(CLAIM_API, {
    path: "/generateClaim",
    patientId,
  });

  return res.data;
}

/* =========================
   VIEW FORM
========================= */
export async function viewForm(patientId: string) {
  const res = await axios.post(VIEW_FORM_API, {
    path: "/viewForm",
    patientId,
  });

  return res.data;
}

/* =========================
   RUN RCM PIPELINE (FIXED)
========================= */
export async function runRCMPipeline(patientId: string) {
  try {
    const res = await axios.post(`${RCM_API}/run-rcm`, {
      patient_id: patientId,
    });

    return res.data;

  } catch (error) {
    console.error("RCM pipeline error:", error);
    throw error;
  }
}
