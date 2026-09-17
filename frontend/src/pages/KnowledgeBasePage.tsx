import {
  DeleteOutlined,
  FolderOpenOutlined,
  PlusOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  Empty,
  List,
  Popconfirm,
  Space,
  Typography,
  Upload,
  message,
} from "antd";
import type { UploadFile } from "antd";
import { useState } from "react";
import { api } from "@/api/endpoints";
import { extractErrorMessage } from "@/api/client";

const { Dragger } = Upload;

export default function KnowledgeBasePage() {
  const queryClient = useQueryClient();
  const [fileList, setFileList] = useState<UploadFile[]>([]);

  const { data: documents, isLoading, isError } = useQuery({
    queryKey: ["documents"],
    queryFn: api.listDocuments,
  });

  const invalidateAll = () => {
    void queryClient.invalidateQueries({ queryKey: ["documents"] });
    void queryClient.invalidateQueries({ queryKey: ["status"] });
  };

  const ingestSamples = useMutation({
    mutationFn: api.ingestSamples,
    onSuccess: (result) => {
      message.success(`已导入 ${result.ingested_files} 个示例文件 / ${result.ingested_chunks} 个分块`);
      invalidateAll();
    },
    onError: (err) => message.error(extractErrorMessage(err)),
  });

  const uploadFiles = useMutation({
    mutationFn: () => api.ingestFiles(fileList.map((f) => f.originFileObj as File)),
    onSuccess: (result) => {
      message.success(`上传成功：${result.ingested_files} 个文件 / ${result.ingested_chunks} 个分块`);
      setFileList([]);
      invalidateAll();
    },
    onError: (err) => message.error(extractErrorMessage(err)),
  });

  const resetData = useMutation({
    mutationFn: () => api.reset(false, false),
    onSuccess: (result) => {
      message.success(`已清空数据（工单 ${result.deleted_tickets}、会话 ${result.deleted_sessions}、评测 ${result.deleted_evaluations}）`);
      invalidateAll();
    },
    onError: (err) => message.error(extractErrorMessage(err)),
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <Card
        title={
          <Space>
            <FolderOpenOutlined /> 知识库管理
          </Space>
        }
        extra={
          <Space>
            <Button
              icon={<PlusOutlined />}
              loading={ingestSamples.isPending}
              onClick={() => ingestSamples.mutate()}
            >
              载入示例知识库
            </Button>
            <Popconfirm
              title="确定清空当前数据？"
              description="将删除全部向量索引、工单、会话与评测记录"
              onConfirm={() => resetData.mutate()}
            >
              <Button danger icon={<DeleteOutlined />} loading={resetData.isPending}>
                清空当前数据
              </Button>
            </Popconfirm>
          </Space>
        }
      >
        <Dragger
          multiple
          accept=".txt,.md,.pdf"
          fileList={fileList}
          beforeUpload={(file) => {
            setFileList((prev) => [...prev, file]);
            return false;
          }}
          onRemove={(file) => {
            setFileList((prev) => prev.filter((item) => item.uid !== file.uid));
          }}
        >
          <p className="ant-upload-drag-icon">
            <UploadOutlined />
          </p>
          <p className="ant-upload-text">点击或拖拽文件到此处上传</p>
          <p className="ant-upload-hint">支持 TXT / Markdown / PDF，单个文件不超过 200MB</p>
        </Dragger>
        <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 12 }}>
          <Button
            type="primary"
            icon={<UploadOutlined />}
            disabled={fileList.length === 0}
            loading={uploadFiles.isPending}
            onClick={() => uploadFiles.mutate()}
          >
            上传并建索引
          </Button>
        </div>
      </Card>

      {isError && (
        <Alert type="error" showIcon message="无法加载知识库文档列表，请检查后端服务。" />
      )}

      <Card title={`已载入文档（${documents?.length ?? 0}）`} loading={isLoading}>
        {!isLoading && documents && documents.length === 0 && (
          <Empty description="还没有载入任何文档" />
        )}
        <List
          dataSource={documents}
          renderItem={(doc) => (
            <List.Item>
              <List.Item.Meta
                title={
                  <Space>
                    <span>{doc.source}</span>
                    <Typography.Text type="secondary">chunks={doc.chunk_count}</Typography.Text>
                  </Space>
                }
                description={doc.snippet || "该文档暂无摘要"}
              />
            </List.Item>
          )}
        />
      </Card>
    </div>
  );
}
