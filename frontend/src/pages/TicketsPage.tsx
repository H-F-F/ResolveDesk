import { ReloadOutlined, TagsOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, Empty, List, Select, Space, Tag, Typography } from "antd";
import { api } from "@/api/endpoints";
import type { TicketRecord, TicketStatus } from "@/api/types";
import { TICKET_STATUSES } from "@/api/types";

const STATUS_META: Record<TicketStatus, { color: string; label: string }> = {
  open: { color: "gold", label: "待处理" },
  processing: { color: "blue", label: "处理中" },
  resolved: { color: "green", label: "已解决" },
  closed: { color: "default", label: "已关闭" },
};

function StatusTag({ status }: { status: string }) {
  const meta = STATUS_META[status as TicketStatus] ?? { color: "default", label: status };
  return <Tag color={meta.color}>{meta.label}</Tag>;
}

export default function TicketsPage() {
  const queryClient = useQueryClient();
  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["tickets"],
    queryFn: api.listTickets,
  });

  const updateStatus = useMutation({
    mutationFn: ({ ticketNo, status }: { ticketNo: string; status: TicketStatus }) =>
      api.updateTicketStatus(ticketNo, status),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["tickets"] });
    },
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
          renderItem={(ticket: TicketRecord) => (
            <List.Item
              actions={[
                <Select
                  key="status"
                  size="small"
                  style={{ minWidth: 108 }}
                  value={ticket.status as TicketStatus}
                  disabled={updateStatus.isPending}
                  onChange={(status: TicketStatus) =>
                    updateStatus.mutate({ ticketNo: ticket.ticket_no, status })
                  }
                  options={TICKET_STATUSES.map((value) => ({
                    value,
                    label: STATUS_META[value].label,
                  }))}
                />,
              ]}
            >
              <List.Item.Meta
                title={
                  <Space wrap>
                    <Tag color="orange">{ticket.ticket_no}</Tag>
                    <StatusTag status={ticket.status} />
                    <span>{ticket.user_question}</span>
                  </Space>
                }
                description={
                  <Space direction="vertical" size={2}>
                    <Typography.Text type="secondary">原因：{ticket.reason}</Typography.Text>
                    <Typography.Text style={{ fontSize: 13 }}>{ticket.summary}</Typography.Text>
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      创建于 {ticket.created_at}
                      {ticket.updated_at ? `，最近更新 ${ticket.updated_at}` : ""}
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
