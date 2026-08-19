from __future__ import annotations

import os
from typing import Any

import requests
import streamlit as st

from backend.app.env_loader import load_local_env


load_local_env()


DEFAULT_API_BASE = os.getenv("FRONTEND_API_BASE", "http://localhost:8000")


def post_json(
    base_url: str,
    path: str,
    payload: dict | None = None,
    *,
    params: dict[str, Any] | None = None,
) -> dict:
    request_kwargs: dict[str, Any] = {"params": params, "timeout": 60}
    if payload is not None:
        request_kwargs["json"] = payload
    response = requests.post(f"{base_url}{path}", **request_kwargs)
    response.raise_for_status()
    return response.json()


def post_files(base_url: str, path: str, files: list[tuple[str, tuple[str, bytes, str]]]) -> dict:
    response = requests.post(f"{base_url}{path}", files=files, timeout=120)
    response.raise_for_status()
    return response.json()


def get_json(base_url: str, path: str) -> list[dict] | dict:
    response = requests.get(f"{base_url}{path}", timeout=60)
    response.raise_for_status()
    return response.json()


def extract_error_message(exc: requests.RequestException) -> str:
    response = exc.response
    if response is not None:
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict) and payload.get("detail"):
            return str(payload["detail"])
    return str(exc)


def refresh_dashboard(base_url: str) -> None:
    st.session_state["status_data"] = get_json(base_url, "/status")
    tickets = get_json(base_url, "/tickets")
    documents = get_json(base_url, "/documents")
    evaluation_runs = get_json(base_url, "/evaluations")
    st.session_state["tickets"] = tickets if isinstance(tickets, list) else []
    st.session_state["documents"] = documents if isinstance(documents, list) else []
    st.session_state["evaluation_runs"] = evaluation_runs if isinstance(evaluation_runs, list) else []


def clear_result_views() -> None:
    st.session_state.pop("last_result", None)
    st.session_state.pop("last_evaluation", None)


def render_evaluation_report(report: dict) -> None:
    st.markdown(
        f"评测批次：`{report.get('run_id') or '未落盘'}`，"
        f"通过率：`{report['pass_rate']}%`，"
        f"通过 `{report['passed_cases']}` / `{report['total_cases']}`，"
        f"评测时间：`{report['evaluated_at']}`"
    )
    for item in report.get("results", []):
        title = f"{item['case_id']} | {'PASS' if item['passed'] else 'FAIL'}"
        with st.expander(title):
            st.write(f"问题：{item['question']}")
            st.write(f"期望模式：{item['expected_mode']} | 实际模式：{item['actual_mode']}")
            st.write(f"期望文档：{item.get('expected_source') or '无'}")
            st.write(f"实际文档：{item.get('actual_source') or '无'}")
            st.write(f"Top1 得分：{item.get('retrieval_score')}")
            if item.get("details"):
                st.write("失败详情：")
                for detail in item["details"]:
                    st.write(f"- {detail}")


def render_service_status(status: dict | None, documents: list[dict]) -> None:
    st.sidebar.markdown("### 服务状态")
    if not status:
        st.sidebar.warning("后端暂时不可用，请检查 API 地址、后端进程或网络连通性。")
        return

    st.sidebar.success("后端已连接")
    st.sidebar.markdown(
        "\n".join(
            [
                f"- 运行环境：`{status['environment']}`",
                f"- 知识文件：`{len(documents)}`",
                f"- 向量分块：`{status['vector_documents']}`",
                f"- 工单数量：`{status['ticket_count']}`",
                f"- 评测记录：`{status['evaluation_run_count']}`",
                f"- 聊天模型：`{status['chat_provider']} / {status['chat_model']}`",
                f"- 向量模型：`{status['embedding_provider']} / {status['embedding_model']}`",
                f"- PDF 支持：`{'已启用' if status['pdf_supported'] else '未启用'}`",
            ]
        )
    )


st.set_page_config(page_title="IT 知识库工单助手", layout="wide")
st.title("企业 IT 知识库工单助手")
st.caption("面试版 MVP：RAG 检索 + 单 Agent 决策 + 模拟工单创建")

api_base = st.sidebar.text_input("后端 API 地址", DEFAULT_API_BASE).rstrip("/")
if st.session_state.get("api_base") != api_base:
    st.session_state["api_base"] = api_base
    st.session_state.pop("status_data", None)
    st.session_state.pop("tickets", None)
    st.session_state.pop("documents", None)
    st.session_state.pop("evaluation_runs", None)
    clear_result_views()

if "status_data" not in st.session_state:
    try:
        refresh_dashboard(api_base)
    except requests.RequestException:
        st.session_state["status_data"] = None
        st.session_state["tickets"] = []
        st.session_state["documents"] = []
        st.session_state["evaluation_runs"] = []

status = st.session_state.get("status_data")
tickets = st.session_state.get("tickets", [])
documents = st.session_state.get("documents", [])
evaluation_runs = st.session_state.get("evaluation_runs", [])

render_service_status(status, documents)

if st.sidebar.button("刷新状态", use_container_width=True):
    try:
        refresh_dashboard(api_base)
        st.sidebar.success("状态已刷新")
    except requests.RequestException as exc:
        st.sidebar.error(f"刷新失败: {extract_error_message(exc)}")

st.sidebar.markdown("### 知识库管理")

