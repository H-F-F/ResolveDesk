import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import KnowledgeBasePage from "@/pages/KnowledgeBasePage";

const { api } = vi.hoisted(() => ({
  api: {
    listDocuments: vi.fn(),
    ingestSamples: vi.fn(),
    ingestFiles: vi.fn(),
    reset: vi.fn(),
    deleteDocument: vi.fn(),
  },
}));

vi.mock("@/api/endpoints", () => ({ api }));
vi.mock("antd", async (importOriginal) => {
  const antd = await importOriginal<typeof import("antd")>();
  return {
    ...antd,
    message: {
      success: vi.fn(),
      error: vi.fn(),
    },
  };
});

const docs = [
  { source: "vpn_troubleshooting.txt", chunk_count: 3, snippet: "VPN 连接失败排查手册" },
  { source: "printer_failure.txt", chunk_count: 2, snippet: "打印机卡纸处理" },
];

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <ConfigProvider locale={zhCN}>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <KnowledgeBasePage />
        </MemoryRouter>
      </QueryClientProvider>
    </ConfigProvider>,
  );
}

describe("KnowledgeBasePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listDocuments.mockResolvedValue(docs);
    api.deleteDocument.mockResolvedValue({ source: "vpn_troubleshooting.txt", deleted_chunks: 3 });
  });

  it("渲染已载入文档列表与分块数", async () => {
    renderPage();
    expect(await screen.findByText("vpn_troubleshooting.txt")).toBeInTheDocument();
    expect(screen.getByText("printer_failure.txt")).toBeInTheDocument();
    expect(screen.getByText("chunks=3")).toBeInTheDocument();
    expect(screen.getByText(/已载入文档（2）/)).toBeInTheDocument();
  });

  it("确认删除后调用删除接口", { timeout: 15000 }, async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    renderPage();
    await screen.findByText("vpn_troubleshooting.txt");

    const deleteButtons = screen.getAllByRole("button", { name: /删\s*除/ });
    await userEvent.click(deleteButtons[0]);

    // Popconfirm 弹层（异步渲染；两字按钮会被 antd 空格化）
    await waitFor(() => {
      expect(screen.getAllByRole("button", { name: /删\s*除/ }).length).toBeGreaterThan(1);
    });
    const confirmButtons = screen.getAllByRole("button", { name: /删\s*除/ });
    await userEvent.click(confirmButtons[confirmButtons.length - 1]);

    expect(api.deleteDocument).toHaveBeenCalledWith("vpn_troubleshooting.txt");
  });

  it("文档为空时展示空状态", async () => {
    api.listDocuments.mockResolvedValue([]);
    renderPage();
    expect(await screen.findByText("还没有载入任何文档")).toBeInTheDocument();
  });
});
