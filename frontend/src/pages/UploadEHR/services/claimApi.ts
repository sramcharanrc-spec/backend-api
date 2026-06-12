import { API_URL } from "../../../config";
import { normalizeClaimsResponse } from "../../../utils/claimSync";

type ClaimRequestError = Error & {
  status?: number;
  data?: any;
};

type FetchClaimOptions = {
  signal?: AbortSignal;
  preferClaimApi?: boolean;
};

const toRequestError = (
  message: string,
  status?: number,
  data?: any
): ClaimRequestError => {
  const error = new Error(message) as ClaimRequestError;
  error.status = status;
  error.data = data;
  return error;
};

const delay = (delayMs: number) =>
  new Promise((resolve) => {
    window.setTimeout(resolve, delayMs);
  });

const CLAIM_ENDPOINT_404_TTL_MS = 5 * 60 * 1000;
const endpoint404Cache = new Map<string, number>();
const fallbackInFlight = new Map<string, Promise<any | null>>();

const endpointCacheKey = (claimId: string, endpoint: string) =>
  `${claimId}:${endpoint}`;

const isEndpointSuppressed = (key?: string) => {
  if (!key) return false;

  const failedAt = endpoint404Cache.get(key);

  if (!failedAt) return false;

  if (Date.now() - failedAt > CLAIM_ENDPOINT_404_TTL_MS) {
    endpoint404Cache.delete(key);
    return false;
  }

  return true;
};

const rememberEndpoint404 = (key?: string) => {
  if (!key) return;
  endpoint404Cache.set(key, Date.now());
};

const clearEndpoint404 = (key?: string) => {
  if (!key) return;
  endpoint404Cache.delete(key);
};

const isAbortError = (error: any) =>
  error?.name === "AbortError" ||
  String(error?.message || "").toLowerCase().includes("aborted");

const readJsonSafely = async (response: Response) => {
  const text = await response.text();

  if (!text) return null;

  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
};

const fetchOptionalJson = async (
  url: string,
  cacheKey?: string,
  signal?: AbortSignal
) => {
  if (isEndpointSuppressed(cacheKey)) {
    return null;
  }

  try {
    const response = await fetch(url, {
      signal,
      headers: {
        Accept: "application/json",
      },
    });

    const data = await readJsonSafely(response);

    if (response.ok) {
      clearEndpoint404(cacheKey);
      return data;
    }

    if (response.status === 404) {
      rememberEndpoint404(cacheKey);
      console.warn("[claim-api] optional endpoint not found:", url);
      return null;
    }

    console.warn("[claim-api] optional fetch failed:", response.status, url, data);
    return null;
  } catch (error: any) {
    if (isAbortError(error)) {
      throw error;
    }

    console.warn("[claim-api] optional fetch error:", url, error);
    return null;
  }
};

const normalizeClaimId = (value: any) =>
  String(value || "").trim().toUpperCase();

const getClaimId = (item: any) =>
  item?.claim_id ||
  item?.claimId ||
  item?.id ||
  item?.claim?.claim_id ||
  item?.claim?.claimId ||
  item?.payload?.claim_id ||
  item?.payload?.claimId ||
  item?.payload?.claim?.claim_id ||
  item?.payload?.claim?.claimId ||
  item?.data?.claim_id ||
  item?.data?.claimId ||
  item?.data?.claim?.claim_id ||
  item?.data?.claim?.claimId;

const findClaimInRecordsPayload = (payload: any, claimId: string) => {
  const records = normalizeClaimsResponse(payload);

  if (!Array.isArray(records)) {
    return null;
  }

  const targetClaimId = normalizeClaimId(claimId);

  return (
    records.find((item: any) => normalizeClaimId(getClaimId(item)) === targetClaimId) ||
    null
  );
};

