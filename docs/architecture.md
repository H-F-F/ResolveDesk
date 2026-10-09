# 系统架构（Architecture）

本文档描述 ResolveDesk 的整体架构：一个**企业 IT 知识库 + 工单助手**，前端 React + TypeScript，后端 FastAPI，知识检索基于 ChromaDB 向量库，回答决策由 **Tool Calling Agent** 完成（未配置模型时降级为离线启发式规则）。

```
┌──────────────────────────────────────────────────────────────────────────┐
│                                前端（React + TS）                          │
│  /chat /knowledge /tickets /sessions /evaluations /dashboard             │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────────────────┐  │
│  │  Pages       │  │  api/ 层      │  │  SSE 流式客户端（chatStream）     │  │
│  │  react-query │→ │  axios client │→ │  ReadableStream 增量渲染 + 重试   │  │
│  └─────────────┘  └──────────────┘  └─────────────────────────────────┘  │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │  /api/*（Vite dev proxy 或 nginx 反代）
┌────────────────────────────────▼─────────────────────────────────────────┐
│                          后端（FastAPI, main.py）                          │
│  /chat  /ingest  /documents  /tickets  /feedback  /evaluations  /status  │
│                                                                          │
│  ┌──────────────────── SupportAgent（决策循环）─────────────────────────┐  │
│  │  真实模式：LLM Tool Calling 循环（search_knowledge / create_ticket） │  │
│  │  离线模式：启发式规则（阈值 + 升级词表）                               │  │
│  └───────────────────────────────┬──────────────────────────────────────┘  │
│          ┌────────────┬──────────┴────────────┬───────────────┐           │
│          ▼            ▼                       ▼               ▼           │
│   VectorStore     TicketService          Conversation       Evaluation    │
│   （ChromaDB）      （SQLite）              Service            Service     │
│   dense+lexical    create/status           sessions/         内置评测套件  │
│   双路检索        流转/列表                messages/反馈                    │
└──────────────────────────────────────────────────────────────────────────┘
```

## 目录结构

```
backend/app/
├── main.py                    # FastAPI 应用入口、SSE 流式端点、API 路由
├── config.py / env_loader.py  # 配置与 .env 加载
├── database.py                # SQLite 连接与建表（兼容旧库补列）
├── schemas.py                 # Pydantic 请求/响应模型
├── tracing.py                 # LangSmith 链路追踪（可选）
└── services/
    ├── agent.py               # SupportAgent：Tool Calling 决策循环 / 离线启发式
    ├── responder.py           # LLM 客户端（含 token 级流式工具调用）+ 回答构建
    ├── providers.py           # 按配置装配 embedder / responder（双模式工厂）
    ├── vector_store.py        # ChromaDB 向量库封装（稠密 + 词法双路检索）
    ├── embedder.py            # 本地哈希 Embedder / OpenAI Compatible Embedder
    ├── ingestion.py           # 文档摄入（去重、入库、分块摘要）
    ├── chunker.py             # 分块策略
    ├── document_loader.py     # txt/md/pdf 解析（PyMuPDF 可选）
    ├── text_matching.py       # 词法匹配（BM25 风格）
    ├── conversations.py       # 会话与消息
    ├── tickets.py             # 工单
    ├── evaluator.py           # 内置评测套件（真实模型基准）
    └── evaluation_history.py  # 评测历史（SQLite）

frontend/src/
├── App.tsx                    # 路由（/chat /knowledge /tickets /sessions /evaluations /dashboard）
├── api/
│   ├── client.ts              # axios 实例与错误提取
│   ├── endpoints.ts           # REST 封装 + chatStream（SSE 解析）
│   └── types.ts               # 类型定义（Ticket / Citation / ChatResponse…）
├── components/layout/         # 侧边导航布局
└── pages/                     # 六个页面
```

## 前端架构

- **React 18 + TypeScript + Vite**，UI 组件库 antd。
- **状态与数据获取**：服务端状态用 `@tanstack/react-query`（查询缓存、mutation），业务组件不直接持有接口逻辑。
- **API 层**：`client.ts` 统一 axios 实例与错误归一化；`endpoints.ts` 为纯函数封装，便于单元测试（用 stub fetch 模拟 SSE 流）。
- **流式聊天**：`chatStream` 用原生 `fetch` + `ReadableStream` 逐行解析 SSE（`data:` 前缀、`[DONE]`、`error` 事件），delta 分片实时回调；`ChatPage` 增量渲染回答，流中断保留已渲染内容并提供重试；组件卸载时以 `AbortController` 中止请求。

