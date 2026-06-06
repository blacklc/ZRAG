# ZRAG 产品需求文档 — 个人 RAG 知识库系统

## 问题陈述

用户的知识分散在 macOS 备忘录、本地 Markdown/PDF/DOCX 文件中。每当需要查找某个知识点时，必须手动翻阅多个来源，效率低下。用户需要一个能够理解自然语言问题的知识库系统，快速检索相关文档内容并生成可信回答。

核心痛点：
- 知识碎片化，散落在不同 App 和文件系统中
- 手动搜索无法处理"语义相近但用词不同"的查询
- 无法对知识进行自然语言级别的归纳与问答

## 解决方案

ZRAG 是一个**本地优先的个人 RAG 知识库系统**。用户将文档导入后，系统自动分块、向量化并存储。用户通过 Web UI 或 API 用自然语言提问，系统执行混合检索（语义 + 关键词），将最相关的内容作为上下文提交给 LLM，生成带来源标注的回答。

核心能力：
- **文档摄入**：从 macOS Notes 等来源自动拉取 → 分块 → 向量化 → 双库存储
- **混合检索**：语义检索（ChromaDB）+ 关键词检索（SQLite FTS5 BM25）→ RRF 融合排序
- **RAG 问答**：检索结果 → Prompt 构建 → LiteLLM Gateway → LLM 生成回答（附来源标注）
- **会话管理**：多轮对话持久化，支持切换、继续和删除历史对话
- **Web UI**：Apple 风格聊天界面，深色/浅色模式切换，Markdown 渲染，代码高亮

## 用户故事

1. 作为知识工作者，我希望用自然语言向知识库提问，以便快速找到相关信息而无须手动翻阅文件
2. 作为笔记用户，我希望 macOS 备忘录能被自动导入知识库，以便不需要手动复制粘贴内容
3. 作为开发者，我希望每条 AI 回答都能标注引用来源，以便验证回答的准确性
4. 作为注重隐私的用户，我希望所有数据都存储在本地，以便个人笔记不会离开我的设备
5. 作为普通用户，我希望能够继续之前的对话，以便在已有问答的基础上进行追问
6. 作为普通用户，我希望删除不需要的旧对话，以便保持对话历史的整洁
7. 作为普通用户，我希望在浅色和深色模式之间切换，以便在白天和晚上都能舒适使用
8. 作为技术用户，我希望 AI 回答中的代码块能够语法高亮，以便技术类回答易于阅读
9. 作为普通用户，我希望 AI 生成回答时有加载动画，以便知道系统正在工作中
10. 作为运维人员，我希望通过一条 docker compose up 命令完成部署，以便部署过程无痛苦
11. 作为普通用户，我希望一键触发增量文档导入，以便新笔记能够快速被索引
12. 作为普通用户，我希望看到导入进度指示，以便知道摄入正在进行中
13. 作为普通用户，我希望 API 调用失败时显示明确的错误提示，以便知道出了什么问题
14. 作为普通用户，我希望能够一键复制 AI 的回答内容，以便在其他地方复用
15. 作为普通用户，我希望选择使用哪个 LLM 模型，以便在质量和速度之间做出权衡
16. 作为普通用户，我希望用 Shift+Enter 输入多行问题，以便能够粘贴代码片段进行分析
17. 作为开发者，我希望有一套 RESTful API 和一致的错误处理，以便在 ZRAG 之上构建集成
18. 作为普通用户，我希望通过左侧边栏切换不同的历史对话，以便查阅之前的讨论

## 实现决策

### 总体架构

- 语言：原生 Python（不使用 LangChain / LlamaIndex）
- API 框架：Django REST Framework（ViewSet + re_path 路由，v1/ 版本前缀）
- 前端：Vue 3 + Vite + Tailwind CSS（Apple 风格 UI），与后端分离
- WSGI Server：uWSGI（1 worker，180 秒 harakiri 超时）
- LLM 网关：LiteLLM Gateway（自托管，OpenAI 兼容端点 localhost:4000/v1）
- 规模：个人使用，< 1000 篇文档，单用户

### 存储层

