// src/api/claims.ts
import axios from "axios";

const CLAIM_API =
  "https://zwht8u3a0e.execute-api.us-east-1.amazonaws.com/prod/generateClaim";
const VIEW_FORM_API =
  "https://zwht8u3a0e.execute-api.us-east-1.amazonaws.com/prod/viewForm";

export type ClaimResponse =
  | { status: "success"; message?: string }
  | { status: "no_claim"; message: string }
  | { status: "error"; message: string };

export interface ViewFormSuccess {
  status: "success";
  url: string;
  form_type?: string;
}

export interface ViewFormError {
  status: "error" | "not_found";
  message: string;
}

export type ViewFormResponse = ViewFormSuccess | ViewFormError;

export async function generateClaim(patientId: string): Promise<ClaimResponse> {
  const res = await axios.post(CLAIM_API, { patientId });
  return res.data;
}

export async function viewForm(patientId: string): Promise<ViewFormResponse> {
  const res = await axios.post(VIEW_FORM_API, { patientId });
  return res.data;
}
