import { Navigate, Route, Routes } from "react-router-dom";
import AppLayout from "@/components/layout/AppLayout";
import ChatPage from "@/pages/ChatPage";
import DashboardPage from "@/pages/DashboardPage";
import EvaluationsPage from "@/pages/EvaluationsPage";
import KnowledgeBasePage from "@/pages/KnowledgeBasePage";
import SessionsPage from "@/pages/SessionsPage";
import TicketsPage from "@/pages/TicketsPage";

export default function App() {
  return (
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
  );
}
