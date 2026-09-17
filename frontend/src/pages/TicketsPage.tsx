import { ReloadOutlined, TagsOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Button, Card, Empty, List, Space, Tag, Typography } from "antd";
import { api } from "@/api/endpoints";

export default function TicketsPage() {
  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["tickets"],
    queryFn: api.listTickets,
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <Card
        title={
          <Space>
            <TagsOutlined /> 工单记录
          </Space>
        }
        extra={
          <Button icon={<ReloadOutlined />} loading={isFetching} onClick={() => void refetch()}>
            刷新
          </Button>
        }
        loading={isLoading}
      >
        {!isLoading && data && data.length === 0 && <Empty description="当前没有工单记录" />}
        <List
          dataSource={data}
          renderItem={(ticket) => (
            <List.Item>
              <List.Item.Meta
                title={
                  <Space wrap>
                    <Tag color="orange">{ticket.ticket_no}</Tag>
                    <span>{ticket.user_question}</span>
                  </Space>
                }
                description={
                  <Space direction="vertical" size={2}>
                    <Typography.Text type="secondary">原因：{ticket.reason}</Typography.Text>
                    <Typography.Text style={{ fontSize: 13 }}>{ticket.summary}</Typography.Text>
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      创建于 {ticket.created_at}
                    </Typography.Text>
                  </Space>
                }
              />
            </List.Item>
          )}
        />
      </Card>
    </div>
  );
}
