// Mirrors backend/app/schemas — keep in sync.

export type Area = "land" | "gd" | "allowance" | "labour";
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
}

export interface Citation {
  marker: number;
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
}

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
}

export interface ApiErrorDetail {
  code: "rate_limited" | "llm_not_configured" | "llm_unavailable" | "index_missing";
  message: string;
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
