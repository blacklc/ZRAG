# ZRAG 数据源与摄入 设计记录

> 分类索引: [QA 文档目录](index.md)

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

## Q38: macOS Notes 全量/增量导入异步方案

**日期**: 2026-06-08 至 2026-06-09

**用户**: 测试全量导入功能时报`FileNotFoundError: osascript`。macOS Notes 数据源需在容器外获取，但触发必须来自 Web UI。

### 38.1 方案选型

经过多轮讨论，最终确定**宿主导出 + 文件桥接 + DB 任务管理**方案：

**核心约束**:
- 导出触发来自操作页面（容器内），不能脱离系统
- 容器与宿主机交互全部通过文件（共享 volume）
- 导出脚本由用户手动在宿主机终端执行
- 摄入流程异步化，支持实时进度和取消

**架构**:
```
浏览器 → POST /v1/documents/ingest → 202 {task_id}
  → 后端创建 task + 写入 manifest.json
  → 前端弹窗 "请在终端执行 python3 zrag/export_notes.py"
  → 用户执行导出脚本
  → MacNotesSource 轮询 result.json
  → Pipeline 逐篇处理 → task DONE → 清理线程删除 export 目录
```

### 38.2 数据传递流程

```
data/pro/export/<task_id>/
  ├── manifest.json         # 后端写入 {task_id,task_type,source_type,processed_docs[]}
  ├── result.json           # 导出脚本写入 {"status":"ok","task_id":"abc-123-def","expected":150,"success":128,"exported_at":"2026-06-09T10:30:00+08:00"}
  └── <note_id>.json        # 单条笔记 {"source_id","source_type","content","content_hash","metadata"}
```

- 增量模式: manifest.json 中含 processed_docs，导出脚本对比 hash 只导出变更
- 全量模式: processed_docs 为空

### 38.3 任务抽象

**日期更新**: 2026-06-10

**TaskStatus**（更新后）:

```python
class TaskStatus(str, Enum):
    PENDING = "pending"              # 已创建任务，等待用户执行导出脚本
    WAITING_EXPORT = "waiting"       # 容器侧轮询等待 result.json
    PROCESSING = "processing"        # Pipeline 逐篇 chunk→embed→store
    DONE = "done"                    # 全部完成
    CANCELLED = "cancelled"          # 用户手动取消
    FAILED = "failed"                # 异常终止
```

| 状态 | 含义 | 可取消 |
|------|------|:--:|
| `PENDING` | 后端已创建任务，写入 manifest.json | ✅ |
| `WAITING_EXPORT` | 容器侧轮询等待 result.json | ✅ |
| `PROCESSING` | result.json 就绪，Pipeline 处理中 | ✅ |
| `DONE` | 全部完成 | ❌ |
| `CANCELLED` | 已被用户取消（终态） | ❌ |
| `FAILED` | 异常终止（终态） | ❌ |

任意非终态（PENDING/WAITING_EXPORT/PROCESSING）都可以被取消。

**IngestTask**（内存对象，字段与 DB 表一一对应）:

```python
@dataclass
class IngestTask:
    id: str                     # DB: id (TEXT PK)
    task_type: str              # DB: task_type (TEXT)
    status: TaskStatus          # DB: status (TEXT)
    total: int = 0              # DB: total (INTEGER)
    processed: int = 0          # DB: processed (INTEGER)
    created_at: str = ""        # DB: created_at (TEXT)
    updated_at: str = ""        # DB: updated_at (TEXT)
```

取消信号由 TaskManager 的 `_events` dict 统一管理，不与 IngestTask 耦合。

**DB 表 ingest_tasks**: id, task_type, status, total, processed, created_at, updated_at（7列，与 IngestTask 字段一一对应）

### 38.4 TaskManager — 线程池 + 取消机制（详见 38.26）

- 模块级单例，`get_instance()` 懒加载
- 线程池 `settings.ZRAG_INGEST_EXECUTOR` 注入
- 核心方法：`create_task()`、`submit()`、`_run()`、`_cleanup()`
- 取消: `threading.Event` 纳秒级检查，每篇文档处理前 `is_set()`

### 38.5 Pipeline 改动（详见 38.23）

- `run()` 新增 `on_document_done` 和 `should_cancel` 回调参数
- 移除 `on_progress` + `ProgressEvent`
- 每篇文档处理前检查取消信号
- 每篇完成后触发 `on_document_done`

### 38.6 MacNotesSource 改动（详见 38.15）

- 原有 `osascript` 子进程调用移除
- `fetch_batch()` 改为轮询 `result.json`（2s 间隔），阻塞等待导出完成
- 逐个读取 JSON 文件 yield RawDocument
- `_html_to_markdown()` 移除（导出脚本直接导出 Markdown）

### 38.7 前端交互

- SourcesView 新增数据源下拉选择
- 点击后 → 202 → 弹窗提示终端命令
- 轮询 `GET /v1/ingest/{task_id}/status` → 显示进度条 "128/3699"
- 支持取消按钮 → `POST /v1/ingest/{id}/cancel`

### 38.8 新 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/v1/documents/ingest` | 改为异步，返回 202 + task_id |
| GET | `/v1/ingest/{id}/status` | 查询任务进度 |
| POST | `/v1/ingest/{id}/cancel` | 取消任务 |

### 38.9 关键文件