- SQLite（data/zrag.db）：数据源，存储 chunks 原文、FTS5 全文索引、processed_docs 处理进度、conversations 会话、messages 消息
- ChromaDB（data/chroma_db/）：向量存储，Cosine 距离，单 Collection "zrag_docs"
- 数据一致性策略：先写 SQLite（ACID 保证），后写 ChromaDB（失败可补偿重试）。processed_docs 标记"双库均已就绪"
- FTS5 提供内置 BM25 评分——无需手写 BM25，零额外依赖

### 文档摄入

- DocumentSource 抽象基类，定义 fetch_batch() 和 source_type 接口——首个实现为 MacNotesSource
- ChunkingStrategy 抽象基类，定义 chunk(document) → list[Chunk] 接口——ParagraphChunker、MarkdownHeadingChunker、RecursiveCharacterChunker、CompositeChunker
- IngestionPipeline 编排全流程：Source → Chunk → Embed → 写 SQLite → 写 ChromaDB → 更新 processed_docs
- 每篇文档独立事务（非批量事务）
- 默认增量导入（content_hash 对比），全量导入通过 {"full": true} 触发
- LLM 调用在数据库事务之外——失败则零副作用，无需回滚

### Embedding

- 模型：BAAI/bge-small-zh-v1.5（512 维，sentence-transformers 加载）
- EmbeddingModel 抽象基类，定义 embed(texts)、embed_query(query) 和 dimension 接口
- 模型在宿主机预下载，容器内通过只读 volume 挂载，启动时零等待

### 检索层

- 混合检索：ChromaDB similarity_search(k=10) + SQLite FTS5 bm25()(k=10) → RRF 融合(k=60)
- RRF 公式：score(d) = 1/(60 + rank_vector) + 1/(60 + rank_bm25)
- 结果按 RRF 分数排序，通过排序融合自然去重
- PromptBuilder 独立负责 Prompt 构建，与 LLM 通信解耦
- 检索异常统一抛出 RetrievalException（500，内层异常链式传递）

### LLM Provider

- LLMProvider 抽象基类：chat(messages) → str、chat_stream(messages) → Iterator[str]（Phase 2）
- LLMGatewayProvider：通过 OpenAI SDK 调用 LiteLLM Gateway
- 错误处理策略：有回调 → 通知回调 + 不抛异常；无回调 → 抛 BaseZragException
- 超时时间：200 秒
- 可用模型（通过 LiteLLM Gateway 配置）：smart-router（负载均衡组）、glm-5、kimi-k2.6、deepseek-v4-flash、minimax-m2.7、deepseek-v4-pro

### API 层

- 自定义 APIResponse 包装器：Message + Data + RequestID + X-Request-ID 响应头
- 异常体系：BaseZragException + Handler Registry（参照 zonebank 模式）
- 异常类型：UnauthorizedException(401)、NotFoundException(404)、RetrievalException(500)、LLMCallException(502)、IngestionException(500)
- 认证：API Key，Authorization Header，全部端点统一要求（健康检查除外）
- CSRF 已禁用，CORS 通过 django-cors-headers（Phase 1 全放通）
- 速率限制：ScopedRateThrottle（聊天 10 次/分钟，摄入 3 次/分钟）
- IngestGuard：基于 SQLite 原子 UPDATE 的并发锁
- 流式端点（/stream）延后至 Phase 2
- 请求校验：DRF Serializer，query 字段 max_length=2000

### 端点列表

| 端点 | 方法 | 说明 |
|------|:--:|------|
| POST /v1/conversations | POST | 新建会话 + 首条问答 |
| POST /v1/conversations/{id}/messages | POST | 在已有会话中继续问答 |
| GET /v1/conversations | GET | 会话列表（含 total 总数，按最近消息倒序） |
| GET /v1/conversations/{id}/messages | GET | 获取某会话的全部消息 |
| DELETE /v1/conversations/{id} | DELETE | 删除会话及消息（幂等） |
| POST /v1/documents/ingest | POST | 触发文档摄入（支持 full 参数） |
| GET /v1/sources | GET | 列出 Source 及文档统计 |
| GET /v1/health/live | GET | Liveness（进程存活） |
| GET /v1/health/ready | GET | Readiness（SQLite + ChromaDB 依赖检查） |

### Web UI

