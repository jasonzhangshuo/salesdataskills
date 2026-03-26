#!/usr/bin/env python3
"""
Metabase 通用降级链连接器（auto mode）。

抓取策略（依次尝试，失败自动降级）：
  A. POST /api/card/:id/query/json
  B. POST /api/dataset/csv（先 GET /api/card/:id 拿 dataset_query）
  C. Playwright 浏览器滚动抓取（兜底，结果需人工复核）

鉴权：从本地 Chrome 提取 metabase.SESSION cookie（browser_cookie3）。
适用于：不带 template-tag 参数的通用问题 URL。

CLI 用法：
  python -m connectors.metabase.auto_connector --url "https://your-mb/question/123-title"
  python -m connectors.metabase.auto_connector --url "https://your-mb/question/123" --output /tmp/out.json
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

import requests


# ── Cookie 提取 ───────────────────────────────────────────────────────────────

def get_metabase_session(host: str) -> dict[str, str]:
    """从本地 Chrome 提取 Metabase session cookie。"""
    try:
        import browser_cookie3

        cj = browser_cookie3.chrome(domain_name=host)
        cookies = {c.name: c.value for c in cj}
        session = cookies.get("metabase.SESSION", "")
        device = cookies.get("metabase.DEVICE", "")
        if not session:
            print(
                f"⚠️  未在 Chrome 中找到 {host} 的 metabase.SESSION cookie。"
                " 请先在 Chrome 中登录 Metabase。",
                file=sys.stderr,
            )
        else:
            masked = session[:8] + "..." if len(session) > 8 else session
            print(f"  metabase.SESSION: {masked}")
        return {"metabase.SESSION": session, "metabase.DEVICE": device}
    except ModuleNotFoundError:
        print(
            "❌ 缺少 browser_cookie3。请在项目 .venv 中安装：\n"
            "   pip install browser-cookie3",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as exc:
        print(f"❌ 无法提取 Chrome cookie: {exc}", file=sys.stderr)
        sys.exit(1)


# ── 方法 A：query/json ────────────────────────────────────────────────────────

def _fetch_via_query_json(
    base_url: str, card_id: int, session_cookies: dict[str, str], timeout: int = 120
) -> bytes | None:
    """POST /api/card/:id/query/json"""
    url = f"{base_url}/api/card/{card_id}/query/json"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Metabase-Session": session_cookies.get("metabase.SESSION", ""),
    }
    try:
        resp = requests.post(url, headers=headers, cookies=session_cookies, timeout=timeout)
        print(f"  [A] query/json → HTTP {resp.status_code}")
        if resp.status_code in (200, 201) and resp.text.strip():
            return resp.content
        print(f"      响应前200字符: {resp.text[:200]}")
    except Exception as exc:
        print(f"  [A] 请求失败: {exc}", file=sys.stderr)
    return None


# ── 方法 B：dataset/csv ───────────────────────────────────────────────────────

def _fetch_via_dataset_csv(
    base_url: str, card_id: int, session_cookies: dict[str, str], timeout: int = 120
) -> bytes | None:
    """GET /api/card/:id 拿 dataset_query，再 POST /api/dataset/csv。"""
    headers = {"X-Metabase-Session": session_cookies.get("metabase.SESSION", "")}
    try:
        r = requests.get(
            f"{base_url}/api/card/{card_id}",
            headers=headers,
            cookies=session_cookies,
            timeout=30,
        )
        if r.status_code != 200:
            print(f"  [B] 获取 card 元数据失败: HTTP {r.status_code}")
            return None
        dataset_query = r.json().get("dataset_query")
        if not dataset_query:
            print("  [B] card 元数据缺少 dataset_query")
            return None

        resp = requests.post(
            f"{base_url}/api/dataset/csv",
            data={"query": json.dumps(dataset_query)},
            headers=headers,
            cookies=session_cookies,
            timeout=timeout,
        )
        print(f"  [B] dataset/csv → HTTP {resp.status_code}")
        if resp.status_code == 200 and resp.text.strip():
            return resp.content
        print(f"      响应前200字符: {resp.text[:200]}")
    except Exception as exc:
        print(f"  [B] 请求失败: {exc}", file=sys.stderr)
    return None


# ── 方法 C：Playwright 浏览器滚动 ─────────────────────────────────────────────

def _fetch_via_playwright(
    url: str,
    session_cookies: dict[str, str],
    headed: bool = False,
    timeout: int = 90,
) -> dict[str, Any] | None:
    """兜底：Playwright 滚动加载全部虚拟滚动行。"""
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    except ImportError:
        print("❌ 缺少 playwright。请安装：pip install playwright && playwright install chromium")
        return None

    print("  [C] 启动 Playwright 滚动抓取...")
    parsed = urlparse(url)
    cookie_list = [
        {
            "name": name,
            "value": value,
            "domain": parsed.hostname,
            "path": "/",
            "secure": False,
            "httpOnly": False,
        }
        for name, value in session_cookies.items()
        if value
    ]

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=not headed,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            )
        )
        if cookie_list:
            context.add_cookies(cookie_list)

        page = context.new_page()
        page.set_default_timeout(timeout * 1000)

        print(f"  打开页面: {url}")
        page.goto(url, wait_until="networkidle", timeout=timeout * 1000)

        if "login" in page.url or "signin" in page.url:
            print("⚠️  跳转到登录页，会话可能已过期。")
            context.close()
            browser.close()
            return None

        try:
            page.wait_for_selector(".LoadingSpinner, .Loading", state="hidden", timeout=30000)
        except PlaywrightTimeout:
            pass
        time.sleep(2)

        headers = page.evaluate("""() => {
            const ths = document.querySelectorAll(
                'thead th, thead td, .TableInteractive-header .cellData'
            );
            return Array.from(ths).map(el => el.innerText.trim()).filter(h => h);
        }""")

        if not headers:
            print("  ⚠️  未找到列头")
            context.close()
            browser.close()
            return None

        ncols = len(headers)
        print(f"  列数: {ncols}，开始滚动...")

        all_rows: list[list[str]] = []
        seen_rows: set[tuple[str, ...]] = set()
        prev_count = -1
        idle_scrolls = 0

        for _ in range(200):
            batch: list[list[str]] = page.evaluate("""(ncols) => {
                const allCells = [];
                const tbRows = document.querySelectorAll('tbody tr');
                if (tbRows.length > 0) {
                    tbRows.forEach(tr => {
                        const cells = tr.querySelectorAll('td, th');
                        if (cells.length === ncols)
                            allCells.push(Array.from(cells).map(c => c.innerText.trim()));
                    });
                    return allCells;
                }
                const wrappers = document.querySelectorAll(
                    '.TableInteractive-cellWrapper:not(.TableInteractive-header)'
                );
                let row = [];
                wrappers.forEach((cell, i) => {
                    row.push(cell.innerText.trim());
                    if (row.length === ncols) { allCells.push(row); row = []; }
                });
                return allCells;
            }""", ncols)

            for row in batch:
                tup = tuple(row)
                if tup not in seen_rows:
                    seen_rows.add(tup)
                    all_rows.append(row)

            if len(seen_rows) == prev_count:
                idle_scrolls += 1
                if idle_scrolls >= 3 and len(seen_rows) > 0:
                    break
            else:
                idle_scrolls = 0
                prev_count = len(seen_rows)

            page.evaluate("""() => {
                const el = (
                    document.querySelector('.TableInteractive-body') ||
                    document.querySelector('.scroll-hide') ||
                    document.querySelector('[data-testid="table-body"]') ||
                    document.querySelector('tbody') ||
                    document.documentElement
                );
                if (el) el.scrollTop += 500;
                window.scrollBy(0, 500);
            }""")
            time.sleep(0.3)

        context.close()
        browser.close()

        if not all_rows:
            return None
        return {"headers": headers, "rows": all_rows}


# ── 解析工具 ──────────────────────────────────────────────────────────────────

def _parse_json(raw: bytes) -> list[dict[str, Any]]:
    data = json.loads(raw.decode("utf-8", errors="replace"))
    if isinstance(data, list):
        return data
    raise ValueError(f"JSON 不是数组，实际类型: {type(data).__name__}")


def _parse_csv(raw: bytes) -> list[dict[str, Any]]:
    text = raw.decode("utf-8", errors="replace")
    return [dict(row) for row in csv.DictReader(io.StringIO(text))]


# ── 公开 API ──────────────────────────────────────────────────────────────────

def fetch(
    url: str,
    *,
    output: str | Path | None = None,
    headed: bool = False,
    timeout: int = 90,
) -> list[dict[str, Any]]:
    """
    按 auto 策略（A→B→C）从 Metabase URL 抓取数据。

    url: Metabase 问题 URL，如 https://mb.example.com/question/123-title
    output: 若提供，将结果写入该路径（JSON 格式）
    headed: Playwright 兜底时是否使用有头模式
    timeout: 请求超时秒数

    返回记录列表。
    """
    parsed = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    m = re.search(r"/question/(\d+)", parsed.path)
    if not m:
        raise ValueError(f"无法从 URL 解析 question id: {url}")
    card_id = int(m.group(1))

    print(f"\n[Metabase auto] card_id={card_id}  host={parsed.netloc}")

    session_cookies = get_metabase_session(parsed.hostname)

    # A
    raw = _fetch_via_query_json(base_url, card_id, session_cookies, timeout)
    if raw:
        try:
            records = _parse_json(raw)
            _maybe_save(records, output)
            print(f"✅ [A] 成功，共 {len(records)} 条")
            return records
        except Exception as exc:
            print(f"  JSON 解析失败: {exc}")

    # B
    raw = _fetch_via_dataset_csv(base_url, card_id, session_cookies, timeout)
    if raw:
        try:
            records = _parse_csv(raw)
            _maybe_save(records, output)
            print(f"✅ [B] 成功，共 {len(records)} 条")
            return records
        except Exception as exc:
            print(f"  CSV 解析失败: {exc}")

    # C
    print("\n[Step C] A/B 均失败，回退到 Playwright（结果需人工复核）...")
    result = _fetch_via_playwright(url, session_cookies, headed, timeout)

    if not result or not result.get("headers"):
        raise RuntimeError("所有方法均失败，请检查 Metabase 登录状态或手动导出。")

    headers = result["headers"]
    rows = [r for r in result["rows"] if r != headers]
    records = [dict(zip(headers, row)) for row in rows]
    print(f"✅ [C] Playwright 完成，共 {len(records)} 条")
    _maybe_save(records, output)
    return records


def _maybe_save(records: list[dict[str, Any]], output: str | Path | None) -> None:
    if output is None:
        return
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  已保存到: {out}")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Metabase auto 模式抓取")
    parser.add_argument("--url", required=True, help="Metabase question URL")
    parser.add_argument("--output", default=None, help="输出 JSON 文件路径")
    parser.add_argument("--headed", action="store_true", help="Playwright 兜底时使用有头模式")
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()

    try:
        records = fetch(args.url, output=args.output, headed=args.headed, timeout=args.timeout)
        if records:
            print(f"\n字段: {list(records[0].keys())}")
    except Exception as exc:
        print(f"❌ {exc}", file=sys.stderr)
        sys.exit(1)
