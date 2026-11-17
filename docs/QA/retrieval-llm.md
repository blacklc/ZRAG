# ZRAG 检索与 LLM 设计记录

> 分类索引: [QA 文档目录](index.md)

## Q21: RRF 结果查重问题

**用户质疑**: 经过 RRF 排名后的结果是否会出现重复项？

**模拟验证**:
- 入库 6 个 chunk（`note_1_chunk_0` ～ `note_4_chunk_0`），各有一个唯一 `chunk_id`
- ChromaDB 检索这批 chunk → 6 个结果，每个 chunk_id 只出现一次
- FTS5 检索这批 chunk → 6 个结果，每个 chunk_id 只出现一次
- RRF 以 `chunk_id` 为 key 合并分数 → 最终列表 6 行，无重复

**结论**: RRF 融合后的结果不会出现重复，无需单独去重。

## Q22: Retriever 抽象接口

**决策**: 提取 Retriever 抽象接口，使上层逻辑不依赖具体检索实现。

```python
class Retriever(ABC):
    @abstractmethod
    def hybrid_search(self, query: str, k: int = 10) -> list[SearchResult]:
        """混合检索：ChromaDB 向量检索 + SQLite FTS5 关键词检索 → RRF 融合"""
        pass
```

**理由**: 未来如需替换检索逻辑（如去掉 FTS5 路、增加第三路检索），API/CLI 层代码无需改动。

**最终检索参数**:
| 参数 | 值 |
|------|------|
| 每路检索 top-K | 10 |
| RRF 常数 k | 60 |
| 结果去重 | 不需要（RRF 天然保证）|

### 增量同步流程

```
1. Source 获取所有文档（所有 source_id）
2. 对每个 source_id：
   a. 查询 processed_docs 中的 content_hash
   b. 计算当前文档的 content_hash
   c. 比较：
      - source_id 不存在 → 新文档 → 执行写入流程
      - hash 相同 → 跳过
      - hash 不同 → 内容变更 → 执行写入流程
```

---

## Q27: Prompt 构建与 LLM 接口分层

**决策**: Prompt 构建独立于 LLM 接口。

```
用户提问
  → Retriever.hybrid_search(query) → list[SearchResult]
  → PromptBuilder.build(query, results) → list[Message]   ← 独立组件
  → LLM.chat(messages) / chat_stream(messages) → 回答
```

**理由**: LLM 接口只需关心通信协议（chat / chat_stream），Prompt 构建逻辑复杂多变，放在 LLM 接口中会违反单一职责。

**PromptBuilder 实现**:

```python
# zrag/retrieval/prompt_builder.py

SYSTEM_PROMPT = """你是一个个人知识库助手。请基于以下参考材料回答用户问题。
如果参考材料中没有相关信息，请如实告知。

参考材料:
{context}"""

def build_rag_prompt(query: str, results: list[SearchResult]) -> list[Message]:
    context = "\n\n---\n\n".join(
        f"[来源: {r.doc_title}]\n{r.content}" for r in results
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT.format(context=context)},
        {"role": "user", "content": query},
    ]
```

**LLM 接口定义**:
```python
class LLMProvider(ABC):
    @abstractmethod
    def chat(self, messages: list[Message], timeout: float = 200) -> str | None:
        """
        timeout 设定原则:
          - 应略大于下游 Gateway 的 request_timeout（LiteLLM 默认 180s）
          - 确保不会在 Gateway 仍在处理请求时提前断开连接
          - 防止极端场景下（Gateway 内部多模型重试 + fallback）因 Proxy 层超时误伤
        """
        ...

    def chat_stream(self, messages: list[Message], timeout: float = 200) -> Iterator[str]:
        """
        流式对话（默认实现：调用 chat() 后作为单次 yield 返回）
        
        Phase 1 不实现真流式输出。子类在 Phase 2 可 override 实现。
        """
        result = self.chat(messages, timeout=timeout)
        if result is not None:
            yield result

    def _retry(self, func: Callable, *args, **kwargs):
        """预留方法，当前不实现"""
        pass
```

