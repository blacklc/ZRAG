# ZRAG 产品需求文档 — 个人 RAG 知识库系统

## 问题陈述

用户的知识分散在 macOS 备忘录、本地 Markdown/PDF/DOCX 文件中。每当需要查找某个知识点时，必须手动翻阅多个来源，效率低下。用户需要一个能够理解自然语言问题的知识库系统，快速检索相关文档内容并生成可信回答。

核心痛点：
- 知识碎片化，散落在不同 App 和文件系统中
- 手动搜索无法处理"语义相近但用词不同"的查询
- 无法对知识进行自然语言级别的归纳与问答
- 中文查询场景下关键词检索无法匹配中文分词，导致混合检索退化为纯向量检索
- **多轮追问时检索系统不理解对话上下文**：追问 "它的性能怎么样？" 时，系统不知道 "它" 指代什么，检索结果偏题；追问 "打分怎么做的" 时，"打分" 由上一轮 AI 回复引入，检索无法关联
- **查询改写每次消耗 API 模型额度**：QueryRewriter 每次调用都走云 API，高频率低难度任务浪费资源

## 解决方案

ZRAG 是一个**本地优先的个人 RAG 知识库系统**。用户将文档导入后，系统自动分块、向量化并存储。用户通过 Web UI 或 API 用自然语言提问，系统执行混合检索（语义 + 关键词），将最相关的内容作为上下文提交给 LLM，生成带来源标注的回答。

核心能力：
- **文档摄入**：从 macOS Notes 等来源自动拉取 → 分块 → 向量化 → 双库存储
- **文档导出**：通过 AppleScript 从 macOS Notes.app 获取 HTML，经增强的 HTML→Markdown 转换器（五阶段流水线，覆盖 12 种标签）处理为结构化 Markdown
- **混合检索**：语义检索（ChromaDB Cosine）+ 关键词检索（SQLite FTS5 BM25 + jieba 中文分词）→ RRF 融合排序 + 同源 chunk 合并
- **上下文感知检索**：系统自动将每轮对话压缩为摘要，追问时 QueryRewriter 结合摘要解析指代（"它"→"Kubernetes 默认调度器"）并精炼查询，使检索结果始终针对当前上下文
- **RAG 问答**：检索结果 → Prompt 构建 → LiteLLM Gateway → LLM 生成回答（附来源标注）
- **会话管理**：多轮对话持久化，支持切换、继续和删除历史对话；对话摘要逐轮自动更新
- **Web UI**：Apple 风格聊天界面，深色/浅色模式切换，Markdown 渲染，代码高亮
- **数据质量优化**：统一 chunk 大小为 1000 字符（适配 BGE-small 512 token 限制）、标签元数据透传 FTS5 索引、代码围栏标题误识别修复、Unicode NFC 规范化
- **智能查询改写**：本地部署的小模型（Qwen3.5-9B）将口语化查询改写为结构化搜索表达（关键词 + 精炼查询），分别流入关键词和语义两条检索路径，节省 API 消费
- **异步对话压缩**：每轮回答后后台异步将 Q&A 压缩为摘要，不阻塞用户请求，摘要持久化到数据库

## 用户故事