| 文件 | 变更 |
|------|------|
| `zrag/export_notes.py` | 新增，宿主机导出脚本 |
| `zrag/api/task_manager.py` | 新增，TaskManager + IngestTask + TaskStatus |
| `zrag/api/views.py` | ingest 异步化 + status/cancel 端点 |
| `zrag/api/urls.py` | 新增路由 |
| `zrag/ingest/pipeline.py` | 逐篇处理 + task 支持 |
| `zrag/ingest/sources/mac_notes.py` | 文件桥接模式 |
| `zrag/store/sqlite_store.py` | init_ingest_tasks 建表 |
| `zrag/settings.py` | ZRAG_INGEST_EXECUTOR |
| `config/ingest.yaml` | task_pool_size |
| `frontend/src/views/SourcesView.vue` | 数据源选择 + 进度轮询 |

### 38.10 核心代码实现

#### TaskStatus + IngestTask + TaskManager

```python
# zrag/api/task_manager.py
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum

from django.conf import settings


class TaskStatus(str, Enum):
    PENDING = "pending"          # 已提交，等待线程池调度
    EXPORTING = "exporting"      # 等待宿主机导出文件就绪（mac_notes 专用）
    INGESTING = "ingesting"      # Pipeline 逐篇 chunk → embed → store 处理中
    DONE = "done"                # 全部完成
    CANCELLED = "cancelled"      # 用户手动取消
    ERROR = "error"              # 异常终止


@dataclass
class IngestTask:
    id: str                      # UUID
    task_type: str               # 'full' | 'incr'
    status: TaskStatus           # 当前状态
    total: int                   # 文档总数
    processed: int               # 已处理数
    created_at: str              # ISO 8601
    updated_at: str              # ISO 8601

    @classmethod
    def create(cls, task_type: str) -> "IngestTask":
        from datetime import datetime
        now = datetime.utcnow().isoformat()
        return cls(
            id=str(uuid.uuid4()),
            task_type=task_type,
            status=TaskStatus.PENDING,
            total=0, processed=0,
            created_at=now, updated_at=now,
        )


class TaskManager:
    """摄入任务管理器（模块级单例）

    线程池由 settings.ZRAG_INGEST_EXECUTOR 注入。
    取消机制：threading.Event（纳秒级检查） + DB UPDATE 兜底。
    """

    def __init__(self, executor: ThreadPoolExecutor):
        self._executor = executor
        self._events: dict[str, threading.Event] = {}

    @classmethod
    def get_instance(cls) -> "TaskManager":
        if not hasattr(cls, "_instance"):
            cls._instance = cls(executor=settings.ZRAG_INGEST_EXECUTOR)
        return cls._instance

    def submit(self, task: IngestTask, fn) -> None:
        self._events[task.id] = threading.Event()
        self._executor.submit(fn, task)

    def cancel(self, task_id: str) -> None:
        if task_id in self._events:
            self._events[task_id].set()

    def is_cancelled(self, task_id: str) -> bool:
        return self._events.get(task_id, threading.Event()).is_set()
```

#### settings.py 线程池配置

```python
# zrag/settings.py
from concurrent.futures import ThreadPoolExecutor

_ingest_cfg = _config.get("ingest", {})
ZRAG_INGEST = _ingest_cfg
ZRAG_INGEST_EXECUTOR = ThreadPoolExecutor(
    max_workers=_ingest_cfg.get("task_pool_size", 2),
    thread_name_prefix="ingest-",
)
```

#### config/ingest.yaml

```yaml
ingest:
  batch_size: 5
  task_pool_size: 2
```

#### DB 建表

```sql
CREATE TABLE IF NOT EXISTS ingest_tasks (
    id            TEXT PRIMARY KEY,
    task_type     TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending',
    total         INTEGER DEFAULT 0,
    processed     INTEGER DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
```

#### MacNotesSource 新版

```python
# zrag/ingest/sources/mac_notes.py — 文件桥接模式
import json
import os
import time
from pathlib import Path
from typing import Iterator

from zrag.ingest.sources.base import DocumentSource
from zrag.models.document import RawDocument

EXPORT_BASE_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "data", "pro", "export"
)


class MacNotesSource(DocumentSource):
    """macOS 备忘录数据源（文件桥接模式）"""

    def __init__(self, task_id: str):
        self._task_id = task_id
        self._export_dir = os.path.join(EXPORT_BASE_DIR, task_id)
        self._total = 0

    @property
    def source_type(self) -> str:
        return "mac_notes"

    def total_count(self) -> int:
        return self._total

    def fetch_batch(self, batch_size: int = 1) -> Iterator[RawDocument]:
        # 阶段 1: 轮询 result.json
        result_file = os.path.join(self._export_dir, "result.json")
        while not os.path.exists(result_file):
            time.sleep(2)

        with open(result_file) as f:
            result = json.load(f)
        if result.get("status") != "ok":
            raise RuntimeError(f"导出失败: {result.get('message', '')}")

        self._total = result["success"]

        # 阶段 2: 逐篇 yield
        for filepath in sorted(Path(self._export_dir).glob("*.json")):
            if filepath.name == "result.json":
                continue
            with open(filepath) as f:
                note = json.load(f)
            yield RawDocument(
                source_id=note["source_id"],
                source_type=note["source_type"],
                content=note["content"],
                content_hash=note["content_hash"],
                metadata=note["metadata"],
            )
```

#### IngestionPipeline 新版（关键改动）

