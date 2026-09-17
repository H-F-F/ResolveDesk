import {
  BugOutlined,
  CheckCircleOutlined,
  FileSearchOutlined,
  SendOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Collapse,
  Empty,
  Input,
  List,
  Space,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/api/endpoints";
import { extractErrorMessage } from "@/api/client";
import type { ChatResponse, Citation, TicketRecord } from "@/api/types";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  response?: ChatResponse;
}

const SESSION_KEY = "resolvedesk.session_id";
const SESSION_MESSAGES_KEY = "resolvedesk.session_messages";
const MAX_PERSISTED_MESSAGES = 100;

function loadPersistedMessages(): ChatMessage[] {
  try {
    const raw = window.sessionStorage.getItem(SESSION_MESSAGES_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function nextId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function CitationList({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) {
    return <Typography.Text type="secondary">无引用片段</Typography.Text>;
  }
  return (
    <List
      size="small"
      dataSource={citations}
      renderItem={(item) => (
        <List.Item>
          <List.Item.Meta
            title={
              <Space>
                <span>{item.source}</span>
                <Tag color="blue">score={item.score.toFixed(4)}</Tag>
              </Space>
            }
            description={item.snippet}
          />
        </List.Item>
      )}
    />
  );
}

function DebugPanel({ debug }: { debug: Record<string, unknown> }) {
  const entries = Object.entries(debug);
  if (entries.length === 0) {
    return <Typography.Text type="secondary">无调试信息</Typography.Text>;
  }
  return (
    <pre
      style={{
        margin: 0,
        padding: 8,
        background: "#fafafa",
        borderRadius: 6,
        fontSize: 12,
        whiteSpace: "pre-wrap",
        wordBreak: "break-all",
      }}
    >
      {JSON.stringify(debug, null, 2)}
    </pre>
  );
}

function TicketCard({ ticket }: { ticket: TicketRecord }) {
  return (
    <Card size="small" style={{ background: "#fffbe6", borderColor: "#faad14" }}>
      <Space direction="vertical" style={{ width: "100%" }}>
        <Space>
          <CheckCircleOutlined style={{ color: "#faad14" }} />
          <Typography.Text strong>已创建升级工单</Typography.Text>
          <Tag color="orange">{ticket.ticket_no}</Tag>
        </Space>
        <Typography.Text>{ticket.summary}</Typography.Text>
      </Space>
    </Card>
  );
}

function AssistantMessage({ message }: { message: ChatMessage }) {
  const response = message.response;
  const isTicket = response?.mode === "ticket";

  return (
    <div style={{ maxWidth: "86%" }}>
      <div
        style={{
          background: "#ffffff",
          border: "1px solid #e8e8e8",
          borderRadius: "4px 16px 16px 16px",
          padding: "12px 16px",
        }}
      >
        {isTicket && response?.ticket ? (
          <TicketCard ticket={response.ticket} />
        ) : (
          <Typography.Paragraph style={{ marginBottom: 8, whiteSpace: "pre-wrap" }}>
            {response?.answer ?? message.content}
          </Typography.Paragraph>
        )}
        {response && response.citations.length > 0 && (
          <Collapse
            ghost
            size="small"
            items={[
              {
                key: "citations",
                label: (
                  <Space size={4}>
                    <FileSearchOutlined />
                    引用来源（{response.citations.length}）
                  </Space>
                ),
                children: <CitationList citations={response.citations} />,
              },
            ]}
          />
        )}
        {response && Object.keys(response.debug).length > 0 && (
          <Collapse
            ghost
            size="small"
            items={[
              {
                key: "debug",
                label: (
                  <Space size={4}>
                    <BugOutlined />
                    调试信息
                  </Space>
                ),
                children: <DebugPanel debug={response.debug} />,
              },
            ]}
          />
        )}
      </div>
    </div>
  );
}

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>(loadPersistedMessages);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(
    () => window.sessionStorage.getItem(SESSION_KEY),
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // 路由切换/刷新后恢复对话记录：消息与 session_id 一起写入 sessionStorage
  useEffect(() => {
    const tail = messages.length > MAX_PERSISTED_MESSAGES
      ? messages.slice(-MAX_PERSISTED_MESSAGES)
      : messages;
    window.sessionStorage.setItem(SESSION_MESSAGES_KEY, JSON.stringify(tail));
  }, [messages]);

  const handleSend = useCallback(async () => {
    const question = input.trim();
    if (!question || loading) {
      return;
    }
    setError(null);
    const userMessage: ChatMessage = { id: nextId(), role: "user", content: question };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setLoading(true);
    try {
      const response = await api.chat({ message: question, session_id: sessionId });
      if (response.session_id) {
        setSessionId(response.session_id);
        window.sessionStorage.setItem(SESSION_KEY, response.session_id);
      }
      setMessages((prev) => [
        ...prev,
        { id: nextId(), role: "assistant", content: response.answer ?? "", response },
      ]);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [input, loading, sessionId]);

  const handleNewSession = useCallback(() => {
    setMessages([]);
    setSessionId(null);
    window.sessionStorage.removeItem(SESSION_KEY);
    window.sessionStorage.removeItem(SESSION_MESSAGES_KEY);
    setError(null);
  }, []);

  const send = () => {
    void handleSend();
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <Card>
        <Space style={{ width: "100%", justifyContent: "space-between", flexWrap: "wrap" }}>
          <Space direction="vertical" size={4}>
            <Typography.Title level={4} style={{ margin: 0 }}>
              <ThunderboltOutlined /> 智能对话
            </Typography.Title>
            <Typography.Text type="secondary">
              RAG 检索 + Tool Calling Agent 自主决策，多轮会话自动携带上下文
            </Typography.Text>
          </Space>
          <Space>
            {sessionId && (
              <Tooltip title="后续提问会自动带上此会话的上下文">
                <Tag color="geekblue" style={{ maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis" }}>
                  会话：{sessionId}
                </Tag>
              </Tooltip>
            )}
            <Button onClick={handleNewSession}>新会话</Button>
          </Space>
        </Space>
      </Card>

      {error && (
        <Alert type="error" showIcon message="请求失败" description={error} closable />
      )}

      <Card
        style={{
          minHeight: 420,
          maxHeight: 560,
          overflowY: "auto",
          background: "#f6f8fa",
        }}
        styles={{ body: { display: "flex", flexDirection: "column", gap: 12 } }}
      >
        {messages.length === 0 && !loading && (
          <Empty
            style={{ margin: "80px auto" }}
            description="输入一个问题开始，例如：VPN 连不上怎么办？"
          />
        )}
        {messages.map((message) =>
          message.role === "user" ? (
            <div key={message.id} style={{ display: "flex", justifyContent: "flex-end" }}>
              <div
                style={{
                  background: "#1677ff",
                  color: "#fff",
                  borderRadius: "16px 4px 16px 16px",
                  padding: "10px 14px",
                  maxWidth: "70%",
                  whiteSpace: "pre-wrap",
                }}
              >
                {message.content}
              </div>
            </div>
          ) : (
            <div key={message.id} style={{ display: "flex" }}>
              <AssistantMessage message={message} />
            </div>
          ),
        )}
        {loading && (
          <div>
            <Typography.Text type="secondary">Agent 正在处理…</Typography.Text>
          </div>
        )}
        <div ref={bottomRef} />
      </Card>

      <Card size="small">
        <Space.Compact style={{ width: "100%" }}>
          <Input.TextArea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="输入你的问题，例如：VPN 连不上怎么办？"
            autoSize={{ minRows: 2, maxRows: 6 }}
            onPressEnter={(e) => {
              if (!e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            disabled={loading}
          />
        </Space.Compact>
        <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 8 }}>
          <Button type="primary" icon={<SendOutlined />} loading={loading} onClick={send}>
            提交问题
          </Button>
        </div>
      </Card>
    </div>
  );
}
