# ZRAG 项目设计对话记录

> 生成日期: 2026-05-26
> 最后更新: 2026-06-02
> 参与人: 用户(lichen) + Claude
>
> **记录约定**: 当一个模块或重点环节设计完成后，须及时记录到本文件中。

---

## Q0: 项目背景

**用户**: 开发一个 RAG 项目用作个人知识库，请帮助逐步完善系统设计。

**确认的需求**:
| 维度 | 决策 |
|------|------|
| 知识来源 | 本地文档 + 读书笔记/个人写作 |
| 技术栈 | 原生 Python（不使用 LangChain/LlamaIndex 框架） |
| 使用方式 | Web UI + RESTful API 双模式 |
| 规模 | 小型（< 1K 文档） |
| LLM | 可切换：OpenAI/Claude API + 本地 Ollama |
| Embedding | 本地模型（sentence-transformers） |
| 向量数据库 | ChromaDB（轻量文件型） |
| 开发者背景 | Python + Go |

---

## Q1: 文档数据源设计方案

**用户**: 文档主要是保存在 macOS 备忘录 APP 中，但不排除后续会有其他形式（本地 Markdown、DOCX、PDF、网络技术博客等）。希望对文档导入操作进行抽象设计，便于后续灵活对接新的文档获取方式。

**决策**: 摄入层拆分为两层：
1. **Source（数据源层）** — 对接不同来源，负责从各来源拉取并标准化内容
2. **Pipeline（处理管线）** — 统一分块 → 嵌入 → 存储，与来源无关

Source 抽象基类设计将后续细化。

---

## Q2: macOS 备忘录读取方案

**用户**: 采用 AppleScript 导出方式读取备忘录。

**现有参考实现**: `/Users/lichen/Documents/workspace/AutoDocUpdater/.claude/skills/exporting-doc/scripts/doc_exporter.py`
- 使用 `osascript` 调用 Notes APP 获取 `body of theNote`（返回 HTML）
- 通过 `_html_to_markdown()` 方法用正则将 HTML 转为 Markdown，无外部依赖
- 支持按文章名称、标签/文件夹筛选
- 支持 PDF 导出（通过 System Events GUI 自动化，需要辅助功能权限）

---

## Q3: 文档分块策略设计

**用户**: 不同类型的文档应有不同的分块方案，需要对分块策略进行抽象设计，便于灵活新增和修改。

**讨论**:
- Markdown 有标题层级结构 → 按标题分块
- 备忘录/纯文本 → 按段落分块
- PDF/DOCX → 段落结构
- 超出最大长度的块需递归切割

**概念澄清**:
- **Chunk（分块）**: 将长文档切成小片段的过程。每个分块会被转为向量存入数据库。提问时找到最相关的分块作为参考材料发给 LLM。
- **保留文档结构信息**: 分块时记录来源标题层级（如"机器学习笔记 → 监督学习"），便于 LLM 回答时标注来源。

**决策**:
- Chunk 的中文翻译用 **分块**
- **先做核心功能**（检索问答能跑通），结构信息保留后续优化
- 每个分块策略拥有独立的配置文件，同时项目有全局配置文件
- 不支持自定义策略组合

分块策略抽象设计（Plan agent 输出）：

```python
ChunkingStrategy (ABC)
├── chunk(document) → list[Chunk]

具体策略:
├── MarkdownHeadingChunker    — 按标题层级结构分块
├── ParagraphChunker          — 按段落（\n\n）分块，适合纯文本/备忘录
├── RecursiveCharacterChunker — 递归字符分割，作为最终兜底
└── WebContentChunker         — 按网页结构分块

组合策略:
└── CompositeChunker — 先用结构策略切分，超出 max_size 的块交给兜底策略递归切割

策略注册:
└── ChunkerRegistry — document.metadata["source_type"] → ChunkingStrategy 映射
```

---

## Q4: Source 抽象层 + MacNotesSource 设计

**用户决策**:
- **方案 B**: 将核心逻辑（`_get_note_content()` + `_html_to_markdown()`）抽取到 ZRAG 项目的 `sources/mac_notes.py` 中，不复用其他项目代码
- 需要增加**全量同步**模式：获取所有备忘录

**RawDocument 中间模型说明**:

RawDocument 是 Source 层和 Pipeline 之间的**统一合约**。不同数据源输出格式不同：
- MacNotes → HTML
- 本地文件 → 原始 MD/TXT/PDF
- 网页 → HTML DOM

每个 Source 负责将自己的原始数据转换为 RawDocument（content 为纯文本/Markdown），Pipeline 统一消费，无需关心来源。

---

## Q5: RawDocument 字段设计 + 去重方案

**决策**:
- RawDocument 采用**方案 B（保留派）**：保留 `raw_content`（原始格式内容）
- 增加 `content_hash`（SHA256）用于检测内容变更
- 已处理文档记录存储在 `data/processed_docs.json`（JSON 文件方案）
- 记录结构精简，只保留去重所需字段

```python
# processed_docs.json 单条记录
{
  "mac_notes:::NOTE:12345": {
    "source_id": "NOTE:12345",
    "source": "mac_notes",
    "content_hash": "sha256...",
    "imported_at": "2026-05-26T12:00:00"
  }
}
```

**source_id 定义**: 数据源内部为每篇文档分配的唯一标识，不会因标题或内容变更而改变。例如 Apple Notes 的 UUID、本地文件的绝对路径或内容哈希、网页的 URL。

---

## Q6: 增量同步策略

- 首次全量导入：获取所有备忘录 → 生成 RawDocument → 记录 source_id → 入库
- 后续增量同步：获取所有备忘录 → 对比 processed_docs.json
  - 新增的 source_id → 入库
  - 已存在但 content_hash 无变化 → 跳过
  - 已存在但 content_hash 有变化 → 重新导入并更新
- 内容变更检测通过 content_hash（SHA256）实现

---

## Q7: MacNotesSource 实现方案

**决策**:
- 将 `AutoDocUpdater` 中 `NotesExporter` 类的全部内容移植到 ZRAG 的 `MacNotesSource` 中作为实例方法
- `doc_exporter.py` 中有用的独立函数也移植为实例方法
- 使用方式参考 `doc_exporter.py` 的 `main()` 方法

**补充修正**: `body of theNote` 返回的是 Apple Notes 的内部富文本格式（非标准 HTML），`_html_to_markdown` 函数实际处理的是 Apple 的富文本格式转换，函数名略有误导。

## Q8: 文档暂存策略

**设计**:
- 每个 DocumentSource 有独立的 `processed_docs.json` 记录已处理文档
- 记录字段: `source_id`, `source`, `content_hash`, `imported_at`
- 增量同步基于 content_hash 检测变更

## Q8: IngestionPipeline 设计

**IngestionPipeline 定义**: 文档摄入流程的总编排器，串联 Source → Chunker → Embedder → Store，不自己做具体工作。

**核心数据流**:
```
IngestionPipeline.run()
  ├── Source.fetch_batch() → list[RawDocument]
  ├── 去重检查（processed_docs.json，Pipeline 统一管理）
  ├── Chunker.chunk(raw_doc) → list[Chunk]
  ├── EmbeddingModel.embed(chunks) → list[vector]
  ├── VectorStore.add_chunks(chunks, embeddings)
  ├── BM25Index.add_chunks(chunks)
  └── _mark_processed(raw_doc) → 写入 processed_docs
```

**决策**: processed_docs.json 由 Pipeline 统一管理，每个 Source 不维护自己的进度文件。

---

## Q9: DocumentSource 注册方案

**决策**:
- SOURCE_REGISTRY 定义在 `zrag/ingest/sources/__init__.py` 中
- 新增 Source 时：创建文件 → 在 `__init__.py` 中 import + 注册
- 配置驱动：`config/defaults.yaml` 中声明哪些 Source 启用

**DocumentSource 抽象接口**:

```python
# zrag/ingest/sources/base.py
from abc import ABC, abstractmethod

class DocumentSource(ABC):
    @abstractmethod
    def fetch_batch(self, batch_size: int) -> Iterator[list[RawDocument]]:
        """分批获取文档，每批最多 batch_size 篇"""
        ...

    @property
    @abstractmethod
    def source_type(self) -> str:
        """返回来源类型标识，如 "mac_notes" """
        ...
```

**SOURCE_REGISTRY**:

```python
# zrag/ingest/sources/__init__.py
from zrag.ingest.sources.base import DocumentSource
from zrag.ingest.sources.mac_notes import MacNotesSource

SOURCE_REGISTRY: dict[str, type[DocumentSource]] = {
    "mac_notes": MacNotesSource,
}
```

**Source 创建**（配置驱动）:

```python
def create_source(source_type: str, config: dict) -> DocumentSource:
    cls = SOURCE_REGISTRY[source_type]
    return cls(**config.get(source_type, {}))
```

## Q10: ChunkingStrategy 抽象设计

**设计**:
```python
class ChunkingStrategy(ABC):
    @abstractmethod
    def chunk(self, document: RawDocument) -> list[Chunk]: ...
    @abstractmethod
    def name(self) -> str: ...
```

