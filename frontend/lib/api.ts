import type {
  AdminDocument,
  AdminJob,
  AdminSection,
  ApiErrorDetail,
  ChatRequest,
  ChatResponse,
  ChunkDetail,
  DocumentDetail,
  DocumentSummary,
  HealthReport,
  UserDocInfo,
} from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: string,
  ) {
    super(message);
  }
}

const NETWORK_MESSAGE = "সার্ভারের সাথে সংযোগ হচ্ছে না। ইন্টারনেট সংযোগ দেখে আবার চেষ্টা করুন।";
const GENERIC_MESSAGE = "কিছু একটা সমস্যা হয়েছে। আবার চেষ্টা করুন।";

function isErrorDetail(value: unknown): value is ApiErrorDetail {
  return typeof value === "object" && value !== null && "code" in value && "message" in value;
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/v1${path}`, {
      ...init,
      headers: init?.body instanceof FormData ? init.headers : { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError(NETWORK_MESSAGE, 0, "network");
  }
  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      /* not JSON */
    }
    const detail = (body as { detail?: unknown } | null)?.detail;
    if (isErrorDetail(detail)) throw new ApiError(detail.message, res.status, detail.code);
    throw new ApiError(GENERIC_MESSAGE, res.status);
  }
  return (await res.json()) as T;
}

export const getHealth = () => request<HealthReport>("/health");

export const askQuestion = (body: ChatRequest) =>
  request<ChatResponse>("/chat", { method: "POST", body: JSON.stringify(body) });

export const listSources = (area?: string) =>
  request<DocumentSummary[]>(`/sources${area ? `?area=${encodeURIComponent(area)}` : ""}`);

export const getDocument = (documentId: string) =>
  request<DocumentDetail>(`/sources/documents/${encodeURIComponent(documentId)}`);

export const getChunk = (chunkId: string) => request<ChunkDetail>(`/sources/${encodeURIComponent(chunkId)}`);

export const sendFeedback = (queryLogId: string | null, rating: "up" | "down") =>
  request<{ ok: boolean; stored: boolean }>("/feedback", {
    method: "POST",
    body: JSON.stringify({ query_log_id: queryLogId, rating }),
  });

export type VoiceLang = "bn" | "en";

export function transcribeAudio(blob: Blob, language: VoiceLang = "bn") {
  const form = new FormData();
  const ext = blob.type.includes("mp4") ? "mp4" : blob.type.includes("ogg") ? "ogg" : "webm";
  form.append("audio", blob, `question.${ext}`);
  form.append("language", language);
  return request<{ transcript: string }>("/chat/voice/transcribe", { method: "POST", body: form });
}

// ---- personal documents (kept in server memory for 1 hour; never added to the knowledge base)
export function uploadUserDoc(file: File) {
  const form = new FormData();
  form.append("file", file);
  return request<UserDocInfo>("/user-docs", { method: "POST", body: form });
}

export const deleteUserDoc = (docId: string) =>
  request<{ deleted: boolean }>(`/user-docs/${encodeURIComponent(docId)}`, { method: "DELETE" });

// ---- admin (token in the Authorization header)
const auth = (token: string) => ({ Authorization: `Bearer ${token}` });

export const adminLogin = (email: string, password: string) =>
  request<{ token: string; email: string; expires_at: number }>("/admin/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });

export const adminCheck = (token: string) =>
  request<{ ok: boolean; email: string; llm_model: string | null; embedding_model: string }>("/admin/check", {
    headers: auth(token),
  });

export const adminDocuments = (token: string) => request<AdminDocument[]>("/admin/documents", { headers: auth(token) });

export const adminDocument = (token: string, id: string) =>
  request<{ document: AdminDocument; sections: AdminSection[] }>(`/admin/documents/${encodeURIComponent(id)}`, {
    headers: auth(token),
  });

export function adminUpload(token: string, file: File, meta: Record<string, string>) {
  const form = new FormData();
  form.append("file", file);
  Object.entries(meta).forEach(([k, v]) => v && form.append(k, v));
  return request<AdminJob>("/admin/documents", { method: "POST", body: form, headers: auth(token) });
}

export const adminJob = (token: string, id: string) =>
  request<AdminJob>(`/admin/jobs/${encodeURIComponent(id)}`, { headers: auth(token) });

export const adminJobs = (token: string) => request<AdminJob[]>("/admin/jobs", { headers: auth(token) });

export const adminDelete = (token: string, id: string) =>
  request<{ deleted: string; chunks_remaining: number }>(`/admin/documents/${encodeURIComponent(id)}`, {
    method: "DELETE",
    headers: auth(token),
  });
