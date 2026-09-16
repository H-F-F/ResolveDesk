# ResolveDesk

ResolveDesk 是一个企业 IT 知识库工单助手，演示一条完整的智能支持流程：

- 导入知识库文档（`txt` / `md` / `pdf`）
- 使用 **RAG** 检索回答常见 IT 问题
- 由 **Tool Calling Agent** 自主决策：检索知识库 → 回答问题，或创建升级工单
- 支持**多轮会话**，Agent 会带上上下文理解追问（如"还是不行"）
- 内置**评测套件**与可观测性（LangSmith 可选接入）

技术栈：`FastAPI + Streamlit + ChromaDB + SQLite`，支持**离线演示模式**（无需任何 API Key）和 **OpenAI Compatible 模型接入**（如阿里云百炼）。

## 核心流程

1. 文档被读取、切分为文本块并写入 ChromaDB 向量库
2. 用户提问后，Agent 通过工具调用检索知识库（`search_knowledge`）
3. 如果结果足够可信，Agent 基于检索片段生成带引用的回答
4. 如果结果不足、前序方案无效，或用户明确要求升级，Agent 调用 `create_ticket` 工具创建工单

### 两种决策路径

| 模式 | 触发条件 | 行为 |
| --- | --- | --- |
| Tool Calling Agent | 配置了真实模型（`CHAT_PROVIDER=openai_compatible`） | LLM 通过函数调用自主决定"检索/回答/转单"，支持多轮上下文 |
| 启发式回退 | 离线模式（`CHAT_PROVIDER=offline`） | 混合分数 + 阈值 + 升级关键词规则决策，零外部依赖 |

两种路径均支持多轮会话与工单记录。

## 目录结构

```text
backend/                    FastAPI 后端
  app/
    main.py                 应用入口与路由
    config.py               配置定义（含维度自动探测）
    database.py             SQLite 初始化与访问（工单/评测/会话）
    schemas.py              API 数据模型
    services/
      agent.py              Tool Calling Agent 与启发式回退
      conversations.py      会话与消息持久化
      vector_store.py       ChromaDB 向量库（含维度一致性校验）
      responder.py          聊天客户端与回答/摘要生成
      evaluator.py          内置评测套件
      ...

frontend/
  app.py                    Streamlit 前端入口（会话管理）

data/
  knowledge_base/           内置样例知识库
  upload_test_docs/         上传测试文件

deploy/
  *.Dockerfile              容器构建文件
  nginx/default.conf        反向代理配置

tests/                      自动化测试与手动测试说明
.github/workflows/ci.yml    GitHub Actions：lint + 测试
```

## 运行要求

- Python 3.11+（推荐 3.12 / 3.13，与 CI 一致）
- 如需解析 PDF，需要 `pymupdf`（requirements 已包含）
- 如需接入外部模型，需要一个 OpenAI Compatible 接口

## 快速开始

```powershell
# 1. 创建虚拟环境并安装依赖
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. 配置环境变量（可选，默认离线模式可直接运行）
copy .env.example .env
# 编辑 .env，填入模型配置

# 3. 启动
./run.ps1
```

也可以分别启动：

```powershell
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
streamlit run frontend/app.py
```

默认访问地址：

- 后端 API：`http://127.0.0.1:8000`（交互文档 `/docs`）
- 前端页面：`http://127.0.0.1:8501`

## Docker 启动

```bash
# 开发环境
docker compose up --build

# 生产环境（含 nginx 统一入口）
docker compose -f docker-compose.prod.yml up --build -d
```

生产编排额外包含 `nginx`：`/api/*` 转发到后端，`/` 转发到前端，默认入口 `http://localhost/`。

## 配置说明

