# 更新日志

本文件记录 ZRAG 的版本变更。ZRAG 是本地优先的 RAG 知识库问答系统，源码采用 MIT 许可证。变更条目按照 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 的组织方式分为 `Added`、`Changed`、`Fixed`、`Removed` 四类。

与多数先有版本号、再有变更记录的项目不同，ZRAG 在开源准备阶段才补齐版本管理。仓库自首次提交起共有 112 次非合并提交（2026-05-31 至 2026-06-19），期间没有创建任何 git tag，也没有启用对外版本号。因此本文件把整个开发期的成果统一归入首个公开版本 `0.1.0`，而不是回头虚构若干个历史版本。条目中标注的提交短哈希均可在仓库的 `git log` 中查到，便于逐条溯源。

需要说明条目取舍：本文件只收录 `feat`、`fix`、`refactor`、`perf`、`style`、`chore` 以及会改变实现内容的 `docs` 提交。纯粹用于维护 `docs/PLAN.md` 进度表的 `docs: 更新进度表` 提交属于内部开发跟踪，不构成对外可见的功能变化，故不逐条列出。提交信息本身含义含糊的（例如仅写了 `fix: ...` 而未展开），一律按原文记录，不改写其含义。

## 版本号策略

ZRAG 采用三层版本号体系，三层各自服务不同的沟通对象，并在发布时通过 Release Notes 建立映射。该体系与仓库内 `.claude/rules/scm.md` 的规定保持一致。

### CalVer：面向使用者的营销版本

对外发布使用日历化版本 `YYYY.MM` 或 `YYYY.MM.MICRO`，例如 `ZRAG 2026.06`、`ZRAG 2026.06.1`。这一层针对的是使用者与外部沟通场景，优点是仅凭版本号即可判断发布时间与产品所处阶段，无需查询额外的版本映射表。`MICRO` 位只在同一个自然月内发生多次对外发布时递增，用于区分同月的迭代版本。

### SemVer：面向开发者的技术版本

内部技术版本使用语义化版本 `MAJOR.MINOR.PATCH`，并遵循 `0.x` 阶段的 ZeroVer 约定：当 `MAJOR` 为 0 时，`MINOR` 递增可以承载不兼容变更，`PATCH` 仍然只用于向下兼容的缺陷修复。ZRAG 当前处于 `0.1.x` 阶段，API 与配置格式在设计上仍在演进，尚未承诺跨 `MINOR` 的兼容性。当对外 API 形态稳定、需要正式承诺兼容性时，`MAJOR` 才会递增到 1。

版本递增的判定依据并不只看提交前缀，而是看是否产生对外可见的影响：新增端点、配置键或用户可感知能力对应 `MINOR`；不改变任何外部契约的内部重构与缺陷修复对应 `PATCH`；删除或重命名端点、配置键、数据库字段这类破坏性改动，在 `0.x` 阶段通过 `MINOR` 表达，在 1.0 之后通过 `MAJOR` 表达。

### 构建版本：面向追溯的构建标识

CI/CD 或本地构建产出的标识形如 `<SemVer>+<meta>`，例如 `0.1.0+git.a1b2c3d` 或 `0.1.0+build.20260619.3`。`meta` 部分承载的是构建来源信息，而不是功能变化信息，因此不参与版本比较，也不出现在对外发布说明的标题中。它的用途是：当镜像或静态资源出现问题时，能从版本字符串直接定位到具体的提交或构建批次。

### 三层版本号的映射关系

一次对外发布可能包含多个技术版本迭代，因此 CalVer 与 SemVer 之间并非一一对应。映射关系在发布时补入下表，作为 Release Notes 的一部分维护。表中日期为版本号对应的开发起止时间或计划发布时间，未打 tag 的版本会明确标注状态，避免把计划中的发版时间误认为既成事实。

| 营销版本 | 技术版本 | 日期 | 主要变更 |
|----------|----------|------|----------|
| ZRAG 2026.11 | 0.1.0 | 未发布（计划 2026-11，尚未打 tag） | 首个公开版本：RAG 问答闭环、混合检索、多轮对话摘要、Vue 3 Web UI、Docker 部署 |
| —（未启用） | 0.0.0 | 2026-05-31 至 2026-06-19 | 内部开发期，112 次非合并提交，未启用对外版本号，无 git tag |

后续发布时，若同月内多次对外发版，则新增 `2026.11.1` 行，并指向对应的 `0.1.1` 技术版本；若功能范围跨越 `MINOR`，则新增一行营销版本并记录新的技术版本号。历史行不修改，仅在表格末尾追加，以保证版本追溯链完整。

## [未发布]

以下改动位于当前工作区，尚未提交到 git 历史，列在此处以便发版时并入 `0.1.0` 的条目中。

### Added