**策略注册**: CHUNKER_REGISTRY dict，位于分块模块中

**策略选择**: Source 在 RawDocument.metadata 中声明 `chunk_strategy`（如 "paragraph"），Pipeline 据此从注册表中查找对应的 Chunker。不由 Pipeline 自行推断。

---

## Q11: Embedding 模型加载机制

**用户**: 不清楚模型的运行机制，请讲解。

**讲解**:
- **加载阶段（一次性）**: 模型文件从磁盘读入内存，构建计算图。耗时约 1~15 秒（取决于模型大小和硬件）
- **推理阶段（每次调用）**: 输入文本 → 模型计算 → 输出向量。CPU 约 1~2 秒/100 段，MPS/GPU 可大幅加速
- **设计原则**: 启动时加载一次，复用实例，不为每次 embed 调用重复加载

**决策**:
- 模型存放位置设计为一个配置项（`model_cache_dir`），可自定义
- 支持切换模型，Embedding 操作做抽象设计

**EmbeddingModel 抽象接口**:

```python
# zrag/embed/base.py
from abc import ABC, abstractmethod

class EmbeddingModel(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """批量文本转向量"""
        ...

    @abstractmethod
    def embed_query(self, query: str) -> list[float]:
        """单条查询文本转向量"""
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        """向量维度"""
        ...
```

---

## Q12: Embedding 模型选型推荐

**用户**: 对本地 Embedding 模型没有概念，需推荐对比。

**推荐的候选模型**（基于真实 C-MTEB 中文基准数据）:

| 模型 | 维度 | 参数量 | C-MTEB 中文平均 | 特点 |
|------|------|--------|:-:|------|
| **bge-small-zh-v1.5** | 384 | ~33M | ~58 | 轻量快速，CPU 友好 |
| **bge-base-zh-v1.5** | 768 | ~110M | ~62 | 均衡之选 |
| **BGE-M3** | 1024 | ~568M | ~69 | 多语言+多粒度，质量最高但需 GPU |
| **Qwen3-Embedding** | 2048 | ~700M | ~69 | 最新最强，也需 GPU |

**用户决策**: 选择 **bge-small-zh-v1.5** 起步（轻量灵活，后续可升级）

