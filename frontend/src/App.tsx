import { Spin } from "antd";
import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import AppLayout from "@/components/layout/AppLayout";

// 路由级懒加载：每个页面独立 chunk，首屏只加载当前路由所需代码
const ChatPage = lazy(() => import("@/pages/ChatPage"));
const KnowledgeBasePage = lazy(() => import("@/pages/KnowledgeBasePage"));
const TicketsPage = lazy(() => import("@/pages/TicketsPage"));
const SessionsPage = lazy(() => import("@/pages/SessionsPage"));
const EvaluationsPage = lazy(() => import("@/pages/EvaluationsPage"));
const DashboardPage = lazy(() => import("@/pages/DashboardPage"));

function PageLoading() {
  return (
    <div style={{ display: "flex", justifyContent: "center", paddingTop: 120 }}>
      <Spin size="large" />
    </div>
  );
}

export default function App() {
  return (
    <Suspense fallback={<PageLoading />}>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<Navigate to="/chat" replace />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/knowledge" element={<KnowledgeBasePage />} />
          <Route path="/tickets" element={<TicketsPage />} />
          <Route path="/sessions" element={<SessionsPage />} />
          <Route path="/evaluations" element={<EvaluationsPage />} />
          <Route path="/dashboard" element={<DashboardPage />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