- 技术栈：Vue 3 + Vite + Vue Router（History 模式）+ Tailwind CSS
- Apple 风格：毛玻璃导航栏、大圆角卡片、柔和阴影、SF 系统字体
- 页面：聊天主页 / + 源管理 /sources
- 深色模式：手动切换（导航栏 ☀️/🌙 图标），偏好存 localStorage
- 键盘快捷键：Enter 发送、Shift+Enter 换行、Cmd+K 新建对话、Cmd+/ 聚焦输入框
- AI 回复加载状态：三个跳动圆点（打字指示器）
- 空状态：ZRAG 标志 + "向你的知识库提问"
- 来源标注：消息下方灰字显示 "📎 来源: 文档标题"
- 消息气泡复制：悬停显示复制按钮
- Markdown 渲染：marked.js + highlight.js（主题跟随深色/浅色模式切换）
- 消息自动滚到底，用户上滚查看历史时不强制跳回
- 404：Apple 极简风格组件
- Favicon：📚 emoji 或简洁 SVG
- 页面标题：固定 "ZRAG"
- 响应式布局：移动端侧边栏可折叠
- 输入框：自动扩展 textarea（最大 6 行），占位符 "向你的知识库提问"
- 源管理页：增量导入 + 全量导入两个按钮，点击后显示不确定进度条，完成后自动刷新
- API 错误处理：网络/500 错误 → Toast 通知；对话错误 → 红色消息气泡
- 无需设置面板（API Key 构建时注入）
- API Key：通过 VITE_API_KEY 环境变量在构建时注入，前端 JS 直接使用

### 会话存储

- conversations 表：id、title、created_at
- messages 表：id、conversation_id、role(user|assistant)、content、sources(JSON)、created_at
- 无 updated_at 字段（通过子查询获取最新消息时间），不存模型名
- 删除级联：同事务中 DELETE messages → DELETE conversations
- 会话在首条消息时自动创建，不需要预先创建空会话

### 配置管理

- config/ 目录下按模块分文件：llm.yaml、embedding.yaml、ingest.yaml、api.yaml、storage.yaml、retrieval.yaml
- 动态合并加载器：排序 glob -> 合并嵌套键 -> 解析环境变量 ${VAR} -> 环境变量覆盖
- 配置加载三阶段流程：
  - 阶段 1：YAML 文件扫描合并
  - 阶段 2：${VAR:-default} 占位符递归替换
  - 阶段 3：同名 UPPER_SNAKE 环境变量覆盖叶子节点（如 LLM_TIMEOUT 覆盖 llm.timeout）
- 环境变量覆盖优先级高于 YAML 配置和 ${VAR:-default} 默认值
- 配置变更流程：修改 .env -> docker compose restart
- 容器部署场景下无需修改 YAML 文件，通过 docker-compose environment 或 .env 即可覆盖任意配置项
- Django 敏感配置（DEBUG、SECRET_KEY、ALLOWED_HOSTS）统一通过 .env 管理

### 部署

- 三容器方案：Nginx（反向代理 + gzip）+ Frontend（nginx:alpine + dist/）+ Backend（uWSGI + Django）
- Nginx：宿主机 80 端口，独立部署（`nginx.sh start`），非 docker-compose 管理
- Frontend：内部 80 端口，仅 expose
- Backend：内部 5965 端口，仅 expose
- 数据持久化：./data/pro:/app/data（zrag.db + chroma_db + django.db）
- 模型挂载：/Users/lichen/Documents/workspace/models:/app/models:ro（只读，绝对路径）
- 日志持久化：./logs/pro:/app/log（业务日志）
- 环境变量：.env 文件 + docker-compose ${VAR} 引用
- entrypoint.sh：migrate → collectstatic → uwsgi（建表由 AppConfig.ready() 自动执行 `CREATE TABLE IF NOT EXISTS`）
- 健康检查：Frontend（curl /）、Backend（curl /v1/health/live）
- 资源限制：Backend 512M/2CPU，Frontend 64M/0.5CPU，Nginx 64M/0.5CPU
- 日志轮转：json-file driver，10MB × 3 文件
- 重启策略：unless-stopped
- Nginx 代理超时：proxy_read_timeout 180s，proxy_connect_timeout 10s
- 无 CI/CD——手动 docker compose build && up -d
- **Python 依赖管理策略**: `requirements.txt` 仅锁定核心生产直接依赖（~7 个包，`==` 精确版本）。传递依赖由 `pip install` 在 Docker Linux 容器构建时自行解析版本。不使用 `pip freeze` 全量锁定的方式，避免 macOS（arm64）开发环境与 Linux（amd64）部署环境的跨平台依赖冲突。
- 时区：Asia/Shanghai

