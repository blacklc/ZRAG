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

## 新增切片（#101-#108）— RAG 回答质量优化

### 方向 1：导入管线优化

| # | 切片名称 | 类型 | 依赖 |
|---|---------|:--:|------|
| 101 | 切分参数统一 max_size=1000 | AFK | 11 |
| 102a | tags 导出 + MacNotesSource 解析 | AFK | 56 |
| 102b | tags chunk 透传 + FTS5 索引 | AFK | 102a |
| 103 | 代码围栏 `#` 误识别修复 | AFK | 63 |
| 104 | embed_query 指令前缀 | AFK | 7 |
| 105 | Unicode NFC 规范化 | AFK | 56 |

### 方向 2：检索优化

| # | 切片名称 | 类型 | 依赖 |
|---|---------|:--:|------|
| 106a1 | query_rewrite.j2 模板 | AFK | 方向 1 全部 |
| 106a2 | QueryRewriter 类实现 | AFK | 106a1 |
| 106a3 | QueryRewriter 单元测试 | AFK | 106a2 |
| 106b | Retriever 集成 QueryRewriter | AFK | 106a2, 15 |
| 107 | 候选池 k×2 扩大 | AFK | 方向 1 全部, 15 |
| 108 | RRF 可配置权重 | AFK | 方向 1 全部, 15 |

### 验证

| # | 切片名称 | 类型 | 依赖 |
|---|---------|:--:|------|
| 109 | 全链路验证 | AFK | 101-108 全部 |

---

## 统计

