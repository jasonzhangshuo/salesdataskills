# 大数据接口查询（system-bigdata-crm-web）

## 描述

查询红松大数据平台的 8 个标准接口，覆盖 PGC 内容、企微聊天、销售 Leads、直播间、用户行为等数据。

- **鉴权**：在本机 Chrome 登录 CRM（`crm.hongsong.info`）即可，cookie 自动读取，无需手动配置 token
- **Base URL**：`https://crm.hongsong.info/crmapi`
- **服务前缀**：`/api/system-bigdata-crm-web`

> 注意：这是「大数据查询接口」，不是 CRM 业务系统（salesWorkbench）本身。
> 两者共用同一个域名登录，但功能不同。

---

## 8 个接口数据字典

| # | 自然语言关键词 | 接口路径 | 说明 |
|---|---|---|---|
| 1 | PGC内容、内容资源、图文视频数据、资源汇总 | `pgc/resourceSummary/page` | PGC 内容资源汇总（阅读/点赞/收藏/广告/线索等） |
| 2 | PGC用户、关注官方号、老师关注数 | `pgc/userSummary/page` | PGC 用户维度汇总（关注官方号核心指标） |
| 3 | 外部联系人、加微、企微好友、externalFollow | `externalFollow/page` | 企微外部联系人关注/删除记录 |
| 4 | 聊天记录、聊天会话、企微聊天、chatSession | `chatSession/page` | 企微聊天会话列表 |
| 5 | 直播、直播间、liveRoom | `liveRoomOperation/page` | 直播间运营数据 |
| 6 | 销售线索、Leads、意向用户 | `salesLeads/page` | 销售 Leads 列表 |
| 7 | 下载app、注册用户、用户信息、userApp | `userApp/page` | 下载 App / 用户基础信息（含活跃度、AI订阅、扩科意图等） |
| 8 | PGC互动明细、点赞评论、互动行为 | `pgc/engageDetail/page` | PGC 内容互动明细（按用户×资源×日期） |

---

## 使用方式

### 连通性测试

```bash
cd {baseDir}
source .venv/bin/activate
python -m connectors.crm.client
```

### 在代码 / Cursor 中调用

```python
from connectors.crm.client import crm_post, fetch_with_time_window, fetch_with_index_paging

# ── 接口 6：销售 Leads（时间窗口分页，毫秒时间戳）──
rows = fetch_with_time_window(
    "salesLeads/page",
    start_ts=1742745600000,   # 2026-03-24 00:00:00
    end_ts=1742832000000,     # 2026-03-25 00:00:00
    dedup_key="leadsId",
)

# ── 接口 4：聊天会话（时间窗口分页）──
rows = fetch_with_time_window(
    "chatSession/page",
    start_ts=1742745600000,
    end_ts=1742832000000,
    extra_params={"corpId": "your_corp_id"},
)

# ── 接口 3：外部联系人关注（字符串时间）──
from connectors.crm.client import fetch_with_time_window_str
rows = fetch_with_time_window_str(
    "externalFollow/page",
    start_time="2026-03-24 00:00:00",
    end_time="2026-03-24 23:59:59",
)

# ── 接口 1：PGC 内容汇总（index 翻页）──
rows = fetch_with_index_paging(
    "pgc/resourceSummary/page",
    {"statDateStart": "2026-03-24", "statDateEnd": "2026-03-24"},
    page_size=200,
)

# ── 接口 2：PGC 用户汇总（index 翻页）──
rows = fetch_with_index_paging(
    "pgc/userSummary/page",
    {"statDateStart": "2026-03-24", "statDateEnd": "2026-03-24"},
    page_size=200,
)

# ── 接口 7：下载App用户（简单单次）──
rows = crm_post("userApp/page", {"page": 1, "pageSize": 500})

# ── 接口 8：PGC 互动明细（index 翻页）──
rows = fetch_with_index_paging(
    "pgc/engageDetail/page",
    {"startDate": "2026-03-24", "endDate": "2026-03-24"},
    page_size=500,
)
```

---

## 各接口分页类型说明

| 分页类型 | 对应接口 | 用哪个函数 |
|---|---|---|
| 时间窗口递归（毫秒时间戳） | salesLeads、chatSession、liveRoomOperation | `fetch_with_time_window` |
| 时间窗口递归（字符串时间） | externalFollow | `fetch_with_time_window_str` |
| index 翻页 | pgc/resourceSummary、pgc/userSummary、pgc/engageDetail | `fetch_with_index_paging` |
| 单次（无分页限制） | userApp | `crm_post` 直接调用 |

---

## 错误排查

- `❌ 无法获取 CRM token` → 在 Chrome 打开 `https://crm.hongsong.info` 并确认已登录
- `❌ CRM_BASE_URL 未设置` → `.env` 中添加 `CRM_BASE_URL=https://crm.hongsong.info/crmapi`
- `HTTP 401 / 403` → Chrome 中的登录 session 已过期，重新登录后再试