- `LICENSE`：MIT 许可证正文，版权人为 blacklc。
- `THIRD-PARTY-LICENSES.md`：第三方组件许可证清单，覆盖 Python 运行时依赖、前端依赖与基础镜像，并标注了 uWSGI 的 GPLv2 义务等需要发布前确认的事项。
- `docs/README.md`：`docs/` 目录的文档总索引，作为根目录 `README.md` 中「文档」一节的落地页。
- `docs/adr/`：架构决策记录目录与索引，首篇 `0001-chromadb-http-server.md` 记录 ChromaDB 从嵌入式模式迁移到独立 HTTP 服务的提案（状态 `Proposed`，尚未实施）。
- `.gitattributes`：换行符、二进制文件与 GitHub Linguist 语言统计规则。
- `CHANGELOG.md`：本文件。

### Changed

- `.gitignore`、`.dockerignore`、`.env.example`、`README.md`、`docker-compose.yml`、`.claude/rules/*` 等文件进行了开源发布前的整理与规则完善。

### Removed

- 删除根目录冗余的 `package-lock.json`，前端依赖锁定以 `frontend/package-lock.json` 为准。
- 删除 `docs/ARCHITECTURE.md`，其内容将由 `docs/design.md` 与 `docs/README.md` 文档体系承接。

## [0.1.0] - 未发布

首个公开版本，覆盖从项目骨架到可运行系统的完整链路。以下条目按功能主题归组，括号内为对应的提交短哈希。

### Added

**存储与嵌入基础（2026-05-31 至 2026-06-02）**

- Django 项目骨架与配置文件加载器，含 10 个测试 (`f3ccf85`)。
- SQLiteStore CRUD 操作封装与数据模型，含 9 个测试 (`66b24cd`)。
- ChromaDB CRUD 操作封装，含 7 个测试 (`498110b`)。
- ChromaDB Collection 管理，含 6 个测试 (`298e61c`、`ea9d435`)。
- 建表初始化改为 `AppConfig.ready()` 自动执行 `CREATE TABLE IF NOT EXISTS`，含 6 个测试 (`b7e8442`)。
- EmbeddingModel 抽象基类，含 3 个测试 (`f2dab87`)。
- BgeSmallEmbedder：基于 bge-small-zh-v1.5 的本地嵌入实现，实测维度为 512，含 4 个测试 (`79eb876`)。

**数据接入与切分（2026-06-03 至 2026-06-15）**

- DocumentSource 抽象基类，含 6 个测试 (`6fe032a`、`9f409ff`)。
- MacNotesSource：macOS Notes 文档来源实现 (`a6685be`)。
- ChunkingStrategy 抽象与实现，以及 IngestionPipeline 编排器 (`7e4474d`)。
- HeadingChunker：按 H1-H3 标题边界切分，并在 chunk 正文前添加标题层级路径 (`167eab5`)。
- macOS Notes 异步摄入方案与实现：文件桥接 + 数据库任务管理 + 异步线程池，包含 TaskStatus / IngestTask / TaskManager 定义、新版文件桥接模式的 MacNotesSource、逐篇处理的 IngestionPipeline (`4711bed`)。
- `export_notes.py` 五阶段 HTML→Markdown 转换，用于导出 macOS Notes 内容 (`167eab5`)。

**检索与 LLM 调用（2026-06-03 至 2026-06-15）**

- Retriever、PromptBuilder、统一 APIResponse 与 RequestIDMiddleware，含 18 个测试 (`c1ff991`)。
- LLM Gateway、API 端点与健康检查 (`852432a`)。
- 会话创建与 RAG 问答消息端点 `POST /v1/conversations`、`POST /v1/conversations/{id}/messages` (`c46474e`)。
- QueryRewriter：LLM 查询改写，将关键词与改写后查询分流到 FTS5 与向量两条检索路径 (`904daac`)。
- 混合检索增强：RRF 融合、候选池扩大到各路径 20 条后截取 top-10、RRF 权重可配置 (`904daac`)。
- FTS5 索引与查询引入 jieba 中文分词，查询时过滤单字 token (`167eab5`)。
- 同源 chunk 在 prompt 中合并为单个材料块 (`167eab5`)。

**多轮对话与上下文压缩（2026-06-18 至 2026-06-19）**

- ConversationSummarizer：增量压缩对话为摘要 (`ea09935`)。
- CompressService：异步压缩调度，复用 `ZRAG_INGEST_EXECUTOR` (`ea09935`)。
- QueryRewriter 接口扩展为 `rewrite(query, summary)`，支持指代消解；Retriever 透传 summary，改写失败时降级为原始 query (`ea09935`)。
- conversations 表新增 `summary`、`summary_updated_at` 字段 (`ea09935`)。
- 摘要压缩 prompt 大小动态限制：按 token 预算截断，`user_query` 与 `assistant_reply` 按 1:3 分配上下文窗口 (`ff87185`)。
- Q&A 导向的摘要指令，摘要长度上限由 200 调整为 500 字符；统一有无摘要时的 user message 格式；要求压缩时保留全部轮次的历史提问 (`df34f22`)。
- 本地小模型接入：Qwen3-4B-Instruct-2507（Q4_K_M），通过宿主机 Ollama 部署 (`ea09935`)。

