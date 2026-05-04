# Theme Picker

`theme_picker` 是一个可独立运行的主题选股服务，目标是把“主题事件发现 -> 板块映射 -> 候选股扩池 -> 技术信号筛选 -> 前端回看与重试”做成完整闭环，而不再依赖主仓库的页面或任务状态。

仓库当前由两部分组成：

- 根目录 Python 服务：FastAPI 接口、主题选股核心逻辑、SQLite 持久化、行情与新闻数据适配层
- `web/` 前端子项目：Vite + React 页面，负责发起扫描、轮询任务、查看历史、恢复结果和重新筛选

## 主要能力

- 支持多种输入方式发起主题选股：
  - 已注册主题 ID
  - 主题名称
  - 板块代码
  - 板块名称
- 异步执行主题扫描任务，并提供状态轮询
- 持久化任务历史到 SQLite
- 服务重启后自动恢复 `pending` / `processing` 任务
- 支持历史任务“恢复查看”和“重新筛选”
- 支持主题事件热度、板块映射路径、候选股列表、单票详情、支撑压力位、数据来源说明等结果展示
- 前后端可独立运行，也可通过一个命令同时启动

## 项目结构

```text
.
├── main.py                    # 本地启动入口，支持后端 / 前端 / 同时启动
├── server.py                  # FastAPI 应用入口
├── data/                      # SQLite、主题注册表、板块映射、缓存
├── src/
│   ├── api/                   # 请求/响应 schema 与路由
│   ├── application/           # 主题选股聚合、任务服务、主题注册
│   ├── core/                  # 主题事件扫描主流程编排
│   ├── infrastructure/        # 持久化、事件扫描、扩池、信号判断、运行时配置
│   ├── data_provider/         # 行情/新闻/板块数据源适配
│   └── domain/                # 领域模型
└── web/                       # 独立前端
```

## 运行要求

- Python 3.11+
- Node.js / npm

## 快速开始

### 1. 安装依赖

后端：

```bash
pip install -e .
```

或：

```bash
pip install -r requirements.txt
```

前端：

```bash
cd web
npm install
```

### 2. 初始化本地配置

安装完成后，执行：

```bash
theme-picker init
```

如果你是在源码目录里直接使用，也可以执行：

```bash
python main.py --init-env
```

这个命令会在根目录生成本地 `.env`：

- 如果 `.env` 不存在，会从 `.env.example` 复制生成
- 如果 `.env` 已存在，不会覆盖
- 如需强制重建，可执行 `theme-picker init --force`

你也可以手动复制：

```bash
cp .env.example .env
```

作为兜底机制，如果根目录没有 `.env`，后端首次加载配置时也会自动从 `.env.example` 生成一份本地 `.env`。

### 3. 核心配置项

这些配置建议优先确认：

- `DATABASE_PATH`：本地 SQLite 路径，默认 `./data/stock_analysis.db`
- `THEME_PICKER_TASK_HISTORY_RETENTION_DAYS`：历史保留天数
- `ENABLE_REALTIME_QUOTE`：是否启用实时行情增强

### 4. 可选配置项

#### 行情与板块数据

- `TUSHARE_TOKEN`：启用 Tushare 数据能力时填写
- `PYTDX_HOST` / `PYTDX_PORT` / `PYTDX_SERVERS`：需要自定义 Pytdx 连接时填写
- `LONGBRIDGE_APP_KEY` / `LONGBRIDGE_APP_SECRET` / `LONGBRIDGE_ACCESS_TOKEN`：接入 Longbridge 时填写

#### 新闻检索与搜索源

- `ANSPIRE_API_KEYS`
- `BOCHA_API_KEYS`
- `MINIMAX_API_KEYS`
- `TAVILY_API_KEYS`
- `BRAVE_API_KEYS`
- `SERPAPI_API_KEYS`
- `SEARXNG_BASE_URLS`
- `SEARXNG_PUBLIC_INSTANCES_ENABLED`

只有在你希望启用对应搜索源时，才需要填写这些配置。

#### 实时行情与筛选行为

