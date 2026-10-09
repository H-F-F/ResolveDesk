import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TicketsPage from "@/pages/TicketsPage";
import type { TicketRecord } from "@/api/types";

const ticket: TicketRecord = {
  ticket_no: "IT-20261009-001",
  user_question: "VPN 无法连接公司内网",
  reason: "知识库检索结果不足以回答，已转人工",
  summary: "员工反馈 VPN 连接失败，需要技术人员排查",
  status: "open",
  created_at: "2026-10-09 10:00:00",
  updated_at: null,
};

const { api } = vi.hoisted(() => ({
  api: {
    listTickets: vi.fn(),
    updateTicketStatus: vi.fn(),
  },
}));

vi.mock("@/api/endpoints", () => ({ api }));

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <ConfigProvider locale={zhCN}>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <TicketsPage />
        </MemoryRouter>
      </QueryClientProvider>
    </ConfigProvider>,
  );
}

describe("TicketsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listTickets.mockResolvedValue([ticket]);
    api.updateTicketStatus.mockResolvedValue({
      ...ticket,
      status: "processing",
      updated_at: "2026-10-09 10:05:00",
    });
  });

  it("渲染工单列表与状态标签", async () => {
    renderPage();
    expect(await screen.findByText("IT-20261009-001")).toBeInTheDocument();
    // 状态标签 + 下拉选中值都会出现"待处理"
    expect(screen.getAllByText("待处理").length).toBeGreaterThan(0);
    expect(screen.getByText(/VPN 无法连接公司内网/)).toBeInTheDocument();
  });

  it("状态下拉展示四个可流转状态", { timeout: 15000 }, async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    renderPage();
    await screen.findByText("IT-20261009-001");

    await userEvent.click(screen.getByRole("combobox"));
    await new Promise((resolve) => setTimeout(resolve, 400));
    const labels = [...document.querySelectorAll(".ant-select-item-option")]
      .map((el) => el.textContent?.trim() ?? "");
    for (const expected of ["待处理", "处理中", "已解决", "已关闭"]) {
      expect(labels).toContain(expected);
    }
  });

  it("工单为空时展示空状态", async () => {
    api.listTickets.mockResolvedValue([]);
    renderPage();
    expect(await screen.findByText("当前没有工单记录")).toBeInTheDocument();
  });
});