export const normalizeStepKey = (value: any) => {
  const raw = String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, "_")
    .replace(/__+/g, "_");

  const aliases: Record<string, string> = {
    extraction: "ocr",
    extract: "ocr",
    intake: "ocr",
    document_processing: "ocr",
    ocr: "ocr",

    validate: "validation",
    validation: "validation",
    rules: "validation",
    rules_validation: "validation",
    eligibility: "validation",

    compliance: "compliance",
    case_orchestrator: "compliance",
    case_orchestration: "compliance",

    submit: "submission",
    submitted: "submission",
    submission: "submission",

    clearinghouse: "clearinghouse",
    clearing_house: "clearinghouse",
    clearinghouse_review: "clearinghouse",
    pending_clearinghouse: "clearinghouse",
    waiting_for_approval: "clearinghouse",
    payer_review: "clearinghouse",

    ack: "acknowledgment",
    acknowledged: "acknowledgment",
    acknowledgment: "acknowledgment",
    acknowledgement: "acknowledgment",
    payer_ack: "acknowledgment",
    payer_acknowledgment: "acknowledgment",

    denial: "denial_ai",
    denial_ai: "denial_ai",
    denialai: "denial_ai",
    denial_analysis: "denial_ai",
    denial_checked: "denial_ai",

    payment: "payment",
    paid: "payment",
    payment_posting: "payment",
    payment_completed: "payment",

    learning: "learning",
    learning_updated: "learning",
    learning_done: "learning",
    feedback: "learning",
    feedback_captured: "learning",

    analytics: "analytics",
    analytics_done: "analytics",
    finish: "analytics",
    completed: "analytics",
    complete: "analytics",
    finalized: "analytics",
    claim_completed: "analytics",
    pipeline_completed: "analytics",
  };

  return aliases[raw] || raw;
};

export const eventToPipelinePatch = (event: any) => {
  const existingPipeline =
    event?.pipeline ||
    event?.claim?.pipeline ||
    event?.payload?.pipeline ||
    event?.payload?.claim?.pipeline ||
    {};

  const stepKey = normalizeStepKey(
    event?.active_step ||
      event?.step ||
      event?.stage ||
      event?.current_stage ||
      existingPipeline?.active_step ||
      existingPipeline?.current_stage ||
      event?.agent ||
      event?.current_agent
  );

  const updatedAt =
    event?.updated_at ||
    event?.updatedAt ||
    event?.timestamp ||
    event?.created_at ||
    new Date().toISOString();

  const currentStage =
    event?.current_stage || event?.stage || existingPipeline?.current_stage;

  const currentAgent =
    event?.current_agent || event?.agent || existingPipeline?.current_agent;

  const pipelineStatus =
    event?.pipeline_status ||
    event?.status ||
    existingPipeline?.pipeline_status ||
    existingPipeline?.status;

  const pipelineState =
    event?.pipeline_state ||
    existingPipeline?.pipeline_state ||
    (currentStage && pipelineStatus
      ? `${String(currentStage).toUpperCase()}_${String(pipelineStatus).toUpperCase()}`
      : undefined);

  return {
    ...event,
    pipeline: {
      ...existingPipeline,

      current_stage: currentStage,
      current_agent: currentAgent,
      active_step: event?.active_step || stepKey || existingPipeline?.active_step,
      pipeline_state: pipelineState,
      pipeline_status: pipelineStatus,
      progress: event?.progress ?? existingPipeline?.progress,

      review_required:
        event?.review_required ?? existingPipeline?.review_required,
      approval_required:
        event?.approval_required ?? existingPipeline?.approval_required,
      pipeline_paused:
        event?.pipeline_paused ?? existingPipeline?.pipeline_paused,

      steps: {
        ...(existingPipeline?.steps || {}),
        ...(stepKey
          ? {
              [stepKey]: {
                ...(existingPipeline?.steps?.[stepKey] || {}),
                status:
                  event?.status ||
                  event?.pipeline_status ||
                  existingPipeline?.steps?.[stepKey]?.status ||
                  existingPipeline?.pipeline_status ||
                  "RUNNING",
                stage: currentStage || stepKey,
                agent: currentAgent,
                progress: event?.progress ?? existingPipeline?.progress,
                message:
                  event?.message ||
                  existingPipeline?.steps?.[stepKey]?.message ||
                  event?.status ||
                  pipelineStatus ||
                  "Updated",
                updated_at: updatedAt,
              },
            }
          : {}),
      },

      stage_status: {
        ...(existingPipeline?.stage_status || {}),
      },

      agents: {
        ...(existingPipeline?.agents || {}),
      },
    },
  };
};