### 数据库 Schema

```sql
CREATE TABLE chunks (chunk_id TEXT PK, source_id TEXT, source_type TEXT, doc_title TEXT, content TEXT, chunk_index INTEGER, created_at TEXT);
CREATE VIRTUAL TABLE chunks_fts USING fts5(content, content=chunks, content_rowid=rowid);
CREATE TABLE processed_docs (source_id TEXT PK, source_type TEXT, content_hash TEXT, imported_at TEXT);
CREATE TABLE conversations (id TEXT PK, title TEXT, created_at TEXT);
CREATE TABLE messages (id TEXT PK, conversation_id TEXT FK, role TEXT, content TEXT, sources TEXT, created_at TEXT);
```

## 测试决策

### 什么构成好的测试
- 只测试外部行为，不测试内部实现细节
- 每个模块的公共接口应可独立测试
- 存储测试使用真实 SQLite（内存或临时文件），不使用 mock
- 向量测试使用真实 ChromaDB（临时目录）
- 仅 mock 外部依赖（LiteLLM Gateway、macOS AppleScript）

### 待测试模块

| 模块 | 测试重点 |
|------|---------|
| 存储层 SQLite | CRUD 操作、FTS5 搜索、事务回滚、processed_docs 追踪 |
| 存储层 ChromaDB | add、similarity_search、delete_by_source、Collection 管理 |
| Embedding | embed() 返回正确维度、embed_query() 一致性、normalize_embeddings |
| 摄入 MacNotesSource | osascript mock、HTML→Markdown 转换、fetch_batch 分页 |
| 摄入 ChunkingStrategy | 分块边界、max_size 强制、overlap 行为、CompositeChunker 递归 |
| 摄入 IngestionPipeline | 全流程 run()、重复检测、全量导入模式、错误事件发送 |
| LLM Provider | chat() 带 mock gateway、错误处理（回调 vs 抛异常）、超时行为 |
| 检索 Retriever | hybrid_search 去重结果、RRF 评分正确性、空结果处理 |
| 检索 PromptBuilder | build() 输出结构、上下文截断、来源格式化 |
| API 全部端点 | 请求/响应校验、认证检查、速率限制、错误响应、404 处理 |
| 会话 API | create/list/get/delete 流程、不存在对话 404、DELETE 幂等、LLM 失败回滚 |
| Web UI | 组件渲染、聊天流程、深色模式切换、加载状态、错误显示 |

### 测试工具
- pytest：全部 Python 测试
- pytest-httpx 或 responses：mock HTTP（LLM Gateway）
- Django test client：API 集成测试
- Vitest + @vue/test-utils + happy-dom：Vue 组件测试 + 纯逻辑测试

## 不在范围内

- 多用户支持（仅单用户）
- 实时流式 SSE 端点（Phase 2）
- 移动端 App 或 PWA
- 云端部署 / Kubernetes / CI/CD 流水线
- 按来源自定义分块策略组合
- 会话标题编辑 / 会话搜索功能
- 源管理页实时进度通过 SSE（仅做不确定进度条）
- 数据备份功能
- PDF/DOCX/TXT 文件源（先做 MacNotesSource，后续扩展）
- Ollama 本地模型支持（LiteLLM Gateway 统一管理模型路由）
- ReRanker 重排序（<1K 文档量级暂无需求）

## 补充说明

- 参考项目：zonebank（DRF 模式、异常处理、uWSGI 配置）
- LiteLLM Gateway 配置位于 ~/.claude/litellm/config.yaml，已配置 smart-router 负载均衡
- 整个项目在同一 Git 仓库中（zrag/ 后端 + frontend/ 前端）
- 全部模块设计方案及各模块代码片段记录于 docs/QA.md（Q0-Q35）
- 全程无 LangChain/LlamaIndex/FastAPI/手写 BM25/Jinja2 服务端渲染
