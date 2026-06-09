# ZRAG 存储与 Embedding 设计记录

> 分类索引: [QA 文档目录](index.md)

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
| **bge-small-zh-v1.5** | 512 | ~33M | ~58 | 轻量快速，CPU 友好 |
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
        return 512
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