export const mergePipelineObjects = (oldClaim: any = {}, incoming: any = {}) => {
  const event = eventToPipelinePatch(incoming);

  const oldPipeline =
    oldClaim?.pipeline ||
    oldClaim?.claim?.pipeline ||
    oldClaim?.payload?.pipeline ||
    oldClaim?.payload?.claim?.pipeline ||
    {};

  const incomingPipeline =
    event?.pipeline ||
    event?.claim?.pipeline ||
    event?.payload?.pipeline ||
    event?.payload?.claim?.pipeline ||
    {};

  return {
    ...oldPipeline,
    ...incomingPipeline,

    steps: {
      ...(oldPipeline?.steps || {}),
      ...(incomingPipeline?.steps || {}),
    },

    stage_status: {
      ...(oldPipeline?.stage_status || {}),
      ...(incomingPipeline?.stage_status || {}),
    },

    agents: {
      ...(oldPipeline?.agents || {}),
      ...(incomingPipeline?.agents || {}),
    },
  };
};

export const mergeClaimLiveUpdate = (oldClaim: any = {}, rawEvent: any = {}) => {
  const event = eventToPipelinePatch(rawEvent);
  const pipeline = mergePipelineObjects(oldClaim, event);

  const oldNestedClaim = oldClaim?.claim || oldClaim?.payload?.claim || {};
  const incomingNestedClaim = event?.claim || event?.payload?.claim || {};

  const claimId =
    event?.claim_id ||
    incomingNestedClaim?.claim_id ||
    oldClaim?.claim_id ||
    oldNestedClaim?.claim_id ||
    getClaimId(event) ||
    getClaimId(oldClaim);

  return {
    ...oldClaim,
    ...event,
    ...incomingNestedClaim,

    claim_id: claimId,

    status:
      event?.status ||
      incomingNestedClaim?.status ||
      oldClaim?.status ||
      oldNestedClaim?.status ||
      pipeline?.pipeline_status ||
      pipeline?.status,

    current_stage:
      event?.current_stage ||
      event?.stage ||
      incomingNestedClaim?.current_stage ||
      oldClaim?.current_stage ||
      oldNestedClaim?.current_stage ||
      pipeline?.current_stage,

    current_agent:
      event?.current_agent ||
      event?.agent ||
      incomingNestedClaim?.current_agent ||
      oldClaim?.current_agent ||
      oldNestedClaim?.current_agent ||
      pipeline?.current_agent,

    active_step:
      event?.active_step ||
      incomingNestedClaim?.active_step ||
      oldClaim?.active_step ||
      oldNestedClaim?.active_step ||
      pipeline?.active_step,

    progress:
      event?.progress ??
      incomingNestedClaim?.progress ??
      oldClaim?.progress ??
      oldNestedClaim?.progress ??
      pipeline?.progress,

    pipeline_state:
      event?.pipeline_state ||
      incomingNestedClaim?.pipeline_state ||
      oldClaim?.pipeline_state ||
      oldNestedClaim?.pipeline_state ||
      pipeline?.pipeline_state,

    pipeline_status:
      event?.pipeline_status ||
      incomingNestedClaim?.pipeline_status ||
      oldClaim?.pipeline_status ||
      oldNestedClaim?.pipeline_status ||
      pipeline?.pipeline_status,

    review_required:
      event?.review_required ??
      incomingNestedClaim?.review_required ??
      oldClaim?.review_required ??
      pipeline?.review_required,

    approval_required:
      event?.approval_required ??
      incomingNestedClaim?.approval_required ??
      oldClaim?.approval_required ??
      pipeline?.approval_required,

    pipeline_paused:
      event?.pipeline_paused ??
      incomingNestedClaim?.pipeline_paused ??
      oldClaim?.pipeline_paused ??
      pipeline?.pipeline_paused,

    pipeline,

    claim: {
      ...oldNestedClaim,
      ...incomingNestedClaim,
      claim_id: claimId,
      pipeline,
    },

    case: event?.case || event?.hitl_case || oldClaim?.case,
    hitl_case: event?.hitl_case || event?.case || oldClaim?.hitl_case,

    updatedAt:
      event?.updated_at ||
      event?.updatedAt ||
      event?.timestamp ||
      oldClaim?.updatedAt ||
      new Date().toISOString(),
  };
};

