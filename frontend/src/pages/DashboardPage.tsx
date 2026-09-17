import {
  CloudServerOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  TagsOutlined,
  TeamOutlined,
} from "@ant-design/icons";
import { Card, Col, Descriptions, Row, Statistic, Tag, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/endpoints";

function providerLabel(provider: string, model: string): string {
  if (provider === "offline") {
    return "离线模式（无需 API Key）";
  }
  return model || provider;
}

export default function DashboardPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["status"],
    queryFn: api.getStatus,
    refetchInterval: 15_000,
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <Card>
        <Typography.Title level={4} style={{ margin: 0 }}>
          <CloudServerOutlined /> 服务状态
        </Typography.Title>
        <Typography.Text type="secondary">每 15 秒自动刷新，展示当前后端运行状态</Typography.Text>
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={12} md={8} lg={4}>
          <Card loading={isLoading}>
            <Statistic title="知识文件" value={data?.vector_documents ?? 0} prefix={<FileTextOutlined />} />
          </Card>
        </Col>
        <Col xs={12} md={8} lg={4}>
          <Card loading={isLoading}>
            <Statistic title="工单数量" value={data?.ticket_count ?? 0} prefix={<TagsOutlined />} />
          </Card>
        </Col>
        <Col xs={12} md={8} lg={4}>
          <Card loading={isLoading}>
            <Statistic title="会话数量" value={data?.session_count ?? 0} prefix={<TeamOutlined />} />
          </Card>
        </Col>
        <Col xs={12} md={8} lg={4}>
          <Card loading={isLoading}>
            <Statistic
              title="评测记录"
              value={data?.evaluation_run_count ?? 0}
              prefix={<ExperimentOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} md={8} lg={8}>
          <Card loading={isLoading}>
            <Statistic
              title="PDF 解析"
              value={data?.pdf_supported ? "已启用" : "未启用"}
              valueStyle={{ fontSize: 20 }}
            />
          </Card>
        </Col>
      </Row>

      <Card title="模型与运行环境" loading={isLoading}>
        {isError ? (
          <Typography.Text type="danger">无法连接后端，请确认服务已启动。</Typography.Text>
        ) : (
          <Descriptions column={{ xs: 1, md: 2 }} bordered size="small">
            <Descriptions.Item label="应用">{data?.app}</Descriptions.Item>
            <Descriptions.Item label="运行环境">
              <Tag>{data?.environment}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="聊天模型">
              {providerLabel(data?.chat_provider ?? "", data?.chat_model ?? "")}
            </Descriptions.Item>
            <Descriptions.Item label="向量模型">
              {providerLabel(data?.embedding_provider ?? "", data?.embedding_model ?? "")}
            </Descriptions.Item>
          </Descriptions>
        )}
      </Card>
    </div>
  );
}
