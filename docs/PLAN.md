# ZRAG 实现计划

## 切片规则

| 规则 | 说明 |
|------|------|
| AFK（Away From Keyboard） | AI 自主实现，测试通过 + review 后 merge |
| HITL（Human In The Loop） | 需人工参与的切片 |
| 测试策略 | 每个 AFK 切片自带测试代码，测试通过视为切片验收门槛 |
| 失败升级 | AFK 切片连续 3 次测试不通过 → 自动升级为 HITL |
| 依赖约束 | 上游切片未 merge，下游不启动 |
| 实现顺序 | 抽象类先于实体类 |

---

## 全部切片（45 个）

### 项目骨架

| # | 切片名称 | 类型 | 依赖 |
|---|---------|:--:|------|
| 1 | 项目骨架 + 配置加载 | AFK | 无 |

### 存储层

| # | 切片名称 | 类型 | 依赖 |
|---|---------|:--:|------|
| 2 | SQLiteStore — CRUD 操作封装 | AFK | 1 |
| 3 | ChromaDB — CRUD 操作封装 | AFK | 1 |

### 存储层初始化

| # | 切片名称 | 类型 | 依赖 |
|---|---------|:--:|------|
| 4 | SQLiteStore — 建表初始化（AppConfig.ready() 自动执行 `CREATE TABLE IF NOT EXISTS`） | AFK | 2 |
| 5 | ChromaDB — Collection 管理 | AFK | 3 |

### Embedding

| # | 切片名称 | 类型 | 依赖 |
|---|---------|:--:|------|
| 6 | EmbeddingModel ABC | AFK | 1 |
| 7 | BgeSmallEmbedder | AFK | 6 |

### Source

| # | 切片名称 | 类型 | 依赖 |
|---|---------|:--:|------|
| 8 | DocumentSource ABC | AFK | 1 |
| 9 | MacNotesSource | AFK | 8 |

### Chunking

| # | 切片名称 | 类型 | 依赖 |
|---|---------|:--:|------|
| 10 | ChunkingStrategy ABC | AFK | 1 |
| 11 | 具体 ChunkingStrategy（Paragraph + Recursive + Composite） | AFK | 10 |

### Ingestion

| # | 切片名称 | 类型 | 依赖 |
|---|---------|:--:|------|
| 12 | IngestionPipeline | AFK | 2, 3, 7, 11 |

### LLM

| # | 切片名称 | 类型 | 依赖 |
|---|---------|:--:|------|
| 13 | LLMProvider ABC | AFK | 1 |
| 14 | LLMGatewayProvider | HITL | 13 |

### 检索 + Prompt

| # | 切片名称 | 类型 | 依赖 |
|---|---------|:--:|------|
| 15 | Retriever（Hybrid Search + RRF） | AFK | 2, 3, 7 |
| 16 | PromptBuilder | AFK | 1 |

### API 基础设施

| # | 切片名称 | 类型 | 依赖 |
|---|---------|:--:|------|
| 17 | APIResponse 包装器 | AFK | 1 |
| 18 | RequestIDMiddleware | AFK | 1 |
| 19 | BaseZragException + Handler Registry | AFK | 1 |
| 20 | 具体 Exception 类（Unauthorized/NotFound/Retrieval/LLMCall/Ingestion） | AFK | 19 |
| 21 | API Key 认证 | AFK | 1 |
| 22 | 速率限制（ScopedRateThrottle） | AFK | 1 |
| 23 | IngestGuard（SQLite 并发锁） | AFK | 2 |
| 24 | CORS + CSRF 配置 | AFK | 1 |

### API 端点

| # | 切片名称 | 类型 | 依赖 |
|---|---------|:--:|------|
| 25 | POST /v1/documents/ingest + GET /v1/sources | AFK | 12, 17-24 |
| 26 | POST /v1/conversations（新建会话 + RAG 问答） | AFK | 14, 15, 16, 17-24 |
| 27 | POST /v1/conversations/{id}/messages（继续对话） | AFK | 14, 15, 16, 17-24 |
| 28 | GET /v1/conversations（会话列表） | AFK | 2, 17-24 |
| 29 | GET /v1/conversations/{id}/messages（消息列表） | AFK | 2, 17-24 |
| 30 | DELETE /v1/conversations/{id}（删除会话） | AFK | 2, 17-24 |

### 健康检查

| # | 切片名称 | 类型 | 依赖 |
|---|---------|:--:|------|
| 31 | GET /v1/health/live | AFK | 1, 17 |
| 32 | GET /v1/health/ready | AFK | 1, 17 |

### Web UI