export const normalizeClaimApiResponse = (claimId: string, payload: any) => {
  if (!payload) return null;

  const patched = eventToPipelinePatch({
    ...payload,
    claim_id: getClaimId(payload) || claimId,
  });

  const claim = patched?.claim || patched?.payload?.claim || patched || {};

  const pipeline =
    patched?.pipeline ||
    claim?.pipeline ||
    patched?.payload?.pipeline ||
    patched?.payload?.claim?.pipeline ||
    {};

  const normalizedClaimId =
    patched?.claim_id ||
    claim?.claim_id ||
    patched?.payload?.claim_id ||
    getClaimId(patched) ||
    claimId;

  const normalized = {
    ...patched,
    ...claim,

    claim_id: normalizedClaimId,

    status:
      patched?.status ||
      claim?.status ||
      pipeline?.pipeline_status ||
      pipeline?.status,

    current_stage:
      patched?.current_stage ||
      claim?.current_stage ||
      pipeline?.current_stage,

    current_agent:
      patched?.current_agent ||
      claim?.current_agent ||
      pipeline?.current_agent,

    active_step:
      patched?.active_step ||
      claim?.active_step ||
      pipeline?.active_step,

    progress:
      patched?.progress ??
      claim?.progress ??
      pipeline?.progress ??
      0,

    pipeline: {
      ...pipeline,
      steps: {
        ...(pipeline?.steps || {}),
      },
      stage_status: {
        ...(pipeline?.stage_status || {}),
      },
      agents: {
        ...(pipeline?.agents || {}),
      },
    },

    claim: {
      ...claim,
      claim_id: normalizedClaimId,
      pipeline: {
        ...pipeline,
        steps: {
          ...(pipeline?.steps || {}),
        },
        stage_status: {
          ...(pipeline?.stage_status || {}),
        },
        agents: {
          ...(pipeline?.agents || {}),
        },
      },
    },
  };

  return mergeClaimLiveUpdate({}, normalized);
};

export const isClaimNotReadyError = (error: any) => {
  const status =
    error?.status ||
    error?.response?.status ||
    error?.statusCode ||
    error?.data?.status;

  const message = String(
    error?.message ||
      error?.detail ||
      error?.data?.detail ||
      error?.data?.message ||
      error?.response?.data?.detail ||
      error?.response?.data?.message ||
      ""
  ).toLowerCase();

  return status === 404 || message.includes("claim not found");
};

export async function retryClaimRequest<T>(
  request: () => Promise<T>,
  attempts = 8,
  delayMs = 1500
): Promise<T | null> {
  let lastError: any = null;

  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      return await request();
    } catch (error: any) {
      lastError = error;

      if (!isClaimNotReadyError(error)) {
        throw error;
      }

      if (attempt < attempts) {
        await delay(delayMs);
      }
    }
  }

  console.info("Claim not ready after retry window", lastError);
  return null;
}