**统一错误处理策略**（LLMProvider 和 IngestionPipeline 一致）:
| 条件 | 行为 |
|------|------|
| Logger | 始终记录异常详情 |
| 提供了 `on_error` 回调 | 通知回调 + 不 raise（`chat` 返回 None，`chat_stream` 终止生成器，Pipeline 跳过文档）|
| 未提供 `on_error` 回调 | 直接 raise |

**on_error 注入时机差异**:
| 模块 | 注入位置 | 原因 |
|------|---------|------|
| LLMProvider | `__init__` | 多次调用复用同一 error handler |
| IngestionPipeline | `run(on_error=...)` | 每次 run 可能由不同调用方触发 |

---

## Q28: LLM Provider 实现 — LLMGatewayProvider

**背景**: 用户使用自建 LiteLLM Gateway（`localhost:4000`），无需为每个 LLM 写单独 Provider。

**LiteLLM Gateway 信息**（来自 `~/.config/litellm/config.yaml`）:

| 配置项 | 值 |
|--------|-----|
| 地址 | `http://localhost:4000` |
| API 协议 | OpenAI 兼容（`/v1/chat/completions`） |
| Master Key | `<redacted>` |
| 可用模型 | `smart-router`（负载均衡组）、`glm-5`、`kimi-k2.6`、`deepseek-v4-flash`、`minimax-m2.7`、`deepseek-v4-pro` |

**实现方案**: 使用 OpenAI SDK（非 LangChain），与你 Q0 中"不使用 LangChain/LlamaIndex"的决策一致。

**错误处理策略**（与 IngestionPipeline 统一）:
- Logger 固定记录异常详情
- 提供了 `on_error` 回调 → 通知回调，不 raise（`chat()` 返回 `None`，`chat_stream()` 生成器终止）
- 未提供 `on_error` 回调 → 直接 raise

**on_error 注入方式**: 放在 `__init__` 中注入（与 IngestionPipeline 不同，IngestionPipeline 在 `run()` 参数中）

```python
from openai import OpenAI, APIError, APITimeoutError, APIConnectionError

class LLMGatewayProvider(LLMProvider):
    def __init__(self, base_url: str, api_key: str, model: str,
                 on_error: Callable[[Exception], None] | None = None):
        # 所有形参为必填项，on_error 从配置/调用方注入
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        self.on_error = on_error

    def chat(self, messages: list[Message]) -> str | None:
        try:
            response = self.client.chat.completions.create(
                model=self.model, messages=messages)
            return response.choices[0].message.content
        except (APITimeoutError, APIConnectionError, APIError) as e:
            logger.error("LLM Gateway 调用失败: %s", e)
            if self.on_error:
                self.on_error(e)
                return None               # 调用方自行处理
            raise

    def chat_stream(self, messages: list[Message]) -> Iterator[str]:
        try:
            stream = self.client.chat.completions.create(
                model=self.model, messages=messages, stream=True)
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except (APITimeoutError, APIConnectionError, APIError) as e:
            logger.error("LLM Gateway 流式调用失败: %s", e)
            if self.on_error:
                self.on_error(e)           # 调用方自行处理，生成器自然结束
                return
            raise
```

**配置结构**（支持多 Provider 扩展）:

```yaml
# config/defaults.yaml
llm:
  provider: "gateway"              # 分辨器: gateway | ollama | openai | claude
  gateway:
    base_url: "http://localhost:4000/v1"
    api_key: "${LITELLM_MASTER_KEY}"
    model: "smart-router"
```

**LLM_PROVIDER_REGISTRY**（独立维护在 `zrag/llm/__init__.py`）:

```python
LLM_PROVIDER_REGISTRY: dict[str, type[LLMProvider]] = {
    "gateway": LLMGatewayProvider,
}

def create_llm(config: dict) -> LLMProvider:
    provider_type = config["llm"]["provider"]
    cls = LLM_PROVIDER_REGISTRY[provider_type]
    provider_cfg = config["llm"].get(provider_type, {})
    return cls(**provider_cfg)
```