| # | 切片名称 | 类型 | 依赖 |
|---|---------|:--:|------|
| 33 | Vue 项目初始化 + Tailwind + Vue Router + API 封装 | AFK | 25-32 |
| 34 | NavBar 组件（导航栏 + 深色模式切换） | AFK | 33 |
| 35 | ChatInput 组件（自动扩展 textarea + 模型选择器 + 键盘快捷键） | AFK | 33 |
| 36 | ChatMessage 组件（Markdown 渲染 + 代码高亮 + 来源标注 + 复制） | AFK | 33 |
| 37 | ChatSidebar 组件（会话列表 + 切换 + 删除确认弹窗） | AFK | 33 |
| 38 | ChatView 页面（组装 Sidebar + Message + Input + 空状态 + 加载） | AFK | 34, 35, 36, 37 |
| 39 | SourcesView 页面（源卡片 + 摄入按钮 + 进度条 + 报告刷新） | AFK | 33 |
| 40 | 404 页面 + 全局错误处理（Toast 通知） | AFK | 33 |
| 41 | 响应式布局 | AFK | 38, 39 |

### 部署

| # | 切片名称 | 类型 | 依赖 |
|---|---------|:--:|------|
| 42 | Dockerfile.backend + uwsgi.ini + entrypoint.sh（migrate → collectstatic → uwsgi） | AFK | 25-32 |
| 43 | Dockerfile.frontend（多阶段构建） | AFK | 38-41 |
| 44 | nginx.conf（反向代理 + gzip + 超时） | AFK | 42, 43 |
| 45 | docker-compose.yml + .env 模板 + .dockerignore | AFK | 44 |

---

## 统计

| 类型 | 数量 |
|------|:--:|
| AFK | 44 |
| HITL | 1（#14 LLMGatewayProvider） |
| 总计 | 45 |

---

## 开发进度

| # | 切片名称 | 状态 | 测试数 | 提交 |
|---|---------|:--:|:-----:|------|
| 1 | 项目骨架 + 配置加载 | ✅ | 10 | `f3ccf85` |
| 2 | SQLiteStore — CRUD 操作封装 | ✅ | 9 | `66b24cd` |
| 3 | ChromaDB — CRUD 操作封装 | ✅ | 7 | `498110b` |
| 4 | SQLiteStore — 建表初始化 | ✅ | 6 | `b7e8442` |
| 5 | ChromaDB — Collection 管理 | ✅ | 6 | `ea9d435` |
| 6 | EmbeddingModel ABC | ✅ | 3 | `f2dab87` |
| 7 | BgeSmallEmbedder | ✅ | 4 | `71b03ff` |
| 8 | DocumentSource ABC | ⬜ | - | - |
| 9 | MacNotesSource | ⬜ | - | - |
| 10 | ChunkingStrategy ABC | ⬜ | - | - |
| 11 | 具体 ChunkingStrategy | ⬜ | - | - |
| 12 | IngestionPipeline | ⬜ | - | - |
| 13 | LLMProvider ABC | ⬜ | - | - |
| 14 | LLMGatewayProvider | ⬜ | - | - |
| 15 | Retriever（Hybrid Search + RRF） | ⬜ | - | - |
| 16 | PromptBuilder | ⬜ | - | - |
| 17 | APIResponse 包装器 | ⬜ | - | - |
| 18 | RequestIDMiddleware | ⬜ | - | - |
| 19 | BaseZragException + Handler Registry | ⬜ | - | - |
| 20 | 具体 Exception 类（5 个） | ⬜ | - | - |
| 21 | API Key 认证 | ⬜ | - | - |
| 22 | 速率限制 | ⬜ | - | - |
| 23 | IngestGuard | ⬜ | - | - |
| 24 | CORS + CSRF 配置 | ⬜ | - | - |
| 25 | POST /v1/documents/ingest + GET /v1/sources | ⬜ | - | - |
| 26 | POST /v1/conversations | ⬜ | - | - |
| 27 | POST /v1/conversations/{id}/messages | ⬜ | - | - |
| 28 | GET /v1/conversations | ⬜ | - | - |
| 29 | GET /v1/conversations/{id}/messages | ⬜ | - | - |
| 30 | DELETE /v1/conversations/{id} | ⬜ | - | - |
| 31 | GET /v1/health/live | ⬜ | - | - |
| 32 | GET /v1/health/ready | ⬜ | - | - |
| 33 | Vue 项目初始化 | ⬜ | - | - |
| 34 | NavBar 组件 | ⬜ | - | - |
| 35 | ChatInput 组件 | ⬜ | - | - |
| 36 | ChatMessage 组件 | ⬜ | - | - |
| 37 | ChatSidebar 组件 | ⬜ | - | - |
| 38 | ChatView 页面 | ⬜ | - | - |
| 39 | SourcesView 页面 | ⬜ | - | - |
| 40 | 404 页面 + 全局错误处理 | ⬜ | - | - |
| 41 | 响应式布局 | ⬜ | - | - |
| 42 | Dockerfile.backend + uwsgi.ini + entrypoint.sh | ⬜ | - | - |
| 43 | Dockerfile.frontend | ⬜ | - | - |
| 44 | nginx.conf | ⬜ | - | - |
| 45 | docker-compose.yml + .env 模板 + .dockerignore | ⬜ | - | - |

- ✅ 已完成 · 🔄 进行中 · ⬜ 待开始 · ⚠ HITL 升级
