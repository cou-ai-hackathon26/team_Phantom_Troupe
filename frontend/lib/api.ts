import type {
  ApiErrorDetail,
  ChatRequest,
  ChatResponse,
  ChunkDetail,
  DocumentDetail,
  DocumentSummary,
  HealthReport,
} from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: ApiErrorDetail["code"] | "network",
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

export function transcribeAudio(blob: Blob) {
  const form = new FormData();
  const ext = blob.type.includes("mp4") ? "mp4" : blob.type.includes("ogg") ? "ogg" : "webm";
  form.append("audio", blob, `question.${ext}`);
  return request<{ transcript: string }>("/chat/voice/transcribe", { method: "POST", body: form });
}