```python
# zrag/ingest/pipeline.py — 逐篇处理 + task 支持

def run(
    self,
    source: DocumentSource,
    full: bool = False,
    task: IngestTask | None = None,
) -> IngestReport:
    from zrag.api.task_manager import TaskManager

    report = IngestReport()

    for doc in source.fetch_batch(batch_size=1):

        # 取消检测
        if task and TaskManager.get_instance().is_cancelled(task.id):
            break

        # 增量判断
        if not full:
            existing = self.sqlite_store.get_processed(doc.source_id)
            if existing and existing["content_hash"] == doc.content_hash:
                report.skipped += 1
                if task:
                    task.processed += 1
                continue
        report.total += 1

        # 处理
        try:
            chunks = self.chunker.chunk(doc)
            vectors = self.embedder.embed([c.content for c in chunks])

            with self.sqlite_store.transaction():
                self.sqlite_store.delete_by_source(doc.source_id)
                self.sqlite_store.add_chunks(chunks)

            self.chroma_store.delete_by_source(doc.source_id)
            self.chroma_store.add(
                ids=[c.chunk_id for c in chunks],
                embeddings=vectors,
                metadatas=[{
                    "source_id": c.source_id, "source_type": c.source_type,
                    "doc_title": c.doc_title, "chunk_index": c.chunk_index,
                } for c in chunks],
            )

            self.sqlite_store.upsert_processed(doc)
            report.new += 1

        except Exception as e:
            logger.exception("文档 %s 处理失败", doc.source_id)
            report.failed += 1

        if task:
            task.processed += 1

    return report
```

#### 导出脚本 manifest.json 格式

```json
{
  "task_id": "abc-123-def",
  "source_type": "mac_notes",
  "processed_docs": [
    {"source_id": "note-1", "content_hash": "sha256..."},
    {"source_id": "note-2", "content_hash": "sha256..."}
  ]
}
```

#### 数据目录结构

```
data/pro/export/<task_id>/
  ├── manifest.json         # 后端写入
  ├── result.json           # 导出脚本写入 {"status":"ok","task_id":"abc-123-def","expected":128,"success":128,"exported_at":"2026-06-09T10:30:00+08:00"}
  └── <note_id>.json        # 单条笔记 {"source_id","source_type","content","content_hash","metadata"}
```

### 38.11 result.json 文件结构设计

**日期**: 2026-06-09

经过多轮讨论，最终确定 result.json 只做汇总统计，不包含逐条元信息和错误列表。

**result.json 最终格式**:

```json
{
  "status": "ok",
  "task_id": "abc-123-def",
  "expected": 150,
  "success": 128,
  "exported_at": "2026-06-09T10:30:00+08:00"
}
```

**字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | string | `"ok"` 表示导出完成。脚本异常退出时不生成此文件 |
| `task_id` | string | 与后端创建的任务 ID 对应，用于关联 |
| `expected` | int | 本次导出计划导出的笔记数量 |
| `success` | int | 最终成功写入文件的数量 |
| `exported_at` | string | 导出完成时间，ISO 8601 格式，含时区 |

**设计决策要点**:

1. **不包含逐条元信息**：每条笔记的元信息（note_id、title、folder、content_hash）保存在对应 `<note_id>.json` 文件中，result.json 只做汇总统计
2. **不包含错误列表**：导出失败的笔记直接跳过，不在 result.json 中单独记录。通过 `expected - success` 的差值即可判断是否有笔记导出失败
3. **`expected` 和 `success` 两个字段**：
   - `expected`：计划导出数（本次应该导出的数量）
   - `success`：成功导出数（最终成功写入文件的数量）
   - `expected - success` = 导出失败被跳过的数量
4. **`expected` 覆盖全量与增量两种模式**：
   - 全量模式：所有笔记数量
   - 增量模式：本次变更的笔记数量（无变更时 `expected=0` 且 `success=0`，视为正常完成）
5. **异常退出不生成 result.json**：导出脚本异常退出时不写入 result.json，容器侧通过文件不存在来感知失败

### 38.12 单条笔记 JSON 文件结构设计

**日期**: 2026-06-09

#### 讨论背景

在 38.10 中，单条笔记文件 `<note_id>.json` 的初始结构为：

```json
{
  "id": "x-coredata://...",
  "name": "笔记标题",
  "folder": "所属文件夹名",
  "content": "# 标题\n\nMarkdown 正文..."
}
```

该结构是一个独立设计的格式，与项目中已有的 RawDocument 数据模型（见 Q5）不一致。这意味着容器侧的 MacNotesSource 在读取每个 JSON 文件后，需要手动进行字段映射（如 `note["id"]` → `RawDocument.source_id`、拼接 metadata 等），增加了不必要的转换逻辑。

**用户要求**：按照 RawDocument 对象的设计来补充 JSON 结构，使导出脚本产出的 JSON 与容器侧 RawDocument 的反序列化直接对应，消除手动映射层。

#### 讨论迭代

1. **对齐 RawDocument 字段**：RawDocument 包含 5 个字段——`source_id`、`source_type`、`content`、`content_hash`、`metadata`。单条笔记 JSON 应直接沿用这 5 个字段，让 MacNotesSource 可以逐字段赋值，无需翻译。
2. **content 格式确认**：`content` 为 Markdown 格式。Notes.app 的 `body of theNote` 返回 Apple 内部富文本格式，由导出脚本的 `_html_to_markdown()` 负责转换为 Markdown。容器侧不再执行 HTML 解析。
3. **metadata 保留但暂为空**：`metadata` 字段保留（类型为 map/dict），当前内容为 `{}`。原先独立存储的 `name`（笔记标题）和 `folder`（所属文件夹）不单独作为顶层字段，后续如有需要可放入 metadata 中扩展。
4. **content_hash 由导出脚本预计算**：原先 content_hash 由 Pipeline 在处理时计算（见 38.10 代码中 `content_hash=""` 的注释），改为导出脚本在写入 JSON 文件时预计算 SHA256 并填入。容器侧直接读取，避免重复 I/O。