| 类型 | 数量 |
|------|:--:|
| AFK | 57 |
| HITL | 1（#14 LLMGatewayProvider） |
| 总计 | 58 |

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
| 8 | DocumentSource ABC | ✅ | 6 | `6fe032a` |
| 9 | MacNotesSource | ✅ | 13 | `e9c0767` |
| 10 | ChunkingStrategy ABC | ✅ | 6 | `4d53919` |
| 11 | 具体 ChunkingStrategy | ✅ | 9 | `10dfa8b` |
| 12 | IngestionPipeline | ✅ | 9 | `711c4a1` |
| 13 | LLMProvider ABC | ✅ | 5 | `73085e7` |
| 14 | LLMGatewayProvider | ✅ | 6 | `852432a` |
| 15 | Retriever（Hybrid Search + RRF） | ✅ | 5 | `c1ff991` |
| 16 | PromptBuilder | ✅ | 4 | `c1ff991` |
| 17 | APIResponse 包装器 | ✅ | 5 | `c1ff991` |
| 18 | RequestIDMiddleware | ✅ | 4 | `c1ff991` |
| 19 | BaseZragException + Handler Registry | ✅ | 23 | `fecdef7` |
| 20 | 具体 Exception 类（5 个） | ✅ | (含在 19) | `fecdef7` |
| 21 | API Key 认证 | ✅ | 4 | `fecdef7` |
| 22 | 速率限制 | ✅ | 3 | `fecdef7` |
| 23 | IngestGuard | ✅ | 4 | `fecdef7` |
| 24 | CORS + CSRF 配置 | ✅ | 3 | `fecdef7` |
| 25 | POST /v1/documents/ingest + GET /v1/sources | ✅ | 15 | `852432a` |
| 26 | POST /v1/conversations | ✅ | 16 | `c46474e` |
| 27 | POST /v1/conversations/{id}/messages | ✅ | (含在 26) | - |
| 28 | GET /v1/conversations | ✅ | (含在 26) | `852432a` |
| 29 | GET /v1/conversations/{id}/messages | ✅ | (含在 28) | `852432a` |
| 30 | DELETE /v1/conversations/{id} | ✅ | (含在 28) | `852432a` |
| 31 | GET /v1/health/live | ✅ | 4 | `852432a` |
| 32 | GET /v1/health/ready | ✅ | (含在 31) | `852432a` |
| 33 | Vue 项目初始化 + 测试基础设施 | ✅ | 76 | `b5f1494` |
| 34 | NavBar 组件 | ✅ | (含在 33) | `d2419fe` |
| 35 | ChatInput 组件 | ✅ | (含在 33) | `bfba551` |
| 36 | ChatMessage 组件 | ✅ | (含在 33) | `577f5c2` |
| 37 | ChatSidebar 组件 | ✅ | (含在 33) | `3ea0395` |
| 38 | ChatView 页面 | ✅ | - | `97fb2b0` |
| 39 | SourcesView 页面 | ✅ | - | `ccb023e` |
| 40 | 404 页面 + 全局错误处理 | ✅ | - | `59817a7` |
| 41 | 响应式布局 | ✅ | - | `6581c3f` |
| — | YAML 配置系统 + 模块集成 | ✅ | 28 | `acc0e23` |
| 42 | Dockerfile.backend + uwsgi.ini + entrypoint.sh | ✅ | - | `3674def` |
| 43 | Dockerfile.frontend | ✅ | - | `a98ea3d` |
| 44 | nginx.conf | ✅ | - | `871441d` |
| 45 | docker-compose.yml + .env 模板 + .dockerignore | ✅ | - | `11b1f83` |
| — | 构建修复: requirements.txt 精简 + curl + log 路径修正 + views.py 延迟导入 | ✅ | - | `(待提交)` |
| — | 日志分级拆分: log_filter.py + settings.py 4 文件 | ✅ | - | `(待提交)` |
| 46 | config/ingest.yaml — task_pool_size + settings.py — ZRAG_INGEST_EXECUTOR | ✅ | - | `(待提交)` |
| 47 | SQLiteStore — init_db() 新增 ingest_tasks 建表 | ✅ | - | `(待提交)` |
| 48 | TaskStatus 枚举 + IngestTask dataclass | ✅ | - | `(待提交)` |
| 49 | TaskManager 模块级单例 | ✅ | - | `(待提交)` |
| 50 | IngestionPipeline — run() 新增 should_cancel/on_document_done | ✅ | - | `(待提交)` |
| 51 | MacNotesSource — 文件桥接模式 | ✅ | - | `(待提交)` |
| 52 | DocumentViewSet.ingest() — 异步返回 202 + task_id | ✅ | - | `(待提交)` |
| 53 | IngestTaskViewSet — status + cancel 端点 | ✅ | - | `(待提交)` |
| 54 | zrag/api/urls.py — task/sources/available 路由 | ✅ | - | `(待提交)` |
| 55 | schema_serializers.py — task 相关 Serializer | ✅ | - | `(待提交)` |
| 56 | export_notes.py — 宿主机导出脚本（根目录） | ✅ | - | `(待提交)` |
| 57 | frontend/src/api/endpoints.js — 新增端点函数 | ✅ | - | `(待提交)` |
| 58 | frontend/src/composables/useIngest.js — 新建 composable | ✅ | - | `(待提交)` |
| 59 | frontend/src/views/SourcesView.vue — 异步交互改造 | ✅ | - | `(待提交)` |
| 60 | 抽象类父类型检查（4 处） | ✅ | - | `(待提交)` |
| 61 | docs/design.md — 同步文档（缺 IngestTaskViewSet） | ⚠️ | - | `(待提交)` |
| 62 | `_html_to_markdown()` 五阶段转换增强 | ✅ | 46 | `167eab5` |
| 63 | 新增 `HeadingChunker` 类 | ✅ | 15 | `167eab5` |
| 64 | registry 中 mac_notes 改用 HeadingChunker | ✅ | (含在 63) | `167eab5` |
| 65 | 安装 jieba + requirements.txt | ✅ | - | `167eab5` |
| 66 | sqlite_store 新增 `_tokenize_text()` | ✅ | 5 | `167eab5` |
| 67 | FTS5 写入路径集成 jieba 分词 | ✅ | 1 | `167eab5` |
| 68 | FTS5 查询路径集成 jieba 分词 | ✅ | 3 | `167eab5` |
| 69 | `SearchResult` 新增 `chunk_index` 字段 | ✅ | 1 | `167eab5` |
| 70 | `_build_results()` 传递 `chunk_index` | ✅ | (含在 69) | `167eab5` |
| 71 | `build_rag_prompt()` 同源 chunks 合并 | ✅ | 2 | `167eab5` |
| 72 | 清空数据库 + 端到端验证 | ✅ | - | `167eab5` |
| 101 | 切分参数统一 max_size=1000 | ✅ | 24 | `(待提交)` |
| 102a | tags 导出 + MacNotesSource 解析 | ✅ | 46 | `(待提交)` |
| 102b | tags chunk 透传 + FTS5 索引 | ✅ | 20 | `(待提交)` |
| 103 | 代码围栏 `#` 误识别修复 | ✅ | 22 | `(待提交)` |
| 104 | embed_query 指令前缀 | ✅ | 5 | `(待提交)` |
| 105 | Unicode NFC 规范化 | ✅ | 54 | `(待提交)` |
| 106a1 | query_rewrite.j2 模板 | ✅ | - | `(待提交)` |
| 106a2 | QueryRewriter 类实现 | ✅ | - | `(待提交)` |
| 106a3 | QueryRewriter 单元测试 | ✅ | 9 | `(待提交)` |
| 106b | Retriever 集成 QueryRewriter | ✅ | 6 | `(待提交)` |
| 107 | 候选池 k×2 扩大 | ✅ | 6 | `(待提交)` |
| 108 | RRF 可配置权重 | ✅ | 6 | `(待提交)` |
| 109 | 全链路验证（构建部署+DB清空） | ✅ | - | `(待提交)` |