项目启动时自动读取根目录下的 `.env` 和 `.env.local`（不存在则使用默认值）。完整模板见 `.env.example`。

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `APP_NAME` | 应用名 | `IT Knowledge Ticket Assistant` |
| `APP_ENV` | 运行环境 | `local` |
| `CHAT_PROVIDER` | 聊天模型提供方 | `offline` |
| `EMBEDDING_PROVIDER` | 向量模型提供方 | `offline` |
| `MODEL_API_BASE` | OpenAI Compatible API 基地址 | 空 |
| `MODEL_API_KEY` | 模型 API Key | 空 |
| `CHAT_MODEL_NAME` | 聊天模型名 | 空 |
| `EMBEDDING_MODEL_NAME` | 向量模型名 | 空 |
| `CHROMA_COLLECTION` | Chroma 集合名前缀 | `it_knowledge_base` |
| `RAG_TOP_K` | 检索返回数量 | `3` |
| `RAG_SCORE_THRESHOLD` | 综合分数阈值（离线模式） | `0.22` |
| `RAG_LEXICAL_SCORE_THRESHOLD` | 词法分数阈值（离线模式） | `0.2` |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | 文本分块大小 / 重叠 | `700` / `120` |
| `EMBEDDING_DIMENSION` | 离线向量维度 | `1536` |
| `LANGSMITH_TRACING` | 是否启用 LangSmith 追踪 | 关 |

> 使用真实嵌入模型时，系统启动时会自动探测模型实际输出维度并用于集合命名（集合名格式 `{collection}_{维度}`），无需手动调整 `EMBEDDING_DIMENSION`；如果既有向量库维度与当前模型不一致，会给出明确报错，调用 `POST /reset` 或删除 `storage/` 后重新导入即可。

## API 概览

### 健康与状态

- `GET /health`
- `GET /status`：环境、文档数、工单数、会话数、评测记录数、模型提供方、PDF 支持

### 知识库

- `GET /documents`
- `POST /ingest`（`multipart/form-data`，字段名 `files`）
- `POST /ingest/samples`

### 对话与工单

- `POST /chat`：可选传入 `session_id` 实现多轮对话，响应返回 `session_id`
- `GET /tickets`
- `GET /sessions`：会话列表（消息数、更新时间）

```json
// 请求（新会话）
{ "message": "VPN 连不上怎么办？" }

// 请求（继续会话）
{ "message": "还是不行", "session_id": "abc123" }
```

响应有两种模式：

- `mode=answer`：返回答案与引用片段
- `mode=ticket`：返回创建的工单与转单原因

### 评测

- `POST /evaluate/samples`：运行内置 6 条评测用例（命中回答 / 未命中转单 / 显式升级）
- `GET /evaluations`、`GET /evaluations/{run_id}`：评测历史与明细

### 重置

- `POST /reset?load_samples=true&clear_evaluations=true`：清空向量库、工单、会话与可选评测历史，并可重新导入样例

## 前端功能

- 服务状态面板（模型、文档、工单、会话、评测统计）
- 知识库管理（导入样例 / 上传文档 / 重置）
- 多轮对话（自动记住当前会话，支持"新会话"）
- 引用来源、调试信息展示
- 内置评测与历史回看

## 数据存储

默认写入 `storage/`（已在 .gitignore 中排除）：

- `storage/app.db`：工单、评测历史、会话与消息
- `storage/chroma/`：向量索引
- `storage/logs/app.log`：运行日志

## 测试与代码规范

```powershell
# 单元测试（22 条用例，覆盖 Agent 工具循环、会话记忆、API 全链路）
python -m unittest discover -s tests -p "test_*.py"

# 代码规范
pip install ruff
ruff check .
```

CI（GitHub Actions）会在每次 push 时自动运行 lint 与测试（Python 3.12 / 3.13）。

手动测试说明见 `tests/manual_test_cases.md`。

## 已知实现特点

- 检索采用 ChromaDB 向量 + 本地词法覆盖率混合排序，分数可解释、可调试
- 真实模型模式下走 Tool Calling Agent 循环，离线模式自动回退到规则决策，保证任何环境可演示
- 工单为本地模拟，不对接真实 ITSM 系统
- 文档按文本块处理，不包含复杂权限、租户和审批流程

## 适合的用途

- RAG / Agent 应用示例
- 企业知识库问答与工单升级策略原型
- 模型接入、离线回退与可观测性方案演示