1. 作为知识工作者，我希望用自然语言向知识库提问，以便快速找到相关信息而无须手动翻阅文件
2. 作为笔记用户，我希望 macOS 备忘录能被自动导入知识库，以便不需要手动复制粘贴内容
3. 作为开发者，我希望每条 AI 回答都能标注引用来源，以便验证回答的准确性
4. 作为注重隐私的用户，我希望所有数据都存储在本地，以便个人笔记不会离开我的设备
5. 作为普通用户，我希望能够继续之前的对话，以便在已有问答的基础上进行追问
6. 作为普通用户，我希望追问时系统能正确理解我在说什么，以便不需要每次都要重复完整的上一轮提问
7. 作为普通用户，我希望追问中使用的指代词（如"它""这个"）能被正确解析，以便检索结果不会因为我用了代词而偏题
8. 作为普通用户，我希望删除不需要的旧对话，以便保持对话历史的整洁
9. 作为普通用户，我希望在浅色和深色模式之间切换，以便在白天和晚上都能舒适使用
10. 作为技术用户，我希望 AI 回答中的代码块能够语法高亮，以便技术类回答易于阅读
11. 作为普通用户，我希望 AI 生成回答时有加载动画，以便知道系统正在工作中
12. 作为运维人员，我希望通过一条 docker compose up 命令完成部署，以便部署过程无痛苦
13. 作为普通用户，我希望一键触发增量文档导入，以便新笔记能够快速被索引
14. 作为普通用户，我希望看到导入进度指示，以便知道摄入正在进行中
15. 作为普通用户，我希望 API 调用失败时显示明确的错误提示，以便知道出了什么问题
16. 作为普通用户，我希望能够一键复制 AI 的回答内容，以便在其他地方复用
17. 作为普通用户，我希望选择使用哪个 LLM 模型，以便在质量和速度之间做出权衡
18. 作为普通用户，我希望用 Shift+Enter 输入多行问题，以便能够粘贴代码片段进行分析
19. 作为开发者，我希望有一套 RESTful API 和一致的错误处理，以便在 ZRAG 之上构建集成
20. 作为普通用户，我希望通过左侧边栏切换不同的历史对话，以便查阅之前的讨论
21. 作为笔记用户，我希望在容器化部署中也能导入 macOS 备忘录，以便在无法直接调用 AppleScript 的环境中使用
22. 作为普通用户，我希望在触发导入后看到实时进度（阶段名称 + 进度条），以便知道当前处于哪个阶段
23. 作为普通用户，我希望能够取消正在进行的导入任务，以便在误操作或等待时间过长时终止
24. 作为普通用户，我希望离开页面后再回来仍能看到正在进行的导入进度，以便追踪任务状态
25. 作为普通用户，我希望选择按笔记标签过滤导出范围，以便只导入特定主题的笔记
26. 作为技术用户，我希望检索系统能理解中文查询的关键词匹配，以便用中文提问时获得准确的检索结果
27. 作为知识工作者，我希望同一篇文档的相关段落被合并展示，以便在 AI 回答中获得更连贯的上下文
28. 作为知识工作者，我希望系统能理解我口语化的提问并将其优化为更精准的搜索表达，以便获得更相关的检索结果
29. 作为笔记用户，我希望笔记的标签信息能被检索系统利用，以便按标签主题过滤和匹配相关内容
30. 作为注重准确性的用户，我希望代码块中的注释符号不会被误判为文档标题，以便代码内容保持完整不被错误切分
31. 作为知识工作者，我希望向量检索和关键词检索的融合权重可以按场景调整，以便在语义理解和精确匹配之间做出平衡
32. 作为运维人员，我希望查询改写和对话压缩使用本地部署的小模型，以便减少对 API 模型额度的消耗
33. 作为运维人员，我希望本地模型部署独立于项目，以便复用给其他项目
34. 作为运维人员，我希望本地模型不可用时检索能自动降级使用原始查询，以便用户的问答请求不会中断

## 实现决策

### 总体架构

- 语言：原生 Python（不使用 LangChain / LlamaIndex）
- API 框架：Django REST Framework（ViewSet + re_path 路由，v1/ 版本前缀）
- 前端：Vue 3 + Vite + Tailwind CSS（Apple 风格 UI），与后端分离
- WSGI Server：uWSGI（1 worker，180 秒 harakiri 超时）
- LLM 网关：LiteLLM Gateway（自托管，OpenAI 兼容端点 localhost:4000/v1），统一管理云 API 模型和本地 Ollama 模型的路由与监控
- 本地模型推理：Ollama（独立 Docker 容器，宿主机部署，Qwen3.5-9B Q4_K_M 量化约 6GB，CPU 推理）
- 规模：个人使用，< 1000 篇文档，单用户

### 上下文感知检索（多轮对话优化）

