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
  ├── result.json           # 导出脚本写入 {"status":"ok","total":3699}
  └── <note_id>.json        # 单条笔记 {id,name,folder,content}
```

- 增量模式: manifest.json 中含 processed_docs，导出脚本对比 hash 只导出变更
- 全量模式: processed_docs 为空

### 38.3 任务抽象

**TaskStatus**:
```python
PENDING     # 已提交，等待线程池调度
EXPORTING   # 等待宿主机导出文件就绪（mac_notes 专用）
INGESTING   # Pipeline 逐篇 chunk→embed→store
DONE        # 全部完成
CANCELLED   # 用户手动取消
ERROR       # 异常终止
```

**DB 表 ingest_tasks**: id, task_type, status, total, processed, created_at, updated_at

**IngestTask**（内存对象）: 与 DB 表字段一一对应

### 38.4 TaskManager — 线程池 + 取消机制

- 线程池: `ThreadPoolExecutor(max_workers=2)` 定义在 settings.py `ZRAG_INGEST_EXECUTOR`，注入 TaskManager
- 配置: `config/ingest.yaml` → `task_pool_size: 2`
- 取消: `threading.Event` 纳秒级检查，每篇文档处理前 `is_set()`；DB 双写兜底

### 38.5 Pipeline 改动

- `all_docs = []` 移除，改为逐篇 `for doc in source.fetch_batch()`
- 每篇前检查取消信号
- 每篇后更新 task.processed
- 完成后清理线程删除 `data/pro/export/<task_id>/`

### 38.6 MacNotesSource 改动

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

        self._total = result["total"]

        # 阶段 2: 逐篇 yield
        for filepath in sorted(Path(self._export_dir).glob("*.json")):
            if filepath.name == "result.json":
                continue
            with open(filepath) as f:
                note = json.load(f)
            yield RawDocument(
                source_id=note["id"],
                source_type=self.source_type,
                content=note["content"],
                content_hash="",  # Pipeline 填入
                metadata={
                    "folder": note.get("folder", ""),
                    "name": note.get("name", ""),
                },
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

#### 异步摄入执行函数

```python
# zrag/api/task_manager.py (补充)
import shutil

def _run_ingest_task(task: IngestTask, source_type: str, full: bool):
    """在线程池中执行的摄入任务"""
    task.status = TaskStatus.EXPORTING
    export_dir = f"data/pro/export/{task.id}"

    if source_type == "mac_notes":
        source = MacNotesSource(task_id=task.id)
    else:
        # 其他 source 直接创建，跳过 EXPORTING
        pass

    task.status = TaskStatus.INGESTING
    pipeline = IngestionPipeline(...)
    try:
        report = pipeline.run(source=source, full=full, task=task)
        task.status = TaskStatus.DONE
    except Exception:
        task.status = TaskStatus.ERROR

    # 清理（独立线程）
    if os.path.exists(export_dir):
        threading.Thread(target=lambda: shutil.rmtree(export_dir)).start()
```

#### 导出脚本 manifest.json 格式

```json
{
    "task_id": "abc123-def456",
    "source_type": "mac_notes",
    "task_type": "incr",
    "exported_at": "2026-06-09T10:00:00",
    "processed_docs": [
        {"source_id": "xxx", "content_hash": "abc...", "imported_at": "..."}
    ]
}
```

#### 数据目录结构

```
data/pro/export/<task_id>/
  ├── manifest.json         # 后端写入
  ├── result.json           # 导出脚本写入 {"status":"ok","total":128}
  └── <note_id>.json        # 单条笔记 {"id","name","folder","content"}
```