export async function fetchJsonWithTimeout(
  url: string,
  options: RequestInit = {},
  timeoutMs = 8000
) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      ...options,
      signal: options.signal || controller.signal,
    });

    const data = await readJsonSafely(response);

    if (!response.ok) {
      throw toRequestError(
        data?.detail ||
          data?.message ||
          `Request failed with HTTP ${response.status}`,
        response.status,
        data
      );
    }

    return data;
  } finally {
    window.clearTimeout(timeout);
  }
}

export async function checkBackendHealth() {
  try {
    await fetchJsonWithTimeout(`${API_URL}/health`, {}, 3000);
    return true;
  } catch {
    return false;
  }
}

export async function fetchLatestClaims(limit = 10) {
  return fetchJsonWithTimeout(
    `${API_URL}/api/claims/latest?limit=${limit}`,
    {},
    8000
  );
}

export async function fetchRecords(
  page = 1,
  limit = 200,
  signal?: AbortSignal
) {
  const response = await fetch(`${API_URL}/records?page=${page}&limit=${limit}`, {
    signal,
    headers: {
      Accept: "application/json",
    },
  });

  const data = await readJsonSafely(response);

  if (!response.ok) {
    throw toRequestError(
      data?.detail ||
        data?.message ||
        `Records request failed with HTTP ${response.status}`,
      response.status,
      data
    );
  }

  return data;
}

async function fetchClaimFromRecordsList(
  claimId: string,
  signal?: AbortSignal
) {
  const data = await fetchRecords(1, 200, signal);
  const found = findClaimInRecordsPayload(data, claimId);

  return found ? normalizeClaimApiResponse(claimId, found) : null;
}

async function fetchClaimFromClaimsApi(
  claimId: string,
  signal?: AbortSignal
) {
  const encodedClaimId = encodeURIComponent(claimId);

  const candidates = [
    {
      key: endpointCacheKey(claimId, "claim"),
      url: `${API_URL}/api/claims/${encodedClaimId}`,
    },
    {
      key: endpointCacheKey(claimId, "claim-root"),
      url: `${API_URL}/claims/${encodedClaimId}`,
    },
    {
      key: endpointCacheKey(claimId, "pipeline"),
      url: `${API_URL}/api/claims/${encodedClaimId}/pipeline`,
    },
  ];

  for (const candidate of candidates) {
    const data = await fetchOptionalJson(candidate.url, candidate.key, signal);

    if (data) {
      return normalizeClaimApiResponse(claimId, data);
    }
  }

  return null;
}

export async function fetchClaimWithFallback(
  claimId: string,
  options: FetchClaimOptions = {}
) {
  const normalizedClaimId = String(claimId || "").trim();

  if (!normalizedClaimId) return null;

  const requestKey = `${normalizedClaimId}:${
    options.preferClaimApi ? "claim-first" : "records-first"
  }`;

  if (fallbackInFlight.has(requestKey)) {
    return fallbackInFlight.get(requestKey) || null;
  }

  const request = (async () => {
    if (!options.preferClaimApi) {
      for (let attempt = 1; attempt <= 3; attempt += 1) {
        try {
          const fromRecords = await fetchClaimFromRecordsList(
            normalizedClaimId,
            options.signal
          );

          if (fromRecords) {
            return fromRecords;
          }
        } catch (error: any) {
          if (isAbortError(error)) {
            throw error;
          }

          console.warn("[claims] records lookup failed", error);
        }

        if (attempt < 3) {
          await delay(600);
        }
      }

      return fetchClaimFromClaimsApi(normalizedClaimId, options.signal);
    }

    const fromClaimsApi = await fetchClaimFromClaimsApi(
      normalizedClaimId,
      options.signal
    );

    if (fromClaimsApi) {
      return fromClaimsApi;
    }

    return fetchClaimFromRecordsList(normalizedClaimId, options.signal);
  })();

  fallbackInFlight.set(requestKey, request);

  try {
    return await request;
  } finally {
    fallbackInFlight.delete(requestKey);
  }
}

