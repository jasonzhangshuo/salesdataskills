#!/usr/bin/env python3
"""
本地 SQLite 数据库初始化。

读取 DATA_REPO_DB_PATH 环境变量（或默认路径），创建数据库目录，
执行 runtime/schema.sql，输出初始化结果。

用法：
  python runtime/init_db.py
  python runtime/init_db.py --db-path /custom/path/my.db
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"
DEFAULT_DB_PATH = Path("~/Documents/salesdataskills/local.db")


def _resolve_db_path(override: str | None = None) -> Path:
    if override:
        return Path(override).expanduser().resolve()

    # 先尝试从环境变量读（install.py 已经把 .env 写入 os.environ）
    env_val = os.environ.get("DATA_REPO_DB_PATH", "")
    if env_val:
        return Path(env_val).expanduser().resolve()

    # 尝试从 .env 文件加载
    repo_root = Path(__file__).resolve().parent.parent
    for env_file in [Path.cwd() / ".env", repo_root / ".env"]:
        if not env_file.exists():
            continue
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DATA_REPO_DB_PATH="):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                if val:
                    return Path(val).expanduser().resolve()

    return DEFAULT_DB_PATH.expanduser().resolve()


def init_db(db_path: str | Path | None = None) -> Path:
    """
    初始化数据库。

    db_path: 覆盖默认路径（可选）。
    返回最终数据库路径。
    """
    resolved = _resolve_db_path(str(db_path) if db_path else None)

    print(f"数据库路径 : {resolved}")

    # 创建目录
    resolved.parent.mkdir(parents=True, exist_ok=True)

    # 读取 schema
    if not SCHEMA_FILE.exists():
        raise FileNotFoundError(f"schema 文件不存在: {SCHEMA_FILE}")

    schema_sql = SCHEMA_FILE.read_text(encoding="utf-8")

    # 执行 schema
    conn = sqlite3.connect(resolved)
    try:
        conn.executescript(schema_sql)
        conn.commit()

        # 确认表已创建
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]
        version_row = conn.execute(
            "SELECT version, applied_at FROM _schema_version ORDER BY version DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()

    print(f"已创建表   : {', '.join(tables)}")
    if version_row:
        print(f"Schema 版本: v{version_row[0]}（{version_row[1]}）")
    print("✅ 数据库初始化完成")

    return resolved


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="salesdataskills 本地数据库初始化")
    parser.add_argument("--db-path", default=None, help="指定数据库路径（覆盖环境变量）")
    args = parser.parse_args()

    try:
        init_db(db_path=args.db_path)
    except Exception as exc:
        print(f"❌ 初始化失败: {exc}", file=sys.stderr)
        sys.exit(1)
