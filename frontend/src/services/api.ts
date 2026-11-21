import type {
  AnalyzeRequest,
  AnalyzeResponse,
  ChecklistTemplate,
  CoverageItemUpdate,
  EvaluationResults,
  Language,
  PublicConfig,
  RecordExplainResponse,
  RecordSample,
  Sample,
  SampleSummary,
} from "../types/api";

// In development default to the local backend; in production VITE_API_BASE_URL must be set at build time
// (an empty value means "same origin", e.g. when the API is served under /api on the same domain).
const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.DEV ? "http://localhost:8000" : "")).replace(/\/$/, "");
const TOKEN_KEY = "tracecare.session";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export function getSessionToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

async function request<T>(path: string, init: RequestInit = {}, timeoutMs = 180_000): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getSessionToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  try {
    const resp = await fetch(`${BASE_URL}${path}`, { ...init, headers, signal: controller.signal });
    if (!resp.ok) {
      let detail = `Request failed (${resp.status})`;
      try {
        const body = await resp.json();
        if (typeof body.detail === "string") detail = body.detail;
      } catch {
        /* non-JSON error body */
      }
      throw new ApiError(resp.status, detail);
    }
    return (await resp.json()) as T;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(0, "The request timed out. Please try again.");
    }
    throw new ApiError(0, `Could not reach the TraceCare API${BASE_URL ? ` at ${BASE_URL}` : ""}. Check that the backend is running and that VITE_API_BASE_URL is correct.`);
  } finally {
    clearTimeout(timer);
  }
}

export const api = {
  config: () => request<PublicConfig>("/api/config"),
  templates: () => request<{ notice: string; templates: ChecklistTemplate[] }>("/api/templates"),
  samples: () => request<{ samples: SampleSummary[] }>("/api/samples"),
  recordSamples: () => request<{ records: RecordSample[] }>("/api/record-samples"),
  explainRecord: (text: string, language: Language, provider?: string) =>
    request<RecordExplainResponse>("/api/explain-record", {
      method: "POST",
      body: JSON.stringify({ text, language, provider }),
    }),
  evaluation: () => request<EvaluationResults>("/api/evaluation"),
  tempPatientId: () => request<{ temp_personnummer: string }>("/api/patients/temp-id"),
  sample: (id: string) => request<Sample>(`/api/samples/${encodeURIComponent(id)}`),
  analyze: (body: AnalyzeRequest) =>
    request<AnalyzeResponse>("/api/analyze", { method: "POST", body: JSON.stringify(body) }),
  encounter: (id: string) => request<AnalyzeResponse>(`/api/encounters/${encodeURIComponent(id)}`),
  deleteEncounter: (id: string) =>
    request<{ deleted: string }>(`/api/encounters/${encodeURIComponent(id)}`, { method: "DELETE" }),
  updateItem: (encounterId: string, templateId: string, itemId: string, body: CoverageItemUpdate) =>
    request<AnalyzeResponse>(
      `/api/encounters/${encodeURIComponent(encounterId)}/coverage-items/${encodeURIComponent(itemId)}` +
        `?template_id=${encodeURIComponent(templateId)}`,
      { method: "PATCH", body: JSON.stringify(body) },
    ),
  async login(password: string): Promise<void> {
    const res = await request<{ token: string | null }>("/api/session", {
      method: "POST",
      body: JSON.stringify({ password }),
    });
    if (res.token) sessionStorage.setItem(TOKEN_KEY, res.token);
  },
};