**数据来源**: [C-MTEB Leaderboard](https://huggingface.co/spaces/mteb/leaderboard) + [BGE 官方](https://github.com/FlagOpen/FlagEmbedding) + [Qwen3 官方](https://huggingface.co/Qwen/Qwen3-Embedding-0.5B)

**bge-small-zh-v1.5 实现**:

```python
# zrag/embed/local.py
from sentence_transformers import SentenceTransformer

class BgeSmallEmbedder(EmbeddingModel):
    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5",
                 cache_dir: str | None = None):
        # 模型加载耗时 ~5s，只做一次
        self._model = SentenceTransformer(model_name, cache_folder=cache_dir)

    def embed(self, texts: list[str]) -> list[list[float]]:
        embeddings = self._model.encode(
            texts,
            normalize_embeddings=True,   # bge 官方推荐 L2 normalize
            show_progress_bar=False,
        )
        return embeddings.tolist()

    def embed_query(self, query: str) -> list[float]:
        return self._model.encode(
            query,
            normalize_embeddings=True,
        ).tolist()

    @property
    def dimension(self) -> int:
        return 384
```

**配置**:
```yaml
embedding:
  model_name: "BAAI/bge-small-zh-v1.5"
  cache_dir: null               # 默认用 sentence-transformers 内置缓存路径
  device: "cpu"                 # cpu | mps | cuda
```

---

## Q13: ChromaDB 基本概念

**用户**: 对 ChromaDB 没有概念，请介绍。

**ChromaDB 简介**: 轻量级向量数据库，无需独立部署服务，数据存储在本地文件系统中。

**三个核心概念**:
1. **Collection（集合）** — 类似数据库中的"表"，创建时指定距离函数（L2/Cosine/IP）
2. **Item（条目）** — 一条记录包含：`id`（唯一标识）、`embedding`（float[]）、`metadata`（dict）、`document`（原始文本，可选）
3. **Similarity Search（相似度搜索）** — 传入 query embedding，返回最相似的 n 条

**距离函数**:
- **L2（欧几里得距离）** — 空间直线距离，越小越相似
- **Cosine（余弦相似度）** — 关注方向而非长度，越小越相似（ChromaDB 返回 1-cos）
- **IP（内积）** — 值越大越相似

**备份**: 直接备份 `data/chroma_db/` 目录即可，无需导出操作。

---

## Q14: ChromaDB Collection 设计

**用户**: 单一 Collection vs 多 Collection 的优缺点？

**对比**:

| 方案 | 优点 | 缺点 |
|------|------|------|
| **单一 Collection** | 检索简单、一次覆盖所有来源、管理简便 | 不同来源数据混合在一起 |
| **多 Collection** | 逻辑隔离、可单独清空重建 | 需跨 collection 检索+结果融合、管理复杂 |

**决策**: 使用**单一 Collection**（规模 < 1K 文档，metadata 过滤可替代物理隔离）

**具体设计**:
- Collection 名称: `"zrag_docs"`
- 距离函数: **Cosine**（bge 模型官方推荐）
- metadata 字段: `source_id`、`source_type`、`doc_title`
- 可通过 `where={"source_type": "mac_notes"}` 实现按来源过滤

---

## Q15: VectorStore 接口设计

**用户决策**:
- `chunk_index` 字段由 Chunker 在分块时自然产生（遍历时用 enumerate 获取）
- Chunk 数据模型需要增加 `chunk_index` 字段
- 支持 `delete_by_source` 方法（ChromaDB 支持按 metadata 的 where 条件 delete）

**VectorStore 抽象接口**:

```python
class VectorStore(ABC):
    @abstractmethod
    def add_chunks(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None: ...
    @abstractmethod
    def similarity_search(self, query_embedding: list[float], k: int) -> list[SearchResult]: ...
    @abstractmethod
    def delete_by_source(self, source_id: str) -> None: ...
```

**ChromaDB 的 update 限制**: 文档内容变更后 chunk 数量可能变化，单纯 update 处理不了。使用 delete + add 两步：先 `delete(where={"source_id": "..."})`，再重新添加新 chunk。

---

## Q16: BM25 方案重定向 — 使用 SQLite FTS5

**用户提出**: 是否有能同时支持向量搜索和关键字搜索的数据库？如果有就不用自行实现 BM25。

**调研结论**: 主流向量数据库的关键词搜索能力对比：

| 数据库 | 关键词搜索 | 部署模式 | 适合 ZRAG |
|--------|:--------:|----------|:--------:|
| ChromaDB | ❌ 无 | 文件型 | 已选 |
| **SQLite + FTS5 + sqlite-vec** | ✅ **原生 BM25** | 文件型，单文件 | ✅ 轻量 |
| Elasticsearch/OpenSearch | ✅ 最成熟 | 需独立服务 | ❌ 太重 |
| Weaviate | ✅ 原生混合搜索 | 需独立服务 | ❌ 太重 |
| pgvector | ⚠️ tsvector | 需 PG 服务 | ❌ 太重 |

**用户决策**: 使用 **SQLite FTS5** 作为全文检索引擎，ChromaDB 做向量搜索，两者通过 RRF 融合。

---

## Q17: SQLite FTS5 深入理解

**用户问**: FTS5 相当于 MySQL 中的 index 吗？

**回答**: 本质都是为搜索优化的索引结构，但 FTS5 能力更强：
- MySQL 普通 Index：精确匹配（`=`, `LIKE 'abc%'`），无相关性排序
- FTS5：全文搜索（分词匹配 + 内置 `bm25()` 相关性排序），支持中文分词

**FTS5 需要两张表的原因**:
- `chunks` = 普通数据表，存放原文
- `chunks_fts` = FTS5 虚拟表，仅存倒排索引（指向 chunks 表）
- FTS5 是虚拟表，不是真实存数据的，而是外挂在普通表上的全文索引

---

## Q18: processed_docs 移入 SQLite

**用户意识到**: processed_docs.json 本身也类似于一个 index 的概念，应该利用数据库统一管理。

**决策**: processed_docs 从独立 JSON 文件移入 SQLite 的一张表，统一管理：
- 解决数据存储与备份问题（一个 .db 文件）
- 可利用 SQLite 的查询能力快速查看处理进度
- 可与 chunks 表 JOIN 做完整性检查

**新的存储架构**:
| 存储 | 内容 | 职责 |
|------|------|------|
| **SQLite** (`data/zrag.db`) | chunks 原文 + FTS5 索引 + processed_docs | 持久化可信源 |
| **ChromaDB** (`data/chroma_db/`) | 向量 + 最小 metadata | 语义检索 |

ChromaDB metadata 精简：只保留 `source_id` 和 `source_type`，原文和完整元数据从 SQLite 查询。

---

## Q19: 数据一致性方案

**用户核心关注**: 双库写入时如何保证数据一致性？

**讨论过程**:
1. 确认两个数据库都不支持跨库事务
2. 提出先 SQLite 再 ChromaDB 的写入顺序
3. 用户质疑：如果 SQLite 事务失败怎么办？→ ChromaDB 未操作，零副作用
4. 深入讨论发现真正危险的是：先删 ChromaDB 旧向量，后写 SQLite 失败 → 数据丢失
5. 最终方案：延迟删除 ChromaDB，先确保 SQLite 写入成功

**最终决策**:

```python
# 写入流程
1. SQLite 事务启动（ACID）
2.   删除 chunks 旧数据（WHERE source_id = ?）
3.   写入 chunks 新数据
4.   更新 processed_docs（content_hash）
5. SQLite 事务提交 ✅
6. 删除 ChromaDB 旧向量（where={"source_id": ...}）→ 可重试
7. 写入 ChromaDB 新向量 → 可重试

# ChromaDB 写入失败时的策略
# → processed_docs 中 content_hash 已更新
# → 下次增量同步检测到 hash 不匹配 → 自动重试 ChromaDB 写入
```

**核心理念**: SQLite 是可信数据源（持久化优先），ChromaDB 是检索核心（功能优先）。写入时先保持久化，再补检索层。容忍短暂的不一致窗口，下次同步自动修复。

---

## Q20: 数据库表结构 + ChromaDB 配置最终设计

### SQLite 表结构（`data/zrag.db`）

**chunks 表 — 原文存储**

```sql
CREATE TABLE chunks (
    chunk_id     TEXT PRIMARY KEY,      -- "{source_id}_chunk_{index}"
    source_id    TEXT NOT NULL,         -- 来源文档唯一标识
    source_type  TEXT NOT NULL,         -- "mac_notes" | "local_file" | ...
    doc_title    TEXT,                  -- 文档标题
    content      TEXT NOT NULL,         -- 分块后的原文
    chunk_index  INTEGER,              -- 在文档中的第几个分块
    created_at   TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_chunks_source_id ON chunks(source_id);
CREATE INDEX idx_chunks_source_type ON chunks(source_type);
```

**chunks_fts 虚拟表 — 全文搜索索引**

```sql
CREATE VIRTUAL TABLE chunks_fts USING fts5(
    content,                     -- 被索引的文本列
    content=chunks,              -- 关联到 chunks 表的 content 列
    content_rowid=rowid          -- 行 ID 映射
);
```

**processed_docs 表 — 处理进度**

```sql
CREATE TABLE processed_docs (
    source_id     TEXT PRIMARY KEY,     -- 来源文档唯一标识
    source_type   TEXT NOT NULL,        -- "mac_notes" | "local_file" | ...
    content_hash  TEXT NOT NULL,        -- SHA256，用于检测内容变更
    imported_at   TEXT NOT NULL         -- 最近一次导入时间
);

CREATE INDEX idx_processed_source_type ON processed_docs(source_type);
```

### ChromaDB 配置（`data/chroma_db/`）

| 配置项 | 值 |
|--------|------|
| Collection 名称 | `"zrag_docs"` |
| 距离函数 | Cosine |
| metadata 字段 | `source_id`（用于 delete_by_source）、`source_type`（用于过滤）|

ChromaDB 不再存原文和完整元数据。向量检索结果通过 `source_id` + `chunk_index` 与 SQLite 关联查询原文。

### 数据一致性写入流程

```python
1. SQLite 事务启动（ACID 保证）
2.   删除 chunks 旧数据（WHERE source_id = ?）
3.   写入 chunks 新数据
4.   更新 processed_docs（content_hash, imported_at）
5. SQLite 事务提交 ✅

6. 删除 ChromaDB 旧向量（collection.delete(where={"source_id": ...})）
7. 写入 ChromaDB 新向量

# 步骤 6/7 若失败：下次同步自动检测 hash 不匹配 → 重试写入 ChromaDB
```

### 混合检索流程

```
用户提问
  ├→ ChromaDB similarity_search (向量搜索，top-K=10)
  └→ SQLite FTS5 MATCH + bm25() (关键词搜索，top-K=10)
       ↓
  RRF 融合（k=60）→ 最终排序结果（已天然去重）
```

---

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

## Q23: IngestionPipeline 批处理 + 事务粒度

**用户要求**: 结合逐文档处理和批量模式，用小批次 + 可配置 batch_size。

**方案对比**:

| 方案 | 事务粒度 | 单篇失败影响 | 残留数据风险 |
|------|---------|:----------:|:----------:|
| 按文档数分批 | 每篇文档独立事务 | 仅该文档跳过 | 无 |
| 按 chunk 数分批 | 每批一个事务 | 整个批次回滚 | 同一文档 chunk 跨批次会残留 |

**决策**: 按**文档数**分批（默认 5 篇/批），每篇文档独立事务。单篇失败跳过继续，零副作用。

---

## Q24: processed_docs 含义澄清

**用户质问**: processed_docs 表示一个库的录入状态还是两个库？

**结论**: processed_docs 表示**两个库都已就绪**。ChromaDB 写入成功后才会更新 processed_docs。

修正后的写入流程:
```
1. Embedder.embed() — 前置计算
2. SQLite 事务: DELETE + INSERT chunks（不更新 processed_docs）
3. ChromaDB: DELETE + INSERT 向量
4. 小事务: 更新 processed_docs
```

**失败分析**:
| 步骤 | 失败后果 | 恢复方式 |
|------|---------|---------|
| Embedder 失败 | 零副作用 | 跳过该文档 |
| SQLite 事务失败 | 全部回滚 | 下次同步重试 |
| ChromaDB 失败 | processed_docs 未更新 | 下次同步重试 |
| processed_docs 更新失败 | 数据已就绪但标记滞后 | 下次同步重试（浪费计算但安全）|

---

## Q25: IngestionPipeline 完整设计

**调用方**: CLI (`python -m zrag ingest`)、API (`POST /api/ingest`)、Web UI（按钮触发）、定时任务（未来可能）

**进度反馈**: Pipeline 自身用 logging 记录日志 + 通过 `on_progress` / `on_error` 回调抛给调用方

**依赖注入**: SQLiteStore、ChromaVectorStore、EmbeddingModel 在 `__init__` 中注入，多次 run() 复用

**错误处理策略**（与 LLMProvider 统一）:
- Logger 固定记录异常
- 提供了 `on_error` 回调 → 通知回调 + 跳过该文档继续
- 未提供 `on_error` 回调 → 直接 raise，中断整个 Pipeline

**最终数据流**:

```python
# zrag/ingest/pipeline.py
from dataclasses import dataclass, field
import logging
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass
class ProgressEvent:
    current: int
    total: int
    source_id: str


@dataclass
class ErrorEvent:
    source_id: str
    error: str


@dataclass
class IngestReport:
    total: int = 0
    new_docs: int = 0
    updated_docs: int = 0
    skipped_docs: int = 0
    failed_docs: int = 0
    errors: list[ErrorEvent] = field(default_factory=list)


class IngestionPipeline:
    def __init__(self, sqlite_store, chroma_store, embedder, batch_size=5):
        self.sqlite_store = sqlite_store
        self.chroma_store = chroma_store
        self.embedder = embedder
        self.batch_size = batch_size

    def run(self, source, on_progress=None, on_error=None) -> IngestReport:
        all_docs = list(source.fetch_batch(batch_size=self.batch_size))
        report = IngestReport(total=len([d for b in all_docs for d in b]))

        for batch in all_docs:
            # 去重检查
            new_or_changed = self._filter_new_or_changed(batch)

            report.skipped_docs += len(batch) - len(new_or_changed)

            for doc in new_or_changed:
                try:
                    chunker = CHUNKER_REGISTRY[doc.metadata["chunk_strategy"]]
                    chunks = chunker.chunk(doc)
                    vectors = self.embedder.embed([c.content for c in chunks])

                    with self.sqlite_store.transaction():
                        self.sqlite_store.delete_by_source(doc.source_id)
                        self.sqlite_store.add_chunks(chunks)

                    self.chroma_store.delete_by_source(doc.source_id)
                    self.chroma_store.add_chunks(chunks, vectors)

                    self.sqlite_store.upsert_processed(doc)
                    report.new_docs += 1

                except Exception as e:
                    logger.exception("文档 %s 处理失败", doc.source_id)
                    report.failed_docs += 1
                    report.errors.append(ErrorEvent(source_id=doc.source_id, error=str(e)))
                    if on_error:
                        on_error(ErrorEvent(source_id=doc.source_id, error=str(e)))
                        continue
                    else:
                        raise

                if on_progress:
                    on_progress(ProgressEvent(
                        current=report.new_docs + report.failed_docs,
                        total=report.total,
                        source_id=doc.source_id,
                    ))

        return report

    def _filter_new_or_changed(self, batch: list[RawDocument]) -> list[RawDocument]:
        result = []
        for doc in batch:
            existing = self.sqlite_store.get_processed(doc.source_id)
            if existing is None:
                result.append(doc)          # 新文档
            elif existing["content_hash"] != doc.content_hash:
                result.append(doc)          # 内容变更
            # else: hash 相同 → 跳过
        return result
```

**SQLiteStore 补充方法**:

```python
# zrag/store/sqlite_store.py
def get_processed(self, source_id: str) -> dict | None:
    """查询 processed_docs 表"""
    ...

def upsert_processed(self, doc: RawDocument):
    """更新或插入 processed_docs"""
    self.execute(
        "INSERT OR REPLACE INTO processed_docs VALUES (?, ?, ?, datetime('now'))",
        (doc.source_id, doc.source_type, doc.content_hash)
    )
```

---

## Q26: 数据模型汇总

### RawDocument
```python
@dataclass
class RawDocument:
    source_id: str
    source_type: str
    content: str          # 清洗后内容，用于分块
    content_hash: str     # SHA256，去重用
    metadata: dict | None # 含 chunk_strategy 等
```

### Chunk
```python
@dataclass
class Chunk:
    chunk_id: str         # "{source_id}_chunk_{index}"
    source_id: str
    source_type: str
    doc_title: str
    content: str
    chunk_index: int
```

### SearchResult
```python
@dataclass
class SearchResult:
    chunk_id: str         # 以 SQLite 为准
    content: str          # SQLite chunks.content
    doc_title: str
    source_id: str
    source_type: str
    score: float          # RRF 融合分数
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

**LiteLLM Gateway 信息**（来自 `/Users/lichen/.claude/litellm/config.yaml`）:

| 配置项 | 值 |
|--------|-----|
| 地址 | `http://localhost:4000` |
| API 协议 | OpenAI 兼容（`/v1/chat/completions`） |
| Master Key | `sk-KTCqa...` |
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
| Web UI | `zrag/frontend/` (Vue 3 + Vite + Tailwind CSS) |
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

## Q30: 配置文件设计

**设计原则**:
- 不同环境使用同一份配置文件
- 每个模块独立配置文件，由加载器自动扫描合并
- 单层结构，不区分 defaults/local

**目录结构**:
```
config/
├── llm.yaml
├── embedding.yaml
├── ingest.yaml
├── api.yaml
├── storage.yaml
└── logging.yaml
```

**各模块配置**:

```yaml
# config/llm.yaml
llm:
  provider: "gateway"
  gateway:
    base_url: "http://localhost:4000/v1"
    api_key: "${LITELLM_MASTER_KEY}"
    model: "smart-router"
```

```yaml
# config/embedding.yaml
embedding:
  model_name: "BAAI/bge-small-zh-v1.5"
  cache_dir: null
  device: "cpu"
```

```yaml
# config/ingest.yaml
ingest:
  batch_size: 5
```

```yaml
# config/api.yaml
api:
  key: "${ZRAG_API_KEY}"
  query_max_length: 2000
```

```yaml
# config/storage.yaml
storage:
  sqlite_path: "data/zrag.db"
  chroma_path: "data/chroma_db"
```

```yaml
# config/logging.yaml
logging:
  level: "INFO"
  dir: "log"
```

**配置加载器**:

```python
# zrag/config/loader.py
def load_config(config_dir: str = "config") -> dict:
    """扫描目录下所有 .yaml 文件，按 top-level key 深度合并"""
    config = {}
    config_path = Path(config_dir)
    for yaml_file in sorted(config_path.glob("*.yaml")):
        data = yaml.safe_load(f.read_text())
        if not data:
            continue
        for key, value in data.items():
            if key in config and isinstance(config[key], dict) and isinstance(value, dict):
                config[key] = {**config[key], **value}
            else:
                config[key] = value

    _resolve_env_vars(config)       # ${ENV_VAR} 替换为实际环境变量值
    return config
```

**settings.py 集成**:

```python
from zrag.config.loader import load_config

_config = load_config("config")

# 映射为 ZRAG_* 快捷变量，供各模块使用
ZRAG_API_KEY = _config["api"]["key"]
ZRAG_LLM_PROVIDER = _config["llm"]["provider"]
# ... 各项 ZRAG_* 变量
```

**与已有代码的兼容性**: `load_config()` 返回的 dict 结构与已有代码引用的结构完全一致（`_config["llm"]["provider"]` 等），无需修改任何已有代码。`settings.ZRAG_*` 是额外快捷访问。

---

## Q29: API 层设计

### SSE 概念

SSE（Server-Sent Events）是 HTTP 长连接，服务器逐块推送数据、客户端逐步接收。

**普通请求 vs SSE 对比**：
| 方式 | 用户体验 | 实现 |
|------|---------|------|
| `/api/chat` | 浏览器转圈 10 秒 → 一次性显示完整回答 | `return JSON` |
| `/api/chat/stream` | 每个 token 生成后立即逐字显示（像 ChatGPT） | `Iterator[str]` → SSE event |

### RESTful 端点（修正后）

| 端点 | 方法 | 说明 |
|------|:--:|------|
| `POST /api/conversations` | POST | 创建对话（RAG 问答）。通过 `Accept` header 区分：`application/json` → 非流式，`text/event-stream` → SSE |
| `POST /api/documents/ingest` | POST | 触发文档摄入。同上 Accept 区分流式 |
| `GET /api/sources` | GET | 列出 Source 及统计（SQLite 查询 processed_docs 实现）|

### 技术选型变更

**决策**: API 层使用 **Django REST Framework**（非原计划的 FastAPI）。

| 维度 | 原计划 (FastAPI) | 新方案 (DRF) |
|------|:---:|:---:|
| 同步/异步 | 原生 async | 同步为主 |
| 项目结构 | 自由 | Django 约定（settings, urls, views, serializers） |
| SSE | StreamingResponse | StreamingHttpResponse |

### 请求/响应模型

**`POST /api/conversations`**:
```json
// 请求
{ "query": "机器学习有哪些分类？" }

// 响应
{
  "answer": "...",
  "sources": [
    {"doc_title": "ML笔记", "content": "...", "score": 0.0328}
  ]
}
```

**`POST /api/documents/ingest`**:
```json
// 请求
{ "source_type": "mac_notes" }   // 可选，不传则全量导入

// 响应
{
  "status": "completed",
  "report": { "total": 42, "new": 3, "updated": 2, "skipped": 37, "failed": 0 }
}
```

**`GET /api/sources`**:
```json
{
  "sources": [
    {"type": "mac_notes", "processed_count": 42}
  ]
}
```

### API 层实现细节

**技术栈变更**: FastAPI → **Django REST Framework**

**路由风格**: ViewSet + re_path，参考 zonebank 模式

**API 版本化**: URL 加 `v1/` 前缀

---

#### 端点列表

| 端点 | 方法 | 说明 |
|------|:--:|------|
| `POST /v1/conversations` | POST | RAG 问答（非流式） |
| `POST /v1/conversations/stream` | POST | RAG 问答（SSE 流式，Phase 2） |
| `POST /v1/documents/ingest` | POST | 文档摄入（非流式） |
| `POST /v1/documents/ingest/stream` | POST | 文档摄入（SSE 流式，Phase 2） |
| `GET /v1/sources` | GET | Source 统计 |
| `GET /v1/health/live` | GET | Liveness（进程存活检查） |
| `GET /v1/health/ready` | GET | Readiness（依赖检查） |

---

#### 自定义 Response

```python
# zrag/api/response.py
from rest_framework.response import Response

class APIResponse(Response):
    def __init__(self, message=None, data=None, request_id=None,
                 http_status=200, headers=None):
        result = {}
        result['Message'] = message or 'ok'
        if data:
            result['Data'] = data
        if request_id:
            result['RequestID'] = request_id

        _headers = headers or {}
        if request_id:
            _headers['X-Request-ID'] = request_id

        super().__init__(data=result, status=http_status, headers=_headers)
```

成功响应: `{"Message": "ok", "Data": {...}, "RequestID": "xxx"}` (+ `X-Request-ID` Header)
失败响应: `{"ErrorCode": "ZRAG-LLM-502", "ErrorMessage": "...", "RequestID": "xxx"}`

---

#### 中间件

```python
# zrag/api/middleware.py
import uuid

class RequestIDMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.META["X-REQUEST-ID"] = str(uuid.uuid4())
        response = self.get_response(request)
        return response
```

---

#### 认证

```python
# zrag/api/auth.py
from rest_framework import authentication, exceptions
from django.conf import settings

class ApiKeyAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        api_key = request.headers.get("Authorization", "").removeprefix("Bearer ")
        if not api_key or api_key != settings.ZRAG_API_KEY:
            raise exceptions.AuthenticationFailed("Invalid API Key")
        return (None, None)
```

所有端点统一要求认证（`/v1/health/*` 除外）。

---

#### 速率限制

```python
# settings.py
REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_CLASSES': ['rest_framework.throttling.ScopedRateThrottle'],
    'DEFAULT_THROTTLE_RATES': {
        'chat': '10/minute',
        'ingest': '3/minute',
    },
}
```

| 端点 | scope | 限制 |
|------|-------|------|
| `/v1/conversations` | `chat` | 10 req/min |
| `/v1/documents/ingest` | `ingest` | 3 req/min |
| `/v1/sources` | — | 不限速 |
| `/v1/health/*` | — | 不限速 + 跳过认证 |

---

#### 请求验证

```python
# zrag/api/serializers.py
from rest_framework import serializers
from django.conf import settings

class ConversationSerializer(serializers.Serializer):
    query = serializers.CharField(required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        max_len = getattr(settings, 'ZRAG_QUERY_MAX_LENGTH', 2000)
        self.fields['query'].max_length = max_len


class IngestSerializer(serializers.Serializer):
    source_type = serializers.CharField(required=False)
```

---

#### 并发摄入保护

```sql
CREATE TABLE ingest_lock (
    id         INTEGER PRIMARY KEY CHECK (id = 1),
    is_running BOOLEAN NOT NULL DEFAULT 0,
    started_at TEXT,
    request_id TEXT
);
```

```python
# zrag/api/ingest_guard.py
class IngestGuard:
    def __init__(self, sqlite_store):
        self.store = sqlite_store
        self.acquired = False

    def acquire(self, request_id: str) -> bool:
        cursor = self.store.execute(
            "UPDATE ingest_lock SET is_running=1, started_at=datetime('now'), request_id=? "
            "WHERE is_running=0",
            (request_id,)
        )
        self.acquired = cursor.rowcount > 0
        return self.acquired

    def release(self):
        if self.acquired:
            self.store.execute(
                "UPDATE ingest_lock SET is_running=0, started_at=NULL, request_id=NULL WHERE id=1"
            )
            self.acquired = False
```

AppConfig.ready() 中清理残留锁:
```python
sqlite_store.execute("UPDATE ingest_lock SET is_running=0 WHERE id=1")
```

---

#### 异常体系

```python
# zrag/api/exceptions.py
class ZragBaseException(Exception):
    def __init__(self, error_code, message_detail, error_type,
                 mitigation, data, request_id, http_status=500):
        self.error_code = error_code
        self.message_detail = message_detail
        self.error_type = error_type
        self.mitigation = mitigation
        self.data = data
        self.request_id = request_id
        self.http_status = http_status

    def get_context(self) -> str:
        return f'{self.message_detail}({self.error_type}) --- {self.mitigation}'
```

异常子类:
```python
class UnauthorizedException(ZragBaseException):
    def __init__(self, request_id: str):
        super().__init__(
            error_code='ZRAG-AUTH-401',
            message_detail='Invalid or missing API Key',
            error_type='Authentication',
            mitigation='Provide a valid API Key in the Authorization header.',
            data={}, request_id=request_id, http_status=401
        )

class RetrievalException(ZragBaseException):
    def __init__(self, query: str, request_id: str, cause: Exception | None = None):
        data = {'query': query}
        if cause:
            data['Cause'] = {'Type': type(cause).__name__, 'Message': str(cause)}
        super().__init__(
            error_code='ZRAG-RETRIEVE-500',
            message_detail=f'Failed to retrieve documents for query: "{query[:100]}"',
            error_type='Retrieval',
            mitigation='Check if ChromaDB and SQLite are accessible and contain data.',
            data=data, request_id=request_id, http_status=500
        )

class LLMCallException(ZragBaseException):
    def __init__(self, model: str, request_id: str, cause: Exception | None = None):
        data = {'model': model}
        if cause:
            data['Cause'] = {'Type': type(cause).__name__, 'Message': str(cause)}
        super().__init__(
            error_code='ZRAG-LLM-502',
            message_detail=f'LLM call failed (model: {model})',
            error_type='LLM',
            mitigation='Verify LiteLLM Gateway is running and the model is available.',
            data=data, request_id=request_id, http_status=502
        )

class IngestionException(ZragBaseException):
    def __init__(self, source_type: str, request_id: str, cause: Exception | None = None):
        data = {'source_type': source_type}
        if cause:
            data['Cause'] = {'Type': type(cause).__name__, 'Message': str(cause)}
        super().__init__(
            error_code='ZRAG-INGEST-500',
            message_detail=f'Document ingestion failed (source: {source_type})',
            error_type='Ingestion',
            mitigation='Check the source configuration and try again.',
            data=data, request_id=request_id, http_status=500
        )

class SourceNotFoundException(ZragBaseException):
    def __init__(self, source_type: str, request_id: str):
        super().__init__(
            error_code='ZRAG-INGEST-404',
            message_detail=f'Unknown source type: "{source_type}"',
            error_type='Source',
            mitigation=f'Available sources: check SOURCE_REGISTRY',
            data={'source_type': source_type}, request_id=request_id, http_status=404
        )
```

异常体系总览:
```
ZragBaseException
├── UnauthorizedException      401 认证失败
├── RetrievalException         500 检索失败（含 Cause）
├── LLMCallException           502 LLM 调用失败（含 Cause）
├── IngestionException         500 摄入失败（含 Cause）
└── SourceNotFoundException    404 未知 Source
```

---

#### 异常 Handler

```python
# zrag/api/exception_handler.py
class BaseExceptionHandler(ABC):
    def __init__(self, exc, context):
        self.exc = exc
        self.context = context

    @abstractmethod
    def handle(self) -> Response: ...

class DefaultErrorHandler(BaseExceptionHandler):
    def handle(self):
        logger.error(...)
        return Response({
            'ErrorCode': 'ZRAG-SERVER-500',
            'ErrorMessage': 'Internal server error',
            'RequestID': 'unknown',
        }, status=500)

# 注册表: exception → handler 映射
error_type = [
    {'exception': ZragBaseException, 'handler': ZragErrorHandler},
    {'exception': AuthenticationFailed, 'handler': AuthErrorHandler},
    {'exception': ValidationError, 'handler': SerializerErrorHandler},
    {'exception': ParseError, 'handler': RequestParseErrorHandler},
]

def api_exception_handler(exc, context):
    for entry in error_type:
        if isinstance(exc, entry['exception']):
            return entry['handler'](exc, context).handle()
    return DefaultErrorHandler(exc, context).handle()
```

配置:
```python
# settings.py
REST_FRAMEWORK['EXCEPTION_HANDLER'] = 'zrag.api.exception_handler.api_exception_handler'
```

---

#### 健康检查

```python
# zrag/api/urls.py (health)
re_path(r'^v1/health/live$',  HealthViewSet.as_view({'get': 'live'})),
re_path(r'^v1/health/ready$', HealthViewSet.as_view({'get': 'ready'})),

# zrag/api/views.py
class HealthViewSet(GenericViewSet):
    permission_classes = []
    throttle_classes = []

    def live(self, request):
        return APIResponse(data={'status': 'alive'})

    def ready(self, request):
        checks = {}
        try:
            get_sqlite_store().execute("SELECT 1")
            checks['sqlite'] = 'ok'
        except Exception as e:
            checks['sqlite'] = str(e)
        try:
            get_chroma_store().collection.count()
            checks['chromadb'] = 'ok'
        except Exception as e:
            checks['chromadb'] = str(e)

        all_ok = all(v == 'ok' for v in checks.values())
        return APIResponse(
            data={'status': 'ready' if all_ok else 'not_ready', 'checks': checks},
            http_status=200 if all_ok else 503,
        )
```

---

#### ViewSet + URL 汇总

```python
# zrag/api/urls.py
from django.urls import re_path
from zrag.api.views import ConversationViewSet, DocumentViewSet, SourceViewSet, HealthViewSet

conversation_urls = [
    re_path(r'^v1/conversations$',        ConversationViewSet.as_view({'post': 'create'})),
    re_path(r'^v1/conversations/stream$', ConversationViewSet.as_view({'post': 'create_stream'})),
]
document_urls = [
    re_path(r'^v1/documents/ingest$',        DocumentViewSet.as_view({'post': 'ingest'})),
    re_path(r'^v1/documents/ingest/stream$', DocumentViewSet.as_view({'post': 'ingest_stream'})),
]
source_urls = [
    re_path(r'^v1/sources$', SourceViewSet.as_view({'get': 'list'})),
]
health_urls = [
    re_path(r'^v1/health/live$',  HealthViewSet.as_view({'get': 'live'})),
    re_path(r'^v1/health/ready$', HealthViewSet.as_view({'get': 'ready'})),
]
urlpatterns = conversation_urls + document_urls + source_urls + health_urls
```

---

#### CORS

```python
# settings.py
INSTALLED_APPS = ['corsheaders', ...]
MIDDLEWARE = ['corsheaders.middleware.CorsMiddleware', ...]
CORS_ALLOW_ALL_ORIGINS = True  # Phase 1 开发阶段，后续收紧
```

---

#### 日志

```python
# settings.py
import logging

LOGGER = logging.getLogger('zrag')
LOGGER.propagate = False
LOGGER.setLevel(logging.INFO)

# 业务日志分层: log/apps/info.log, error.log, warning.log
# Django 框架日志分层: log/django/info.log, error.log (LOGGING dict 配置)
```

```python
# zrag/tools/utils.py
def format_log_record(action, message, request_id, data=None, internal_error=None) -> str:
    info = {'RequestID': request_id, 'Action': action, 'Message': message}
    if data:
        info['Data'] = data
    if internal_error:
        info['InternalError'] = str(internal_error)
    return json.dumps(info, ensure_ascii=False, cls=DjangoJSONEncoder)
```

---

#### 数据库

Django 自身用 `data/django.db`（session/migration），业务数据用 `data/zrag.db`，两个独立 SQLite 文件。

---

#### 依赖管理

- 基础层全局单例（AppConfig.ready() 初始化）: Embedder、SQLiteStore、ChromaDB
- 组合层按需组装: Retriever、IngestionPipeline、LLMProvider

---

#### 已确认细节清单

| 细节 | 决策 |
|------|------|
| 框架 | DRF（非 FastAPI） |
| 路由 | ViewSet + re_path，v1/ 前缀 |
| 响应 | APIResponse（Message + Data + RequestID） |
| 认证 | API Key，Authorization Header，所有端点统一要求 |
| CSRF | 禁用 |
| CORS | django-cors-headers，Phase 1 全放通 |
| request_id | RequestIDMiddleware 自动生成 UUID |
| 流式 | 独立 /stream 端点，Phase 2 实现 |
| 速率限制 | ScopedRateThrottle，chat 10/min，ingest 3/min |
| 验证 | query max_length=2000，配置项 |
| 并发保护 | SQLite ingest_lock 表 |
| 异常 | BaseZragException + 注册表 handler，多层 Cause 不丢失 |
| 日志 | LOGGER on settings，业务/框架分层，format_log_record |
| 健康检查 | Liveness + Readiness，跳过认证和限速 |
| 数据库 | django.db（框架）+ zrag.db（业务）分离 |
| 检索无结果 | 200 + LLM 自然回复 |

| 模块 | 状态 |
|------|:----:|
| API 层（DRF） | ✅ |


## Q31: 会话存储设计

**用户**: 会话记录应该存在哪里？

**决策**: 在已有 `zrag.db` 中新增两张表，复用 SQLite 存储层。

### 表结构

```sql
CREATE TABLE conversations (
    id         TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role            TEXT NOT NULL,        -- 'user' | 'assistant'
    content         TEXT NOT NULL,
    sources         TEXT,                 -- JSON: [{"doc_title":"...","chunk_id":"..."}]
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);

CREATE INDEX idx_messages_conv_id ON messages(conversation_id);
CREATE INDEX idx_messages_created ON messages(conversation_id, created_at);
```

### 关键决策

| 决策点 | 结论 | 理由 |
|--------|------|------|
| updated_at 字段 | 删除 | 用子查询 `(SELECT MAX(m.created_at) FROM messages m WHERE m.conversation_id = c.id) AS last_msg_at` 获取最近消息时间，避免数据冗余和不一致 |
| sources 字段存储内容 | 只存 `[{"doc_title":"...","chunk_id":"..."}]` | 前端渲染来源标注的最少信息。不存 chunk 原文，原文始终走 chunks 表 |
| 模型名 | 不存 | UI 上的"当前模型"放前端状态管理 |
| 删除级联 | 先 `DELETE FROM messages WHERE conversation_id = ?`，再 `DELETE FROM conversations WHERE id = ?` | 同一 SQLite 事务中 |
| 数据库选型 | 使用已有 SQLite，不引入 NoSQL | 数据量小、结构固定、SQLite 足够 |

---

## Q32: 会话 API 设计

**用户**: 需要支持会话的 CRUD 操作。

### 端点汇总

| 端点 | 方法 | 说明 |
|------|:--:|------|
| `POST /v1/conversations` | POST | 新建会话 + 首条问答 |
| `POST /v1/conversations/{id}/messages` | POST | 在已有会话中继续问答 |
| `GET /v1/conversations` | GET | 会话列表（含 total 总数，按最近消息时间倒序） |
| `GET /v1/conversations/{id}/messages` | GET | 获取某会话的所有消息 |
| `DELETE /v1/conversations/{id}` | DELETE | 删除会话及其所有消息（幂等） |

> 流式端点（`/stream`）属于 Phase 2，暂不实现。

### 核心设计决策

| 决策点 | 结论 | 理由 |
|--------|------|------|
| 会话创建方式 | **方案 B** — 首条消息即创建会话 | 打开页面直接提问即可，无需"先创建空会话" |
| 对话 ID 传递 | URL 路径参数 | RESTful 标准。本地工具无安全隐患 |
| LLM 调用位置 | 数据库事务**外** | LLM 失败 → 零写入；LLM 成功 → 事务快速写入 |
| 分页 | 不需要 | 个人工具数据量小 |
| 对话总数 | `GET /v1/conversations` 返回 `{"total": N, "conversations": [...]}` | 前端需要显示总数和列表 |
| 对话不存在 | `NotFoundException` → 404 | 给用户明确提示 |
| DELETE 幂等 | 删除不存在的对话也返回成功 | 目标状态（资源不存在）已满足 |
| sources 返回粒度 | 只返回 `doc_title` + `chunk_id` | 前端渲染来源标注所需的最少字段 |

### 请求/响应示例

**POST `/v1/conversations`**:
```json
// 请求
{ "query": "什么是过拟合？", "model": "smart-router" }

// 响应
{
  "Data": {
    "conversation_id": "abc-123",
    "title": "什么是过拟合？",
    "answer": "过拟合是指模型在训练数据上表现很好但在测试数据上表现差的现象...",
    "sources": [
      {"doc_title": "机器学习笔记", "chunk_id": "xxx_chunk_3"}
    ]
  }
}
```

**GET `/v1/conversations`**:
```json
{
  "Data": {
    "total": 23,
    "conversations": [
      {"id": "abc-123", "title": "什么是过拟合？", "created_at": "...", "last_msg_at": "..."}
    ]
  }
}
```

### 代码实现

**ChatSerializer**:
```python
class ChatSerializer(serializers.Serializer):
    query = serializers.CharField(max_length=2000)
    model = serializers.CharField(max_length=100, required=False, default="smart-router")
```

**NotFoundException**（新增异常类）:
```python
class NotFoundException(BaseZragException):
    def __init__(self, message, error_code="NOT-FOUND"):
        super().__init__(http_status=404, message=message, error_code=error_code)
```

**ConversationViewSet**:
```python
class ConversationViewSet(viewsets.ViewSet):

    def create(self, request):
        """POST /v1/conversations — 新建会话 + 首条问答"""
        serializer = ChatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        query = serializer.validated_data['query']
        model = serializer.validated_data.get('model', 'smart-router')

        # 1. RAG + LLM（事务外，失败则零副作用）
        try:
            results = get_retriever().hybrid_search(query, k=10)
            prompt_messages = get_prompt_builder().build(query, results)
            answer = get_llm_provider().chat(prompt_messages)
        except Exception as e:
            raise RetrievalException(str(e))

        # 2. 事务写入：会话 + 用户消息 + AI 回复
        sources_json = json.dumps([
            {"doc_title": r.doc_title, "chunk_id": r.chunk_id} for r in results
        ])
        conv_id = str(uuid4())
        now = datetime.utcnow().isoformat()
        with sqlite_store.transaction() as db:
            db.execute("INSERT INTO conversations (id, title, created_at) VALUES (?, ?, ?)",
                       (conv_id, query[:50], now))
            db.execute("INSERT INTO messages (id, conversation_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
                       (str(uuid4()), conv_id, 'user', query, now))
            db.execute("INSERT INTO messages (id, conversation_id, role, content, sources, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                       (str(uuid4()), conv_id, 'assistant', answer, sources_json, now))
        return APIResponse(data={
            "conversation_id": conv_id, "title": query[:50],
            "answer": answer, "sources": json.loads(sources_json),
        })

    def send_message(self, request, conversation_id=None):
        """POST /v1/conversations/{id}/messages — 继续对话"""
        conv = sqlite_store.fetch_one("SELECT id FROM conversations WHERE id = ?", (conversation_id,))
        if not conv:
            raise NotFoundException(
                message="Conversation not found: %s" % conversation_id,
                error_code="CONVERSATION-NOT-FOUND")
        serializer = ChatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        query = serializer.validated_data['query']
        model = serializer.validated_data.get('model', 'smart-router')
        try:
            results = get_retriever().hybrid_search(query, k=10)
            prompt_messages = get_prompt_builder().build(query, results)
            answer = get_llm_provider().chat(prompt_messages)
        except Exception as e:
            raise RetrievalException(str(e))
        sources_json = json.dumps([
            {"doc_title": r.doc_title, "chunk_id": r.chunk_id} for r in results
        ])
        now = datetime.utcnow().isoformat()
        with sqlite_store.transaction() as db:
            db.execute("INSERT INTO messages (id, conversation_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
                       (str(uuid4()), conversation_id, 'user', query, now))
            db.execute("INSERT INTO messages (id, conversation_id, role, content, sources, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                       (str(uuid4()), conversation_id, 'assistant', answer, sources_json, now))
        return APIResponse(data={"answer": answer, "sources": json.loads(sources_json)})

    def list(self, request):
        """GET /v1/conversations"""
        rows = sqlite_store.fetch_all("""
            SELECT c.id, c.title, c.created_at,
                   (SELECT MAX(m.created_at) FROM messages m WHERE m.conversation_id = c.id) AS last_msg_at
            FROM conversations c ORDER BY last_msg_at DESC
        """)
        conversations = [{"id": r['id'], "title": r['title'], "created_at": r['created_at'], "last_msg_at": r['last_msg_at']} for r in rows]
        return APIResponse(data={"total": len(conversations), "conversations": conversations})

    def get_messages(self, request, conversation_id=None):
        """GET /v1/conversations/{id}/messages"""
        conv = sqlite_store.fetch_one("SELECT id FROM conversations WHERE id = ?", (conversation_id,))
        if not conv:
            raise NotFoundException(message="Conversation not found: %s" % conversation_id, error_code="CONVERSATION-NOT-FOUND")
        rows = sqlite_store.fetch_all(
            "SELECT id, role, content, sources, created_at FROM messages WHERE conversation_id = ? ORDER BY created_at",
            (conversation_id,))
        messages = []
        for r in rows:
            msg = {"id": r['id'], "role": r['role'], "content": r['content'], "created_at": r['created_at']}
            if r['sources']:
                msg['sources'] = json.loads(r['sources'])
            messages.append(msg)
        return APIResponse(data={"messages": messages})

    def destroy(self, request, conversation_id=None):
        """DELETE /v1/conversations/{id} — 幂等删除"""
        with sqlite_store.transaction() as db:
            db.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            db.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        return APIResponse(data={"deleted": conversation_id})
```

**路由**:
```python
# zrag/api/urls.py（与原 conversation_urls 合并）
conversation_urls = [
    re_path(r'^v1/conversations$', ConversationViewSet.as_view({'post': 'create', 'get': 'list'})),
    re_path(r'^v1/conversations/(?P<conversation_id>[^/]+)/messages$',
            ConversationViewSet.as_view({'post': 'send_message', 'get': 'get_messages'})),
    re_path(r'^v1/conversations/(?P<conversation_id>[^/]+)$',
            ConversationViewSet.as_view({'delete': 'destroy'})),
]
```

---

## Q33: Web UI 方案设计

**用户**: Web UI 要前后端分离，使用 Vue 实现 Apple 风格 UI。对前端不熟悉，需要多提供备选方案。

### 架构调整

原架构总览中的 `Jinja2 + Vanilla JS` 改为前后端分离：

```
浏览器                             Django 后端
┌──────────────────────────┐      ┌──────────────────┐
│ Vue 3 + Vite             │ HTTP │ DRF              │
│ ├─ Vue Router            │────→ │ ├─ REST API      │
│ ├─ Tailwind CSS          │ SSE  │ └─ SSE (Phase 2) │
│ └─ fetch / ReadableStream│←──── │                  │
└──────────────────────────┘      └──────────────────┘
```

### 技术栈选型

| 环节 | 方案 | 备选 | 理由 |
|------|------|------|------|
| 构建工具 | **Vite** | webpack | Vue 官方推荐，无争议 |
| CSS | **Tailwind CSS** | Element Plus, Naive UI | Apple 风格（毛玻璃/大圆角/柔和阴影）用 Tailwind 内置类名最自然。组件库默认风格偏企业，覆写成本高 |
| 图标库 | **Lucide Icons** | Heroicons | Apple 风格线性图标 |
| 路由 | **Vue Router** | — | 官方配套 |
| 状态管理 | **Vue 内置 reactive/ref** | Pinia | 场景简单，无需额外依赖 |
| HTTP 请求 | **fetch** | axios | 浏览器内置，零依赖 |
| Markdown 渲染 | **marked + highlight.js** | markdown-it | 轻量，代码高亮 |
| SSE 流式（Phase 2）| **fetch + ReadableStream** | EventSource | EventSource 仅支持 GET，无法传 POST body |
| UI 组件库 | **不使用** | Element Plus, Naive UI | Apple 风格极简，手写组件代码量小，不引入对抗式样式覆写 |

### Apple 风格关键实现

```css
/* 毛玻璃导航栏 */
nav { @apply bg-white/70 backdrop-blur-xl border-b border-gray-200/50; }

/* 圆角卡片 */
.card { @apply rounded-2xl shadow-sm bg-white; }

/* SF 系统字体 */
body { font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 
       'Helvetica Neue', sans-serif; }

/* 输入框 */
input { @apply rounded-xl border border-gray-200 bg-gray-50/50 
              focus:bg-white focus:ring-2 focus:ring-blue-500/20; }
```

### 页面设计

**聊天主页 `/`**：
- 左侧：会话历史列表（切换、删除，按最近消息时间排序）
- 中间：消息列表（AI 消息带 Markdown 渲染 + 来源标注）
- 底部：输入框 + 发送按钮 + 模型选择器
- 顶部：毛玻璃导航栏（聊天 / 源管理入口）

**源管理 `/sources`**：
- 源状态卡片 + 触发摄入按钮 + 最近导入记录

### 文件结构

```
zrag/frontend/
├── index.html
├── package.json
├── vite.config.js
├── src/
│   ├── main.js
│   ├── App.vue
│   ├── router/index.js
│   ├── api/index.js            # fetch 封装 + API 调用
│   ├── views/
│   │   ├── ChatView.vue
│   │   └── SourcesView.vue
│   ├── components/
│   │   ├── NavBar.vue          # 毛玻璃导航栏
│   │   ├── ChatInput.vue       # 输入框 + 模型选择器
│   │   ├── ChatMessage.vue     # 消息气泡 + Markdown 渲染
│   │   ├── ChatSidebar.vue     # 历史对话列表
│   │   └── SourceCard.vue      # 源状态卡片
│   ├── composables/
│   │   ├── useChat.js          # 聊天逻辑
│   │   └── useConversation.js  # 对话管理
│   └── assets/
│       └── style.css
```

### 依赖

```json
{
  "dependencies": {
    "vue": "^3.4",
    "vue-router": "^4.3",
    "marked": "^12.0",
    "highlight.js": "^11.9"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.0",
    "vite": "^5.4",
    "tailwindcss": "^3.4"
  }
}
```

### 开发部署

- 开发时：`python manage.py runserver` + `npm run dev`（Vite proxy 转发 `/v1/*` 到 Django）
- 部署时：`npm run build` → `dist/` 静态文件

### 细化设计决策

以下是在 grill-me 流程中逐一确认的全部 Web UI 细节：

**深色模式**:
- 手动切换（方案 C），切换按钮 → 导航栏右侧 ☀️/🌙 图标
- 用户偏好存 localStorage，下次打开自动恢复
- 深色模式切换时，highlight.js 代码高亮主题跟随切换：浅色 → `github`，深色 → `github-dark`

**键盘快捷键**:
- `Enter` — 发送消息
- `Shift + Enter` — 换行
- `Cmd + K` — 新建对话
- `Cmd + /` — 聚焦输入框

**API Key**:
- 方案 A：构建时注入。`.env` 文件 `VITE_API_KEY=sk-xxxx`，Vite 构建时将 `import.meta.env.VITE_API_KEY` 替换为字面量
- 前端 JS 代码直接使用，无需用户手动输入

**输入框**:
- textarea 初始单行，内容多了自动增高（max 6 行）
- 占位符："向你的知识库提问"

**AI 回复加载状态**:
- 三个跳动的圆点（类似 ChatGPT 打字指示器），发完消息后显示，AI 回复返回后替换为实际内容

**首次打开/空状态**:
- 无对话时聊天区中间显示 ZRAG 标志 + "向你的知识库提问"
- 左侧会话列表为空时灰色小字"暂无对话，开始提问吧"
- 打开页面时显示空状态（不自动选中任何对话）

**消息气泡**:
- AI 消息右上角悬浮复制按钮
- AI 消息下方来源标注：`📎 来源: 机器学习笔记、深度学习入门`（方案 A 文字链接，灰字小号，来源只展示 doc_title）
- 点击来源暂不实现

**消息滚动**:
- 新消息/AI 回复时自动 scrollToBottom
- 用户手动上滚查看历史时不强制跳回

**删除对话**:
- 悬停显示删除按钮 → 弹出确认弹窗"确定删除此对话？"
- 确认删除后：如果删除的是当前正在查看的对话 → 跳转到空状态（方案 A）

**代码高亮**:
- marked.js 渲染 Markdown，highlight.js 做代码块语法高亮
- 深色/浅色模式切换时自动切换高亮主题

**404 页面**:
- Vue Router 兜底路由 `/:pathMatch(.*)*` → Apple 风格极简 404 组件（方案 B）

**Favicon**:
- 极简 SVG 或 📚 emoji 作为标签页图标（方案 B）

**浏览器标题**:
- 固定显示 "ZRAG"（方案 A）

**Vue Router 模式**:
- History 模式，URL 干净无 `#`，Nginx `try_files $uri /index.html`

**响应式布局**:
- 桌面端标准布局，移动端侧边栏可折叠、消息区弹性宽度（方案 B）

**源管理页交互**:
- 两个按钮："增量导入" + "全量导入"（方案 A）
- 全量导入：请求 `{"source_type": "mac_notes", "full": true}`，后端清空该 source_type 的 processed_docs 后重新处理
- 点击后显示不确定进度条（Apple 风格灰色流动条纹，方案 A）
- 摄入完成后用 IngestReport 直接更新 UI，失败时回退调 `GET /v1/sources`（方案 B + 兜底 A）

**API 调用失败处理**:
- 网络断/500 → Toast 通知（右上角短暂弹出）
- 对话相关错误 → 红色消息气泡插入聊天区

**设置面板**:
- 不需要。导航栏只放 ☀️/🌙 切换和 📊 源管理入口

**消息复制**:
- 气泡右上角悬浮复制图标，点击复制整条消息

### 部署架构

**三容器方案**（Nginx + Frontend + Backend）:
- Nginx 容器（80:80，唯一对外入口）→ `/` 代理到 Frontend 容器（内部 80，expose），`/v1/*` 代理到 Backend 容器（内部 5965，expose）
- Frontend 容器：`nginx:alpine + dist/`
- Backend 容器：`gunicorn :5965`
- 生产环境：`npm run build` → dist/ 打进 Frontend 镜像 → 容器化部署
- 开发环境：`npm run dev`（Vite Dev Server localhost:5173）+ `python manage.py runserver`（localhost:8000），Vite proxy 转发 `/v1/*`

### 待确认
- Vue 项目初始化方式（手动创建 vs 实现阶段自动生成）


---

## Q34: 部署与运维设计

**用户**: 部署方式是什么？需要 CI/CD 吗？

**决策**: 本机 Docker Desktop，三容器方案，不需要 CI/CD。手动 `docker compose build && up -d` 更新。

**用户**: 三容器之间怎么通信？

**决策**: docker-compose 默认创建网络，容器名即主机名。Nginx 通过 `proxy_pass http://backend:5965` 和 `proxy_pass http://frontend:80` 转发。Backend 不对外暴露端口（仅 expose），Frontend 同理，只有 Nginx 将 8080 映射到宿主机（避免 80 端口冲突）。

### 容器架构

```
┌──────────────────────────────────────────┐
│  Nginx (8080→80, 唯一对外入口)             │
│    ├── /     → Frontend (内部 80)          │
│    └── /v1/* → Backend (内部 5965)         │
├──────────────────────────────────────────┤
│  Frontend (expose 80)                    │
│    └── nginx:alpine + dist/              │
├──────────────────────────────────────────┤
│  Backend (expose 5965)                   │
│    ├── uWSGI + Django                    │
│    ├── volumes: data/, models/, logs/    │
│    └── entrypoint.sh                     │
└──────────────────────────────────────────┘
```

### docker-compose.yml

```yaml
services:
  nginx:
    image: nginx:alpine
    ports:
      - "8080:80"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
    depends_on:
      frontend:
        condition: service_healthy
      backend:
        condition: service_healthy
    restart: unless-stopped
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
    deploy:
      resources:
        limits:
          memory: 64M
          cpus: "0.5"

  frontend:
    build:
      context: .
      dockerfile: Dockerfile.frontend
    expose:
      - "80"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:80/"]
      interval: 10s
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
    deploy:
      resources:
        limits:
          memory: 64M
          cpus: "0.5"

  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    expose:
      - "5965"
    volumes:
      - ./data:/app/data
      - ./models:/app/models:ro
      - ./logs:/app/log
    environment:
      - LLM_GATEWAY_URL=${LLM_GATEWAY_URL}
      - LLM_GATEWAY_MODEL=${LLM_GATEWAY_MODEL}
      - ZRAG_API_KEY=${ZRAG_API_KEY}
      - DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY}
      - DJANGO_DEBUG=${DJANGO_DEBUG:-False}
      - DJANGO_ALLOWED_HOSTS=${DJANGO_ALLOWED_HOSTS:-localhost}
      - DJANGO_TIME_ZONE=${DJANGO_TIME_ZONE:-Asia/Shanghai}
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5965/v1/health/live"]
      interval: 10s
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: "2"
```

### .env 文件

```bash
ZRAG_API_KEY=sk-xxxx
LLM_GATEWAY_URL=http://host.docker.internal:4000/v1
LLM_GATEWAY_MODEL=smart-router
DJANGO_SECRET_KEY=<python -c "import secrets; print(secrets.token_urlsafe(50))">
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=localhost
DJANGO_TIME_ZONE=Asia/Shanghai
```

### entrypoint.sh

```bash
#!/bin/sh
set -e
python manage.py migrate --no-input
python manage.py collectstatic --no-input
exec "$@"
```

> 建表初始化（`CREATE TABLE IF NOT EXISTS`）由 AppConfig.ready() 自动执行，无需 management command。

### nginx.conf

```nginx
server {
    listen 80;
    gzip on;
    gzip_types text/css application/javascript;

    location / {
        proxy_pass http://frontend:80;
        proxy_set_header Host $host;
    }

    location /v1/ {
        proxy_pass http://backend:5965;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Request-ID $request_id;
        proxy_read_timeout 180s;
        proxy_connect_timeout 10s;
    }
}
```

### uwsgi.ini

```ini
[uwsgi]
module = zrag.wsgi:application
master = true
processes = 1
http = 0.0.0.0:5965
harakiri = 180
vacuum = true
```

### Dockerfile.backend

```dockerfile
FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY zrag/ ./zrag/
COPY config/ ./config/
COPY manage.py .
COPY uwsgi.ini .
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

EXPOSE 5965
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uwsgi", "--ini", "/app/uwsgi.ini"]
```

### Dockerfile.frontend

```dockerfile
FROM node:22-alpine AS builder
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ARG VITE_API_KEY
ENV VITE_API_KEY=$VITE_API_KEY
RUN npm run build

FROM nginx:alpine
COPY --from=builder /src/dist/ /usr/share/nginx/html/
EXPOSE 80
```

### .dockerignore

```
node_modules/
.git/
data/
__pycache__/
*.pyc
.venv/
venv/
.env
.DS_Store
*.log
models/
logs/
```

### Embedding 模型管理

部署前宿主机预下载模型：

```bash
pip install sentence-transformers
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-zh-v1.5', cache_folder='./models')"
```

容器通过只读 volume 加载：

```yaml
volumes:
  - ./models:/app/models:ro
```

配置指定路径：

```yaml
# config/embedding.yaml
embedding:
  model_name: "BAAI/bge-small-zh-v1.5"
  cache_dir: "/app/models"
```

### 启动流程

```bash
# 首次部署
# 1. 预下载模型
pip install sentence-transformers
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-zh-v1.5', cache_folder='./models')"

# 2. 创建 .env 并填入配置
# 3. 启动
docker compose up -d

# 更新代码后
docker compose build backend && docker compose up -d     # 只改后端
docker compose build frontend && docker compose up -d    # 只改前端
docker compose build && docker compose up -d             # 全部重建
```

### 日志管理

| 日志类型 | 处理方式 |
|----------|---------|
| uWSGI 访问/错误日志 | stdout/stderr → docker logs |
| Django 业务日志 | stdout + volume `./logs:/app/log` 持久化 |
| Nginx 入口日志 | stdout → docker logs |
| Frontend Nginx 日志 | stdout → docker logs |
| Vue 客户端 JS 错误 | 浏览器 console，服务端不管理 |
| 日志轮转 | json-file, 10MB × 3 file |

### 运维决策汇总

| 决策项 | 结论 |
|--------|------|
| 部署目标 | 本机 Docker Desktop |
| CI/CD | 不需要，手动构建更新 |
| 容器架构 | 三容器：Nginx + Frontend + Backend |
| 对外端口 | 8080（避免 80 冲突） |
| Backend 端口 | 5965（内部 expose） |
| 启动顺序 | health check + depends_on，Frontend 和 Backend 就绪后 Nginx 才接受请求 |
| WSGI Server | uWSGI（与 zonebank 一致） |
| Worker 数量 | 1（个人工具，无并发需求） |
| Harakiri 超时 | 180 秒（LLM 调用可能慢） |
| Nginx 代理 | proxy_read_timeout 180s, proxy_connect_timeout 10s |
| 环境变量 | .env 文件 + docker-compose `${VAR}` 引用 |
| Django DEBUG | .env 控制，默认 False |
| ALLOWED_HOSTS | .env 控制，默认 localhost |
| SECRET_KEY | .env 管理，`secrets.token_urlsafe(50)` 生成 |
| 时区 | Asia/Shanghai |
| 数据库迁移 | entrypoint.sh 自动执行 migrate，建表由 AppConfig.ready() 自动完成（`CREATE TABLE IF NOT EXISTS`） |
| 静态文件 | entrypoint.sh 自动执行 collectstatic |
| 日志限制 | json-file，10MB × 3 |
| 重启策略 | unless-stopped |
| 资源限制 | Backend 512M/2CPU，Frontend 64M/0.5CPU，Nginx 64M/0.5CPU |
| 业务日志 | stdout + volume 持久化到 ./logs/ |
| 前端日志 | 全部 stdout → docker logs |
| Docker 网络 | compose 默认自动管理 |
| 数据持久化 | ./data:/app/data（zrag.db + chroma_db + django.db） |
| 模型管理 | 宿主机预下载 → ./models:/app/models:ro |
| 镜像更新 | docker compose build \<service\> && docker compose up -d |
| Gunicorn | 替换为 uWSGI（用户指定） |
