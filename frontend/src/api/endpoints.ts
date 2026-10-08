import { apiClient } from "./client";
import type {
  AppStatus,
  ChatRequest,
  ChatResponse,
  DocumentDeleteResponse,
  DocumentSummary,
  EvaluationReport,
  EvaluationRunSummary,
  FeedbackRequest,
  FeedbackResponse,
  HealthResponse,
  IngestResponse,
  ResetResponse,
  SessionSummary,
  TicketRecord,
  TicketStatus,
} from "./types";

export const api = {
  getStatus: () => apiClient.get<AppStatus>("/status").then((r) => r.data),

  getHealth: () => apiClient.get<HealthResponse>("/health").then((r) => r.data),

  listDocuments: () => apiClient.get<DocumentSummary[]>("/documents").then((r) => r.data),

  deleteDocument: (source: string) =>
    apiClient
      .delete<DocumentDeleteResponse>(`/documents/${encodeURIComponent(source)}`)
      .then((r) => r.data),

  listTickets: () => apiClient.get<TicketRecord[]>("/tickets").then((r) => r.data),

  listSessions: () => apiClient.get<SessionSummary[]>("/sessions").then((r) => r.data),

  listEvaluations: () => apiClient.get<EvaluationRunSummary[]>("/evaluations").then((r) => r.data),

  getEvaluation: (runId: string) =>
    apiClient.get<EvaluationReport>(`/evaluations/${encodeURIComponent(runId)}`).then((r) => r.data),

  chat: (payload: ChatRequest) => apiClient.post<ChatResponse>("/chat", payload).then((r) => r.data),

  updateTicketStatus: (ticketNo: string, status: TicketStatus) =>
    apiClient
      .patch<TicketRecord>(`/tickets/${encodeURIComponent(ticketNo)}`, { status })
      .then((r) => r.data),

  submitFeedback: (payload: FeedbackRequest) =>
    apiClient.post<FeedbackResponse>("/feedback", payload).then((r) => r.data),

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


/**
 * 流式对话：走原生 fetch 读取 SSE（/api/chat?stream=true）。
 * delta 事件逐块回调累积文本，done 事件携带完整 ChatResponse（引用/调试/message_id）。
 */
export async function chatStream(
  payload: ChatRequest,
  onDelta: (content: string) => void,
  signal?: AbortSignal,
): Promise<ChatResponse> {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...payload, stream: true }),
    signal,
  });
  if (!response.ok || !response.body) {
    throw new Error(`流式请求失败：HTTP ${response.status}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let final: ChatResponse | null = null;
  for (;;) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const dataLine = raw.split("\n").find((line) => line.startsWith("data:"));
      if (!dataLine) {
        continue;
      }
      try {
        const event = JSON.parse(dataLine.slice(5).trim());
        if (event.type === "delta") {
          onDelta(event.content ?? "");
        } else if (event.type === "done") {
          final = event.response as ChatResponse;
        }
      } catch {
        // 忽略无法解析的 SSE 事件
      }
    }
  }
  if (!final) {
    throw new Error("流式响应未收到完成事件");
  }
  return final;
}
