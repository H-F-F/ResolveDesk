import { CommentOutlined, ReloadOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Button, Card, Empty, List, Space, Tag, Typography } from "antd";
import { api } from "@/api/endpoints";

export default function SessionsPage() {
  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["sessions"],
    queryFn: api.listSessions,
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <Card
        title={
          <Space>
            <CommentOutlined /> 会话列表
          </Space>
        }
        extra={
          <Button icon={<ReloadOutlined />} loading={isFetching} onClick={() => void refetch()}>
            刷新
          </Button>
        }
        loading={isLoading}
      >
        {!isLoading && data && data.length === 0 && (
          <Empty description="还没有会话记录，去智能对话页发起一次提问吧" />
        )}
        <List
          dataSource={data}
          renderItem={(session) => (
            <List.Item>
              <List.Item.Meta
                title={
                  <Space wrap>
                    <Tag color="geekblue" style={{ fontFamily: "monospace" }}>
                      {session.session_id}
                    </Tag>
                    <Typography.Text type="secondary">
                      消息数：{session.message_count}
                    </Typography.Text>
                  </Space>
                }
                description={
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    最近更新：{session.updated_at}
                  </Typography.Text>
                }
              />
            </List.Item>
          )}
        />
      </Card>
    </div>
  );
}
