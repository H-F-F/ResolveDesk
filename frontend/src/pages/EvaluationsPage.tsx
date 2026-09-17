import { ExperimentOutlined, PlayCircleOutlined, ReloadOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Button,
  Card,
  Empty,
  List,
  Space,
  Statistic,
  Tag,
  Typography,
  message,
} from "antd";
import { useState } from "react";
import { api } from "@/api/endpoints";
import { extractErrorMessage } from "@/api/client";
import type { EvaluationReport } from "@/api/types";

function ReportPanel({ report }: { report: EvaluationReport }) {
  return (
    <Card size="small" title={`评测结果：${report.suite_name}`} style={{ marginTop: 16 }}>
      <Space size={32} wrap>
        <Statistic title="通过率" value={report.pass_rate} suffix="%" precision={1} />
        <Statistic title="总用例" value={report.total_cases} />
        <Statistic title="通过" value={report.passed_cases} valueStyle={{ color: "#52c41a" }} />
        <Statistic title="失败" value={report.failed_cases} valueStyle={{ color: "#ff4d4f" }} />
      </Space>
      <List
        style={{ marginTop: 16 }}
        dataSource={report.results}
        renderItem={(caseItem) => (
          <List.Item>
            <List.Item.Meta
              title={
                <Space wrap>
                  <Typography.Text>{caseItem.question}</Typography.Text>
                  <Tag color={caseItem.passed ? "green" : "red"}>
                    {caseItem.passed ? "通过" : "失败"}
                  </Tag>
                </Space>
              }
              description={
                <Space direction="vertical" size={2} wrap>
                  <Space wrap>
                    <span>
                      期望模式：<Tag>{caseItem.expected_mode}</Tag>
                    </span>
                    <span>
                      实际模式：<Tag>{caseItem.actual_mode}</Tag>
                    </span>
                    {caseItem.retrieval_score != null && (
                      <span>Top1 得分：{caseItem.retrieval_score.toFixed(4)}</span>
                    )}
                  </Space>
                  {caseItem.expected_source && <span>期望来源：{caseItem.expected_source}</span>}
                  {caseItem.actual_source && <span>实际来源：{caseItem.actual_source}</span>}
                  {caseItem.details.length > 0 && (
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      {caseItem.details.join("；")}
                    </Typography.Text>
                  )}
                </Space>
              }
            />
          </List.Item>
        )}
      />
    </Card>
  );
}

export default function EvaluationsPage() {
  const queryClient = useQueryClient();
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [activeReport, setActiveReport] = useState<EvaluationReport | null>(null);

  const { data: runs, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["evaluations"],
    queryFn: api.listEvaluations,
  });

  const runEvaluation = useMutation({
    mutationFn: api.evaluateSamples,
    onSuccess: (report) => {
      message.success(`评测完成：通过率 ${report.pass_rate}%`);
      setActiveReport(report);
      void queryClient.invalidateQueries({ queryKey: ["evaluations"] });
    },
    onError: (err) => message.error(extractErrorMessage(err)),
  });

  const loadReport = useMutation({
    mutationFn: (runId: string) => api.getEvaluation(runId),
    onSuccess: (report) => setActiveReport(report),
    onError: (err) => message.error(extractErrorMessage(err)),
  });

  const handleSelectRun = (runId: string) => {
    setSelectedRunId(runId);
    loadReport.mutate(runId);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <Card
        title={
          <Space>
            <ExperimentOutlined /> 评测中心
          </Space>
        }
        extra={
          <Space>
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              loading={runEvaluation.isPending}
              onClick={() => runEvaluation.mutate()}
            >
              运行示例评测
            </Button>
            <Button icon={<ReloadOutlined />} loading={isFetching} onClick={() => void refetch()}>
              刷新
            </Button>
          </Space>
        }
      >
        <Typography.Paragraph type="secondary">
          内置评测用例覆盖三类场景：知识库命中回答、未命中转单、用户显式升级。
        </Typography.Paragraph>
        {!isLoading && runs && runs.length === 0 && (
          <Empty description="还没有评测记录，点击「运行示例评测」开始" />
        )}
        <List
          dataSource={runs}
          renderItem={(run) => (
            <List.Item
              onClick={() => handleSelectRun(run.run_id)}
              style={{ cursor: "pointer" }}
            >
              <List.Item.Meta
                title={
                  <Space wrap>
                    <Typography.Text strong>{run.suite_name}</Typography.Text>
                    <Tag color={run.pass_rate >= 100 ? "green" : run.pass_rate >= 60 ? "blue" : "red"}>
                      {run.pass_rate}%
                    </Tag>
                    <Tag>{run.run_id}</Tag>
                    {selectedRunId === run.run_id && <Tag color="geekblue">查看中</Tag>}
                  </Space>
                }
                description={`${run.total_cases} 条用例 · ${run.passed_cases} 通过 / ${run.failed_cases} 失败 · ${run.evaluated_at}`}
              />
            </List.Item>
          )}
        />
      </Card>

      {activeReport && <ReportPanel report={activeReport} />}
    </div>
  );
}