- 每轮对话回答生成后，系统异步将当前 Q&A 按 Q&A 导向压缩为自然语言摘要（描述"用户问了什么 + 助手答了什么"），存入 conversations 表的 summary 字段
- 下一轮追问时，QueryRewriter 读取摘要，结合当前 query 做指代消解和查询改写
- 摘要采用增量压缩策略：每次传入已有摘要 + 最新一轮 Q&A，LLM 按 Q&A 导向生成更新后的摘要（描述"用户问了什么 + 助手答了什么"，最大 500 字）
- 摘要格式经 compress.j2 模板约束：明确指令要求描述用户提出的问题/关注点 + 助手给出的关键回答要点，配合示例格式参考锚定 Q&A 导向输出，替代此前模糊的"概括对话主题、核心概念"指令
- 多轮融合按时间线串下来（非话题归并）：保留已有摘要中的对话时间线，将本轮新内容追加到时间线末尾；接近长度上限时优先保留最近轮次，早期轮次可适度归并。选择时间线而非话题归并的理由：查询改写需要时序信息消解指代词，话题归并会丢失追问链
- 摘要长度通过配置项 `summary_max_chars` 控制，默认 500（从 200 提升，以适应 Q&A 格式更丰富的信息密度。单轮新格式约 80-120 字，3-5 轮累积约 200-350 字，500 字留有安全边际）
- 压缩在响应返回后异步执行（复用全局线程池 ZRAG_INGEST_EXECUTOR），不阻塞用户请求
- 异步压缩失败静默降级：仅写日志，不重试，不影响下次对话。下次追问时使用旧摘要
- 首轮对话结束后的压缩在 create 端点中触发（与 add_message 相同流程）
- 摘要压缩的 prompt 各部分大小不再硬编码，改为基于模型 context_window 动态计算
- user_query 和 assistant_reply 按 token 预算比例分配：user_query 保留 1/4 预算，assistant_reply 保留 3/4
- 中文按约 1.5 字符/token 估算，截断时向上取整

### 本地小模型（查询改写 + 对话压缩）

- 模型选型：Qwen3-4B-Instruct-2507，Q4_K_M 量化（约 6GB 磁盘），CPU 推理延迟约 7-11 秒/次
- Qwen3-4B-Instruct-2507 上下文窗口：32,768 tokens，通过 `rewriter_model_context_window` 配置
- 部署方式：Ollama 独立 Docker 容器（`ollama/ollama:0.9.0`），`docker run -d --name ollama -p 11434:11434 -v ollama_data:/root/.ollama -e OLLAMA_KEEP_ALIVE=24h -e OLLAMA_HOST=0.0.0.0 --memory="10g"`。Ollama 与 LiteLLM 属于同一级别的独立基础设施，不入 ZRAG 的 docker-compose.yml，独立部署、独立升级、可被多个项目复用
- LiteLLM Gateway 中注册 Ollama 后端：`model_name: qwen3:4b-instruct-2507-q4_K_M, api_base: http://host.docker.internal:11434`
- 查询改写和对话压缩通过统一 LiteLLM Gateway 路由，均使用 `model=qwen3:4b-instruct-2507-q4_K_M`，与 Chat 生成的 `smart-router` 走同一个 base_url
- Chat 生成继续走云 API 模型（smart-router），不受影响
- BGE embedding 模型不受影响：Embedding 模型（encoder-only）与 LLM（decoder-only）架构不同，Ollama 不支持。BGE 继续通过 SentenceTransformer 进程内加载，保持零网络开销
- 降级策略：Ollama 不可用时（容器宕机、冷启动超时），查询改写自动降级使用原始 query，回答请求不中断
- LiteLLM 重启由运维人员手动操作，不自动执行

### 新增模块：ConversationSummarizer

- 职责：将多轮对话内容按 Q&A 导向压缩为自然语言摘要（描述"用户问了什么 + 助手答了什么"），用于注入查询改写阶段和 LLM 生成阶段
- 公开接口：`summarize(old_summary, user_query, assistant_reply, max_chars=500, context_window=32768) → str`
- `max_chars` 和 `context_window` 作为方法形参而非对象属性，便于每次调用灵活调整
- 仅注入 LLM provider（构造函数参数），模板路径硬编码
- 内部封装：Jinja2 模板渲染（compress.j2）+ LLM 调用 + 输出清理（移除废话前缀，截断到 max_chars）
- 动态截断：根据 context_window 扣除固定开销后，按 1:3 分配 user_query 和 assistant_reply 的 token 预算，中文按约 1.5 字符/token 换算
- 删除硬编码 `_MAX_REPLY_CHARS = 500`

### 新增模块：CompressService

- 职责：封装异步压缩的调度逻辑，线程池管理 + ConversationSummarizer 调用
- 公开接口：`submit(conversation_id, old_summary, user_query, assistant_reply)` → 立即返回
- 复用项目全局线程池（ZRAG_INGEST_EXECUTOR，默认 2 workers），不新建线程池
- `_run()` 内部从 settings 读取 `rewriter_model_context_window` 和 `summary_max_chars`，在调用 `summarize()` 时作为参数传入
- 模块级单例（DoLC 懒加载），首次调用时从 Django settings 读取 rewriter_model 和线程池配置
- 线程安全：压缩任务创建独立的 SqliteStore 实例（WAL 模式支持并发写），不共享主请求线程的连接
- 静默失败：压缩 LLM 调用或 DB 写入失败仅写日志，不抛异常，不重试