**注册表设计**: 各模块独立维护（SOURCE_REGISTRY、CHUNKER_REGISTRY、LLM_PROVIDER_REGISTRY），不抽象通用注册工具。

---

## 系统模块架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                        ZRAG 系统架构                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ════════════ 摄入时（离线）═══════════                           │
│                                                                  │
│  Source 层                                                       │
│  ├── DocumentSource (ABC)                                        │
│  ├── MacNotesSource     ← AppleScript → macOS Notes APP          │
│  └── SOURCE_REGISTRY    ← zrag/ingest/sources/__init__.py       │
│         │                                                        │
│         ▼ RawDocument                                            │
│                                                                  │
│  IngestionPipeline（总编排器，__init__ 注入依赖）                  │
│  │                                                               │
│  ├── 去重检查  ← SQLite processed_docs 表，content_hash 对比       │
│  ├── Chunker   ← CHUNKER_REGISTRY[chunk_strategy]，产出 Chunk     │
│  ├── Embedder  ← bge-small-zh-v1.5（sentence-transformers）       │
│  │                                                               │
│  └── 双库写入（每篇文档独立事务）                                   │
│       ├── [1] SQLite 事务: DELETE + INSERT chunks                 │
│       ├── [2] ChromaDB:  DELETE + INSERT 向量                     │
│       └── [3] SQLite 小事务: 更新 processed_docs                  │
│                                                                  │
│  存储层                                                          │
│  ├── SQLite (data/zrag.db)                                       │
│  │   ├── chunks 表         — 原文                                 │
│  │   ├── chunks_fts 虚拟表 — FTS5 全文索引                         │
│  │   └── processed_docs 表 — 处理进度（替代原 JSON 文件）           │
│  │   ├── conversations 表 — 会话记录                              │
│  │   └── messages 表 — 消息记录                                   │
│  └── ChromaDB (data/chroma_db/)                                  │
│       └── "zrag_docs" Collection — 向量 + source_id/source_type    │
│                                                                  │
│  ════════════ 运行时（在线）═══════════                           │
│                                                                  │
│  用户提问                                                        │
│       │                                                          │
│       ▼                                                          │
│  Embedder.embed_query(query) → query_vector                      │
│       │                                                          │
│       ▼                                                          │
│  Retriever.hybrid_search(query, k=10)                            │
│       │                                                          │
│       ├── ChromaDB similarity_search（语义，top-10）              │
│       ├── SQLite FTS5 MATCH + bm25()（关键词，top-10）            │
│       └── RRF 融合（k=60）→ 最终排序列表，天然去重                 │
│       │                                                          │
│       ▼ list[SearchResult]                                        │
│                                                                  │
│  PromptBuilder.build(query, results) → list[Message]             │
│       │                                                          │
│       ▼                                                          │
│  LLMProvider (ABC)                                               │
│       └── LLMGatewayProvider (OpenAI SDK → LiteLLM Gateway)      │
│       └── chat(messages) / chat_stream(messages)                 │
│       │                                                          │
│       ▼ 回答                                                     │
│                                                                  │
│  ════════════ 对外接口（两种使用方式）═══════════                   │
│                                                                  │
│  ├── Web UI  ← Vue 3 + Vite + Tailwind CSS（前后端分离）          │
│  ├── RESTful API  ← DRF ViewSet + re_path                    │
│  └── CLI  ← python -m zrag serve / ingest / query                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 模块文件对应

