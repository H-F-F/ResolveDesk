import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ChatPage from "@/pages/ChatPage";

vi.mock("@/api/endpoints", () => ({
  api: {
    chat: vi.fn().mockResolvedValue({
      mode: "answer",
      answer: "测试回答",
      citations: [],
      ticket: null,
      retrieval_score: 0.5,
      session_id: "test-session",
      debug: { decision: "heuristic" },
    }),
  },
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
  });

  it("空状态时展示引导文案", () => {
    renderPage();
    expect(screen.getByText(/输入一个问题开始/)).toBeInTheDocument();
  });

  it("提交问题后渲染用户消息与助手回答", async () => {
    renderPage();
    const textarea = screen.getByPlaceholderText(/输入你的问题/);
    const button = screen.getByRole("button", { name: /提交问题/ });

    // 模拟输入并提交
    await import("@testing-library/user-event").then(({ default: userEvent }) =>
      userEvent.type(textarea, "VPN 连不上怎么办"),
    );
    const userEvent = (await import("@testing-library/user-event")).default;
    await userEvent.click(button);

    expect(await screen.findByText("VPN 连不上怎么办")).toBeInTheDocument();
    expect(await screen.findByText("测试回答")).toBeInTheDocument();
    // 会话 id 已持久化
    expect(window.sessionStorage.getItem("resolvedesk.session_id")).toBe("test-session");
  });
});