- `REALTIME_SOURCE_PRIORITY`：实时行情主优先级
- `THEME_REALTIME_SOURCE_PRIORITY`：主题选股使用的实时行情优先级
- `THEME_REALTIME_QUOTE_TIMEOUT`：主题行情超时秒数
- `THEME_TENCENT_QUOTE_TIMEOUT`：腾讯行情超时秒数
- `PREFETCH_REALTIME_QUOTES`：是否预取实时行情
- `ENABLE_EASTMONEY_PATCH`：是否启用 Eastmoney 兼容 patch
- `THEME_BOARD_CACHE_TTL_SECONDS`：板块缓存时长
- `THEME_EXPANSION_QUERY_TIMEOUT`：扩池查询超时
- `NEWS_MAX_AGE_DAYS`：新闻时间窗口
- `NEWS_STRATEGY_PROFILE`：新闻策略窗口档位
- `BIAS_THRESHOLD`：技术分析偏离阈值
- `SQLITE_WAL_ENABLED` / `SQLITE_BUSY_TIMEOUT_MS`：SQLite 运行参数
- `THEME_PICKER_TASK_HISTORY_CLEANUP_BATCH_SIZE`：历史清理批量大小

### 5. 启动服务

只启动后端：

```bash
python main.py --serve
```

只启动前端：

```bash
python main.py --serve-web
```

同时启动前后端：

```bash
python main.py --serve-all
```

也可以直接启动 FastAPI：

```bash
uvicorn server:app --host 127.0.0.1 --port 8765
```

默认地址：

- 后端：`http://127.0.0.1:8765`
- 前端：`http://127.0.0.1:5183/theme-picker`

## API 概览

### 健康检查

- `GET /health`

### 获取可用主题

- `GET /api/v1/theme-picker/themes`

### 提交主题选股任务

- `POST /api/v1/theme-picker/scan`

请求体示例：

```json
{
  "theme_id": "deepseek",
  "strategy_mode": "holding",
  "max_candidates": 8,
  "include_untriggered": false
}
```

也支持以下输入字段中的任意一种：

- `theme_id`
- `theme_name`
- `board_code`
- `board_name`

其中 `strategy_mode` 目前支持：

- `event`：偏短线异动
- `holding`：偏趋势持有

### 查询任务状态

- `GET /api/v1/theme-picker/status/{task_id}`

### 获取任务历史

- `GET /api/v1/theme-picker/history?limit=20`

### 重试历史任务

- `POST /api/v1/theme-picker/retry/{task_id}`

重试会基于历史任务的原始请求重新创建一个新任务，而不是复用旧 `task_id`。

## 前端说明

`web/` 是一个独立前端子项目，当前页面能力包括：

- 注册主题 chips 展示
- 主题 / 板块输入与策略切换
- 异步任务轮询
- 历史抽屉查看
- 历史结果恢复查看
- 失败或已完成任务重新筛选
- 单票详情面板与结果卡片展示

如需单独运行前端：

```bash
cd web
npm run dev
```

前端支持通过环境变量覆盖后端地址：

```bash
VITE_API_URL=http://127.0.0.1:8765
VITE_DEV_PROXY_TARGET=http://127.0.0.1:8765
```

## 开发命令

后端安装开发依赖后可使用：

```bash
pip install -e .[dev]
```

前端常用命令：

```bash
cd web
npm run lint
npm run test
npm run build
```

运行单个前端测试：

```bash
cd web
npm run test -- src/pages/__tests__/ThemeStockPickerPage.test.tsx
```

说明：

- `npm run test` 使用 Vitest + jsdom
- `npm run test:smoke` 已预留给 Playwright，但仓库当前还没有提交 `e2e/` 用例或 `playwright.config.*`

## 当前实现边界

- 已具备独立运行能力，但还没有独立 CI / Dockerfile
- 任务恢复目前基于单进程线程池模型，多实例部署时需要额外设计互斥与抢占
- 后端尚未补齐正式的 `pytest` 测试目录，当前测试主要集中在前端页面交互

## 适用场景

这个仓库更适合以下场景：

- 需要快速验证某个题材是否已出现事件催化
- 想从主题/板块出发筛出一批更可交易的候选股
- 需要把选股结果通过 Web 页面沉淀成可回看、可重试、可恢复的任务历史
