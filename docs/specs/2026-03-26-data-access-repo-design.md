# 数据访问仓库设计稿

> 创建时间：2026-03-26 16:33  
> 状态：已确认，待实施

---

## 一、项目定位

**`salesdataskills`** 是一个独立的「通用数据访问能力底座」，面向销售团队，通过 OpenClaw skills 方式暴露数据访问能力。

核心原则：
- 抽象能力，不迁移业务链接（用户配置自己的链接）
- 每人独立一套本地数据库，互不影响
- 凭据不完整，禁止安装/启动/运行

---

## 二、架构设计

### 目录结构（目标）

```
salesdataskills/
├── config/
│   ├── config.template.json        # 凭据配置模板（用户复制后填写）
│   └── schema.json                 # 配置项 JSON Schema（preflight 校验用）
├── connectors/
│   ├── crm/
│   │   ├── client.py               # 统一 CRM API 客户端（从 crm_api_client.py 抽象）
│   │   └── endpoints.py            # endpoint registry（可配置，不写死业务路径）
│   └── metabase/
│       ├── auto_connector.py       # 通用降级链：query/json → dataset/csv → Playwright
│       └── native_connector.py     # 参数化 query：/api/card/:id/query + template-tag
├── runtime/
│   ├── init_db.py                  # 本地 SQLite 初始化（每人独立）
│   ├── schema.sql                  # 表结构定义
│   └── migrate.py                  # schema 迁移工具
├── skills/
│   ├── crm-query/
│   │   └── SKILL.md                # CRM 查询 skill（面向 OpenClaw）
│   ├── metabase-fetch/
│   │   └── SKILL.md                # Metabase 抓取 skill
│   └── data-sync/
│       └── SKILL.md                # 数据同步 skill
├── scripts/
│   ├── install.py                  # 安装向导（交互式 + Cursor 引导双入口）
│   └── preflight.py                # 启动前强校验（缺凭据即失败）
├── .env.example                    # 环境变量模板（用户复制后填写）
├── .gitignore                      # 排除 config.local.json、.env、*.db
└── README.md
```

---

## 三、连接器设计

### 3.1 CRM 连接器（`connectors/crm/`）

**能力来源**：从 `openclaw-work/scripts/data-sync/crm_api_client.py` 抽象

**核心能力**：
- 统一鉴权：`INTERNAL_API_KEY / WORKWX_API_KEY / CRM_TOKEN`（三者兼容）
- JWT 过期检测（提前 7 天告警）
- 统一 payload 包装：`{"data": ...}`
- 分页策略：时间窗口递归切片 / index 翻页 / list 批量

**endpoint registry（可配置，不硬编码业务）**：
```json
{
  "chat_session":      "chatSession/page",
  "external_follow":   "externalFollow/page",
  "sales_leads":       "salesLeads/page",
  "user_app":          "userApp/page",
  "live_room_ops":     "liveRoomOperation/page",
  "pgc_resource":      "pgc/resourceSummary/page",
  "pgc_user_summary":  "pgc/userSummary/page",
  "pgc_engage_detail": "pgc/engageDetail/page"
}
```

用户安装时只配置 `base_url` 和 `api_key`，endpoint 路径本仓库内置。

### 3.2 Metabase 连接器（`connectors/metabase/`）

**两种 connector，可配置 mode**：

| Connector | 适用场景 | 降级链 |
|---|---|---|
| `auto_connector` | 通用链接，不带参数 | `query/json` → `dataset/csv` → `Playwright` |
| `native_connector` | 带 template-tag 参数的 native query | 只走 `/api/card/:id/query + parameters`，失败直接报错 |

**mode 参数**：
- `mode=auto`：A 失败自动 B → C
- `mode=strict`：只走 A（带敏感参数/口径必须一致时用）

**鉴权方式**：从 Chrome 本地 cookie 读取 `metabase.SESSION`（`browser_cookie3`）

---

## 四、安装与凭据设计

### 4.1 必填凭据（安装时强校验）

| 凭据 | 对应服务 | 环境变量 |
|---|---|---|
| CRM API Token | CRM / 企微接口 | `INTERNAL_API_KEY` |
| Metabase host | Metabase 实例地址 | `METABASE_HOST` |
| 本地 DB 路径 | 本地 SQLite | `DATA_REPO_DB_PATH` |

缺任何一项 → preflight 失败 → 阻断安装/启动。

### 4.2 双入口安装流程

**Cursor 自然语言入口**：
```
用户说"帮我安装数据访问仓库"
→ Cursor 触发 skills/install-guide/SKILL.md
→ 引导用户逐步填写凭据
→ 调用 scripts/install.py 完成配置
→ 运行 scripts/preflight.py 验证
→ 运行 runtime/init_db.py 建库
```

**终端入口**：
```bash
python scripts/install.py       # 交互式向导
python scripts/preflight.py     # 单独运行校验
python runtime/init_db.py       # 单独初始化数据库
```

两个入口写入同一份 `config.local.json`（不提交 git）。

---

## 五、数据库设计

- 每个用户本地独立一份 SQLite，路径由 `DATA_REPO_DB_PATH` 决定
- 默认路径：`~/Documents/salesdataskills/local.db`
- 初始化脚本：`runtime/init_db.py`
- schema 版本管理：`runtime/migrate.py`

---

## 六、Skills 封装（面向 OpenClaw）

每个 skill 调用通用 connector，不内置业务 URL：

```
skill 被触发
→ 读取 config.local.json 取 base_url + api_key
→ 调用 connector
→ 写入本地 DB 或直接返回 JSON
→ 输出结构化结果
```

---

## 七、错误处理与安全

**强阻断规则（硬门禁）**：
- 任一必填凭据缺失 → 安装失败
- 凭据校验失败（401/403）→ 启动失败
- DB 路径不可写 → 初始化失败

**安全规则**：
- `config.local.json` 和 `.env` 不提交 git（.gitignore 保护）
- 日志默认脱敏（token、cookie 前8位后4位显示）
- skill 不回显凭据

---

## 八、分批抽取计划

| 阶段 | 内容 | 来源文件 | 优先级 |
|---|---|---|---|
| P1 | CRM 通用 CLI 核心 | `openclaw-work/scripts/data-sync/crm_api_client.py` | 最高 |
| P2 | Metabase 通用/参数化抓取器 | `fetch_metabase_question.py` + `fetch_q14390_json.py` | 高 |
| P3 | 安装向导 + preflight | 新建 | 高 |
| P4 | runtime DB 初始化 | `workwx-local-runtime/scripts/init_db.py`（去耦后重写） | 中 |
| P5 | skills 封装 | `shared/skills/` 各 SKILL.md（去耦 baseDir 后移植） | 中 |

**去耦必做项（抽取前必须处理）**：
1. 去掉 `~/openclaw-work` 硬编码 → 改为 `{baseDir}` 或配置项
2. 去掉写死 DB 路径 → 改为 `DATA_REPO_DB_PATH` 环境变量
3. 去掉对 `workspace-techops` 的直接引用 → 改为仓库内部依赖

---

## 九、验收标准

- 新机器安装 ≤ 5 分钟完成配置，通过 preflight
- 至少跑通 1 条 CRM 查询、1 条 Metabase 抓取
- A/B 两个用户 DB 数据互不可见
- OpenClaw skill 调用返回稳定 JSON，不依赖 `openclaw-work` 路径
