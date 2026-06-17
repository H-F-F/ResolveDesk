# ResolveDesk

ResolveDesk 是一个企业 IT 知识库工单助手示例项目，用来演示一条完整的支持流程：

- 导入知识库文档
- 使用 RAG 检索回答常见 IT 问题
- 在低置信度或用户明确要求升级时自动转工单
- 通过前端面板查看状态、知识库、工单和评测结果

项目采用 `FastAPI + Streamlit + ChromaDB + SQLite`，同时支持离线演示模式和 OpenAI Compatible 模型接入模式。

## 项目能力

- 知识库导入
  - 支持 `txt`、`md`、`pdf`
  - 可导入本地样例知识库
  - 可通过前端或 API 上传文件
- 问答与转单
  - 命中知识库时返回答案和引用片段
  - 未命中、置信度不足或用户明确要求升级时自动创建工单
- 可观测与管理
  - 查看当前文档数、分块数、工单数、评测次数
  - 查看已导入文档摘要
  - 查看历史工单
- 内置评测
  - 内置一组样例问答/转单用例
  - 支持保存评测历史并回看明细

## 核心流程

1. 文档被读取并切分为文本块
2. 文本块写入 ChromaDB 向量库
3. 用户提问后，系统执行向量检索和词法匹配混合排序
4. 如果结果足够可信，则生成回答
5. 如果结果不足够可信，或用户显式要求升级，则写入 SQLite 工单表

当前决策逻辑的关键点：

- 检索分数由 `dense score` 和 `lexical score` 混合计算
- 默认阈值由 `RAG_SCORE_THRESHOLD` 和 `RAG_LEXICAL_SCORE_THRESHOLD` 控制
- 命中升级关键词时会优先创建工单

## 技术栈

- 后端：FastAPI
- 前端：Streamlit
- 向量库：ChromaDB
- 持久化：SQLite
- PDF 解析：PyMuPDF
- HTTP 调用：requests / httpx
- 可选追踪：LangSmith

## 目录结构

```text
backend/                    FastAPI 后端
  app/
    main.py                 应用入口与路由
    config.py               配置定义
    database.py             SQLite 初始化与访问
    schemas.py              API 数据模型
    services/               检索、问答、工单、评测等核心服务

frontend/
  app.py                    Streamlit 前端入口

data/
  knowledge_base/           内置样例知识库
  upload_test_docs/         上传测试文件

deploy/
  *.Dockerfile              容器构建文件
  nginx/default.conf        反向代理配置

tests/                      自动化测试与手动测试说明
storage/                    本地运行产生的数据
run.ps1                     Windows 本地一键启动脚本
```

## 运行要求

- Python 3.12 左右的环境
- Windows PowerShell 或任意可运行 Python 的环境
- 如需解析 PDF，需要安装 `pymupdf`
- 如需接入外部模型，需要一个 OpenAI Compatible 接口

## 安装依赖

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 本地启动

### 方式一：分别启动后端和前端

启动后端：

```powershell
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

启动前端：

```powershell
streamlit run frontend/app.py
```

默认访问地址：

- 后端 API：`http://127.0.0.1:8000`
- 前端页面：`http://127.0.0.1:8501`

### 方式二：Windows 一键启动

```powershell
./run.ps1
```

这个脚本会：

- 自动寻找可用 Python
- 启动 FastAPI 后端
- 等待后端健康检查
- 启动 Streamlit 前端

## Docker 启动

开发环境：

```bash
docker compose up --build
```

启动后：

- 后端映射到 `8000`
- 前端映射到 `8501`

生产环境：

```bash
docker compose -f docker-compose.prod.yml up --build -d
```

生产编排额外包含：

- `nginx` 统一入口
- `/api/*` 转发到后端
- `/` 转发到前端

默认入口：

- `http://localhost/`

## 配置说明

项目启动时会自动读取根目录下的 `.env` 和 `.env.local`。