#### 最终结构

单条笔记 JSON 文件（`<note_id>.json`）结构：

```json
{
  "source_id": "note-uuid-xxxx",
  "source_type": "mac_notes",
  "content": "Markdown正文...",
  "content_hash": "sha256...",
  "metadata": {}
}
```

#### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `source_id` | string | Apple Notes 的 note_id（UUID），对应 RawDocument.source_id |
| `source_type` | string | 固定为 `"mac_notes"`，对应 RawDocument.source_type |
| `content` | string | 笔记正文，Markdown 格式。由导出脚本负责 HTML→Markdown 转换 |
| `content_hash` | string | SHA256 哈希值，由导出脚本在导出时预计算，对应 RawDocument.content_hash |
| `metadata` | dict | 保留字段，当前内容为空 `{}`，后续可扩展（如追加 title、folder、tags 等） |

#### 设计要点

- **与 RawDocument 一一对应**：容器侧 MacNotesSource 读取 JSON 后可直接构造 RawDocument 对象，无需额外字段翻译或拼接。例如：`RawDocument(source_id=note["source_id"], source_type=note["source_type"], content=note["content"], content_hash=note["content_hash"], metadata=note["metadata"])`
- **content_hash 预计算**：导出脚本在生成 JSON 时一并计算 SHA256 并填入，容器侧 Pipeline 无需再次读取 content 计算 hash，减少容器侧 I/O 开销
- **metadata 为空对象**：当前不存储 name、folder 等字段，但保留 `{}` 占位，为后续扩展预留空间（如新增 tags、created_at、modified_at 等维度）
- **name 和 folder 暂不单独存储**：这些信息当前在摄入流程中未被使用（分块、向量化、检索均不依赖笔记标题或文件夹名），避免在 JSON 中引入冗余字段。后续如有需要，可加入 metadata

### 38.13 manifest.json 文件结构设计

**日期**: 2026-06-09

#### 讨论背景

manifest.json 是文件桥接方案中由后端在创建摄入任务时写入的配置文件，导出脚本通过读取它来确定本次导出的范围（全量还是增量、变更了哪些笔记）。

#### 讨论过程

**初始方案**包含 `task_type` 字段区分全量/增量：

```json
{
  "task_id": "...",
  "task_type": "full",
  "source_type": "mac_notes",
  "processed_docs": []
}
```

**讨论迭代**：用户质疑 `task_type` 字段是否有存在的必要。分析发现 `processed_docs` 本身已隐含全量/增量的语义——为空数组即全量模式，非空即增量模式。`task_type` 是冗余字段，移除。

同时确认 `processed_docs` 中的 `source_id` + `content_hash` 足以让导出脚本完成增量判断：
1. `source_id` 不在 processed_docs 中 → 新笔记 → 导出
2. `source_id` 在但 `content_hash` 不同 → 内容变更 → 导出
3. `source_id` 在且 `content_hash` 一致 → 跳过

导出脚本仅凭这对信息即可完成增量判断，无需访问数据库。

**最终格式**:

```json
{
  "task_id": "abc-123-def",
  "source_type": "mac_notes",
  "processed_docs": [
    {"source_id": "note-1", "content_hash": "sha256..."}
  ]
}
```

**字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` | string | 与 result.json 中的 task_id 对应，用于关联 |
| `source_type` | string | 固定为 `"mac_notes"` |
| `processed_docs` | array | 已处理文档列表。全量模式为空数组 `[]`；增量模式包含已有文档的 source_id + content_hash 记录 |

processed_docs 数组项结构：

| 字段 | 类型 | 说明 |
|------|------|------|
| `source_id` | string | 已处理笔记的唯一标识 |
| `content_hash` | string | SHA256 哈希值 |

**设计要点**:

- **后端写入，导出脚本读取**：后端从 SQLite processed_docs 表读取已有记录，序列化为 JSON 写入 manifest.json
- **全量/增量语义由 processed_docs 承载**：空数组即全量，非空即增量。无需额外的 task_type 字段
- **导出脚本零数据库依赖**：仅凭 manifest.json 中的 source_id + content_hash 即可完成增量比对
- **向后兼容**：首次导入时 processed_docs 为空，等价于全量导出

### 38.14 导出脚本工作流程设计

**日期**: 2026-06-09

#### expected 字段的语义澄清

`expected` 不是 Notes.app 中的总笔记数，也不是遍历前的预估值。它是导出脚本经过 `processed_docs` 比对后"判定需要导出的笔记数量"——即在步骤 3d 中逐步累加的值。增量模式下，只有内容确实变更了（hash 不匹配或新增）的笔记才被计入 `expected`。

#### 一次遍历流程

导出脚本只遍历一次 Notes.app，在遍历中同时完成比对和导出，无需预处理扫描：

```
1. 读取 manifest.json → 获取 processed_docs 列表（存为内存 HashMap）

2. expected = 0, success = 0

3. for each note in Notes.app（一次 AppleScript 遍历）:
   a. 获取 note_id + HTML body
   b. 计算 content_hash = SHA256(content)
   c. 查 processed_docs:
      - note_id 不在表中 或 content_hash 不一致 → 需要导出
      - 一致 → 跳过（continue）
   d. expected += 1
   e. HTML → Markdown 转换
   f. 写入 <note_id>.json
      - 成功 → success += 1
      - 失败 → 跳过，不写文件