**API 与安全（2026-06-03 至 2026-06-06）**

- 异常体系、Auth、限速、IngestGuard 与 CORS 配置，含 36 个新测试 (`fecdef7`)。
- 集成 drf-spectacular 提供 Swagger API 文档 (`673d5d5`)，Swagger UI 仅在 `DEBUG=True` 时开启 (`7603d90`)。
- Swagger 文档完善：端点描述、Schema 与 Bearer 认证 (`3676b49`)。

**前端（2026-06-03 至 2026-06-04）**

- Vue 项目初始化 (`b5f1494`)。
- NavBar 组件：顶部导航、深色模式切换与新建会话入口 (`288a013`)。
- ChatInput 组件 (`df06dfc`)。
- ChatSidebar 组件 (`22f38a4`)。
- ChatMessage 组件 (`a44133a`)。
- 404 页面与全局 Toast 通知系统 (`f238f56`)。
- ChatView 页面 (`2f84c52`)。
- SourcesView 页面 (`f0a0420`)。
- 响应式布局 (`9b0bf72`)。
- 前端测试基础设施（vitest + happy-dom + @vue/test-utils）(`72bca8f`)，以及 composable、API 层、组件与页面级测试 (`d713d78`、`0abd276`、`7a1ff17`、`14dd7ee`)。

**配置与部署（2026-06-04 至 2026-06-08）**

- YAML 配置系统，含 loader 的 default 语法增强 (`acc0e23`)。
- 配置系统集成：`settings.py` 与各业务模块统一读取 `config/` (`38a17d1`)。
- 配置系统生产级增强：环境变量可直接覆盖任意 YAML 键值，支持类型自动转换，含 7 个新增测试 (`d630dbc`)。
- 后端容器化：`Dockerfile.backend`、`uwsgi.ini` 与 `entrypoint.sh`，基础镜像 python:3.10-slim (`3674def`)。
- 前端容器化：`Dockerfile.frontend`，多阶段构建基于 node:22-alpine 与 nginx:alpine (`a98ea3d`)。
- `nginx.conf`：反向代理、gzip 与超时配置 (`871441d`)。
- `docker-compose.yml`、`.env` 模板与 `.dockerignore` (`11b1f83`)。
- 前端 nginx 结构化日志格式，并在 docker-compose 中挂载日志卷 (`5841762`)。

**可观测性（2026-06-06 至 2026-06-18）**

- Trace ID 全链路：注册 RequestIDMiddleware，响应头返回 `X-Request-ID`，业务节点日志附带请求标识 (`6f72369`)。
- 后端全部 API 端点添加业务日志 (`d214cca`)。
- 全量 JSON 日志格式：新增 `JsonFormatter`，输出 ISO 8601 北京时间、通过 `extra` 透出结构化字段、自动附加 traceback 并对不可序列化值降级处理 (`e717650`)。

**文档（2026-05-31 至 2026-06-09）**

- 中文 PRD 产品需求文档 (`2a314f4`)。
- 系统架构图、模块流程图与部署架构图（`.drawio` 源文件保留在 `docs/diagrams/`）(`59537ff`、`7a1eac5`)。
- ZRAG 实现计划：45 个切片，44 AFK + 1 HITL (`1fe3be2`)。
- QA 文档按主题拆分为分类文件，并建立索引 (`302ab82`)。
- 设计对话留档：部署与运维设计 (`74edf9c`)、会话存储与会话 API 及 Web UI 设计 (`df243e4`)。
- 日志 JSON 格式设计讨论留档 (`e717650`)、RAG 回答质量优化讨论留档 (`904daac`)。

### Changed

