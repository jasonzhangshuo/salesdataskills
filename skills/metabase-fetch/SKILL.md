# Metabase 数据抓取

## 描述

从 Metabase 问题（question）抓取数据，支持两种模式：
- **auto**：通用降级链（A→B→C），适合普通链接
- **native/strict**：参数化 native query，适合带日期等参数的精确查询

## 前置要求

- `METABASE_HOST` 在 `.env` 中已配置
- 已在本机 Chrome 浏览器登录过 Metabase（session cookie 自动提取）
- 依赖：`pip install requests browser-cookie3`

## 使用方式

### auto 模式（通用 URL，自动降级）

```bash
cd {baseDir}
python -m connectors.metabase.auto_connector \
    --url "https://your-metabase/question/123-title" \
    --output /tmp/result.json
```

### native/strict 模式（带参数，精确口径）

```bash
python -m connectors.metabase.native_connector \
    --url "https://your-metabase/question/14390" \
    --param biz_date=2026-03-25 \
    --output /tmp/result.json
```

多个参数：
```bash
python -m connectors.metabase.native_connector \
    --url "..." \
    --param biz_date=2026-03-25 \
    --param another=value
```

### 在代码中调用

```python
# auto 模式
from connectors.metabase.auto_connector import fetch
records = fetch("https://your-metabase/question/123", output="/tmp/out.json")

# native 模式
from connectors.metabase.native_connector import fetch
records = fetch(
    "https://your-metabase/question/14390",
    {"biz_date": "2026-03-25"},
    output="/tmp/out.json",
)
```

## 降级链说明（auto 模式）

| 步骤 | 方法 | 说明 |
|---|---|---|
| A | `POST /api/card/:id/query/json` | 最优先，直接拿 JSON |
| B | `POST /api/dataset/csv` | A 失败后尝试，解析 CSV |
| C | Playwright 页面滚动 | 最后兜底，结果需复核 |

## 何时用 native/strict 模式

- 问题是 native SQL，带有 `{{biz_date}}` 等 template-tag
- 口径必须精确，不能接受降级（如日报/月报同步）
- 数据量大（如 Q14390 10 万行），直接 API 最高效

## 错误排查

- `未找到 metabase.SESSION cookie` → 在 Chrome 打开 Metabase 并登录
- `HTTP 401` → session 已过期，重新在 Chrome 登录
- `无法解析 question id` → URL 格式需为 `/question/数字` 开头
- `browser_cookie3 未安装` → `pip install browser-cookie3`