### 修改模块：QueryRewriter

- 接口扩展：`rewrite(query, summary=None)` 新增 summary 参数
- summary 注入到 user message 中（而非 system prompt），保持 system prompt 简洁不变
- `_render_messages()` 渲染时，统一使用 `"对话上下文摘要：{summary or '（无）'}\n\n当前用户查询：{query}"` 格式，无论是否有摘要都保持相同结构。无摘要时用"（无）"明确告知 LLM，而非裸传原始查询

### 修改模块：Retriever

- `hybrid_search()` 签名增加 `summary` 参数（默认 None），透传给 `query_rewriter.rewrite(query, summary)`
- 查询改写调用包裹 try/except：失败时降级使用原始 query，记录 warning 日志
- 日志级别规范：
  - `hybrid_search()` 在 summary 入口处：有摘要 → info，无摘要 → warning（缺失摘要意味着查询改写失去指代消解支撑，属于需关注但不阻塞的事件）
  - 混合检索内部 Path A (keyword) 和 Path B (vector+SQLite) 逐 chunk 日志从 info 降为 debug（属于排查用细节）
  - QueryRewriter 改写成功、_build_results 汇总保持 info 级别

### Prompt 模板更新

- query_rewrite.j2：新增指代消解指令（引导 LLM 结合摘要解析 "它""这个" 等指代词）；同义词替换策略改为核心词提取（"实现原理"→"原理"），降低对 LLM 领域知识的依赖
- compress.j2：压缩 prompt 模板。摘要要求改为明确的 Q&A 导向指令（描述用户提出的问题/关注点 + 助手给出的关键回答要点），配合示例格式参考（"用户询问了...，助手介绍了..."）锚定输出格式，替代此前模糊的"概括对话主题、核心概念"指令。多轮融合规则：保留已有时间线，追加本轮新内容，优先保留最近轮次。约束输出格式为纯文本、禁止废话前缀。`{{ max_chars }}` 参数由 `summarize()` 调用时动态传入

### 数据库 Schema 变更

在 conversations 表新增两个字段：
- `summary TEXT NOT NULL DEFAULT ''` — 对话压缩摘要
- `summary_updated_at TEXT NOT NULL DEFAULT ''` — 摘要最后更新时间

新数据库直接包含新字段；旧数据库通过 `_migrate()` 方法安全追加（try/except sqlite3.OperationalError 跳过已存在列）

### 配置文件变更

- config/llm.yaml：在 gateway 段下新增 `rewriter_model: "${REWRITER_LLM_MODEL:-qwen3:4b-instruct-2507-q4_K_M}"`。base_url 不变（统一指向 LiteLLM Gateway），仅 model 参数不同实现路由区分
- config/llm.yaml：在 gateway 段下新增 `rewriter_model_context_window: 32768`（Qwen3-4B-Instruct-2507 上下文窗口）
- config/retrieval.yaml：新增 `summary_max_chars: 500`
- .env 新增：`REWRITER_LLM_MODEL=qwen3:4b-instruct-2507-q4_K_M`

### API 层

- create 端点：返回 Response 前触发异步压缩（old_summary=""）
- add_message 端点：校验后先读取 conversations.summary，传入 hybrid_search 的 summary 参数；返回前触发异步压缩
- API 接口无变化（请求/响应格式不变），前后端 API 契约不变

### 存储层

- SQLite（data/zrag.db）：数据源，存储 chunks 原文、FTS5 全文索引（jieba 中文分词）、processed_docs 处理进度、conversations 会话、messages 消息
- ChromaDB（data/chroma_db/）：向量存储，Cosine 距离，单 Collection "zrag_docs"
- 数据一致性策略：先写 SQLite（ACID 保证），后写 ChromaDB（失败可补偿重试）。processed_docs 标记"双库均已就绪"
- FTS5 提供内置 BM25 评分——无需手写 BM25，零额外依赖
- FTS5 中文分词：写入和查询时对 content 列统一调用 jieba 分词，中英混合文本仅对中文部分做分词，英文/代码部分保留原样
- FTS5 索引内容除 chunk content 外，也包含 metadata 中的 tags 字段，使标签关键词可被全文检索命中