4. 写入 result.json {status:"ok", task_id, expected, success, exported_at}
```

模式判断由 processed_docs 隐含：
- 全量模式：`processed_docs = []`，所有笔记都判定为"需要导出"
- 增量模式：`processed_docs` 非空，仅 hash 不匹配或新增的笔记才导出

### 38.15 容器侧 MacNotesSource 文件桥接模式

**日期**: 2026-06-09

#### fetch_batch() 实现

文件桥接模式下，`MacNotesSource.fetch_batch()` 改为两阶段工作：

**阶段 1 — 轮询等待导出完成**：阻塞等待宿主机导出脚本写入 `result.json`：

```python
result_file = os.path.join(self._export_dir, "result.json")
while not os.path.exists(result_file):
    time.sleep(2)

with open(result_file) as f:
    result = json.load(f)

if result["status"] != "ok":
    raise IngestionException("导出脚本未正常完成")
```

**阶段 2 — 逐篇 yield RawDocument**：遍历导出目录下所有 `<note_id>.json`，跳过 manifest.json 和 result.json，逐篇构造 RawDocument：

```python
for filepath in sorted(Path(self._export_dir).glob("*.json")):
    if filepath.name in ("manifest.json", "result.json"):
        continue
    with open(filepath) as f:
        note = json.load(f)
    yield [RawDocument(
        source_id=note["source_id"],
        source_type=note["source_type"],
        content=note["content"],
        content_hash=note["content_hash"],
        metadata=note.get("metadata", {}),
    )]
```

#### 设计决策

**batch_size=1**：文件桥接模式下每篇笔记已是独立 JSON 文件，batch_size 固定为 1（逐篇处理）。这与 AppleScript 模式下的 batch_size=10（一次 osascript 获取 10 条）不同，但两种模式共享同一套 Pipeline（逐篇独立事务），无需做代码适配。

**轮询不设超时**：容器侧等待 `result.json` 的循环不设硬超时。原因是导入操作本质上是一个"异步任务"：用户在前端点击"开始导入"后，需要手动在终端执行导出脚本。导出时间取决于笔记数量和系统性能，无法预设合理上限。取而代之的方案是通过任务管理机制——如果用户想中止等待中的导入任务，可以通过 task_id 取消任务，轮询循环检测到取消信号后终止。

### 38.16 摄入任务状态与取消机制

**日期**: 2026-06-09

#### 任务状态机

```
PENDING ──→ WAITING_EXPORT ──→ PROCESSING ──→ DONE
   │              │                │
   └──────────────┼────────────────┘
                  ▼
             CANCELLED
```

任意非 DONE 状态都可以被取消。

| 状态 | 含义 | 取消行为 |
|------|------|---------|
| `PENDING` | 后端已创建任务，写入 manifest.json，等待用户执行导出脚本 | 直接标记 CANCELLED，清理 manifest.json |
| `WAITING_EXPORT` | 容器侧轮询等待 result.json | 设置取消信号，轮询循环检测到后退出 |
| `PROCESSING` | result.json 就绪，Pipeline 开始逐篇处理 | 设置取消信号，Pipeline 在文档间检测，中断后续处理 |
| `DONE` | 全部完成 | 不可取消 |
| `CANCELLED` | 已被用户取消 | 终态 |

#### 取消信号实现

使用 `threading.Event()` 作为线程安全取消信号：

```python
class IngestTask:
    def __init__(self):
        self._cancel_event = threading.Event()
    
    def cancel(self):
        self.status = CANCELLED
        self._cancel_event.set()
    
    def is_cancelled(self):
        return self._cancel_event.is_set()
```

MacNotesSource 轮询中检查（WAITING_EXPORT 阶段）：

```python
while not os.path.exists(result_file):
    if task.is_cancelled():
        return
    time.sleep(2)
```

Pipeline 逐篇处理时检查（PROCESSING 阶段）：

```python
for doc in all_docs:
    if task.is_cancelled():
        break
    # ... chunk → embed → store
```

#### 设计要点

- `threading.Event` 是 Python 内置的线程安全布尔标志，nanosecond 级别的检查开销，无需引入额外依赖
- 取消信号不强制中断正在处理中的文档（那会导致数据不一致），仅在文档间检查
- 取消后任务状态持久化到 DB，前端轮询状态时更新为"已取消"

### 38.17 导出目录清理策略

**日期**: 2026-06-09

任务结束（DONE 或 CANCELLED）后，`data/pro/export/<task_id>/` 目录不再需要，应清理以释放磁盘空间。

**清理时机与方式**：

- **由单独的清理线程负责**：不在 Pipeline 线程中执行清理，而是提交给一个独立的清理线程。这样 Pipeline 线程可以快速结束，不阻塞任务状态的最终更新
- **DONE 和 CANCELLED 都需要清理**：无论任务是正常完成还是被取消，导出文件都已无用，统一清理
- **清理操作**：`shutil.rmtree(export_dir)`，删除整个任务导出目录
- **清理失败不影响任务结果**：如果清理失败（如权限问题），仅记录日志，不影响任务 DONE/CANCELLED 状态

### 38.18 API 端点调整

**日期**: 2026-06-09

#### 现有端点修改

`POST /v1/documents/ingest` 由同步阻塞改为异步：

| | 修改前 | 修改后 |
|------|------|------|
| 行为 | 同步调用 `pipeline.run()`，等待全部完成后返回 | 创建任务 → 提交线程池 → 立即返回 |
| HTTP 状态码 | `200` | `202 Accepted` |
| 返回值 | `{total, new, updated, skipped, failed, errors}` | `{task_id, status: "PENDING"}` |

所有 source_type 统一走异步，不区分 mac_notes 或其他类型。

#### 新增端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v1/ingest/{task_id}/status` | 查询任务状态和进度 |
| POST | `/v1/ingest/{task_id}/cancel` | 取消任务 |