- Python 降级至 3.10，重建虚拟环境并将全部依赖锁定写入 `requirements.txt` (`40d88ef`)。
- `frontend` 目录从 `zrag/frontend/` 移动到项目根目录 `frontend/` (`1fdc483`)。
- 前端代码风格按 `nodejs-code-style.md` 统一 (`9268d0a`)。
- 前端架构重构：提取 `useChat`、`useMarkdown`、`useToast` 等 composable 与 `utils/time.js`，路由拆分为独立模块；API 层新增 AbortController 超时机制；`getUserMessage()` 按 ErrorCode/HTTP status 映射用户友好消息 (`67add3d`)。
- nginx 代理路径改为 `/zrag/`，前端同步适配 (`8997843`)。
- 容器名称加入 `zrag-` 前缀（`zrag-frontend`、`zrag-backend`）(`6f8039a`)。
- nginx 从 `docker-compose.yml` 中移除，改为独立的多项目网关 (`63d6693`)。
- 数据目录改为 `data/pro`，同步更新 `.env` 注释 (`a6e1bfe`)。
- Prompt 模板改用 Jinja2：新增 `zrag/prompts/chat_system.j2`，移除硬编码的 `SYSTEM_PROMPT`，支持无参考材料时的条件渲染 (`1007a40`)。
- 摘要压缩逻辑重构：`summarize()` 改为接收 `max_chars` 与 `context_window`，新增 `_truncate_by_chars()` 按 token 预算动态截断；`config/llm.yaml` 新增 `rewriter_model_context_window: 32768` (`ff87185`)。
- 后端 Dockerfile 优化，`requirements.txt` 精简 (`465a264`)。
- uWSGI 配置调整：`http` 改为 `http-socket`，新增 `die-on-term`、`harakiri-verbose`、`lazy-apps`；docker-compose 的 `stop_grace_period` 设为 310s，健康检查间隔由 10s 调整为 30s 并新增 `start_period` (`f8dd8d7`)。
- 切分参数统一为 `max_size=1000`（HeadingChunker / CompositeChunker / RecursiveCharacterChunker）；`embed_query` 增加检索指令前缀；文本统一 Unicode NFC 规范化 (`904daac`)。
- 日志迁移：99 处 `logger` 调用改为结构化写法，结构化参数从 message 移入 `extra`，key 使用全拼 `snake_case`；前端请求超时由 60s 调整为 210s，与后端 200s 对齐并留 10s 缓冲 (`e717650`)。
- 摘要压缩参数调整：`summary_max_chars` 由 200 改为 500；`retriever.py` 日志级别规范化（摘要入口 info/warning，Path A/B 降为 debug）(`df34f22`)。
- MacNotesSource 合并 AppleScript 调用，subprocess 次数从约 1000+ 次减少到 N+1 次 (`6b8e328`)。
- `.gitignore` 增加 `.claude/worktrees/` 忽略规则 (`19973c9`)。

### Fixed

- 按编码规范补全所有类和方法的中文 `@param` / `@type` / `@return` / `@raises` 注释 (`6a58dbc`)。
- ChromaStore 补全 `@raises` 注释，修正测试文件格式 (`bc9ae95`)。
- `cache_dir` 默认设为 None，未设置时抛出提示异常，并由测试校验 (`35ac27e`)。
- BgeSmallEmbedder 设为离线模式，避免联网超时 (`71b03ff`)。
- uWSGI 容器化优化与 ChromaDB SQLite fork-safety 修复：ChromaStore 与 BgeSmallEmbedder 改为模块级单例，配合 `lazy-apps` 保证每个 worker 进程拥有独立连接 (`f8dd8d7`)。
- 前后端 API 数据结构对齐：修正 conversations/messages 响应中的嵌套字段解析，`SourcesView` 归一化改用 `data.sources`，`DocumentViewSet.ingest` 改用单例 (`9a08eef`)。
- 提高限流阈值（chat 由 10/min 调整为 60/min），补充 429 错误提示，侧边栏在 429 限流时仍执行本地删除 (`e552607`)。
- 修复对话时间戳时区偏差 (`e1cd582`)。
- 容器添加 `TZ=Asia/Shanghai` 统一时区 (`86aa465`)。
- Swagger UI 报 `TemplateDoesNotExist`，补充 TEMPLATES 配置 (`a92c0aa`)。
- 恢复误删的 `docs/uwsgi-containerization.md` (`cd83b46`)。
- `docker-compose` 端口改为 `80:80`，修复漏合并的切片 45 文件 (`bc21fa9`)。
- 混合检索缺陷修复：Path C 的空壳 SearchResult 改为跳过；`doc_title` 为 null 时增加防御与 fallback；HeadingChunker 首段过短时延迟合并 `pending_prefix`；vector_store 对 metadata None 做显式检测；Path A/B/C 全部补充 INFO 级别日志 (`167eab5`)。

### Removed

- 删除硬编码的 `_MAX_REPLY_CHARS=500`，以及 `ConversationSummarizer` 的 `template_dir`、`max_chars` 构造参数 (`ff87185`)。
- 移除 `prompt_builder.py` 中硬编码的 `SYSTEM_PROMPT`，改由 Jinja2 模板渲染 (`1007a40`)。
- nginx 不再作为 `docker-compose.yml` 中的服务存在，改由外部独立网关承担 (`63d6693`)。
- 清理切片开发过程中遗留的 git worktree 引用与子模块引用 (`4fcc508`、`4ee2893`)。
