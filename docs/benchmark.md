# 真实模型评测基准（Benchmark）

本文档记录 ResolveDesk 在**真实大模型**（阿里云百炼 · OpenAI Compatible）下的可量化表现，用于验证 RAG 检索、Tool Calling Agent 决策与转单链路在真实推理下的效果与边界。

## 评测配置

| 项 | 值 |
| --- | --- |
| 聊天模型 | `qwen-plus`（阿里云百炼，OpenAI Compatible） |
| 向量模型 | `text-embedding-v4`（1024 维，启动时自动探测并命名集合） |
| 知识库 | 内置样例 5 篇（VPN / 打印机 / 邮箱 / Git / Wi-Fi） |
| 评测套件 | 内置 6 条用例：4 条知识库命中问答 + 2 条转单 |
| 运行时间 | 2026-10-09（总耗时约 58s，含模型推理与工具调用） |

> 复现：真实模式启动后调用 `POST /evaluate/samples`，或在前端"评测中心"点击"运行内置评测"；也可直接运行 `python scripts/run_evaluation.py --reset`（自动检查服务、重载样例、运行评测并打印明细）。结果保存于 SQLite 并可经 `GET /evaluations` 回看。

## 结果汇总

**5 / 6 通过（83.33%）**

| 用例 | 问题 | 期望 | 实际 | 命中文档 | 检索得分 | 结果 |
| --- | --- | --- | --- | --- | --- | --- |
| vpn_answer | VPN 连不上怎么办 | answer | answer | vpn_troubleshooting.txt | 0.6093 | ✅ |
| printer_answer | 打印机无法打印怎么处理 | answer | answer | printer_failure.txt | 0.8732 | ✅ |
| email_answer | 邮箱提示密码错误怎么处理 | answer | answer | email_login_reset.txt | 0.5261 | ✅ |
| git_answer | Git push 提示权限不足怎么办 | answer | answer | git_access_issue.txt | 0.8113 | ✅ |
| escalation_ticket | VPN 我试过了还是不行，帮我创建工单 | ticket | ticket | — | — | ✅ |
| unknown_ticket | 公司报销系统打不开 | ticket | answer | wifi_setup.txt（弱相关） | 低分命中 | ❌ |

## 结论

- **知识库问答全部命中**（4/4）：Agent 正确调用 `search_knowledge` 并基于检索片段生成带引用的回答，命中文档与用例期望完全一致。
- **显式升级转单正确**：用户明确要求创建工单时，Agent 正确调用 `create_ticket`。
- **弱相关边界（1 例失败）**：`公司报销系统打不开` 在知识库中无对应文档，但混合检索返回了弱相关的 `wifi_setup.txt`，LLM 选择了基于弱相关片段作答而非转单。这是真实模型下 RAG 的典型边界：**检索有噪声时，模型倾向"尽力回答"而非"承认未知"**。

### 失败案例分析

- 现象：`unknown_ticket` 期望 `mode=ticket`，实际 `mode=answer`，引用 `wifi_setup.txt`。
- 根因：词法覆盖把"打不开"与 Wi-Fi 文档的故障描述产生弱匹配，`RAG_SCORE_THRESHOLD` 未拦截；LLM 在低分证据下仍生成了回答。
- 可选改进方向：
  1. 调高 `RAG_SCORE_THRESHOLD`，低分结果直接引导 Agent 转单；
  2. Agent 系统提示中增加"证据不足时优先转单"约束；
  3. 引入二次判定（如引用分数 + LLM 置信度双门控）。

## 流式延迟实测

真实模型 `stream=true` 下，SSE 为 **token 级真流式**：

- 问题"VPN 连不上怎么办"共返回 **43 个 delta 事件**（token 级分片）
- 总耗时约 **21.5s**，delta 到达间隔 30–158ms（非均匀，为真实逐 token 生成节奏）
- 回答附带 **3 条引用**，首 token 到达即开始前端渲染，无需等待完整答案

## 环境与复现

```powershell
# 1. 配置真实模型（.env）
CHAT_PROVIDER=openai_compatible
EMBEDDING_PROVIDER=openai_compatible
MODEL_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
MODEL_API_KEY=sk-***
CHAT_MODEL_NAME=qwen-plus
EMBEDDING_MODEL_NAME=text-embedding-v4

# 2. 启动后端（自动探测嵌入维度并校验向量库）
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

# 3. 导入样例并运行评测
POST /reset?load_samples=true
POST /evaluate/samples
GET /evaluations
```

> 未配置真实模型时，默认 `offline` 模式零依赖可运行，决策走启发式规则（见 README"两种决策路径"）。