GET /status 返回：
```json
{
  "task_id": "abc-123",
  "task_type": "full",
  "source_type": "mac_notes",
  "status": "PROCESSING",
  "total": 128,
  "processed": 45,
  "created_at": "...",
  "updated_at": "..."
}
```

POST /cancel 返回当前任务状态，确认已标记为取消。

### 38.19 前端交互设计

**日期**: 2026-06-09

#### 操作流程

1. 用户先选择数据源（如"macOS 备忘录"）
2. 用户选择全量导入或增量导入
3. 前端调用 `POST /v1/documents/ingest` → 获得 `task_id`
4. 对于需要宿主机导出脚本的数据源（如 mac_notes）：页面内持久性提示"请在终端执行 `python3 zrag/export_notes.py <task_id>`"
5. 前端轮询 `GET /v1/ingest/{task_id}/status`（2s 间隔）
6. 显示当前阶段名称 + 进度条（`processed / total`）
7. 用户可点击"取消"按钮终止任务
8. 任务 DONE 或 CANCELLED 时停止轮询，刷新来源列表

#### 提示方式

执行导出脚本的提示必须是**永久性提示**，而非页面右上角的临时 Toast 弹窗。形式为内联消息条，持久显示直到任务状态变更后才消失。这样用户不会因 Toast 自动消失而错过操作指引。

#### 进度展示

同时展示两个维度的进度信息：
- **阶段名称**：如"等待导出..."、"正在处理（45/128）"、"处理完成"
- **进度条**：可视化 `processed / total` 比例

#### 页面布局

```
┌──────────────────────────────────────────────────────┐
│  NavBar                                              │
├──────────────────────────────────────────────────────┤
│  知识库来源                                          │
│  ┌─────────────────────┐ ┌──────────┐ ┌──────────┐  │
│  │ 数据源: macOS备忘录 ▾│ │ 增量摄入 │ │ 全量摄入 │  │
│  └─────────────────────┘ └──────────┘ └──────────┘  │
│                                                      │
│  ┌────────────────────────────────────────────────┐  │
│  │ ⚠️ 请在终端执行:                               ✕ │  │
│  │    python3 zrag/export_notes.py abc-123         │  │
│  │                              [📋 复制]          │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  正在处理（45/128）                    [取消]        │
│  ████████████████░░░░░░░░░░░░░░░░░░░░░  35%         │
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │ mac_notes│  │          │  │          │          │
│  └──────────┘  └──────────┘  └──────────┘          │
└──────────────────────────────────────────────────────┘
```

#### 三个交互状态

**状态 1 — 等待导出（WAITING_EXPORT）**：
- 阶段名："等待导出笔记..."
- 进度条：indeterminate 动画（无 total，无法确定进度）
- 提示区：显示导出命令 + 复制按钮

**状态 2 — 处理中（PROCESSING）**：
- 阶段名："正在处理（45/128）"
- 进度条：确定进度，百分比
- 提示区：隐藏
- 取消按钮：可用

**状态 3 — 完成（DONE）**：
- 提示区、进度区、阶段名：全部隐藏
- Toast：摄入概要（新增/更新/跳过数量）
- 来源列表：自动刷新

**状态 4 — 取消/失败（CANCELLED/FAILED）**：
- 提示区、进度区、阶段名：全部隐藏
- Toast：取消确认或错误信息

### 38.20 线程池配置

**日期**: 2026-06-09

```python
# config/ingest.yaml
task_pool_size: 2

# zrag/settings.py
from concurrent.futures import ThreadPoolExecutor
ZRAG_INGEST_EXECUTOR = ThreadPoolExecutor(max_workers=ingest_cfg["task_pool_size"])
```

`max_workers=2`：个人使用场景下最多同时运行一个摄入任务，2 个 worker 覆盖"一个运行中任务 + 一个清理线程"。

### 38.21 MacNotesSource 模式

**日期**: 2026-06-09

只实现文件桥接模式，移除 AppleScript/osascript 直接调用代码。`MacNotesSource.fetch_batch()` 统一为轮询 `result.json` + 逐篇读取 `<note_id>.json` 的实现。

### 38.22 导出脚本（export_notes.py）

**日期**: 2026-06-09

脚本运行在宿主机（macOS）上，由用户在终端手动执行：`python3 zrag/export_notes.py <task_id>`。不打包进容器镜像。

核心流程：
1. 读取 `manifest.json`，构建 `{source_id: content_hash}` HashMap
2. 通过 AppleScript 调用 Notes.app，遍历所有笔记
3. 增量比对：`note_id` 不在 HashMap 中或 `content_hash` 不一致则需导出
4. HTML → Markdown（纯正则，零外部依赖）
5. 写入 `<note_id>.json`
6. 写入 `result.json`

日志要求：
- 关键节点必须有屏幕打印日志（`print()`）：
  - 开始导出：`"开始导出，计划导出 {expected} 条笔记"`
  - 每条笔记导出：`"[{n}/{total}] {note_title}"`
  - 完成：`"导出完成。成功 {success} 条"`
