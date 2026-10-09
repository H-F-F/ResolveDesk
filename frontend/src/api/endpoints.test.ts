import { afterEach, describe, expect, it, vi } from "vitest";
import { chatStream } from "@/api/endpoints";
import type { ChatResponse } from "@/api/types";

function sseStream(events: unknown[]): ReadableStream<Uint8Array> {
  const text = events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join("");
  return new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(text));
      controller.close();
    },
  });
}

function mockFetch(ok: boolean, status: number, body?: ReadableStream<Uint8Array>) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok,
      status,
      body,
    } as Response),
  );
}

const doneResponse: ChatResponse = {
  mode: "answer",
  answer: "根据知识库，建议先重启路由器。",
  citations: [],
  ticket: null,
  retrieval_score: 0.6,
  session_id: "s1",
  message_id: 7,
  debug: {},
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("chatStream", () => {
  it("按 delta 事件逐块累积，done 事件返回完整响应", async () => {
    mockFetch(
      true,
      200,
      sseStream([
        { type: "delta", content: "根据知识库，" },
        { type: "delta", content: "建议先重启路由器。" },
        { type: "done", response: doneResponse },
      ]),
    );

    const deltas: string[] = [];
    const result = await chatStream({ message: "VPN 连不上怎么办" }, (chunk) =>
      deltas.push(chunk),
    );

    expect(deltas).toEqual(["根据知识库，", "建议先重启路由器。"]);
    expect(result.message_id).toBe(7);
    expect(result.answer).toBe(doneResponse.answer);
  });

  it("跨网络分片也能正确解析 SSE（多个 fetch chunk）", async () => {
    const first = "data: {\"type\": \"delta\", \"content\": \"你好\"}\n\nda";
    const second = "ta: {\"type\": \"delta\", \"content\": \"世界\"}\n\ndata: {\"type\": \"done\", \"response\": "
      + JSON.stringify(doneResponse) + "}\n\n";
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(first));
        setTimeout(() => {
          controller.enqueue(new TextEncoder().encode(second));
          controller.close();
        }, 5);
      },
    });
    mockFetch(true, 200, stream);

    const deltas: string[] = [];
    const result = await chatStream({ message: "hi" }, (chunk) => deltas.push(chunk));
    expect(deltas).toEqual(["你好", "世界"]);
    expect(result.message_id).toBe(7);
  });

  it("收到 error 事件时抛出后端错误信息", async () => {
    mockFetch(
      true,
      200,
      sseStream([{ type: "error", detail: "模型接口超时" }]),
    );
    await expect(chatStream({ message: "hi" }, () => {})).rejects.toThrow("模型接口超时");
  });

  it("HTTP 非 2xx 时抛出状态码错误", async () => {
    mockFetch(false, 503, undefined);
    await expect(chatStream({ message: "hi" }, () => {})).rejects.toThrow(/503/);
  });

  it("流结束未收到 done 事件时抛错", async () => {
    mockFetch(true, 200, sseStream([{ type: "delta", content: "只有一半" }]));
    await expect(chatStream({ message: "hi" }, () => {})).rejects.toThrow(/未收到完成事件/);
  });
});
