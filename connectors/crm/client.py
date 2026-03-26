#!/usr/bin/env python3
"""
CRM 通用 API 客户端。

所有 CRM 接口（system-bigdata-crm-web 服务）共用此模块：
- 统一鉴权：INTERNAL_API_KEY / WORKWX_API_KEY / CRM_TOKEN（优先级依次降低）
- 统一 base URL：由 CRM_BASE_URL 环境变量配置
- 统一 payload 包装：{"data": ...}
- 内置时间窗口递归分页（应对 page=1, pageSize=20 限制）
- index 翻页（用于 pgc/resourceSummary 等接口）
- JWT 过期检测（过期前 7 天告警，过期则拒绝）

可作为 library import，也可 CLI 直接执行做连通性测试：
  python -m connectors.crm.client
  python -m connectors.crm.client --path salesLeads/page
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# ── 默认值（用户可通过环境变量覆盖）──
SERVICE_PREFIX_DEFAULT = "/api/system-bigdata-crm-web"


# ── 环境变量加载 ──────────────────────────────────────────────────────────────

def load_dotenv(extra_paths: list[Path] | None = None) -> None:
    """
    按顺序尝试加载 .env 文件：
    1. 当前目录 .env
    2. 调用方指定的额外路径（extra_paths）
    已设置的环境变量不会被覆盖（setdefault 语义）。
    """
    candidates: list[Path] = [Path.cwd() / ".env"]
    if extra_paths:
        candidates.extend(extra_paths)

    for env_path in candidates:
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):].strip()
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# ── JWT 工具 ──────────────────────────────────────────────────────────────────

def _decode_jwt_exp(token: str) -> int:
    """解码 JWT payload，返回 exp 时间戳（无法解析则返回 0）。"""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return 0
        payload = parts[1] + "=" * (4 - len(parts[1]) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        return int(data.get("exp", 0))
    except Exception:
        return 0


# ── 凭据读取 ──────────────────────────────────────────────────────────────────

def get_api_key() -> str:
    """
    按优先级读取 CRM API key：
      INTERNAL_API_KEY → WORKWX_API_KEY → CRM_TOKEN
    任一存在即使用；全部缺失则以非零状态退出。
    """
    load_dotenv()
    key = (
        os.environ.get("INTERNAL_API_KEY")
        or os.environ.get("WORKWX_API_KEY")
        or os.environ.get("CRM_TOKEN")
        or ""
    )
    if not key:
        print(
            "❌ CRM API key 未设置。请在 .env 中配置以下任一变量：\n"
            "   INTERNAL_API_KEY / WORKWX_API_KEY / CRM_TOKEN",
            file=sys.stderr,
        )
        raise SystemExit(1)

    exp = _decode_jwt_exp(key)
    if exp > 0:
        now = int(time.time())
        days_left = (exp - now) // 86400
        if now >= exp:
            print(
                f"❌ CRM API token 已过期（{time.strftime('%Y-%m-%d', time.localtime(exp))}）",
                file=sys.stderr,
            )
            raise SystemExit(1)
        if days_left < 7:
            print(
                f"⚠️  CRM API token 还剩 {days_left} 天过期，请尽快刷新",
                file=sys.stderr,
            )

    return key


def get_base_url() -> str:
    """从 CRM_BASE_URL 环境变量读取 base URL，未配置则报错。"""
    load_dotenv()
    url = os.environ.get("CRM_BASE_URL", "").rstrip("/")
    if not url:
        print(
            "❌ CRM_BASE_URL 未设置。请在 .env 中添加：\n"
            "   CRM_BASE_URL=https://your-crm-host/crmapi",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return url


def get_service_prefix() -> str:
    """从 CRM_SERVICE_PREFIX 环境变量读取服务前缀，默认 /api/system-bigdata-crm-web。"""
    load_dotenv()
    return os.environ.get("CRM_SERVICE_PREFIX", SERVICE_PREFIX_DEFAULT)


# ── 请求核心 ──────────────────────────────────────────────────────────────────

def _build_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "accept": "application/json",
    }


def crm_post(
    path: str,
    data: dict[str, Any],
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    service_prefix: str | None = None,
    timeout: int = 30,
) -> list[dict[str, Any]]:
    """
    调用 CRM 接口，返回 data 列表。

    path: 接口路径，可带或不带 /api/... 前缀。
          - 以 "/" 开头：直接拼接 base_url，不加 service_prefix
          - 否则：自动加上 service_prefix
    data: 业务参数（自动包装成 {"data": ...}）
    """
    if api_key is None:
        api_key = get_api_key()
    if base_url is None:
        base_url = get_base_url()
    if service_prefix is None:
        service_prefix = get_service_prefix()

    url = f"{base_url}{path}" if path.startswith("/") else f"{base_url}{service_prefix}/{path}"
    payload = json.dumps({"data": data}, ensure_ascii=False).encode("utf-8")
    headers = _build_headers(api_key)

    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {url} -> {err_body[:500]}") from exc

    state = body.get("state", {})
    code = str(state.get("code", ""))
    if code != "0":
        raise RuntimeError(
            f"CRM API 错误 code={code} msg={state.get('msg', '')} path={path}"
        )

    return body.get("data") or []


def crm_post_raw(
    path: str,
    data: dict[str, Any],
    **kwargs: Any,
) -> dict[str, Any]:
    """同 crm_post 但返回完整响应体（含 state / timestamp）。"""
    if "api_key" not in kwargs:
        kwargs["api_key"] = get_api_key()
    if "base_url" not in kwargs:
        kwargs["base_url"] = get_base_url()
    if "service_prefix" not in kwargs:
        kwargs["service_prefix"] = get_service_prefix()

    base_url = kwargs.pop("base_url")
    api_key = kwargs.pop("api_key")
    service_prefix = kwargs.pop("service_prefix")
    timeout = kwargs.pop("timeout", 30)

    url = (
        f"{base_url}{path}"
        if path.startswith("/")
        else f"{base_url}{service_prefix}/{path}"
    )
    payload_bytes = json.dumps({"data": data}, ensure_ascii=False).encode("utf-8")
    headers = _build_headers(api_key)

    req = urllib.request.Request(url, data=payload_bytes, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {url} -> {err_body[:500]}") from exc


# ── 分页策略 ──────────────────────────────────────────────────────────────────

def fetch_with_time_window(
    path: str,
    start_ts: int,
    end_ts: int,
    *,
    page_size: int = 20,
    dedup_key: str = "",
    max_depth: int = 8,
    extra_params: dict[str, Any] | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> list[dict[str, Any]]:
    """
    对 page=1/pageSize=20 限制的接口做时间窗口递归分页（时间戳版本）。

    当单窗口返回 >= page_size 条时，自动二分窗口递归拉取。
    dedup_key: 用于去重的字段名（如 "leadsId"），空则不去重。
    """
    if api_key is None:
        api_key = get_api_key()
    if base_url is None:
        base_url = get_base_url()

    def _fetch(s: int, e: int, depth: int) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "startTimestamp": s,
            "endTimestamp": e,
            "page": 1,
            "pageSize": page_size,
        }
        if extra_params:
            params.update(extra_params)

        rows = crm_post(path, params, api_key=api_key, base_url=base_url)
        if len(rows) < page_size:
            return rows

        if depth >= max_depth:
            print(
                f"⚠️  递归深度 {depth}，窗口 {s}~{e} 仍 {len(rows)} 条，可能不完整",
                file=sys.stderr,
            )
            return rows

        mid = (s + e) // 2
        left = _fetch(s, mid, depth + 1)
        right = _fetch(mid + 1, e, depth + 1)

        if dedup_key:
            seen: set[str] = set()
            result: list[dict[str, Any]] = []
            for r in left + right:
                k = str(r.get(dedup_key, ""))
                if k and k not in seen:
                    seen.add(k)
                    result.append(r)
                elif not k:
                    result.append(r)
            return result

        return left + right

    return _fetch(start_ts, end_ts, 0)


def fetch_with_time_window_str(
    path: str,
    start_time: str,
    end_time: str,
    *,
    page_size: int = 20,
    dedup_key: str = "",
    max_depth: int = 8,
    extra_params: dict[str, Any] | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> list[dict[str, Any]]:
    """
    同 fetch_with_time_window 但接受字符串时间（yyyy-MM-dd HH:mm:ss）。
    用于 externalFollow/page 等使用字符串时间的接口。
    """
    if api_key is None:
        api_key = get_api_key()
    if base_url is None:
        base_url = get_base_url()

    def _fetch(s: str, e: str, depth: int) -> list[dict[str, Any]]:
        from datetime import datetime

        params: dict[str, Any] = {
            "startTime": s,
            "endTime": e,
            "page": 1,
            "pageSize": page_size,
        }
        if extra_params:
            params.update(extra_params)

        rows = crm_post(path, params, api_key=api_key, base_url=base_url)
        if len(rows) < page_size:
            return rows

        if depth >= max_depth:
            print(
                f"⚠️  递归深度 {depth}，窗口 {s}~{e} 仍 {len(rows)} 条，可能不完整",
                file=sys.stderr,
            )
            return rows

        fmt = "%Y-%m-%d %H:%M:%S"
        dt_s = datetime.strptime(s, fmt)
        dt_e = datetime.strptime(e, fmt)
        mid_ts = (dt_s.timestamp() + dt_e.timestamp()) / 2
        mid_str = datetime.fromtimestamp(mid_ts).strftime(fmt)

        left = _fetch(s, mid_str, depth + 1)
        right_start = datetime.fromtimestamp(mid_ts + 1).strftime(fmt)
        right = _fetch(right_start, e, depth + 1)

        if dedup_key:
            seen: set[str] = set()
            result: list[dict[str, Any]] = []
            for r in left + right:
                k = str(r.get(dedup_key, ""))
                if k and k not in seen:
                    seen.add(k)
                    result.append(r)
                elif not k:
                    result.append(r)
            return result

        return left + right

    return _fetch(start_time, end_time, 0)


def fetch_with_index_paging(
    path: str,
    data: dict[str, Any],
    *,
    page_size: int = 200,
    api_key: str | None = None,
    base_url: str | None = None,
) -> list[dict[str, Any]]:
    """
    对 index/pageSize 分页的接口做自动翻页。
    适用于 pgc/resourceSummary/page, pgc/userSummary/page, pgc/engageDetail/page 等。
    """
    if api_key is None:
        api_key = get_api_key()
    if base_url is None:
        base_url = get_base_url()

    all_rows: list[dict[str, Any]] = []
    index = 0
    while True:
        params = {**data, "index": index, "pageSize": page_size}
        rows = crm_post(path, params, api_key=api_key, base_url=base_url)
        all_rows.extend(rows)
        if len(rows) < page_size:
            break
        index += page_size
    return all_rows


# ── CLI：连通性测试 ────────────────────────────────────────────────────────────

def _recent_ts_range() -> tuple[int, int]:
    """返回今日 00:00~08:00 的毫秒时间戳范围（用于 smoke test）。"""
    import datetime

    now = datetime.datetime.now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + datetime.timedelta(hours=8)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def test_connectivity(paths: list[str] | None = None, timeout: int = 15) -> bool:
    """
    测试 CRM 接口连通性。
    paths: 要测试的接口路径列表，默认测试 salesLeads/page 和 userApp/page 两条基础接口。
    返回 True 表示全部通过。
    """
    api_key = get_api_key()
    base_url = get_base_url()
    s, e = _recent_ts_range()

    default_tests: list[tuple[str, dict[str, Any]]] = [
        ("salesLeads/page", {"startTimestamp": s, "endTimestamp": e, "page": 1, "pageSize": 1}),
        ("userApp/page", {"page": 1, "pageSize": 1}),
    ]

    if paths:
        tests = [(p, {"page": 1, "pageSize": 1}) for p in paths]
    else:
        tests = default_tests

    print(f"CRM base URL : {base_url}")
    masked = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"
    print(f"API key      : {masked}")
    print()

    ok = fail = 0
    for path, data in tests:
        try:
            rows = crm_post(path, data, api_key=api_key, base_url=base_url, timeout=timeout)
            print(f"✅ {path:45s} rows={len(rows)}")
            ok += 1
        except Exception as exc:
            print(f"❌ {path:45s} {str(exc)[:100]}")
            fail += 1

    print(f"\n总计: {ok} 通过, {fail} 失败")
    return fail == 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="CRM API 连通性测试")
    parser.add_argument("--path", nargs="*", help="要测试的接口路径（可多个）")
    parser.add_argument("--timeout", type=int, default=15)
    args = parser.parse_args()

    success = test_connectivity(paths=args.path, timeout=args.timeout)
    sys.exit(0 if success else 1)