- 任何异常必须记录：单条笔记失败打印 `"[WARN] 笔记 {note_id} 导出失败: {error}"`，致命异常打印完整 traceback

### 38.23 IngestionPipeline 改动

**日期**: 2026-06-09

#### 取消信号检查

`run()` 新增 `should_cancel` 可选回调参数。Pipeline 在每篇文档处理开始前检查取消信号，返回 True 时中断后续处理：

```python
def run(self, source, full=False, on_document_done=None, should_cancel=None) -> IngestReport:
    for doc in all_docs:
        if should_cancel and should_cancel():
            break
        # ... chunk → embed → store
```

取消信号不强制中断正在处理的文档（那会导致数据不一致），仅在文档间检查。

#### full 参数保留

文件桥接模式下导出脚本已完成增量比对，但 Pipeline 内部仍通过 `full` 参数控制是否二次检查 `processed_docs` 表，作为安全冗余。

#### on_progress 移除

移除 `on_progress` 回调和 `ProgressEvent` 数据结构。替换为简化的 `on_document_done` 回调：每篇文档处理完成（成功或失败）后调用一次，不传参数。Pipeline 不感知 TaskManager 和 DB 细节，TaskManager 通过此回调更新 DB 中的 `processed` 计数。

**设计原则**：Pipeline 只做编排，不关心进度如何被消费。进度上报和任务取消都是可选的外部关注点，通过回调解耦。

### 38.24 导出脚本 tag 过滤

**日期**: 2026-06-10

导出脚本支持通过 `--tag` 参数按笔记标签过滤：

```bash
python3 zrag/export_notes.py <task_id>                     # 全部笔记
python3 zrag/export_notes.py <task_id> --tag "技术笔记"     # 仅匹配标签的笔记
```

- tag 过滤只在导出脚本中实现，不涉及 manifest.json 和后端
- `expected` 统计匹配标签的笔记数
- 标签过滤可以与增量模式组合（先按标签过滤，再比对 processed_docs 决定是否导出）

### 38.25 IngestTaskViewSet 实现

**日期**: 2026-06-10

基于项目已有 ViewSet 模式（`DocumentViewSet`、`ConversationViewSet`），新增任务管理 ViewSet：

```python
class IngestTaskViewSet(viewsets.ViewSet):
    authentication_classes = [APIKeyAuthentication]

    def status(self, request, task_id=None):
        """GET /v1/ingest/{task_id}/status"""
        manager = TaskManager.get_instance()
        task = manager.get_task(task_id)
        if task is None:
            return APIResponse(data=None, message="task not found", http_status=404)
        return APIResponse(data=manager.to_dict(task))

    def cancel(self, request, task_id=None):
        """POST /v1/ingest/{task_id}/cancel"""
        manager = TaskManager.get_instance()
        task = manager.get_task(task_id)
        if task is None:
            return APIResponse(data=None, message="task not found", http_status=404)
        manager.cancel_task(task_id)
        return APIResponse(data=manager.to_dict(task))
```

路由注册（`zrag/api/urls.py`）：

```python
task_urls = [
    re_path(r'^v1/ingest/(?P<task_id>[^/]+)/status$',
        IngestTaskViewSet.as_view({'get': 'status'})),
    re_path(r'^v1/ingest/(?P<task_id>[^/]+)/cancel$',
        IngestTaskViewSet.as_view({'post': 'cancel'})),
]
```

`manager.to_dict(task)` 返回结构：

```json
{
    "task_id": "abc-123",
    "task_type": "full",
    "status": "PROCESSING",
    "total": 128,
    "processed": 45,
    "created_at": "2026-06-10T...",
    "updated_at": "2026-06-10T..."
}
```

### 38.26 TaskManager 核心实现

**日期**: 2026-06-10

TaskManager 作为模块级单例，统一管理摄入任务的生命周期。

```python
class TaskManager:
    _instance = None

    @classmethod
    def get_instance(cls) -> "TaskManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        from django.conf import settings
        self._executor = settings.ZRAG_INGEST_EXECUTOR
        self._tasks: dict[str, IngestTask] = {}
        self._events: dict[str, threading.Event] = {}

    def create_task(self, task_type: str) -> IngestTask:
        """创建任务并持久化"""
        now = datetime.utcnow().isoformat()
        task = IngestTask(
            id=str(uuid.uuid4()),
            task_type=task_type,
            status=TaskStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
        self._write_manifest(task)
        self._upsert_task_db(task)
        self._tasks[task.id] = task
        self._events[task.id] = threading.Event()
        return task

    def submit(self, task: IngestTask, pipeline, source, full: bool):
        """提交任务到线程池"""
        task.status = TaskStatus.WAITING_EXPORT
        self._executor.submit(self._run, task, pipeline, source, full)

    def cancel_task(self, task_id: str):
        """标记取消"""
        task = self._tasks.get(task_id)
        if task:
            task.status = TaskStatus.CANCELLED
            self._events[task_id].set()

    def get_task(self, task_id: str) -> IngestTask | None:
        return self._tasks.get(task_id)

    def to_dict(self, task: IngestTask) -> dict:
        return {
            "task_id": task.id,
            "task_type": task.task_type,
            "status": task.status.value,
            "total": task.total,
            "processed": task.processed,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        }

    def _run(self, task, pipeline, source, full):
        try:
            task.status = TaskStatus.PROCESSING
            report = pipeline.run(
                source=source,
                full=full,
                on_document_done=lambda: self._on_document_done(task),
                should_cancel=lambda: self._events[task.id].is_set(),
            )
            task.status = TaskStatus.DONE
        except Exception:
            if self._events[task.id].is_set():
                task.status = TaskStatus.CANCELLED
            else:
                task.status = TaskStatus.FAILED
        finally:
            self._cleanup(task)

    def _cleanup(self, task: IngestTask):
        export_dir = os.path.join(settings.BASE_DIR, "data", "pro", "export", task.id)
        self._executor.submit(self._do_cleanup, export_dir)

    def _do_cleanup(self, export_dir: str):
        try:
            shutil.rmtree(export_dir)
        except Exception:
            logger.exception("清理导出目录失败: %s", export_dir)

    def _on_document_done(self, task: IngestTask):
        task.processed += 1
        task.updated_at = datetime.utcnow().isoformat()
        self._upsert_task_db(task)
```

