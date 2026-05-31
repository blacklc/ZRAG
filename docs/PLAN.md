# ZRAG - 个人 RAG 知识库 设计计划

## 背景

开发一个个人 RAG 知识库项目（项目名：ZRAG），用于管理本地文档和读书笔记/个人写作，通过自然语言问答的方式检索和利用知识。

## 已确认的需求

| 维度 | 决策 |
|------|------|
| 知识来源 | 本地文档（PDF/MD/DOCX/TXT）+ 读书笔记/个人写作 |
| 技术栈 | 原生 Python（不使用 LangChain/LlamaIndex 等框架） |
| 使用方式 | Web UI + RESTful API 双模式 |
| 规模 | 小型（< 1K 文档） |
| LLM | 支持可切换：API（OpenAI/Claude）+ 本地（Ollama） |
| Embedding | 本地模型（sentence-transformers） |
| 向量数据库 | ChromaDB（轻量文件型，零配置） |
| 开发者背景 | Python + Go 都熟悉，偏底层控制 |

## 项目结构

```
ZRAG/
├── pyproject.toml                 # 依赖与构建配置
├── config/
│   ├── defaults.yaml              # 默认配置
│   └── settings.py                # 配置加载器（YAML + 环境变量，优先级：env > yaml > 默认值）
├── zrag/
│   ├── __main__.py                # python -m zrag 入口，分发 serve/ingest/query 命令
│   ├── models/
│   │   ├── document.py            # Document, Chunk 数据类
│   │   └── retrieval.py           # RetrievalResult, QueryResult 数据类
│   ├── ingest/
│   │   ├── loader.py              # 文件加载器：PDFLoader, MarkdownLoader, DocxLoader, TextLoader
│   │   ├── chunker.py             # 递归字符分割 + Markdown 标题感知分块（512字符/64重叠）
│   │   └── pipeline.py            # 编排：load → chunk → embed → store
│   ├── embed/
│   │   ├── base.py                # 抽象 EmbeddingModel 接口
│   │   └── local.py               # sentence-transformers 实现（BGE-small-zh-v1.5，384维）
│   ├── store/
│   │   ├── vector_store.py        # ChromaDB 封装：add/similarity_search/delete/count
│   │   ├── bm25_index.py          # 纯 Python BM25（jieba 可选，字符 bigram 兜底）
│   │   └── fusion.py              # RRF（Reciprocal Rank Fusion）混合排序
│   ├── retrieval/
│   │   ├── retriever.py           # 检索编排：vector/bm25/hybrid 三种模式
│   │   └── reranker.py            # 可选重排序：交叉编码器（BGE-reranker）或 LLM 排序
│   ├── llm/
│   │   ├── base.py                # 抽象 BaseLLM 接口（chat + chat_stream）
│   │   ├── openai_.py             # OpenAI API 兼容（也支持 DeepSeek 等）
│   │   ├── claude.py              # Anthropic Claude API
│   │   └── ollama.py              # Ollama REST API（httpx 直接调用，无额外依赖）
│   ├── api/
│   │   ├── server.py              # FastAPI app 创建 + lifespan + CORS
│   │   ├── schemas.py             # 请求/响应 Pydantic 模型
│   │   └── routes/
│   │       ├── documents.py       # POST/GET/DELETE /api/documents
│   │       ├── chat.py            # POST /api/chat + /api/chat/stream（SSE）
│   │       └── system.py          # GET /api/health, /api/config
│   ├── web/
│   │   ├── router.py              # Jinja2 页面路由
│   │   ├── templates/
│   │   │   ├── base.html          # 基础布局
│   │   │   ├── chat.html          # 对话页面
│   │   │   └── documents.html     # 文档管理页面
│   │   └── static/
│   │       ├── css/app.css        # 单文件样式
│   │       └── js/app.js          # 单文件 JS（SSE 流式 + 上传逻辑）
│   └── cli/
│       ├── serve.py               # 启动服务
│       ├── ingest.py              # 批量导入文档
│       └── query.py               # 一键查询
├── data/                          # 运行时数据（gitignored）
│   ├── chroma_db/                 # ChromaDB 持久化存储
│   ├── documents/                 # 上传的文件副本
│   └── bm25_cache/                # BM25 索引缓存
└── tests/
```

## 核心数据流

**摄入流程**：

```
文件 → loader（按扩展名自动选择解析器）→ Document（原始文本+元数据）
    → chunker（递归分割+重叠窗口）→ list[Chunk]
        → embed 生成向量
        → ChromaDB（持久化存储）
        → BM25 Index（内存+JSON 缓存）
```

**查询流程**：

```
用户问题 → embed_query 获取 query 向量
    ┌─→ ChromaDB 向量检索（cosine similarity）
    └─→ BM25 关键词检索
         → RRF 融合排序
         → [可选] 交叉编码器/LLM 重排序
         → 构建 Prompt（system + context + question）
         → LLM（API/Ollama）生成回答
         → 返回 {answer, sources}
```

## 核心依赖

| 包 | 用途 |
|------|------|
| chromadb | 向量数据库（文件型，零配置） |
| sentence-transformers + torch | 本地嵌入模型 |
| fastapi + uvicorn | Web 服务框架 |
| httpx | LLM API 调用（async HTTP） |
| pydantic + pyyaml | 配置与校验 |
| pypdf / python-docx / markdown | 文档解析 |
| jinja2 | 模板渲染 |
| openai / anthropic（可选） | 云端 LLM |

无需 langchain/llama-index，无需 rank-bm25（约50行代码自己写）

## Web UI 策略

- 无构建工具、无 Node.js、无 React
- FastAPI + Jinja2 服务端渲染
- Vanilla JS（~200行）处理 SSE 流式对话
- CDN 加载 `marked.js` 渲染 Markdown
- 两个页面：聊天 `/` + 文档管理 `/documents`

## 分步实施

| 阶段 | 内容 | 预估 |
|------|------|------|
| 1. 基础 | pyproject.toml → config → models → 空目录结构 | 半天 |
| 2. 摄入 | loader（4种文件类型）→ chunker → pipeline | 1天 |
| 3. 存储与嵌入 | embed → vector_store → bm25_index → fusion | 半天 |
| 4. LLM | base 抽象 → OpenAI → Claude → Ollama | 半天 |
| 5. 检索 | retriever（3种模式）→ reranker | 半天 |
| 6. API | FastAPI 路由 + schemas + 流式 SSE | 半天 |
| 7. Web UI | Jinja2 模板 + CSS + JS | 1天 |
| 8. CLI + 收尾 | serve/ingest/query 命令 + README | 半天 |

## 验证方式

1. 启动后访问 `http://localhost:8765` 看到 Web UI
2. 上传一个 Markdown 文档，检查 ChromaDB 中是否有对应 chunks
3. 在聊天框提问，确认能检索并生成带来源的回答
4. 测试流式 SSE 输出是否正常
5. 切换 LLM provider（ollama ↔ openai）验证可工作
6. 通过 `python -m zrag query "xxx"` CLI 模式验证
