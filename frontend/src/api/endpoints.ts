import { apiClient } from "./client";
import type {
  AppStatus,
  ChatRequest,
  ChatResponse,
  DocumentSummary,
  EvaluationReport,
  EvaluationRunSummary,
  HealthResponse,
  IngestResponse,
  ResetResponse,
  SessionSummary,
  TicketRecord,
} from "./types";

export const api = {
  getStatus: () => apiClient.get<AppStatus>("/status").then((r) => r.data),

  getHealth: () => apiClient.get<HealthResponse>("/health").then((r) => r.data),

  listDocuments: () => apiClient.get<DocumentSummary[]>("/documents").then((r) => r.data),

  listTickets: () => apiClient.get<TicketRecord[]>("/tickets").then((r) => r.data),

  listSessions: () => apiClient.get<SessionSummary[]>("/sessions").then((r) => r.data),

  listEvaluations: () => apiClient.get<EvaluationRunSummary[]>("/evaluations").then((r) => r.data),

  getEvaluation: (runId: string) =>
    apiClient.get<EvaluationReport>(`/evaluations/${encodeURIComponent(runId)}`).then((r) => r.data),

  chat: (payload: ChatRequest) => apiClient.post<ChatResponse>("/chat", payload).then((r) => r.data),

  ingestSamples: () => apiClient.post<IngestResponse>("/ingest/samples").then((r) => r.data),

  ingestFiles: async (files: File[]) => {
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    return apiClient
      .post<IngestResponse>("/ingest", form, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      .then((r) => r.data);
  },

  evaluateSamples: () =>
    apiClient.post<EvaluationReport>("/evaluate/samples").then((r) => r.data),

  reset: (loadSamples = false, clearEvaluations = false) =>
    apiClient
      .post<ResetResponse>("/reset", null, {
        params: { load_samples: loadSamples, clear_evaluations: clearEvaluations },
      })
      .then((r) => r.data),
};
