# 摄入任务后端进度相关问题记录

## 背景

前端「知识库」页面在点击「增量摄入」或「全量摄入」后，会创建后台摄入任务并轮询 `/v1/ingest/{task_id}/status` 展示进度。在排查前端进度条显示问题时，发现后端存在以下两个问题，它们共同导致前端在手动导出等待期显示「正在处理（0/0）」且无法展示真实的百分比进度。

## 问题 1：任务状态切换过早，导致前端显示失真

### 现象

用户在点击摄入按钮后，页面提示执行 `python3 export_notes.py {taskId}`。在**用户尚未执行导出脚本**前，前端轮询到的任务状态已经是 `processing`，且 `total=0`、`processed=0`，于是渲染出「正在处理（0/0）」。

### 根因

在 `zrag/api/task_manager.py` 中：

1. `TaskManager.submit()` 创建任务后把状态设为 `WAITING_EXPORT`，并立即提交到线程池。
2. 线程池中的 `TaskManager._run()` 在 `pipeline.run()` **开始执行时**就立刻把状态改为 `PROCESSING`。
3. `pipeline.run()` 第一步调用 `source.fetch_batch()`；对于 `mac_notes` 来源，该调用会阻塞等待 `result.json` 文件生成。

因此，在用户手动执行导出脚本之前，后端 API 已经返回 `processing`，而真正的文档处理尚未开始。

### 相关代码路径

- `zrag/api/task_manager.py`：`TaskManager._run()` 第 246 行将状态设为 `PROCESSING`。
- `zrag/ingest/pipeline.py`：`pipeline.run()` 第 181 行调用 `source.fetch_batch()`。
- `zrag/ingest/sources/mac_notes.py`：`fetch_batch()` 阻塞等待 `result.json`。

## 问题 2：`task.total` 始终为 0，无法支持真实百分比进度

### 现象

即使 `result.json` 已经就绪、后端开始逐篇处理文档，`GET /v1/ingest/{task_id}/status` 返回的 `total` 仍然为 0。前端无法计算 `(processed / total)` 百分比，只能退化为 indeterminate 动画。

### 根因

`IngestionPipeline.run()` 在本地构建了 `IngestReport` 并记录了 `report.total = len(all_docs)`，但从未将总数回写到 `IngestTask.total`。`TaskManager` 中的 `task.total` 从创建到结束始终保持默认值 0。

### 相关代码路径

- `zrag/ingest/pipeline.py` 第 184 行：`report = IngestReport(total=len(all_docs))`。
- `zrag/api/task_manager.py`：`IngestTask.total` 字段默认值为 0，且 `_run()` 未从 pipeline 结果更新它。

## 建议的后端改动

### 改动 1：在文档总数确定后回写 `task.total`

在 `pipeline.run()` 增加可选回调 `on_total_known`，在 `fetch_batch()` 完成后、进入单篇文档处理循环前，把文档总数通知给调用方。

#### `zrag/ingest/pipeline.py`

```python
def run(
    self,
    source: DocumentSource,
    full: bool = False,
    on_document_done: Callable | None = None,
    on_total_known: Callable[[int], None] | None = None,
    should_cancel: Callable | None = None,
) -> IngestReport:
```

在 `all_docs` 聚合完成后调用：

```python
all_docs = []
for batch in source.fetch_batch(batch_size=self.batch_size):
    all_docs.extend(batch)

if on_total_known:
    on_total_known(len(all_docs))
```

#### `zrag/api/task_manager.py`

新增 `_on_total_known` 方法：

```python
def _on_total_known(self, task: IngestTask, total: int) -> None:
    task.total = total
    task.updated_at = datetime.now(timezone.utc).isoformat()
    self._upsert_task_db(task)
```

在 `_run()` 中传入回调：

```python
pipeline.run(
    source=source,
    full=full,
    on_document_done=lambda: self._on_document_done(task),
    on_total_known=lambda n: self._on_total_known(task, n),
    should_cancel=lambda: self._events[task.id].is_set(),
)
```

### 改动 2（可选）：让 `WAITING_EXPORT` 真正覆盖手动等待期

当前 `WAITING_EXPORT` 状态存在的时间极短：任务提交到线程池后，线程立即将状态改为 `PROCESSING`，而真正的等待发生在 `PROCESSING` 状态内部。

若要彻底修复，可考虑把状态切换推迟到 `result.json` 就绪之后。实现方式包括：

- 在 Source 层暴露「导出就绪」事件或方法，由 `TaskManager` 控制状态切换。
- 或在 `pipeline.run()` 内部检测 `result.json` 就绪后再调用 `on_processing_start` 回调。

该改动涉及 Pipeline 与 Source 的协作方式，影响面比改动 1 更大。前端侧可以通过对 `total=0` 的降级显示来容忍当前状态行为。

## 影响与风险

- 改动 1 只增加了一个可选回调参数，向后兼容：不传入回调时 `pipeline.run()` 行为不变。
- 改动 1 实施后，`GET /v1/ingest/{task_id}/status` 将在 `fetch_batch()` 完成后返回真实 `total`，前端 determinate 进度条才能正确显示百分比。
- 若不实施后端正向改动，前端仍会在整个 `processing` 阶段使用 indeterminate 动画，但不会显示误导性的「（0/0）」。
- 改动 2 涉及状态机重构，需要更仔细地评估对现有测试和任务取消逻辑的影响。

## 记录时间

2026-06-14
