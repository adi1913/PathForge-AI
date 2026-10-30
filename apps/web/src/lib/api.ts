import type { components } from "./api-types";
import { expireSession, getToken } from "./auth";

/**
 * FastAPI marks fields that have server-side defaults as optional in the schema, but Pydantic always serializes
 * them, so responses always contain them. `Strict` removes that optionality (nullability is kept).
 */
export type Strict<T> = T extends (infer U)[] ? Strict<U>[] : T extends object ? { [K in keyof T]-?: Strict<T[K]> } : T;
type Raw = components["schemas"];
export type S = { [K in keyof Raw]: Strict<Raw[K]> };

/** Request bodies: server defaults are optional for the caller, so only `K` is required. */
export type Body<T, K extends keyof T> = Partial<T> & Pick<T, K>;

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api").replace(/\/+$/, "");

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

type Query = Record<string, string | number | boolean | null | undefined>;

interface RequestOptions {
  method?: string;
  query?: Query;
  json?: unknown;
  form?: FormData;
  signal?: AbortSignal;
  /** false for the login/register calls, which never carry (or invalidate) a session. */
  auth?: boolean;
}

/** FastAPI errors are {detail: string | [{msg, loc}]}. Always reduce to a readable string. */
export function describeDetail(payload: unknown, fallback: string): string {
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = (payload as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      const parts = detail.map((d) => (d && typeof d === "object" && "msg" in d ? String((d as { msg: unknown }).msg) : String(d)));
      if (parts.length) return parts.join("; ");
    }
  }
  return fallback;
}