if st.sidebar.button("重置并载入示例知识库", use_container_width=True):
    try:
        payload = post_json(api_base, "/reset", params={"load_samples": True, "clear_evaluations": True})
        refresh_dashboard(api_base)
        clear_result_views()
        st.sidebar.success(
            f"已清空 {payload['deleted_tickets']} 条工单、{payload['deleted_evaluations']} 条评测记录，并导入 {payload['ingested_files']} 个示例文件"
        )
    except requests.RequestException as exc:
        st.sidebar.error(f"重置失败: {extract_error_message(exc)}")

if st.sidebar.button("清空当前数据", use_container_width=True):
    try:
        payload = post_json(api_base, "/reset", params={"clear_evaluations": True})
        refresh_dashboard(api_base)
        clear_result_views()
        st.sidebar.success(
            f"已清空 {payload['deleted_tickets']} 条工单、{payload['deleted_evaluations']} 条评测记录和全部向量索引"
        )
    except requests.RequestException as exc:
        st.sidebar.error(f"清空失败: {extract_error_message(exc)}")

if st.sidebar.button("载入示例知识库", use_container_width=True):
    try:
        payload = post_json(api_base, "/ingest/samples")
        refresh_dashboard(api_base)
        clear_result_views()
        st.sidebar.success(
            f"已导入 {payload['ingested_files']} 个文件，生成 {payload['ingested_chunks']} 个分块"
        )
    except requests.RequestException as exc:
        st.sidebar.error(f"载入失败: {extract_error_message(exc)}")

uploaded_files = st.sidebar.file_uploader(
    "上传知识文档",
    type=["txt", "md", "pdf"],
    accept_multiple_files=True,
)

if st.sidebar.button("上传并建索引", use_container_width=True):
    if not uploaded_files:
        st.sidebar.warning("请先选择文件")
    else:
        try:
            multipart_files = [
                (
                    "files",
                    (
                        file.name,
                        file.getvalue(),
                        "application/octet-stream",
                    ),
                )
                for file in uploaded_files
            ]
            payload = post_files(api_base, "/ingest", multipart_files)
            refresh_dashboard(api_base)
            clear_result_views()
            st.sidebar.success(
                f"已导入 {payload['ingested_files']} 个文件，生成 {payload['ingested_chunks']} 个分块"
            )
        except requests.RequestException as exc:
            st.sidebar.error(f"上传失败: {extract_error_message(exc)}")

st.markdown("### 已载入文档")
if documents:
    for document in documents:
        with st.expander(f"{document['source']} | chunks={document['chunk_count']}"):
            st.write(document["snippet"] or "该文档暂无摘要")
else:
    st.info("当前还没有载入知识文档。")

st.markdown("### 提问")
question = st.text_area(
    "输入你的问题",
    placeholder="例如：VPN 连不上怎么办？",
    height=120,
    key="question_input",
)

if st.button("提交问题", type="primary"):
    if not question.strip():
        st.warning("请输入问题")
    else:
        try:
            st.session_state["last_result"] = post_json(api_base, "/chat", {"message": question})
            refresh_dashboard(api_base)
        except requests.RequestException as exc:
            st.error(f"请求失败: {extract_error_message(exc)}")

result = st.session_state.get("last_result")
if result:
    if result["mode"] == "answer":
        st.success("知识库已命中")
        st.markdown(result["answer"].replace("\n", "  \n"))
    else:
        st.warning("已触发工单创建")
        ticket = result["ticket"]
        st.markdown(f"**工单号**：`{ticket['ticket_no']}`")
        st.markdown(f"**创建原因**：{ticket['reason']}")
        st.markdown(f"**工单摘要**：{ticket['summary']}")

    st.markdown(f"**Top1 检索得分**：`{result.get('retrieval_score', 0)}`")

    citations = result.get("citations", [])
    if citations:
        st.markdown("### 引用来源")
        for citation in citations:
            with st.expander(f"{citation['source']} | score={citation['score']}"):
                st.write(citation["snippet"])

    debug = result.get("debug", {})
    if debug:
        with st.expander("调试信息"):
            st.json(debug)

st.markdown("### 内置评测")
if st.button("运行示例评测"):
    try:
        st.session_state["last_evaluation"] = post_json(api_base, "/evaluate/samples")
        refresh_dashboard(api_base)
    except requests.RequestException as exc:
        st.error(f"评测失败: {extract_error_message(exc)}")

st.markdown("### 评测历史")
if evaluation_runs:
    selected_run_id = st.selectbox(
        "选择历史评测批次",
        options=[item["run_id"] for item in evaluation_runs],
        format_func=lambda run_id: next(
            (
                f"{item['run_id']} | {item['suite_name']} | {item['pass_rate']}%"
                for item in evaluation_runs
                if item["run_id"] == run_id
            ),
            run_id,
        ),
    )
    if st.button("查看历史评测详情"):
        try:
            st.session_state["last_evaluation"] = get_json(api_base, f"/evaluations/{selected_run_id}")
        except requests.RequestException as exc:
            st.error(f"读取评测历史失败: {extract_error_message(exc)}")
else:
    st.info("当前还没有评测历史记录。")

evaluation = st.session_state.get("last_evaluation")
if evaluation:
    render_evaluation_report(evaluation)

st.markdown("### 最近工单")
if st.button("刷新工单列表"):
    try:
        refresh_dashboard(api_base)
    except requests.RequestException as exc:
        st.error(f"读取工单失败: {extract_error_message(exc)}")

if tickets:
    st.dataframe(tickets, use_container_width=True)
else:
    st.info("当前没有工单记录")
