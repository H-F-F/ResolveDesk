import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ChatPage from "@/pages/ChatPage";
import type { ChatResponse } from "@/api/types";

const { fullResponse } = vi.hoisted(() => ({
  fullResponse: {
    mode: "answer",
    answer: "测试回答",
    citations: [],
    ticket: null,
    retrieval_score: 0.5,
    session_id: "test-session",
    message_id: 42,
    debug: { decision: "heuristic" },
  } as ChatResponse,
}));

vi.mock("@/api/endpoints", () => ({
  api: {
    chat: vi.fn(),
    submitFeedback: vi.fn().mockResolvedValue({
      status: "ok",
      feedback_positive: 1,
      feedback_negative: 0,
    }),
  },
  chatStream: vi.fn().mockImplementation(
    async (_payload: unknown, onDelta: (content: string) => void) => {
      onDelta("测试");
      onDelta("回答");
      return fullResponse;
    },
  ),
}));

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <ConfigProvider locale={zhCN}>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <ChatPage />
        </MemoryRouter>
      </QueryClientProvider>
    </ConfigProvider>,
  );
}

describe("ChatPage", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    vi.clearAllMocks();
  });

  it("空状态时展示引导文案", () => {
    renderPage();
    expect(screen.getByText(/输入一个问题开始/)).toBeInTheDocument();
  });

  it("提交问题后流式渲染助手回答", { timeout: 15000 }, async () => {
    renderPage();
    const textarea = screen.getByPlaceholderText(/输入你的问题/);
    const button = screen.getByRole("button", { name: /提交问题/ });

    const { default: userEvent } = await import("@testing-library/user-event");
    await userEvent.type(textarea, "VPN 连不上怎么办");
    await userEvent.click(button);

    expect(await screen.findByText("VPN 连不上怎么办")).toBeInTheDocument();
    // 流式累积的完整答案
    expect(await screen.findByText("测试回答")).toBeInTheDocument();
    // 会话 id 已持久化
    expect(window.sessionStorage.getItem("resolvedesk.session_id")).toBe("test-session");
    // 回答反馈入口出现
    expect(await screen.findByText("这个回答有帮助吗？")).toBeInTheDocument();
  });

  it("点击有用后调用反馈接口并标记状态", { timeout: 15000 }, async () => {
    renderPage();
    const textarea = screen.getByPlaceholderText(/输入你的问题/);
    const button = screen.getByRole("button", { name: /提交问题/ });

    const { default: userEvent } = await import("@testing-library/user-event");
    await userEvent.type(textarea, "VPN 连不上怎么办");
    await userEvent.click(button);

    const like = await screen.findByRole("button", { name: "标记为有用" });
    await userEvent.click(like);

    const { api } = await import("@/api/endpoints");
    expect(api.submitFeedback).toHaveBeenCalledWith({
      message_id: 42,
      rating: 1,
    });
    expect(screen.getByText("这个回答有帮助吗？")).toBeInTheDocument();
  });

  it("流式请求失败时展示错误与重试按钮，重试成功后渲染回答", { timeout: 15000 }, async () => {
    const { chatStream } = await import("@/api/endpoints");
    const mockedStream = vi.mocked(chatStream);
    mockedStream.mockImplementationOnce(async () => {
      throw new Error("模型接口超时");
    });

    renderPage();
    const textarea = screen.getByPlaceholderText(/输入你的问题/);
    const button = screen.getByRole("button", { name: /提交问题/ });

    const { default: userEvent } = await import("@testing-library/user-event");
    await userEvent.type(textarea, "VPN 连不上怎么办");
    await userEvent.click(button);

    // 失败：展示错误信息与重试按钮
    expect(await screen.findByText("模型接口超时")).toBeInTheDocument();
    const retryButton = screen.getByRole("button", { name: /重\s*试/ });

    // 重试：第二次调用成功（默认 mock 实现）
    await userEvent.click(retryButton);
    expect(await screen.findByText("测试回答")).toBeInTheDocument();
    expect(screen.queryByText("模型接口超时")).not.toBeInTheDocument();
  });
});
