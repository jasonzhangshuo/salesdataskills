# salesdataskills

销售团队通用数据访问能力底座。将 CRM、Metabase 等数据接口抽象为 CLI 工具和 OpenClaw skills，每人本地独立部署，独立凭据，独立数据库。

---

## 快速开始

### 方式 A：Cursor 自然语言安装（推荐给 Cursor 用户）

用 Cursor 打开项目目录，直接对 AI 说：

> 帮我安装 salesdataskills，引导我配置凭据

Cursor AI 会自动读取 `skills/setup-guide/SKILL.md`，逐步引导你：
建虚拟环境 → 填写凭据到 `.env` → preflight 验证 → 初始化数据库。

### 方式 B：终端交互式安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/install.py      # 交互向导，引导填写凭据
```

### 方式 C：手动配置

```bash
cp .env.example .env
# 编辑 .env，填写 INTERNAL_API_KEY、CRM_BASE_URL、METABASE_HOST
python scripts/preflight.py    # 验证配置
python runtime/init_db.py      # 初始化数据库
```

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
| `CRM_BASE_URL` | CRM 接口 base URL，如 `https://crm.xxx.com/crmapi` | ✅ |
| `METABASE_HOST` | Metabase 实例地址，如 `https://metabase.xxx.com` | ✅ |
| `DATA_REPO_DB_PATH` | 本地 SQLite 路径 | 可选（默认 `~/Documents/salesdataskills/local.db`） |
| `INTERNAL_API_KEY` | CRM token（手动指定时优先于 Chrome cookie）| 可选 |
| `CRM_COOKIE_NAME` | CRM session 的 cookie 名称（自动读取失败时才需要填）| 可选 |

**Token 获取方式**：CRM 和 Metabase 的 token **均自动从 Chrome 读取**，只需在 Chrome 保持登录状态即可，不需要手动复制 token。

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