### 文档摄入

- DocumentSource 抽象基类，定义 fetch_batch() 和 source_type 接口——首个实现为 MacNotesSource
- ChunkingStrategy 抽象基类，定义 chunk(document) → list[Chunk] 接口。首个实现为 ParagraphChunker（按段落切分），后续新增 HeadingChunker：按 Markdown 标题层级（H1-H3）作为语义切分边界，无标题时回退到 RecursiveCharacterChunker，超长段二次切分时子 chunk 继承父标题路径。mac_notes 来源使用 CompositeChunker(HeadingChunker, RecursiveCharacterChunker)，参数为 levels=[1,2,3], max_size=1000, min_size=200, overlap=100。所有切分器（HeadingChunker、CompositeChunker、RecursiveCharacterChunker）的 max_size 统一为 1000 字符。依据：Embedding 模型 BGE-small-zh-v1.5 的 max sequence length 为 512 tokens，中文约 1 token ≈ 1.5-2 字符，512 tokens ≈ 800-1000 字符。CompositeChunker 默认 max_size=512 保持不变（向后兼容），仅在 SOURCE_REGISTRY 中显式传 max_size=1000
- IngestionPipeline 编排全流程：Source → Chunk → Embed → 写 SQLite → 写 ChromaDB → 更新 processed_docs
- 每篇文档独立事务（非批量事务）
- 默认增量导入（content_hash 对比），全量导入通过 {"full": true} 触发
- LLM 调用在数据库事务之外——失败则零副作用，无需回滚
- **异步摄入**：`POST /v1/documents/ingest` 改为异步模式——创建任务后立即返回 202 + task_id，实际处理在后台线程池中执行
- **任务管理**：TaskStatus 状态机 PENDING → WAITING_EXPORT → PROCESSING → DONE/CANCELLED/FAILED；任意非终态可取消；取消信号通过 threading.Event 实现
- **文件桥接模式**：MacNotesSource 在容器环境中不直接调用 AppleScript，改为通过共享 Volume 读取宿主机导出脚本生成的 JSON 文件（manifest.json + result.json + 单条笔记 JSON）
- Pipeline `run()` 新增 `should_cancel` 和 `on_document_done` 回调参数，移除 `on_progress` + `ProgressEvent`

### Markdown 转换

- `export_notes.py` 中 `NotesExporter._html_to_markdown()` 采用五阶段流水线：预处理（移除 base64 图片 + 统一换行）→ 块级元素（pre/code→```, h1-h6→#, ul/ol/li→列表, blockquote→>, table→表格, hr→---, p/br→换行）→ 内联元素（b/strong→**, i/em→*, del/s→~~, code→`, a→[](), img→![]()）→ 清理（移除剩余标签 + HTML 实体解码）→ 整理（压缩空白 + base64 安全网）
- 作为通用转换器实现，不依赖 Apple Notes 特定 HTML 结构，覆盖 12 种常见 HTML 标签

### Unicode 规范化

- `export_notes.py` 导出流程中对所有文本输出（title、folder、tags、content）执行 NFC 规范化
- macOS 文件系统倾向使用 NFD 编码，若不做规范化会导致：content_hash 不一致（同一文档重复摄入）、FTS5 检索不匹配（相同字符不同编码）、Embedding 向量漂移（不同 Unicode 编码产生不同向量）

### 标签元数据透传

- `export_notes.py` 提取的 tags 写入 JSON metadata 字段 → MacNotesSource 解析后存入 RawDocument.metadata["tags"] → ChunkingStrategy 透传到 chunk metadata → SQLite chunks 表 content 尾部追加 tags（参与 FTS5 索引）

### 代码围栏标题误识别修复

- HeadingChunker 的标题检测正则可能在 re.MULTILINE 模式下误匹配代码围栏（```...```）内的 `#` 注释行
- 解决方案：在标题检测前新增 `_remove_code_fences()` 方法，扫描并暂时移除代码围栏区域，标题检测在剥离代码干扰后的文本上执行，代码围栏内容仍完整保留在 chunk 中

### Embedding

