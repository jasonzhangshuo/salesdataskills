# 安装向导（Cursor AI 版）

## 描述

引导用户在本机完成 salesdataskills 的首次安装配置。
适合在 Cursor 中通过自然语言操作（不需要手动敲命令）。

## 触发词

用户说以下任意内容时启动此向导：
- "帮我安装数据访问仓库"
- "配置 salesdataskills"
- "我要开始用这个库"
- "setup"

---

## 向导步骤（AI 执行）

### Step 1：环境检查

```bash
python3 --version
```

确认 Python ≥ 3.9，否则提示用户先安装 Python。

### Step 2：创建虚拟环境并安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Step 3：收集凭据（AI 逐项询问用户）

对用户说：
> 现在需要你提供 3 项凭据，我来帮你写入 .env 文件：
>
> 1. **CRM API Token**（登录 CRM 系统后从"个人设置"或管理员处获取的 JWT token）
> 2. **CRM 接口地址**（格式：`https://crm.your-company.com/crmapi`）
> 3. **Metabase 地址**（格式：`https://metabase.your-company.com`，不加路径）
>
> Metabase 不需要 token，只要你在本机 Chrome 登录过 Metabase 就行。

用户提供后，**把以下内容写入项目根目录的 `.env` 文件**（用 Write 工具，不要用 echo）：

```
INTERNAL_API_KEY=<用户提供的 token>
CRM_BASE_URL=<用户提供的 CRM 地址>
METABASE_HOST=<用户提供的 Metabase 地址>
```

### Step 4：运行 preflight 验证

```bash
source .venv/bin/activate && python scripts/preflight.py
```

- 全部 ✅ → 继续 Step 5
- 有 ❌ → 根据错误信息引导用户修复，修复后重跑此步

### Step 5：初始化本地数据库

```bash
source .venv/bin/activate && python runtime/init_db.py
```

### Step 6：验收测试

```bash
source .venv/bin/activate && python -m connectors.crm.client
```

看到 `✅ salesLeads/page` 表示 CRM 连通成功。

---

## 安装后快速使用

```bash
# 抓取 Metabase 数据（把 URL 换成实际链接）
python -m connectors.metabase.auto_connector --url "https://your-metabase/question/123"

# 带日期参数抓取
python -m connectors.metabase.native_connector \
    --url "https://your-metabase/question/456" \
    --param biz_date=2026-03-26
```

---

## 注意事项

- `.env` 文件已在 `.gitignore` 中，不会被提交，放心填写真实 token
- 每个人有自己独立的 `.env` 和本地数据库，互不影响
- token 过期时 preflight 会提前 7 天告警