## 后端架构

- **FastAPI 单进程多线程**，路由集中在 `main.py`，业务逻辑按领域拆分到 `services/`。
- **双模式装配（providers.py）**：
  - `offline`：本地哈希 Embedder（词袋签名）+ 启发式 Responder，零依赖、零 API Key 可跑通全流程；
  - `openai_compatible`：真实 Embedding + LLM（阿里云百炼等），启动时自动探测嵌入维度并对齐向量集合。

## Agent 决策循环

### 真实模式（Tool Calling）

系统提示词约束 Agent 行为，循环最多 4 轮：

1. LLM 收到用户问题，通常先调用 `search_knowledge(query)`；
2. 工具结果（带检索得分的片段列表）回填到消息上下文；
3. LLM 决定：**直接回答**（附带引用）或 **create_ticket**（知识不足 / 前序方案无效 / 用户要求转人工）；
4. 多轮会话历史从 SQLite 加载进上下文，支持"试过了还是不行"式追问升级。

### 离线模式（启发式）

- 检索 Top-K 片段，`dense_score` 与 `lexical_score` 任一低于阈值即判定"知识不足"→ 转单；
- 命中升级词表（"创建工单 / 转人工 / 还是不行"等）→ 强制转单；
- 否则基于命中的片段拼接步骤式回答。

两种模式产出**同一套 ChatResponse 结构**（mode / answer / citations / ticket / retrieval_score），前端无需感知后端模式差异。

## RAG 数据流

```
上传文件（txt/md/pdf）
   │  document_loader 解析 → RawDocument
   ▼
chunker 按语义切分 → ChunkRecord（含 snippet 摘要）
   │
   ▼
embedder 向量化（真实模型 1024 维 / 离线哈希签名）
   │
   ▼
ChromaDB（按嵌入维度自动命名集合）
   │
   ▼  查询时
VectorStore.search：稠密相似度 + 词法匹配 双路召回 → 合并排序 → 得分阈值过滤
   │
   ▼
回答生成（LLM 基于片段回答 / 启发式拼步骤）→ 每条引用附 source + score
```

## 流式实现（SSE）

- `POST /chat?stream=true` 用 `threading.Thread` 跑 Agent 决策，`Queue` 传递事件，`StreamingResponse` 按 SSE 格式输出 `data: {"type":"delta","content":...}`。
- 真实模式走 `complete_with_tools_stream`：`requests` 流式读取上游 SSE 行，`content` 分片实时回调 `on_delta`，`tool_calls` 按 index 累积（工具轮不推送内容）。
- 离线模式按固定块大小（8 字符）+ 0.05s 节奏模拟分块，保证无模型时流式体验一致。
- **断连清理**：生成器 `finally` 置位 `cancel` 事件，后台线程在 `on_delta` 与分块循环中检查并提前退出，避免资源泄漏。
- **部署注意**：反代层必须关闭缓冲（见 `deploy/nginx/default.conf` 的 `proxy_buffering off`），否则 token 级增量会被整段缓冲。

## 数据存储（SQLite）

| 表 | 用途 |
| --- | --- |
| `conversations` | 会话（session_id、创建/更新时间） |
| `messages` | 会话内消息（角色、内容、`rating` 反馈字段） |
| `tickets` | 工单（ticket_no、问题、原因、摘要、状态流转 open→processing→resolved/closed） |
| `evaluation_runs` | 评测记录（run_id、通过率、完整报告 JSON） |

运行时产物（`storage/app.db`、`storage/chroma`、日志）不入库，`gitignore` 排除。

## 评测

内置 6 条用例套件（4 条知识库命中问答 + 2 条转单），真实模型实测结果见 [docs/benchmark.md](benchmark.md)：

- `POST /evaluate/samples` 运行并落库，`GET /evaluations` 列表、`GET /evaluations/{run_id}` 明细；
- 前端"评测中心"页可一键运行与回看。

## 部署

`docker-compose.yml`（本地）/ `docker-compose.prod.yml`（生产）编排两个服务：

| 服务 | 说明 |
| --- | --- |
| backend | Python 3.12，uvicorn 单进程，挂载 `storage/` 持久化 SQLite 与向量库 |
| frontend | 构建产物由 nginx 托管，`/api` 反代到 backend，SSE 缓冲已关闭 |

- 生产与本地行为一致：`.env` 注入模型配置，未配置即 offline 零依赖运行。
- 健康检查：`GET /health`（`deploy/healthcheck_http.py`）。