- 模型：BAAI/bge-small-zh-v1.5（512 维，sentence-transformers 加载）
- EmbeddingModel 抽象基类，定义 embed(texts)、embed_query(query) 和 dimension 接口
- 模型在宿主机预下载，容器内通过只读 volume 挂载，启动时零等待
- `embed_query()` 方法添加 BGE 推荐的中文查询指令前缀 `"为这个句子生成表示以用于检索相关文章："`。`embed()` 方法（文档向量化）不加前缀，保持原样。BGE v1.5 对无指令容忍度较高（下降约 1-5%），但 s2p（短查询匹配长文档）场景下仍建议添加指令前缀

### 检索层

- **查询改写（Query Rewriting）**：`hybrid_search()` 在 embedding 和 FTS5 查询前，先通过 QueryRewriter 调用本地模型将用户原始查询改写为结构化 JSON `{keywords, refined_query}`。多轮对话时，QueryRewriter 接收对话摘要用于指代消解和上下文感知。`keywords` 为提炼后的关键词列表（空格分隔），直接流入 FTS5 全文检索路径（走 jieba 分词索引）；`refined_query` 为精炼后的自然语言表达，流入向量语义检索路径。改写始终执行，无跳过条件。QueryRewriter 使用 Jinja2 模板（query_rewrite.j2）构建 System Prompt。改写失败时自动降级使用原始 query
- 混合检索：ChromaDB similarity_search(k=k×2，默认 20) + SQLite FTS5 BM25 with jieba 分词(k=k×2，默认 20) → RRF 融合。扩大候选池后 RRF 有更充分的材料进行排序融合，最终截取 top-k（默认 10）返回，避免遗漏"只有一条路径认可"的优质结果
- RRF 公式：`score(d) = w_vector/(k + rank_vector) + w_keyword/(k + rank_keyword)`。权重从 config/retrieval.yaml 读取，默认等权（1.0/1.0），可按语料特征和场景调整偏向
- 结果按 RRF 分数排序，通过排序融合自然去重
- SearchResult 数据类包含 chunk_index 字段，供同源合并时排序
- build_rag_prompt() 中按 doc_title 合并同源 chunks，按 chunk_index 排序后拼接为单个 [来源: X] 块
- PromptBuilder 独立负责 Prompt 构建，与 LLM 通信解耦
- 检索异常统一抛出 RetrievalException（500，内层异常链式传递）

### LLM Provider

- LLMProvider 抽象基类：chat(messages) → str、chat_stream(messages) → Iterator[str]（Phase 2）
- LLMGatewayProvider：通过 OpenAI SDK 调用 LiteLLM Gateway。内部代码不变，仅调用方根据用途传入不同的 model 参数（`smart-router` 用于 Chat 生成，`ollama/qwen3.5:9b` 用于查询改写和压缩）
- 错误处理策略：有回调 → 通知回调 + 不抛异常；无回调 → 抛 BaseZragException
- 超时时间：200 秒（Chat 生成）、120 秒（查询改写/压缩）
- 可用模型（通过 LiteLLM Gateway 配置）：smart-router（云 API 负载均衡组）、ollama/qwen3.5:9b（本地 Ollama）

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
| POST /v1/conversations | POST | 新建会话 + 首条问答（含异步压缩） |
| POST /v1/conversations/{id}/messages | POST | 在已有会话中继续问答（读摘要→改写→检索→异步压缩） |
| GET /v1/conversations | GET | 会话列表（含 total 总数，按最近消息倒序） |
| GET /v1/conversations/{id}/messages | GET | 获取某会话的全部消息 |
| DELETE /v1/conversations/{id} | DELETE | 删除会话及消息（幂等） |
| POST /v1/documents/ingest | POST | 触发文档摄入（改为异步，返回 202 + task_id） |
| GET /v1/ingest/{id}/status | GET | 查询摄入任务状态和进度 |
| POST /v1/ingest/{id}/cancel | POST | 取消摄入任务 |
| GET /v1/sources | GET | 列出已摄入 Source 及文档统计 |
| GET /v1/sources/available | GET | 返回 SOURCE_REGISTRY 中已注册的数据源类型 |
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
- 源管理页：数据源下拉选择器 + 增量/全量导入按钮 + 永久性导出命令提示 + 阶段名称 + 确定进度条 + 取消按钮；摄入中关闭页面后重开自动恢复轮询；使用 useIngest composable 管理状态；sessionStorage 持久化活跃 taskId
- API 错误处理：网络/500 错误 → Toast 通知；对话错误 → 红色消息气泡
- 无需设置面板（API Key 构建时注入）
- API Key：通过 VITE_API_KEY 环境变量在构建时注入，前端 JS 直接使用

