import type {
  AnalysisList,
  AnalysisRun,
  ChangedFileOut,
  GraphOut,
  HealthOut,
  JobEventOut,
  RefOut,
  RepositoryList,
  RepositoryOut,
  TestRecordOut,
  VerificationAttemptOut,
} from "./types";

const BASE = "/api/v1";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body.error ?? body);
    } catch {
      try {
        detail = (await res.text()).slice(0, 300) || detail;
      } catch {
      }
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => request<HealthOut>("/health"),
  ready: () => request<HealthOut>("/ready"),
  listRepositories: (limit = 100) => request<RepositoryList>(`/repositories?limit=${limit}`),
  listRefs: (id: string) => request<RefOut[]>(`/repositories/${id}/refs`),
  createRepository: (body: { name: string; git_url?: string; local_path?: string }) =>
    request<RepositoryOut>("/repositories", { method: "POST", body: JSON.stringify(body) }),
  listAnalyses: (limit = 25, offset = 0) => request<AnalysisList>(`/analyses?limit=${limit}&offset=${offset}`),
  getAnalysis: (id: string) => request<AnalysisRun>(`/analyses/${id}`),
  createAnalysis: (body: {
    repository_id: string;
    baseline_ref?: string | null;
    target_ref?: string | null;
    options?: Record<string, unknown>;
  }) => request<AnalysisRun>(`/analyses`, { method: "POST", body: JSON.stringify(body) }),
  cancelAnalysis: (id: string) => request<AnalysisRun>(`/analyses/${id}/cancel`, { method: "POST" }),
  retryAnalysis: (id: string) => request<AnalysisRun>(`/analyses/${id}/retry`, { method: "POST" }),
  listFiles: (id: string) => request<ChangedFileOut[]>(`/analyses/${id}/files`),
  getFileDiff: (id: string, fileId: string) =>
    fetch(`${BASE}/analyses/${id}/files/${fileId}/diff`).then(async (r) => {
      if (!r.ok) throw new ApiError(r.status, `diff unavailable (${r.status})`);
      return r.text();
    }),
  listTests: (id: string) => request<TestRecordOut[]>(`/analyses/${id}/tests`),
  listVerifications: (id: string) => request<VerificationAttemptOut[]>(`/analyses/${id}/verifications`),
  listEvents: (id: string, limit = 200) => request<JobEventOut[]>(`/analyses/${id}/events?limit=${limit}`),
  getGraph: (id: string) => request<GraphOut>(`/analyses/${id}/graph`),
  reportUrl: (id: string, format: "md" | "json") => `${BASE}/analyses/${id}/report?format=${format}`,
};
