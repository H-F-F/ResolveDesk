/** 与后端 backend/app/schemas.py 对齐的 API 数据类型 */

export interface Citation {
  source: string;
  chunk_id: string;
  score: number;
  snippet: string;
}

export interface TicketRecord {
  ticket_no: string;
  user_question: string;
  reason: string;
  summary: string;
  created_at: string;
}

export interface ChatRequest {
  message: string;
  session_id?: string | null;
}

export interface ChatResponse {
  mode: "answer" | "ticket";
  answer: string | null;
  citations: Citation[];
  ticket: TicketRecord | null;
  retrieval_score: number | null;
  session_id: string | null;
  debug: Record<string, unknown>;
}

export interface IngestResponse {
  ingested_files: number;
  ingested_chunks: number;
  sources: string[];
}

export interface DocumentSummary {
  source: string;
  chunk_count: number;
  snippet: string;
}

export interface AppStatus {
  app: string;
  environment: string;
  vector_documents: number;
  ticket_count: number;
  session_count: number;
  evaluation_run_count: number;
  chat_provider: string;
  chat_model: string;
  embedding_provider: string;
  embedding_model: string;
  pdf_supported: boolean;
}

export interface HealthResponse {
  status: "ok";
  vector_documents: number;
  ticket_count: number;
}

export interface ResetResponse {
  deleted_tickets: number;
  deleted_evaluations: number;
  deleted_sessions: number;
  vector_documents: number;
  sample_data_loaded: boolean;
  ingested_files: number;
  ingested_chunks: number;
  sources: string[];
}

export interface SessionSummary {
  session_id: string;
  message_count: number;
  updated_at: string;
}

export interface EvaluationRunSummary {
  run_id: string;
  suite_name: string;
  evaluated_at: string;
  total_cases: number;
  passed_cases: number;
  failed_cases: number;
  pass_rate: number;
}

export interface EvaluationCaseResult {
  case_id: string;
  question: string;
  expected_mode: "answer" | "ticket";
  actual_mode: "answer" | "ticket";
  expected_source: string | null;
  actual_source: string | null;
  retrieval_score: number | null;
  passed: boolean;
  details: string[];
}

export interface EvaluationReport {
  run_id: string | null;
  suite_name: string;
  evaluated_at: string;
  total_cases: number;
  passed_cases: number;
  failed_cases: number;
  pass_rate: number;
  results: EvaluationCaseResult[];
}
