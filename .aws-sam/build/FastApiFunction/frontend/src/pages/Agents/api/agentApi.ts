import axiosClient from "./axiosClient";

export type InitiateClaimPayload = {
  patientId: string;
  formValues?: Record<string, any>;
};

export type InitiateResponse = {
  jobId: string;
  presignKey?: string;
};

export async function initiateClaim(payload: InitiateClaimPayload) {
  const resp = await axiosClient.post<InitiateResponse>("/initiate-claim", payload);
  return resp.data;
}

export async function getPresignUpload(key: string) {
  const resp = await axiosClient.get<{ url: string }>(
    `/presign-upload?key=${encodeURIComponent(key)}`
  );
  return resp.data;
}

export async function notifyUploadComplete(jobId: string, key: string) {
  await axiosClient.post("/upload-complete", { jobId, key });
}

export async function getStatus(jobId: string) {
  const resp = await axiosClient.get<{ jobId: string; status: string; progress?: number; resultKey?: string }>(
    `/status/${jobId}`
  );
  return resp.data;
}

export async function getResultPresign(jobId: string) {
  const resp = await axiosClient.get<{ url: string }>(`/result-presign/${jobId}`);
  return resp.data;
}
