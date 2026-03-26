#!/usr/bin/env python3
"""
Metabase 参数化 native query 连接器（strict mode）。

适用于：
- 带 template-tag 参数的 native SQL 问题（如日期参数 biz_date）
- 口径必须精确一致、不允许降级的场景

策略：
  仅走 POST /api/card/:id/query（带 parameters），失败直接报错，不自动降级。

鉴权：从本地 Chrome 提取 metabase.SESSION cookie（browser_cookie3）。

CLI 用法：
  python -m connectors.metabase.native_connector \\
      --url "https://your-mb/question/14390" \\
      --param biz_date=2026-03-25

  # 多个参数：
  python -m connectors.metabase.native_connector \\
      --url "https://your-mb/question/14390" \\
      --param biz_date=2026-03-25 \\
      --param another_param=value
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from .auto_connector import get_metabase_session


# ── 核心请求 ──────────────────────────────────────────────────────────────────

def fetch_native(
    base_url: str,
    card_id: int,
    parameters: list[dict[str, Any]],
    session_cookies: dict[str, str],
    *,
    timeout: int = 120,
) -> list[dict[str, Any]]:
    """
    调用 POST /api/card/:id/query（native 参数化版本）。

    parameters: Metabase template-tag 参数列表，格式如：
      [{"type": "category", "target": ["variable", ["template-tag", "biz_date"]], "value": "2026-03-25"}]

    返回数据行列表（已将 cols/rows 展开为 dict list）。
    """
    url = f"{base_url}/api/card/{card_id}/query"
    headers = {
        "Content-Type": "application/json",
        "X-Metabase-Session": session_cookies.get("metabase.SESSION", ""),
    }
    payload = {"parameters": parameters}

    try:
        resp = requests.post(
            url,
            json=payload,
            headers=headers,
            cookies=session_cookies,
            timeout=timeout,
        )
    except Exception as exc:
        raise RuntimeError(f"HTTP 请求失败: {exc}") from exc

    if resp.status_code not in (200, 201):
        raise RuntimeError(
            f"HTTP {resp.status_code} {url}\n{resp.text[:500]}"
        )

    body = resp.json()

    # Metabase /query 返回 {"data": {"cols": [...], "rows": [[...], ...]}}
    data_block = body.get("data", {})
    cols = data_block.get("cols", [])
    rows = data_block.get("rows", [])

    if not cols:
        # 兼容部分版本直接返回 list
        if isinstance(body, list):
            return body
        raise RuntimeError(f"无法解析响应结构，keys={list(body.keys())}")

    col_names = [c.get("display_name") or c.get("name", f"col{i}") for i, c in enumerate(cols)]
    return [dict(zip(col_names, row)) for row in rows]


# ── 参数构建工具 ──────────────────────────────────────────────────────────────

def build_parameters(
    param_dict: dict[str, str],
    *,
    param_type: str = "category",
) -> list[dict[str, Any]]:
    """
    将 key=value 字典转成 Metabase template-tag parameters 列表。

    param_type: 默认 "category"，日期字段可改 "date/single"。
    """
    return [
        {
            "type": param_type,
            "target": ["variable", ["template-tag", key]],
            "value": value,
        }
        for key, value in param_dict.items()
    ]


# ── 公开 API ──────────────────────────────────────────────────────────────────

def fetch(
    url: str,
    param_dict: dict[str, str],
    *,
    output: str | Path | None = None,
    timeout: int = 120,
) -> list[dict[str, Any]]:
    """
    strict 模式：仅走 /api/card/:id/query + parameters，失败直接报错。

    url: Metabase 问题 URL，如 https://mb.example.com/question/14390
    param_dict: template-tag 参数，如 {"biz_date": "2026-03-25"}
    output: 若提供，将结果写入该路径（JSON 格式）

    返回记录列表。
    """
    parsed = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    m = re.search(r"/question/(\d+)", parsed.path)
    if not m:
        raise ValueError(f"无法从 URL 解析 question id: {url}")
    card_id = int(m.group(1))

    print(f"\n[Metabase native] card_id={card_id}  host={parsed.netloc}")
    print(f"  参数: {param_dict}")

    session_cookies = get_metabase_session(parsed.hostname)
    parameters = build_parameters(param_dict)

    records = fetch_native(base_url, card_id, parameters, session_cookies, timeout=timeout)
    print(f"✅ 成功，共 {len(records)} 条")

    if output is not None:
        out = Path(output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  已保存到: {out}")

    return records


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Metabase native/strict 模式参数化抓取")
    parser.add_argument("--url", required=True, help="Metabase question URL")
    parser.add_argument(
        "--param",
        action="append",
        metavar="KEY=VALUE",
        default=[],
        help="template-tag 参数，可多次指定，如 --param biz_date=2026-03-25",
    )
    parser.add_argument("--output", default=None, help="输出 JSON 文件路径")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    param_dict: dict[str, str] = {}
    for kv in args.param:
        if "=" not in kv:
            print(f"❌ 参数格式错误（需 KEY=VALUE）: {kv}", file=sys.stderr)
            sys.exit(1)
        k, v = kv.split("=", 1)
        param_dict[k.strip()] = v.strip()

    if not param_dict:
        print("❌ native 模式至少需要一个 --param KEY=VALUE", file=sys.stderr)
        sys.exit(1)

    try:
        records = fetch(args.url, param_dict, output=args.output, timeout=args.timeout)
        if records:
            print(f"\n字段: {list(records[0].keys())}")
    except Exception as exc:
        print(f"❌ {exc}", file=sys.stderr)
        sys.exit(1)
