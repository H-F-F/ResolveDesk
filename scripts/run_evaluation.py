#!/usr/bin/env python3
"""复现 ResolveDesk 内置评测套件（docs/benchmark.md）。

流程：检查服务状态 → 知识库为空时自动导入样例 → 运行评测 → 打印明细表。

用法：
    python scripts/run_evaluation.py                    # 不清空已有数据
    python scripts/run_evaluation.py --reset            # 清空会话/工单/向量库并重载样例后评测
    python scripts/run_evaluation.py --json report.json # 额外保存原始报告
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def request_json(method: str, url: str, timeout: int = 300) -> dict:
    request = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"请求失败 {method} {url}: HTTP {exc.code}\n{detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"无法连接后端 {url}: {exc.reason}\n请先启动后端（run.ps1 或 uvicorn）") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="复现 ResolveDesk 内置评测套件")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="后端地址")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="评测前清空会话/工单/向量库并重载样例（会删除本地数据）",
    )
    parser.add_argument("--json", dest="json_path", help="把原始评测报告写入指定 JSON 文件")
    parser.add_argument("--timeout", type=int, default=300, help="单次请求超时秒数")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    status = request_json("GET", f"{base_url}/status", timeout=args.timeout)
    chat = status.get("chat_provider", "-")
    chat_model = status.get("chat_model") or "-"
    embedding = status.get("embedding_provider", "-")
    embedding_model = status.get("embedding_model") or "-"
    print(f"服务: {status.get('app', '-')}")
    print(f"LLM: {chat} ({chat_model}) | Embedding: {embedding} ({embedding_model})")

    if args.reset:
        print("清空数据并重载样例知识库 ...")
        request_json("POST", f"{base_url}/reset?load_samples=true", timeout=args.timeout)
    elif status.get("vector_documents", 0) == 0:
        print("知识库为空，导入样例文档 ...")
        request_json("POST", f"{base_url}/ingest/samples", timeout=args.timeout)

    print("运行评测套件（真实模型模式可能需要数十秒）...")
    report = request_json("POST", f"{base_url}/evaluate/samples", timeout=args.timeout)

    print()
    print(f"运行 ID: {report.get('run_id')}  套件: {report['suite_name']}  时间: {report['evaluated_at']}")
    print(f"结果: {report['passed_cases']}/{report['total_cases']} 通过，通过率 {report['pass_rate']:.2f}%")
    print()
    print(f"{'用例':<22}{'期望':<8}{'实际':<8}{'检索分':<8}结果")
    print("-" * 60)
    for case in report["results"]:
        score = case.get("retrieval_score")
        score_text = "-" if score is None else f"{score:.2f}"
        mark = "PASS" if case["passed"] else "FAIL"
        print(f"{case['case_id']:<22}{case['expected_mode']:<8}{case['actual_mode']:<8}{score_text:<8}{mark}")
        for detail in case.get("details", []):
            print(f"  - {detail}")

    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
        print(f"\n原始报告已写入 {args.json_path}")

    return 0 if report["failed_cases"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
