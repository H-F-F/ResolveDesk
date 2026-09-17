import {
  CommentOutlined,
  DashboardOutlined,
  ExperimentOutlined,
  FolderOpenOutlined,
  TagsOutlined,
} from "@ant-design/icons";
import { Layout, Menu, Typography } from "antd";
import { useEffect, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { api } from "@/api/endpoints";

const { Sider, Content } = Layout;

const NAV_ITEMS = [
  { key: "/chat", icon: <CommentOutlined />, label: "智能对话" },
  { key: "/knowledge", icon: <FolderOpenOutlined />, label: "知识库管理" },
  { key: "/tickets", icon: <TagsOutlined />, label: "工单记录" },
  { key: "/sessions", icon: <CommentOutlined />, label: "会话列表" },
  { key: "/evaluations", icon: <ExperimentOutlined />, label: "评测中心" },
  { key: "/dashboard", icon: <DashboardOutlined />, label: "系统状态" },
];

function BackendBadge() {
  const [online, setOnline] = useState<boolean | null>(null);

  useEffect(() => {
    let mounted = true;
    const check = () => {
      api
        .getHealth()
        .then(() => mounted && setOnline(true))
        .catch(() => mounted && setOnline(false));
    };
    check();
    const timer = window.setInterval(check, 15_000);
    return () => {
      mounted = false;
      window.clearInterval(timer);
    };
  }, []);

  const text = online === null ? "检测中…" : online ? "后端已连接" : "后端未连接";
  const color = online === null ? "#8c8c8c" : online ? "#52c41a" : "#ff4d4f";
  return (
    <div
      style={{
        padding: "12px 16px",
        fontSize: 12,
        color,
        borderTop: "1px solid #30363d",
        display: "flex",
        alignItems: "center",
        gap: 6,
      }}
    >
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: color,
          display: "inline-block",
        }}
      />
      {text}
    </div>
  );
}

export default function AppLayout() {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider
        theme="dark"
        width={220}
        style={{ position: "sticky", top: 0, height: "100vh", display: "flex", flexDirection: "column" }}
      >
        <div style={{ padding: "20px 16px 12px", color: "#fff" }}>
          <Typography.Title level={4} style={{ color: "#fff", margin: 0 }}>
            ResolveDesk
          </Typography.Title>
          <Typography.Text style={{ color: "rgba(255,255,255,.55)", fontSize: 12 }}>
            企业 IT 知识库工单助手
          </Typography.Text>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={NAV_ITEMS}
          onClick={({ key }) => navigate(key)}
          style={{ flex: 1, borderInlineEnd: "none" }}
        />
        <BackendBadge />
      </Sider>
      <Layout>
        <Content style={{ padding: 24, maxWidth: 1200, width: "100%", margin: "0 auto" }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