调用方（views.py）：

```python
manager = TaskManager.get_instance()
task = manager.create_task(task_type="full", source_type="mac_notes")
manager.submit(task, pipeline, source, full)
return APIResponse(data={"task_id": task.id, "status": task.status}, http_status=202)
```

设计要点：
- `_cleanup` 向线程池提交清理任务，不阻塞 Pipeline 线程
- 清理失败只记录日志，不影响任务终态
- `ThreadPoolExecutor` 通过 Django settings 注入，统一管理线程资源

### 38.27 前端 API 层改动

**日期**: 2026-06-10

`frontend/src/api/endpoints.js` 新增两个端点函数，`ingestDocuments` 透传后端响应不变：

```javascript
export const ingestDocuments = (body) => apiPost('/v1/documents/ingest', body)  // 返回 {task_id, status}
export const getTaskStatus = (taskId) => apiGet(`/v1/ingest/${taskId}/status`)
export const cancelIngestTask = (taskId) => apiPost(`/v1/ingest/${taskId}/cancel`)
```

### 38.28 数据源可用列表端点

**日期**: 2026-06-10

新增 `GET /v1/sources/available` 返回 SOURCE_REGISTRY 中已注册的数据源 key 列表，供前端下拉选择器使用。

views.py（DocumentViewSet）:

```python
def list_available_sources(self, request):
    return APIResponse(
        data={"sources": list(SOURCE_REGISTRY.keys())},
        request=request,
    )
```

urls.py:

```python
re_path(r'^v1/sources/available$',
    DocumentViewSet.as_view({'get': 'list_available_sources'})),
```

### 38.29 轮询完成后的统计展示

**日期**: 2026-06-10

前端 DONE 时不展示详细的 ingest 统计（new/updated/skipped/failed），仅显示"摄入完成，共处理 N 篇"。详细统计信息可通过 swagger 或日志查看。

### 38.30 轮询错误处理

**日期**: 2026-06-10

轮询 `GET /v1/ingest/{task_id}/status` 过程中的网络错误不停止轮询，而是持续重试直至任务到达终态或被用户取消。失败期间显示"连接中断，重试中..."提示，恢复后自动消失。

### 38.31 跨页面状态恢复

**日期**: 2026-06-10

用户离开 SourcesView（切换页面/刷新）后，后端任务仍在运行。使用 `sessionStorage` 存储活跃 `taskId`，页面挂载时自动恢复轮询：

- 发起导入 → `sessionStorage.setItem('activeIngestTask', taskId)`
- 轮询中发现终态 → `sessionStorage.removeItem('activeIngestTask')`
- 页面 `onMounted` 时 → 读取 sessionStorage，存在则调用 `startPolling(taskId)` 恢复轮询

`sessionStorage` 仅在当前标签页存活，关闭标签页后自动清除，无需手动管理。

### 38.32 按钮状态约束

**日期**: 2026-06-10

- 未选数据源时，"增量摄入"和"全量摄入"按钮均禁用
- `ingesting` 期间，数据源下拉选择器 + 两个摄入按钮均禁用

### 38.33 取消操作前端流程

**日期**: 2026-06-10

```
[取消] 按钮点击
  → 按钮变为 "取消中..." + disabled（防二次点击）
  → cancelIngestTask(taskId) API 调用
  → 后端 TaskManager.cancel_task → event.set() + status = CANCELLED
  → 下一次轮询（2s内）检测到 status === 'CANCELLED'
  → 停止轮询，隐藏进度区和提示区
  → sessionStorage.removeItem('activeIngestTask')
```

取消 API 调用失败时，恢复"取消"按钮可用，让用户重试。

### 38.34 抽象类父类型检查

**日期**: 2026-06-10

依据 `.claude/rules/python-code-style.md` 中"抽象类的父类型检查机制"，通过依赖注入接收抽象类实例的功能逻辑，必须在**使用前**检查该实例是否继承了指定的抽象类。不通过则抛出异常终止流程。

需要添加检查的位置：

| 文件 | 位置 | 需检查的抽象类 |
|------|------|--------------|
| `zrag/ingest/pipeline.py` | `IngestionPipeline.__init__` | `EmbeddingModel`（embedder）、`ChunkingStrategy`（chunker） |
| `zrag/ingest/pipeline.py` | `IngestionPipeline.run()` | `DocumentSource`（source） |
| `zrag/retrieval/retriever.py` | `Retriever.__init__` | `EmbeddingModel`（embedder） |
| `zrag/api/views.py` | `ConversationViewSet._get_llm()` | `LLMProvider`（llm_provider） |

检查模板：

```python
if not isinstance(embedder, EmbeddingModel):
    raise TypeError(
        f"embedder 必须是 EmbeddingModel 的子类，实际类型: {type(embedder).__name__}"
    )
```
