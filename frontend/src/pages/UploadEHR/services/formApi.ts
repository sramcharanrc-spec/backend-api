import { API_URL } from "../../../config";

export async function fetchCMS1500Pdf(claimId: string, signal?: AbortSignal) {
  const response = await fetch(`${API_URL}/api/claims/${claimId}/cms1500`, {
    signal,
  });

  if (!response.ok) {
    throw new Error(`CMS1500 request failed with HTTP ${response.status}`);
  }

  return response.blob();
}

export async function fetchUB04Pdf(claimId: string, signal?: AbortSignal) {
  const response = await fetch(`${API_URL}/api/claims/${claimId}/ub04`, {
    signal,
  });

  if (!response.ok) {
    throw new Error(`UB04 request failed with HTTP ${response.status}`);
  }

  return response.blob();
}

export function getCMS1500PreviewUrl(claimId: string) {
  return `${API_URL}/api/claims/${claimId}/cms1500`;
}

export function getUB04PreviewUrl(claimId: string) {
  return `${API_URL}/api/claims/${claimId}/ub04`;
}

export function getFormPreviewUrl(claimId: string, form: "CMS1500" | "UB04") {
  if (form === "CMS1500") {
    return getCMS1500PreviewUrl(claimId);
  }

  return getUB04PreviewUrl(claimId);
}