export async function uploadClaimFile(formData: FormData) {
  const response = await fetch(`${API_URL}/intake/upload`, {
    method: "POST",
    body: formData,
  });

  const data = await readJsonSafely(response);

  if (!response.ok) {
    throw toRequestError(
      data?.detail || data?.message || "Upload failed",
      response.status,
      data
    );
  }

  return data;
}

export async function fetchClaimById(claimId: string) {
  if (!claimId) return null;

  return fetchClaimWithFallback(claimId);
}

export async function fetchRecordById(claimId: string) {
  if (!claimId) return null;

  const encodedClaimId = encodeURIComponent(claimId);
  const cacheKey = endpointCacheKey(claimId, "record");

  const direct = await fetchOptionalJson(
    `${API_URL}/api/records/${encodedClaimId}`,
    cacheKey
  );

  if (direct) {
    return normalizeClaimApiResponse(claimId, direct);
  }

  return fetchClaimFromRecordsList(claimId);
}

export async function fetchClaimPipeline(claimId: string) {
  const data = await fetchClaimWithFallback(claimId);

  if (!data) {
    return null;
  }

  const pipeline =
    data?.pipeline ||
    data?.claim?.pipeline ||
    data?.payload?.pipeline ||
    data?.payload?.claim?.pipeline ||
    {};

  return {
    claim_id: claimId,
    ...pipeline,
    pipeline: {
      ...pipeline,
      steps: {
        ...(pipeline?.steps || {}),
      },
      stage_status: {
        ...(pipeline?.stage_status || {}),
      },
      agents: {
        ...(pipeline?.agents || {}),
      },
    },
  };
}

export async function deleteClaimById(
  claimId: string,
  headers: Record<string, string> = {}
) {
  const encodedClaimId = encodeURIComponent(claimId);

  const response = await fetch(`${API_URL}/api/claims/${encodedClaimId}`, {
    method: "DELETE",
    headers: {
      "Content-Type": "application/json",
      ...headers,
    },
  });

  const data = await readJsonSafely(response);

  return {
    ok: response.ok,
    status: response.status,
    data,
  };
}

export async function fetchCompletedClaims(limit = 200, signal?: AbortSignal) {
  const params = new URLSearchParams();
  params.set("status", "COMPLETED");
  params.set("limit", String(limit));

  const candidates = [
    `${API_URL}/claims?${params.toString()}`,
    `${API_URL}/api/claims?${params.toString()}`,
    `${API_URL}/api/command-center/claims?${params.toString()}`,
  ];

  let lastError: unknown = null;

  for (const url of candidates) {
    try {
      const response = await fetch(url, {
        signal,
        headers: {
          Accept: "application/json",
        },
      });

      const data = await readJsonSafely(response);

      if (response.ok) {
        return data;
      }

      lastError = data;
    } catch (error) {
      if (isAbortError(error)) {
        throw error;
      }

      lastError = error;
    }
  }

  throw new Error(
    lastError instanceof Error
      ? lastError.message
      : "Completed claims request failed"
  );
}

export async function fetchClaimSuggestions(claimId: string) {
  const encodedClaimId = encodeURIComponent(claimId);

  const response = await fetch(
    `${API_URL}/api/claims/${encodedClaimId}/suggestions`
  );

  const data = await readJsonSafely(response);

  if (!response.ok) {
    throw toRequestError(
      data?.detail || data?.message || "Suggestions request failed",
      response.status,
      data
    );
  }

  return data;
}

export async function fetchDenialAnalysis(claimId: string) {
  const encodedClaimId = encodeURIComponent(claimId);

  const response = await fetch(
    `${API_URL}/api/claims/${encodedClaimId}/denial-analysis`
  );

  const data = await readJsonSafely(response);

  if (!response.ok) {
    throw toRequestError(
      data?.detail || data?.message || "Denial analysis request failed",
      response.status,
      data
    );
  }

  return data;
}
