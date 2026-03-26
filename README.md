# salesdataskills

销售团队通用数据访问能力底座。将 CRM、Metabase 等数据接口抽象为 CLI 工具和 OpenClaw skills，每人本地独立部署，独立凭据，独立数据库。

---

## 快速开始

### 1. 创建虚拟环境并安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# 可选：Metabase Playwright 兜底
playwright install chromium
```

### 2. 配置凭据

**方式 A：交互式安装向导（推荐）**
```bash
python scripts/install.py
```

**方式 B：手动编辑**
```bash
cp .env.example .env
# 用编辑器填写 INTERNAL_API_KEY、CRM_BASE_URL、METABASE_HOST
```

### 3. 验证安装

```bash
python scripts/preflight.py
```

所有项 ✅ 即可正常使用。

---

## 使用

### CRM 查询

```bash
# 连通性测试
python -m connectors.crm.client

# 测试指定接口
python -m connectors.crm.client --path salesLeads/page
```

### Metabase 抓取

```bash
# auto 模式（自动降级）
python -m connectors.metabase.auto_connector \
    --url "https://your-metabase/question/123" \
    --output /tmp/result.json

# native/strict 模式（带参数）
python -m connectors.metabase.native_connector \
    --url "https://your-metabase/question/14390" \
    --param biz_date=2026-03-25
```

---

## 目录结构

```
salesdataskills/
├── connectors/
│   ├── crm/
│   │   └── client.py           # CRM 统一 API 客户端
│   └── metabase/
│       ├── auto_connector.py   # 通用降级链（A→B→C）
│       └── native_connector.py # 参数化 native query
├── runtime/
│   ├── init_db.py              # SQLite 初始化
│   └── schema.sql              # 表结构定义
├── scripts/
│   ├── install.py              # 交互式安装向导
│   └── preflight.py            # 启动前强校验
├── skills/
│   ├── crm-query/SKILL.md      # OpenClaw CRM 查询 skill
│   └── metabase-fetch/SKILL.md # OpenClaw Metabase 抓取 skill
├── docs/specs/                 # 设计文档
├── .env.example                # 凭据模板
├── requirements.txt
└── README.md
```

---

## 凭据说明

| 变量 | 说明 | 必填 |
|---|---|---|
| `INTERNAL_API_KEY` | CRM API token（JWT）| ✅ 三选一 |
| `WORKWX_API_KEY` | 同上，优先级次之 | ✅ 三选一 |
| `CRM_TOKEN` | 同上，优先级最低 | ✅ 三选一 |
| `CRM_BASE_URL` | CRM 接口 base URL | ✅ |
| `METABASE_HOST` | Metabase 实例地址 | ✅ |
| `DATA_REPO_DB_PATH` | 本地 SQLite 路径 | 可选（有默认值） |

**安全说明**：`.env` 已加入 `.gitignore`，不会被提交。

---

## Metabase 两种模式

| 模式 | 适用场景 | 降级链 |
|---|---|---|
| `auto` | 普通链接，不带参数 | `query/json` → `dataset/csv` → `Playwright` |
| `native/strict` | 带 template-tag 参数（如日期） | 仅 `/api/card/:id/query`，失败即报错 |

---

## 错误排查

**CRM token 过期**
```
❌ CRM API token 已过期
```
→ 重新登录 CRM 系统，复制新 token 到 `.env` 的 `INTERNAL_API_KEY`

**Metabase session 未找到**
```
⚠️ 未在 Chrome 中找到 metabase.SESSION cookie
```
→ 在本机 Chrome 打开 Metabase 地址并登录，然后重试

**preflight 失败**
```
❌ CRM_BASE_URL 未设置
```
→ 在 `.env` 中添加 `CRM_BASE_URL=https://your-crm-host/crmapi`
