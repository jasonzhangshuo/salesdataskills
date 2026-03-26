#!/usr/bin/env python3
"""
交互式安装向导。

引导用户填写 .env 凭据，运行 preflight，然后初始化本地数据库。

用法：
  python scripts/install.py        # 交互式（推荐）
  python scripts/install.py --check-only  # 仅 preflight，不修改 .env

Cursor 自然语言入口提示（给 AI 助手用）：
  如果用户说"帮我安装数据访问仓库"，请引导他运行：
    python scripts/install.py
  然后按照交互提示填写各项凭据。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / ".env"
ENV_EXAMPLE = REPO_ROOT / ".env.example"


# ── 工具 ──────────────────────────────────────────────────────────────────────

def _read_existing_env() -> dict[str, str]:
    result: dict[str, str] = {}
    if not ENV_FILE.exists():
        return result
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        result[k.strip()] = v.strip().strip('"').strip("'")
    return result


def _write_env(values: dict[str, str]) -> None:
    lines = ["# salesdataskills 凭据（由 install.py 生成，请勿提交 git）", ""]
    for k, v in values.items():
        lines.append(f"{k}={v}")
    lines.append("")
    ENV_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n✅ 已写入 {ENV_FILE}")


def _prompt(label: str, current: str, required: bool = True) -> str:
    hint = f"（当前：{current[:8]}...）" if current and len(current) > 8 else f"（当前：{current}）" if current else ""
    suffix = " [必填]" if required else " [可选，回车跳过]"
    while True:
        val = input(f"  {label}{hint}{suffix}: ").strip()
        if val:
            return val
        if current:
            return current
        if not required:
            return ""
        print("  ⚠️  此项为必填，请输入值。")


# ── 安装流程 ──────────────────────────────────────────────────────────────────

def run_install(check_only: bool = False) -> None:
    print("\n══════════════════════════════════════════════")
    print("  salesdataskills 安装向导")
    print("══════════════════════════════════════════════\n")

    existing = _read_existing_env()

    if check_only:
        print("ℹ️  --check-only 模式，跳过 .env 编辑\n")
    else:
        print("请依次填写以下凭据（回车保留已有值）：\n")

        print("── CRM 配置 ──")
        crm_key = _prompt(
            "CRM API Token (INTERNAL_API_KEY)",
            existing.get("INTERNAL_API_KEY", ""),
            required=True,
        )
        crm_url = _prompt(
            "CRM Base URL (如 https://crm.your-company.com/crmapi)",
            existing.get("CRM_BASE_URL", ""),
            required=True,
        )

        print("\n── Metabase 配置 ──")
        mb_host = _prompt(
            "Metabase Host (如 https://metabase.your-company.com)",
            existing.get("METABASE_HOST", ""),
            required=True,
        )

        print("\n── 本地数据库路径（可选）──")
        db_path = _prompt(
            "DB 路径（默认 ~/Documents/salesdataskills/local.db）",
            existing.get("DATA_REPO_DB_PATH", ""),
            required=False,
        )

        new_env: dict[str, str] = {
            "INTERNAL_API_KEY": crm_key,
            "CRM_BASE_URL": crm_url,
            "METABASE_HOST": mb_host,
        }
        if db_path:
            new_env["DATA_REPO_DB_PATH"] = db_path

        print()
        _write_env(new_env)

    # preflight
    print("\n── 运行 preflight 检查 ──")
    sys.path.insert(0, str(REPO_ROOT))
    from scripts.preflight import run_preflight

    ok = run_preflight()
    if not ok:
        print("❌ 安装中止，请修复上方问题后重新运行。")
        sys.exit(1)

    # 初始化数据库
    print("── 初始化本地数据库 ──")
    try:
        from runtime.init_db import init_db
        init_db()
    except Exception as exc:
        print(f"❌ 数据库初始化失败: {exc}", file=sys.stderr)
        sys.exit(1)

    print("\n🎉 安装完成！\n")
    print("下一步：")
    print("  • 查询 CRM 数据：python -m connectors.crm.client")
    print("  • 抓取 Metabase：python -m connectors.metabase.auto_connector --url <URL>")
    print("  • 带参数抓取：python -m connectors.metabase.native_connector --url <URL> --param biz_date=2026-03-25")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="salesdataskills 安装向导")
    parser.add_argument("--check-only", action="store_true", help="仅运行 preflight，不修改 .env")
    args = parser.parse_args()

    run_install(check_only=args.check_only)