常用配置项如下：

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `APP_NAME` | 应用名 | `IT Knowledge Ticket Assistant` |
| `APP_ENV` | 运行环境 | `local` |
| `LOG_LEVEL` | 日志级别 | `INFO` |
| `FRONTEND_API_BASE` | 前端调用的后端地址 | `http://localhost:8000` |
| `CHAT_PROVIDER` | 聊天模型提供方 | `offline` |
| `EMBEDDING_PROVIDER` | 向量模型提供方 | `offline` |
| `MODEL_API_BASE` | OpenAI Compatible API 基地址 | 空 |
| `MODEL_API_KEY` | 模型 API Key | 空 |
| `CHAT_MODEL_NAME` | 聊天模型名 | 空 |
| `EMBEDDING_MODEL_NAME` | 向量模型名 | 空 |
| `MODEL_TIMEOUT_SECONDS` | 模型请求超时 | `60` |
| `MODEL_TEMPERATURE` | 聊天温度 | `0.2` |
| `MODEL_VERIFY_SSL` | 是否校验证书 | `true` |
| `CHROMA_COLLECTION` | Chroma 集合名 | `it_knowledge_base` |
| `RAG_TOP_K` | 检索返回数量 | `3` |
| `RAG_SCORE_THRESHOLD` | 综合分数阈值 | `0.22` |
| `RAG_LEXICAL_SCORE_THRESHOLD` | 词法分数阈值 | `0.2` |
| `CHUNK_SIZE` | 文本分块大小 | `700` |
| `CHUNK_OVERLAP` | 分块重叠长度 | `120` |
| `EMBEDDING_DIMENSION` | 向量维度 | `1536` |
| `STORAGE_DIR` | 存储目录 | `storage/` |
| `VECTOR_STORE_DIR` | 向量库目录 | `storage/chroma` |
| `SQLITE_PATH` | SQLite 文件 | `storage/app.db` |
| `LOGS_DIR` | 日志目录 | `storage/logs` |
| `KNOWLEDGE_BASE_DIR` | 样例知识库目录 | `data/knowledge_base` |

### 两种模型模式

#### 1. 离线模式

默认模式，适合本地演示和测试。

- `CHAT_PROVIDER=offline`
- `EMBEDDING_PROVIDER=offline`

特点：

- 向量由本地哈希嵌入生成
- 回答由启发式模板生成
- 不依赖外部模型服务

#### 2. OpenAI Compatible 模式

适合接入真实模型服务。

最少需要配置：

```env
CHAT_PROVIDER=openai_compatible
EMBEDDING_PROVIDER=openai_compatible
MODEL_API_BASE=https://your-endpoint/v1
MODEL_API_KEY=your-key
CHAT_MODEL_NAME=your-chat-model
EMBEDDING_MODEL_NAME=your-embedding-model
```

项目当前的 `.env` 已经配置为 OpenAI Compatible 模式，本地运行前建议先确认其中的模型地址和密钥是否仍可用。

## API 概览

### 健康与状态

- `GET /health`
- `GET /status`

`/status` 会返回：

- 当前环境
- 已写入的向量文档数
- 工单数
- 评测记录数
- 聊天/向量模型提供方与模型名
- 是否支持 PDF 解析

### 知识库

- `GET /documents`
- `POST /ingest`
- `POST /ingest/samples`

上传文件接口：

- 路径：`POST /ingest`
- 形式：`multipart/form-data`
- 字段名：`files`

### 对话与工单

- `POST /chat`
- `GET /tickets`

请求示例：

```json
{
  "message": "VPN 连不上怎么办？"
}
```

返回有两种模式：

- `mode=answer`
  - 返回答案
  - 返回引用片段
- `mode=ticket`
  - 返回创建的工单
  - 返回转单原因

### 评测

- `POST /evaluate/samples`
- `GET /evaluations`
- `GET /evaluations/{run_id}`

内置评测包含 6 条样例用例，覆盖：

- 命中知识库回答
- 未命中时转工单
- 用户明确升级时转工单

### 重置

- `POST /reset`

可选参数：

- `load_samples=true`
- `clear_evaluations=true`

示例：

```text
POST /reset?load_samples=true&clear_evaluations=true
```

这个接口会清空：

- 向量库
- 工单
- 可选的评测历史

并可选地重新导入样例知识库。

## 前端功能

前端页面支持：

- 查看后端连接状态
- 导入样例知识库
- 上传知识文档
- 提问并查看引用来源
- 查看最近工单
- 执行样例评测
- 查看历史评测结果

前端通过 `FRONTEND_API_BASE` 指向后端地址。

## 数据存储

默认数据写入 `storage/`：

- `storage/app.db`：工单和评测历史
- `storage/chroma/`：向量索引
- `storage/logs/app.log`：运行日志

## 测试

运行自动化测试：

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

当前测试覆盖的重点包括：

- 样例知识库导入
- `/status`、`/documents`、`/tickets`、`/reset`
- 问答与转单分支
- 内置评测及评测历史
- OpenAI Compatible 运行时配置校验

手动测试说明见：

- `tests/manual_test_cases.md`

## 已知实现特点

- 当前是单 Agent 决策，不是多 Agent 编排
- 工单是本地模拟工单，不对接真实 ITSM 系统
- 检索采用 ChromaDB + 本地词法覆盖率混合排序
- 文档按文本块处理，不包含复杂权限、租户和审批流程

## 适合的用途

- RAG/Agent Demo
- 企业知识库问答原型
- 工单升级策略验证
- 模型接入与离线回退方案示例