| 模块 | 核心文件 |
|------|---------|
| 数据模型 | `zrag/models/` |
| Source 层 | `zrag/ingest/sources/base.py`, `mac_notes.py` |
| Chunking 层 | `zrag/ingest/chunking/base.py`, `paragraph.py` |
| Pipeline | `zrag/ingest/pipeline.py` |
| SQLite 存储 | `zrag/store/sqlite_store.py` |
| 会话存储 | `zrag.db`: conversations 表 + messages 表 |
| ChromaDB 存储 | `zrag/store/vector_store.py` |
| Embedding | `zrag/embed/base.py`, `local.py` |
| 检索 + RRF | `zrag/retrieval/retriever.py` |
| Prompt 构建 | `zrag/retrieval/prompt_builder.py` |
| LLM 接口 | `zrag/llm/base.py`, `gateway.py`, `__init__.py` |
| API | `zrag/api/views.py`, `serializers.py`, `urls.py`, `auth.py`, `response.py`, `middleware.py`, `exceptions.py`, `exception_handler.py`, `ingest_guard.py` |
| Web UI | `frontend/` (Vue 3 + Vite + Tailwind CSS) |
| CLI | `zrag/cli/`, `zrag/__main__.py` |

### 已完成设计的模块

| 模块 | 状态 |
|------|:----:|
| 存储层（SQLite + ChromaDB） | ✅ |
| 混合检索 + RRF + Retriever | ✅ |
| 数据模型（RawDocument, Chunk, SearchResult） | ✅ |
| IngestionPipeline（含 IngestReport/ErrorEvent/ProgressEvent） | ✅ |
| Embedding（bge-small-zh-v1.5 + ABC + 实现） | ✅ |
| Source 抽象 + MacNotesSource + DocumentSource ABC | ✅ |
| ChunkingStrategy 抽象 | ✅ |
| PromptBuilder 实现 | ✅ |
| LLM Provider（LLMGatewayProvider + 注册表 + 配置） | ✅ |
| API 层（DRF） | ✅ |
| Web UI | ⬜ |
| CLI | ⬜ |
| 配置文件 | ✅ |
| 会话存储（conversations + messages） | ✅ |
| 会话 API（5 个端点） | ✅ |
| Web UI 方案（Vue + Tailwind） | ✅ |
| Web UI — 深色模式（手动切换 + localStorage + highlight.js 跟随） | ✅ |
| Web UI — 键盘快捷键（Enter/Shift+Enter/Cmd+K/Cmd+/） | ✅ |
| Web UI — API Key（构建时注入） | ✅ |
| Web UI — 输入框（自动扩展 textarea） | ✅ |
| Web UI — 加载状态 + 空状态 + 消息滚动 | ✅ |
| Web UI — 消息气泡（复制 + 来源标注） | ✅ |
| Web UI — 删除确认弹窗 + 删除后跳转空状态 | ✅ |
| Web UI — 代码高亮（浅色/深色跟随主题） + 404 + Favicon | ✅ |
| Web UI — 源管理页（不定进度条 + 全量/增量导入 + IngestReport 刷新） | ✅ |
| Web UI — Vue Router History 模式 + 响应式布局 | ✅ |
| Web UI — API 错误处理（Toast + 红色气泡） | ✅ |
| 部署 — Docker 三容器方案 + docker-compose | ✅ |
| 部署 — 启动顺序（health check + depends_on） | ✅ |
| 部署 — 资源限制 + 日志轮转 + 重启策略 | ✅ |
| 部署 — 环境变量管理（.env + docker-compose） | ✅ |
| 部署 — Django 配置（DEBUG/ALLOWED_HOSTS/SECRET_KEY/时区） | ✅ |
| 部署 — uWSGI（1 worker + 180s harakiri） | ✅ |
| 部署 — Nginx 代理超时 + gzip | ✅ |
| 部署 — entrypoint.sh（migrate → collectstatic → uwsgi，建表由 AppConfig.ready() 自动完成） | ✅ |
| 部署 — 业务日志（stdout + volume 持久化） + 前端日志（docker logs） | ✅ |
| 部署 — Embedding 模型（宿主机预下载 + 只读 volume） | ✅ |
| 部署 — 端口（8080 对外 + 5965 内部） | ✅ |

---