### 会话存储

- conversations 表：id、title、summary、summary_updated_at、created_at
- messages 表：id、conversation_id、role(user|assistant)、content、sources(JSON)、created_at
- 无 updated_at 字段（通过子查询获取最新消息时间），不存模型名
- 删除级联：同事务中 DELETE messages → DELETE conversations
- 会话在首条消息时自动创建，不需要预先创建空会话

### 配置管理

- config/ 目录下按模块分文件：llm.yaml、embedding.yaml、ingest.yaml、api.yaml、storage.yaml、retrieval.yaml
  - llm.yaml gateway 段新增 rewriter_model 字段，指向本地模型
  - retrieval.yaml 新增检索和摘要相关配置项：
    ```yaml
    retrieval:
      top_k: 10
      rrf_k: 60
      rrf_weights:
        vector: 1.0
        keyword: 1.0
      summary_max_chars: 500
    ```
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

- 四容器方案：Nginx（反向代理 + gzip）+ Frontend（nginx:alpine + dist/）+ Backend（uWSGI + Django）+ LiteLLM Gateway
- Ollama 独立容器部署（不入 docker-compose.yml），与 LiteLLM 同级基础设施
- Nginx：宿主机 80 端口，独立部署（`nginx.sh start`），非 docker-compose 管理
- Frontend：内部 80 端口，仅 expose
- Backend：内部 5965 端口，仅 expose
- 数据持久化：./data/pro:/app/data（zrag.db + chroma_db + django.db）
- 模型挂载：/Users/lichen/Documents/workspace/models:/app/models:ro（只读，绝对路径，仅 BGE 用）
- 日志持久化：./logs/pro:/app/log（业务日志）
- 环境变量：.env 文件 + docker-compose ${VAR} 引用
- entrypoint.sh：migrate → collectstatic → uwsgi（建表由 AppConfig.ready() 自动执行 `CREATE TABLE IF NOT EXISTS`，Column migration 由 SqliteStore._migrate() 执行）
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
CREATE TABLE conversations (id TEXT PK, title TEXT, summary TEXT NOT NULL DEFAULT '', summary_updated_at TEXT NOT NULL DEFAULT '', created_at TEXT);
CREATE TABLE messages (id TEXT PK, conversation_id TEXT FK, role TEXT, content TEXT, sources TEXT, created_at TEXT);
CREATE TABLE ingest_tasks (id TEXT PK, task_type TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', total INTEGER DEFAULT 0, processed INTEGER DEFAULT 0, created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT NOT NULL DEFAULT (datetime('now')));
```

## 测试决策

### 什么构成好的测试
- 只测试外部行为，不测试内部实现细节
- 每个模块的公共接口应可独立测试
- 存储测试使用真实 SQLite（内存或临时文件），不使用 mock
- 向量测试使用真实 ChromaDB（临时目录）
- 仅 mock 外部依赖（LiteLLM Gateway 返回的 LLM 调用、macOS AppleScript）

### 本次新增/修改的测试

| 模块 | 测试重点 |
|------|---------|
| ConversationSummarizer | summarize 首轮/增量压缩正确性、_clean_summary 废话前缀移除、max_chars 截断、助手回复截断、输出为 Q&A 导向格式（形式特征断言，如包含"用户询问"等关键词，不依赖 LLM 输出质量） |
| CompressService（新） | submit 后摘要写入 DB、LLM 调用失败静默不抛异常、并发提交不出现竞态崩溃 |
| QueryRewriter（修改） | 传入 summary 时 user message 包含摘要、不传 summary 时 user message 应包含 `"对话上下文摘要：（无）"` 而非仅为原始 query、LLM 结合摘要解析指代、核心词提取策略 |
| Retriever（修改） | QueryRewriter 调用失败时降级使用原始 query |
| 集成测试 | 模拟 3 轮对话，验证摘要逐轮更新、改写使用正确摘要 |

### 已有测试覆盖（不变）

| 模块 | 测试重点 |
|------|---------|
| 存储层 SQLite | CRUD 操作、FTS5 搜索、事务回滚、processed_docs 追踪 |
| 存储层 ChromaDB | add、similarity_search、delete_by_source、Collection 管理 |
| Embedding | embed() 返回正确维度、embed_query() 一致性、normalize_embeddings |
| 摄入 MacNotesSource | 文件桥接模式：轮询 result.json、逐篇读取 JSON 文件构造 RawDocument |
| 摄入 TaskManager | 创建任务、提交线程池、取消信号、状态转换、DB 持久化 |
| 摄入 ChunkingStrategy | 分块边界、max_size 强制、overlap 行为、CompositeChunker 递归 |
| HeadingChunker | 标题边界切分、无标题回退、超长段降级、min_size 合并、标题路径继承 |
| 摄入 IngestionPipeline | 全流程 run()、重复检测、全量导入模式、错误事件发送 |
| LLM Provider | chat() 带 mock gateway、错误处理（回调 vs 抛异常）、超时行为 |
| HTML→Markdown 转换 | 12 种标签转换正确性、base64 图片移除、实体解码、空白整理 |
| FTS5 jieba 分词 | 中文分词正确性、中英混合文本处理、写入/查询一致性 |
| 检索 Retriever | hybrid_search 去重结果、RRF 评分正确性、空结果处理、查询改写分流正确性、k×2 候选池截断、RRF 权重计算 |
| 检索 PromptBuilder | build() 输出结构、上下文截断、来源格式化 |
| API 全部端点 | 请求/响应校验、认证检查、速率限制、错误响应、404 处理 |
| 会话 API | create/list/get/delete 流程、不存在对话 404、DELETE 幂等、LLM 失败回滚 |
| Web UI | 组件渲染、聊天流程、深色模式切换、加载状态、错误显示 |

### 测试工具
- pytest：全部 Python 测试
- pytest-httpx 或 responses：mock HTTP（LLM Gateway）
- Django test client：API 集成测试
- Vitest + @vue/test-utils + happy-dom：Vue 组件测试 + 纯逻辑测试

### 测试前准备
- 仅清空会话相关表（conversations、messages），chunks、chunks_fts 及 ChromaDB 向量库数据必须保持不动

## 不在范围内

- 多用户支持（仅单用户）
- 实时流式 SSE 端点（Phase 2）
- 移动端 App 或 PWA
- 云端部署 / Kubernetes / CI/CD 流水线
- 会话标题编辑 / 会话搜索功能
- 源管理页实时进度通过 SSE
- 数据备份功能
- PDF/DOCX/TXT 文件源（先做 MacNotesSource，后续扩展）
- ReRanker 重排序（<1K 文档量级暂无需求）
- 本地模型切换 API 或 UI（模型通过配置文件指定，不运行时切换）
- 全量历史对话压缩（仅做增量压缩，不做定期全量重建）
- GPU 推理（当前 CPU 推理满足需求，未来可切换到 vLLM 仅改 LiteLLM Gateway 配置）

## 补充说明

- 参考项目：zonebank（DRF 模式、异常处理、uWSGI 配置）
- LiteLLM Gateway 配置位于 ~/.claude/litellm/config.yaml，已配置 smart-router 负载均衡
- LiteLLM Gateway 配置中新增 `qwen3:4b-instruct-2507-q4_K_M` 模型指向本地 Ollama（api_base: http://host.docker.internal:11434）
- Ollama 独立 Docker 容器部署（docker run），模型文件约 6GB 持久化在 ollama_data volume 中。更换电脑时拷贝 volume 数据即可
- 整个项目在同一 Git 仓库中（zrag/ 后端 + frontend/ 前端）
- 全部模块设计方案及各模块代码片段记录于 docs/QA/（Q0-Q35）
- 全程无 LangChain/LlamaIndex/FastAPI/手写 BM25/Jinja2 服务端渲染
- Prompt 模板引擎：Jinja2（zrag/prompts/ 目录），支持条件渲染和格式化
- 混合检索准确度优化设计讨论记录于 docs/QA/hybrid-search-accuracy.md
- 中文分词方案采用 jieba（纯 Python 实现，轻量无外部服务依赖）
- RAG 回答质量优化设计讨论记录于 docs/QA/rag-quality-optimization.md
- 多轮对话优化（指代消解、上下文感知检索、本地小模型部署）设计细节记录于 docs/QA/rag-quality-optimization.md Q16-Q20
