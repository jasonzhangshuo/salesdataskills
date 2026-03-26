# CRM 数据查询

## 描述

查询 CRM 系统数据（销售线索、企微聊天、外部跟进等）。
凭据从用户本地 `.env` 读取，结果写入本地 SQLite 数据库。

## 前置要求

用户必须在项目 `.env` 中配置：
- `INTERNAL_API_KEY`（或 `WORKWX_API_KEY` / `CRM_TOKEN`）
- `CRM_BASE_URL`

## 使用方式

### 连通性测试
```bash
cd {baseDir}
python -m connectors.crm.client
```

### 测试指定接口
```bash
python -m connectors.crm.client --path salesLeads/page --path chatSession/page
```

### 在代码中调用
```python
from connectors.crm.client import crm_post, fetch_with_time_window, fetch_with_index_paging

# 简单查询（单次，最多 20 条）
rows = crm_post("salesLeads/page", {
    "startTimestamp": 1742745600000,
    "endTimestamp": 1742832000000,
    "page": 1,
    "pageSize": 20,
})

# 时间窗口递归分页（自动处理 20 条限制）
rows = fetch_with_time_window(
    "salesLeads/page",
    start_ts=1742745600000,
    end_ts=1742832000000,
    dedup_key="leadsId",
)

# index 翻页（pgc 类接口）
rows = fetch_with_index_paging(
    "pgc/resourceSummary/page",
    {"statDateStart": "2026-03-25", "statDateEnd": "2026-03-25"},
    page_size=200,
)
```

## 支持的 Endpoint

| 业务名称 | 接口路径 | 分页类型 |
|---|---|---|
| 销售线索 | `salesLeads/page` | 时间窗口 |
| 企微聊天 | `chatSession/page` | 时间窗口 |
| 外部跟进 | `externalFollow/page` | 时间窗口（字符串） |
| 用户应用 | `userApp/page` | index 翻页 |
| 直播间操作 | `liveRoomOperation/page` | 时间窗口 |
| PGC 资源汇总 | `pgc/resourceSummary/page` | index 翻页 |
| PGC 用户汇总 | `pgc/userSummary/page` | index 翻页 |
| PGC 互动详情 | `pgc/engageDetail/page` | index 翻页 |

## 错误排查

- `❌ CRM API key 未设置` → 检查 `.env` 中是否有 `INTERNAL_API_KEY`
- `❌ CRM_BASE_URL 未设置` → 检查 `.env` 中是否有 `CRM_BASE_URL`
- `❌ API token 已过期` → 重新登录 CRM 获取新 token，更新 `.env`
- `HTTP 401` → token 无效或已失效