- ✅ 已完成 · 🔄 进行中 · ⬜ 待开始 · ⚠ HITL 升级

---

## 新增切片（#46-#61）— macOS Notes 异步文件桥接方案

### 配置 + 存储

| # | 切片名称 | 类型 | 依赖 |
|---|---------|:--:|------|
| 46 | config/ingest.yaml — task_pool_size + settings.py — ZRAG_INGEST_EXECUTOR | AFK | 1 |
| 47 | SQLiteStore — init_db() 新增 ingest_tasks 建表 | AFK | 4 |

### 任务核心

| # | 切片名称 | 类型 | 依赖 |
|---|---------|:--:|------|
| 48 | TaskStatus 枚举 + IngestTask dataclass | AFK | 46 |
| 49 | TaskManager 模块级单例 | AFK | 48, 47 |

### Pipeline

| # | 切片名称 | 类型 | 依赖 |
|---|---------|:--:|------|
| 50 | IngestionPipeline — run() 新增 should_cancel/on_document_done，移除 on_progress/ProgressEvent | AFK | 48 |

### Source

| # | 切片名称 | 类型 | 依赖 |
|---|---------|:--:|------|
| 51 | MacNotesSource — 文件桥接模式，移除 AppleScript | AFK | 49 |

### API

| # | 切片名称 | 类型 | 依赖 |
|---|---------|:--:|------|
| 52 | DocumentViewSet.ingest() — 改为异步返回 202 + task_id | AFK | 50, 51 |
| 53 | IngestTaskViewSet — status + cancel 端点 | AFK | 49 |
| 54 | zrag/api/urls.py — 新增 task/sources/available 路由 | AFK | 52, 53 |
| 55 | schema_serializers.py — 新增 task 相关 Serializer | AFK | 52 |

### 导出脚本

| # | 切片名称 | 类型 | 依赖 |
|---|---------|:--:|------|
| 56 | zrag/export_notes.py — 宿主机导出脚本 | AFK | 无 |

### 前端

| # | 切片名称 | 类型 | 依赖 |
|---|---------|:--:|------|
| 57 | frontend/src/api/endpoints.js — 新增端点函数 | AFK | 53 |
| 58 | frontend/src/composables/useIngest.js — 新建 composable | AFK | 57 |
| 59 | frontend/src/views/SourcesView.vue — 异步交互改造 | AFK | 58 |

### 代码质量

| # | 切片名称 | 类型 | 依赖 |
|---|---------|:--:|------|
| 60 | 抽象类父类型检查（4 处） | AFK | 50, 51, 52 |

### 文档

| # | 切片名称 | 类型 | 依赖 |
|---|---------|:--:|------|
| 61 | docs/design.md — 同步 manifest.json、IngestTaskViewSet 等 | AFK | 全 |

### 混合检索准确度优化（#62-#72）

| # | 切片名称 | 类型 | 依赖 |
|---|---------|:--:|------|
| 62 | `_html_to_markdown()` 五阶段转换增强 | AFK | 无 |
| 63 | 新增 `HeadingChunker` 类 | AFK | 无 |
| 64 | registry 中 mac_notes 改用 `CompositeChunker(HeadingChunker, RecursiveCharacterChunker)` | AFK | 63 |
| 65 | 安装 jieba + requirements.txt | AFK | 无 |
| 66 | sqlite_store 新增 `_tokenize_text()` | AFK | 65 |
| 67 | FTS5 写入路径集成 jieba 分词 | AFK | 66 |
| 68 | FTS5 查询路径集成 jieba 分词 | AFK | 66 |
| 69 | `SearchResult` 新增 `chunk_index` 字段 | AFK | 无 |
| 70 | `_build_results()` 传递 `chunk_index` | AFK | 69 |
| 71 | `build_rag_prompt()` 同源 chunks 合并 | AFK | 70 |
| 72 | 清空数据库 + 端到端验证 | AFK | 62,64,68,71 |


