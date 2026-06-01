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

### 健康检查

| # | 切片名称 | 类型 | 依赖 |
|---|---------|:--:|------|
| 2 | GET /v1/health/live | AFK | 1 |
| 3 | GET /v1/health/ready | AFK | 1 |

### 存储层

| # | 切片名称 | 类型 | 依赖 |
|---|---------|:--:|------|
| 4 | SQLiteStore — 建表初始化 | AFK | 1 |
| 5 | SQLiteStore — CRUD 操作封装 | AFK | 4 |
| 6 | ChromaDB — Collection 管理 | AFK | 1 |
| 7 | ChromaDB — CRUD 操作封装 | AFK | 6 |

### Embedding

| # | 切片名称 | 类型 | 依赖 |
|---|---------|:--:|------|
| 8 | EmbeddingModel ABC | AFK | 1 |
| 9 | BgeSmallEmbedder | AFK | 8 |

### Source

| # | 切片名称 | 类型 | 依赖 |
|---|---------|:--:|------|
| 10 | DocumentSource ABC | AFK | 1 |
| 11 | MacNotesSource | AFK | 10 |

### Chunking

| # | 切片名称 | 类型 | 依赖 |
|---|---------|:--:|------|
| 12 | ChunkingStrategy ABC | AFK | 1 |
| 13 | 具体 ChunkingStrategy（Paragraph + Recursive + Composite） | AFK | 12 |

### Ingestion

| # | 切片名称 | 类型 | 依赖 |
|---|---------|:--:|------|
| 14 | IngestionPipeline | AFK | 5, 7, 9, 13 |

### LLM

| # | 切片名称 | 类型 | 依赖 |
|---|---------|:--:|------|
| 15 | LLMProvider ABC | AFK | 1 |
| 16 | LLMGatewayProvider | HITL | 15 |

### 检索 + Prompt

| # | 切片名称 | 类型 | 依赖 |
|---|---------|:--:|------|
| 17 | Retriever（Hybrid Search + RRF） | AFK | 5, 7, 9 |
| 18 | PromptBuilder | AFK | 1 |

### API 基础设施

| # | 切片名称 | 类型 | 依赖 |
|---|---------|:--:|------|
| 19 | APIResponse 包装器 | AFK | 1 |
| 20 | RequestIDMiddleware | AFK | 1 |
| 21 | BaseZragException + Handler Registry | AFK | 1 |
| 22 | 具体 Exception 类（Unauthorized/NotFound/Retrieval/LLMCall/Ingestion） | AFK | 21 |
| 23 | API Key 认证 | AFK | 1 |
| 24 | 速率限制（ScopedRateThrottle） | AFK | 1 |
| 25 | IngestGuard（SQLite 并发锁） | AFK | 5 |
| 26 | CORS + CSRF 配置 | AFK | 1 |

### API 端点

| # | 切片名称 | 类型 | 依赖 |
|---|---------|:--:|------|
| 27 | POST /v1/documents/ingest + GET /v1/sources | AFK | 14, 19-26 |
| 28 | POST /v1/conversations（新建会话 + RAG 问答） | AFK | 16, 17, 18, 19-26 |
| 29 | POST /v1/conversations/{id}/messages（继续对话） | AFK | 16, 17, 18, 19-26 |
| 30 | GET /v1/conversations（会话列表） | AFK | 5, 19-26 |
| 31 | GET /v1/conversations/{id}/messages（消息列表） | AFK | 5, 19-26 |
| 32 | DELETE /v1/conversations/{id}（删除会话） | AFK | 5, 19-26 |

### Web UI

| # | 切片名称 | 类型 | 依赖 |
|---|---------|:--:|------|
| 33 | Vue 项目初始化 + Tailwind + Vue Router + API 封装 | AFK | 27-32 |
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
| 42 | Dockerfile.backend + uwsgi.ini + entrypoint.sh | AFK | 27-32 |
| 43 | Dockerfile.frontend（多阶段构建） | AFK | 38-41 |
| 44 | nginx.conf（反向代理 + gzip + 超时） | AFK | 42, 43 |
| 45 | docker-compose.yml + .env 模板 + .dockerignore | AFK | 44 |

---

## 统计

| 类型 | 数量 |
|------|:--:|
| AFK | 44 |
| HITL | 1（#16 LLMGatewayProvider） |
| 总计 | 45 |
