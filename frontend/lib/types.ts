// Mirrors backend/app/schemas — keep in sync.

export type Area = "land" | "gd" | "allowance" | "labour" | "general";
export type Status = "answered" | "partial" | "refused" | "clarify";

export interface ServiceStatus {
  ok: boolean;
  detail: string;
}

export interface HealthReport {
  status: "ok" | "degraded";
  services: Record<string, ServiceStatus>;
  version: string;
}

export interface ChatRequest {
  message: string;
  area?: Area;
  debug?: boolean;
  user_doc_id?: string;
  /** Follow-up mode: both from the first response of this chat. Omit both to start a new conversation. */
  conversation_id?: string;
  conversation_token?: string;
}

export interface Citation {
  marker: number;
  kind: "official" | "user" | "web"; // web = official website found by the web fallback
  chunk_id: string;
  act: string;
  section: string;
  title: string;
  citation: string;
  excerpt: string;
  source_url: string | null;
  notes: string[];
}

export interface TraceCandidate {
  chunk_id: string;
  citation: string;
  title: string;
  part: number | null;
  dense_rank: number | null;
  dense_score: number | null;
  bm25_rank: number | null;
  bm25_score: number | null;
  fused_score: number;
  exact_section: boolean;
}

export interface Trace {
  candidates: TraceCandidate[];
  best_dense_score: number;
  llm_calls: number;
  model: string | null;
  gate: string;
  /** Follow-up mode: how the question relates to the earlier ones; null for a first question. */
  followup_intent?: FollowupIntent | null;
  reused_chunk_ids?: string[];
  dropped_reuse?: Record<string, string>;
}

export type FollowupIntent = "CONTINUE" | "EXPAND" | "NEW_TOPIC" | "CLARIFY";

export interface ChatResponse {
  status: Status;
  answer: string;
  citations: Citation[];
  normalized_question: string;
  area: string;
  warnings: string[];
  trace: Trace | null;
  latency_ms: number;
  cached: boolean;
  request_id: string | null;
  /** Lets the 🔊 button send this answer to /tts (ElevenLabs). Null: browser voice only (e.g. personal documents). */
  speech_token?: string | null;
  conversation_id?: string | null;
  /** Only in the first response of a conversation: keep it with conversation_id for the follow-ups. */
  conversation_token?: string | null;
  turn_id?: string | null;
}

export interface ApiErrorDetail {
  code: string; // rate_limited | llm_not_configured | llm_unavailable | index_missing | user_doc_expired | conversation_expired | conversation_busy | unauthorized | …
  message: string;
}

export interface UserDocInfo {
  doc_id: string;
  filename: string;
  pages: number;
  chars: number;
  methods: string[];
  needs_review: boolean;
  preview: string;
  expires_at: string;
}

export interface AdminDocument {
  document_id: string;
  title: string;
  area: string;
  issuer: string | null;
  source_url: string | null;
  sections: number;
  chunks: number;
  builtin: boolean;
  source_files: string[];
}

export interface AdminSection {
  id: string;
  section: string;
  title: string;
  citation: string;
  chars: number;
  notes: number;
  page_start: number | null;
  source_file: string;
  text: string;
}

export interface AdminJob {
  id: string;
  filename: string;
  document_id: string;
  title: string;
  area: string;
  status: "queued" | "running" | "done" | "failed";
  steps: string[];
  error: string | null;
  sections: number;
  chunks: number;
  needs_review: boolean;
  created_at: string;
  finished_at: string | null;
}

export interface DocumentSummary {
  document_id: string;
  title: string;
  area: string;
  issuer: string | null;
  source_url: string | null;
  section_count: number;
  chunk_count: number;
}

/** One page of a paginated list. */
export interface Paged<T> {
  items: T[];
  total: number;
  page: number; // 1-based
  page_size: number;
  pages: number;
}

export interface DocumentPage extends Paged<DocumentSummary> {
  counts: Record<string, number>; // area -> documents matching the search ("all" = every area)
}

export interface AdminTotals {
  docs: number;
  chunks: number;
  uploaded: number;
  chunks_by_area: Record<string, number>;
  docs_by_area: Record<string, number>;
}

export interface AdminDocumentPage extends Paged<AdminDocument> {
  totals: AdminTotals;
}

export interface AdminDocumentDetail {
  document: AdminDocument;
  sections: AdminSection[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface SectionSummary {
  section: string;
  title: string;
  citation: string;
  chunk_ids: string[];
}

export interface DocumentDetail {
  document: DocumentSummary;
  sections: SectionSummary[];
}

export interface ChunkDetail {
  chunk_id: string;
  document_id: string;
  area: string;
  act: string;
  chapter: string | null;
  section: string;
  part: number | null;
  title: string;
  citation: string;
  text: string;
  notes: string[];
  source_url: string | null;
  page_start: number | null;
  page_end: number | null;
}
