#!/usr/bin/env python3
"""
启动前强校验（preflight check）。

凭据缺失或无效时以非零状态退出，阻断安装/启动/运行。

用法：
  python scripts/preflight.py              # 检查全部
  python scripts/preflight.py --skip-crm  # 跳过 CRM 检查
  python scripts/preflight.py --skip-metabase  # 跳过 Metabase 检查
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


# ── .env 加载 ─────────────────────────────────────────────────────────────────

def _load_dotenv() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    for env_path in [Path.cwd() / ".env", repo_root / ".env"]:
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


# ── 各项检查 ──────────────────────────────────────────────────────────────────

class _Check:
    def __init__(self, name: str, ok: bool, detail: str) -> None:
        self.name = name
        self.ok = ok
        self.detail = detail


def check_crm() -> list[_Check]:
    results: list[_Check] = []

    # API key
    key = (
        os.environ.get("INTERNAL_API_KEY")
        or os.environ.get("WORKWX_API_KEY")
        or os.environ.get("CRM_TOKEN")
        or ""
    )
    if not key:
        results.append(_Check(
            "CRM API key",
            False,
            "未设置 INTERNAL_API_KEY / WORKWX_API_KEY / CRM_TOKEN",
        ))
    else:
        import base64, json as _json, time
        try:
            parts = key.split(".")
            payload = parts[1] + "=" * (4 - len(parts[1]) % 4)
            exp = int(_json.loads(base64.urlsafe_b64decode(payload)).get("exp", 0))
            if exp > 0:
                days_left = (exp - int(time.time())) // 86400
                if days_left < 0:
                    results.append(_Check("CRM token 有效期", False, f"已过期（{days_left} 天）"))
                elif days_left < 7:
                    results.append(_Check("CRM token 有效期", True, f"⚠️  还剩 {days_left} 天，请尽快刷新"))
                else:
                    results.append(_Check("CRM token 有效期", True, f"还剩 {days_left} 天"))
            else:
                results.append(_Check("CRM API key", True, "已设置（非 JWT 格式，跳过过期检查）"))
        except Exception:
            results.append(_Check("CRM API key", True, "已设置"))

    # base URL
    base_url = os.environ.get("CRM_BASE_URL", "").strip()
    if not base_url:
        results.append(_Check("CRM_BASE_URL", False, "未设置，请在 .env 中配置 CRM_BASE_URL"))
    else:
        results.append(_Check("CRM_BASE_URL", True, base_url))

    return results


def check_metabase() -> list[_Check]:
    results: list[_Check] = []

    host = os.environ.get("METABASE_HOST", "").strip()
    if not host:
        results.append(_Check("METABASE_HOST", False, "未设置，请在 .env 中配置 METABASE_HOST"))
    else:
        results.append(_Check("METABASE_HOST", True, host))

    # 检查 browser_cookie3 是否可用
    try:
        import browser_cookie3  # noqa: F401
        results.append(_Check("browser_cookie3", True, "已安装"))
    except ImportError:
        results.append(_Check(
            "browser_cookie3",
            False,
            "未安装，请运行：pip install browser-cookie3",
        ))

    return results


def check_db() -> list[_Check]:
    results: list[_Check] = []
    db_path_str = os.environ.get(
        "DATA_REPO_DB_PATH",
        "~/Documents/salesdataskills/local.db",
    )
    db_path = Path(db_path_str).expanduser()

    # 检查父目录可写
    parent = db_path.parent
    if not parent.exists():
        try:
            parent.mkdir(parents=True, exist_ok=True)
            results.append(_Check("DB 目录", True, f"{parent}（已自动创建）"))
        except Exception as exc:
            results.append(_Check("DB 目录", False, f"无法创建 {parent}: {exc}"))
    elif not os.access(parent, os.W_OK):
        results.append(_Check("DB 目录", False, f"{parent} 不可写"))
    else:
        results.append(_Check("DB 目录", True, str(parent)))

    results.append(_Check("DB 路径", True, str(db_path)))
    return results


def check_python_deps() -> list[_Check]:
    results: list[_Check] = []
    required = {
        "requests": "requests",
        "browser_cookie3": "browser-cookie3",
    }
    for module, pkg in required.items():
        try:
            __import__(module)
            results.append(_Check(f"dep:{pkg}", True, "已安装"))
        except ImportError:
            results.append(_Check(f"dep:{pkg}", False, f"请运行：pip install {pkg}"))
    return results


# ── 汇总输出 ──────────────────────────────────────────────────────────────────

def run_preflight(skip_crm: bool = False, skip_metabase: bool = False) -> bool:
    _load_dotenv()

    all_checks: list[_Check] = []
    all_checks += check_python_deps()
    all_checks += check_db()
    if not skip_crm:
        all_checks += check_crm()
    if not skip_metabase:
        all_checks += check_metabase()

    print("\n── salesdataskills preflight ──\n")
    failed: list[_Check] = []
    for c in all_checks:
        icon = "✅" if c.ok else "❌"
        print(f"  {icon} {c.name:<30s}  {c.detail}")
        if not c.ok:
            failed.append(c)

    print()
    if failed:
        print(f"🚫 preflight 失败，{len(failed)} 项未通过：")
        for c in failed:
            print(f"   • {c.name}: {c.detail}")
        print("\n请按上方提示修复后重新运行 python scripts/preflight.py\n")
        return False

    print("✅ 所有检查通过，可以继续安装/启动。\n")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="salesdataskills 启动前检查")
    parser.add_argument("--skip-crm", action="store_true", help="跳过 CRM 凭据检查")
    parser.add_argument("--skip-metabase", action="store_true", help="跳过 Metabase 检查")
    args = parser.parse_args()

    ok = run_preflight(skip_crm=args.skip_crm, skip_metabase=args.skip_metabase)
    sys.exit(0 if ok else 1)