export function buildUrl(path: string, query?: Query): string {
  const url = `${API_URL}${path}`;
  if (!query) return url;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== null && value !== undefined && value !== "") params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${url}?${qs}` : url;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", query, json, form, signal } = options;
  const headers: Record<string, string> = {};
  let body: BodyInit | undefined;
  if (form) {
    body = form; // the browser sets the multipart boundary
  } else if (json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(json);
  }
  const token = options.auth === false ? null : getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  let response: Response;
  try {
    response = await fetch(buildUrl(path, query), { method, headers, body, signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, `Cannot reach the API at ${API_URL}. Is the backend running?`);
  }
  let payload: unknown = null;
  const text = await response.text();
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }
  if (response.status === 401 && token) expireSession(); // expired, revoked or tampered token: back to /login
  if (!response.ok) throw new ApiError(response.status, describeDetail(payload, `Request failed (${response.status})`));
  return payload as T;
}

const post = <T>(path: string, json: unknown) => request<T>(path, { method: "POST", json });

export const api = {
  register: (body: Body<S["RegisterRequest"], "email" | "password">) =>
    request<S["TokenOut"]>("/auth/register", { method: "POST", json: body, auth: false }),
  login: (email: string, password: string) =>
    request<S["TokenOut"]>("/auth/login", { method: "POST", json: { email, password }, auth: false }),
  me: () => request<S["UserOut"]>("/auth/me"),

  health: () => request<{ status: string; demo_mode?: boolean; [k: string]: unknown }>("/health"),

  analyzeResume: (userId: string, input: { text?: string; file?: File }) => {
    const form = new FormData();
    form.set("user_id", userId);
    if (input.file) form.set("file", input.file);
    if (input.text) form.set("text", input.text);
    return request<S["ResumeAnalyzeResponse"]>("/resume/analyze", { method: "POST", form });
  },
  analyzeJob: (userId: string, input: { text?: string; file?: File }) => {
    const form = new FormData();
    form.set("user_id", userId);
    if (input.file) form.set("file", input.file);
    if (input.text) form.set("text", input.text);
    return request<S["JobDescriptionAnalyzeResponse"]>("/job-descriptions/analyze", { method: "POST", form });
  },

  listRoadmaps: (userId: string) => request<S["RoadmapListItem"][]>("/roadmaps", { query: { user_id: userId } }),
  getRoadmap: (id: string) => request<S["RoadmapResponse"]>(`/roadmaps/${id}`),
  generateRoadmap: (body: Body<S["RoadmapGenerateRequest"], "user_id">) => post<S["RoadmapResponse"]>("/roadmaps/generate", body),
  roadmapProgress: (id: string, userId: string) =>
    request<S["RoadmapProgressResponse"]>(`/roadmaps/${id}/progress`, { query: { user_id: userId } }),
  updateProgress: (roadmapId: string, itemId: string, body: Body<S["ProgressUpdateRequest"], "user_id" | "status">) =>
    request<S["ProgressUpdateResponse"]>(`/roadmaps/${roadmapId}/items/${itemId}/progress`, { method: "PATCH", json: body }),
  replan: (roadmapId: string, body: Body<S["ReplanRequest"], "user_id">) => post<S["ReplanResponse"]>(`/roadmaps/${roadmapId}/replan`, body),

  listApplications: (userId: string) =>
    request<S["ApplicationListResponse"]>("/applications", { query: { user_id: userId, limit: 100 } }),
  createApplication: (body: Body<S["ApplicationCreateRequest"], "user_id">) => post<S["ApplicationDetail"]>("/applications", body),
  getApplication: (id: string, userId: string) =>
    request<S["ApplicationDetail"]>(`/applications/${id}`, { query: { user_id: userId } }),
  updateApplicationStatus: (id: string, body: Body<S["StatusUpdateRequest"], "user_id" | "status">) =>
    request<S["ApplicationDetail"]>(`/applications/${id}/status`, { method: "PATCH", json: body }),
  addApplicationNote: (id: string, body: S["NoteRequest"]) => post<S["ApplicationDetail"]>(`/applications/${id}/notes`, body),
  applicationReadiness: (id: string, userId: string) =>
    request<S["ReadinessResponse"]>(`/applications/${id}/readiness`, { query: { user_id: userId } }),

  evaluateRepo: (userId: string, repositoryUrl: string) =>
    post<S["EvaluationResponse"]>("/github/evaluate", { user_id: userId, repository_url: repositoryUrl }),
  listRepos: (userId: string) => request<S["RepositoryListItem"][]>("/github/repositories", { query: { user_id: userId } }),
  getEvaluation: (id: string, userId: string) =>
    request<S["EvaluationResponse"]>(`/github/evaluations/${id}`, { query: { user_id: userId } }),
  githubEvidence: (userId: string) => request<S["EvidenceListItem"][]>("/github/evidence", { query: { user_id: userId } }),

  generateAssessment: (body: Body<S["GenerateRequest"], "user_id">) => post<S["AssessmentOut"]>("/assessments/generate", body),
  listAssessments: (userId: string) => request<S["AssessmentListItem"][]>("/assessments", { query: { user_id: userId } }),
  getAssessment: (id: string, userId: string) =>
    request<S["AssessmentOut"]>(`/assessments/${id}`, { query: { user_id: userId } }),
  startAttempt: (id: string, userId: string) => post<S["AttemptStartOut"]>(`/assessments/${id}/attempts`, { user_id: userId }),
  submitAttempt: (attemptId: string, body: S["SubmitRequest"]) =>
    post<S["SubmitOut"]>(`/assessments/attempts/${attemptId}/submit`, body),
  assessmentEvidence: (userId: string) => request<S["EvidenceOut"][]>("/assessments/evidence", { query: { user_id: userId } }),

  createMentorSession: (userId: string, title?: string) => post<S["SessionOut"]>("/mentor/sessions", { user_id: userId, title }),
  listMentorSessions: (userId: string) => request<S["SessionOut"][]>("/mentor/sessions", { query: { user_id: userId } }),
  getMentorSession: (id: string, userId: string) =>
    request<S["SessionDetail"]>(`/mentor/sessions/${id}`, { query: { user_id: userId } }),
  sendMentorMessage: (id: string, userId: string, message: string) =>
    post<S["MentorReply"]>(`/mentor/sessions/${id}/messages`, { user_id: userId, message }),
};
