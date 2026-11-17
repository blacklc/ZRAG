# 日志格式改为 JSON 串

> 分类索引: [QA 文档目录](index.md)

## 需求背景

项目现有的日志输出使用 Python 标准格式字符串:

```python
'%(asctime)s [%(levelname)s] %(thread)d %(funcName)s:%(lineno)d %(message)s'
```

产生的日志形如:

```
2026-06-18 10:30:00,123 [INFO] 12345 func_name:42 Pipeline 执行完成 total=5 new=3 updated=1 skipped=1 failed=0
```

这种方式在开发时人工阅读尚可，但在生产环境存在以下问题:

- **日志聚合困难**: 容器化部署后，日志通过 Docker json-file driver 采集到日志中心（如 ELK、Loki），纯文本格式无法被日志系统结构化解析，丧失了按字段过滤、聚合和告警的能力。
- **字段提取成本高**: 日志中携带的 context 信息（request_id、conversation_id、task_id 等）嵌在 message 字符串中，需要在日志处理端用正则提取，易出错且性能差。
- **机器可读性差**: 后续若引入自动异常检测或告警规则，JSON 结构化日志是基本前提。

## 方案选型讨论: 全量 JSON vs 内部参考项目混合方案

### 方案 A: 全量 JSON

所有日志（包含简单的一行信息）统一输出为 JSON 串。每个日志记录包含固定字段（timestamp、level、logger、thread、funcName、lineno、message）和按需透出的 extra fields。

### 方案 B: 内部参考项目混合方案（沿用该项目）

简单日志保持纯文本，仅在需要携带结构化数据时使用 JSON。message 字段固定位置注入 key=value 对。

### 决策结果: 选择方案 A

| 对比维度 | 方案 A（全量 JSON） | 方案 B（混合方案） |
|---------|:-----------------:|:----------------:|
| 日志系统解析 | 开箱即用，无需额外配置 | 仍需要解析部分 text message |
| 人工阅读 | 借助 `jq` 或日志系统格式化 | 直接阅读体验更好 |
| 实现复杂度 | 一个 JsonFormatter 即可覆盖 | 两套格式逻辑，需要维护切换规则 |
| 后期维护成本 | 低 | 高 |

核心考量:

1. 项目采用容器化部署，生产环境基本不会有人直接 `docker logs` 查看原始日志，日志输出是给日志采集系统消费的。
2. 全量 JSON 方案只需实现一个 JsonFormatter，所有 handler 统一套用，改动集中且可测试。
3. 若确实需要人工查看原始日志，Docker 的 json-file driver 本身已经对日志做了一轮 JSON 包装（stdout/stderr 流），不需要靠格式本身来保证可读性。

## 最终设计要点

### 1. JsonFormatter 设计

实现一个 `JsonFormatter(logging.Formatter)`，其 `format()` 方法将 LogRecord 转为 JSON 串:

```python
class JsonFormatter(logging.Formatter):
    """将日志记录格式化为 JSON 串"""

    def format(self, record: logging.LogRecord) -> str:
        # 固定字段
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "thread": record.thread,
            "funcName": record.funcName,
            "lineno": record.lineno,
            "message": record.getMessage(),
        }
        # extra 字段透出: 通过 record.__dict__ 中不在标准 LogRecord 属性集合中的 key
        standard_attrs = {
            "args", "asctime", "created", "exc_info", "exc_text", "filename",
            "funcName", "levelname", "levelno", "lineno", "module", "msecs",
            "message", "msg", "name", "pathname", "process", "processName",
            "relativeCreated", "stack_info", "thread", "threadName",
        }
        for key, value in record.__dict__.items():
            if key not in standard_attrs:
                log_data[key] = value
        # traceback 处理
        if record.exc_info and record.exc_info[1]:
            log_data["exception"] = {
                "type": type(record.exc_info[1]).__name__,
                "message": str(record.exc_info[1]),
            }
        # TypeError 兜底: 当 message 或 extra 字段包含不可序列化类型时
        try:
            return json.dumps(log_data, ensure_ascii=False)
        except TypeError:
            log_data["message"] = str(record.getMessage())
            return json.dumps(log_data, ensure_ascii=False, default=str)
```

关键设计决策：

- **固定字段选取**: `timestamp`（ISO 8601 UTC）、`level`、`logger`、`thread`、`funcName`、`lineno`、`message`。这些是定位问题所需的最少信息。
- **extra 透出方式**: 通过 LogRecord 的 `__dict__` 遍历，排除标准属性集合后剩下的 key 即为用户通过 `logging.extra` 传入的自定义字段。无需在 JsonFormatter 中逐个声明允许的 extra key。
- **traceback 字段**: 当 `exc_info` 存在（即调用了 `logger.exception()`）时，在 JSON 中增加 `exception` 对象，包含 `type` 和 `message`，而非将 traceback 拼入 message。traceback 的完整格式化可通过 `exc_text` 在需要时加入，但默认不包含以防日志体积过大。
- **TypeError 兜底**: 当 message 内容或 extra 字段值包含不可 JSON 序列化的类型（如自定义对象）时，先尝试正常序列化，若失败则 fallback 到 `str()` 转换后再序列化。
- 不继承 `logging.Formatter` 的默认格式字符串行为，完全由自定义 `format()` 方法控制。

### 2. 时间戳格式

使用 **ISO 8601 UTC** 格式，例如: `2026-06-18T02:30:00.123456+00:00`。

选用 ISO 8601 而非 epoch timestamp 的原因:
- 人工可读，无需额外转换
- 大多数日志系统（ELK、Loki、Datadog）原生支持 ISO 8601 解析
- 带时区信息，避免在不同时区的日志系统中混淆

使用 `datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()` 获取。

### 3. console 和 file handler 统一格式

不区分 console handler 和 file handler 的日志格式。两者统一使用 JsonFormatter:

```python
'formatters': {
    'json': {
        '()': 'zrag.utils.logging.JsonFormatter',
    },
},
'handlers': {
    'console': {
        'level': 'DEBUG',
        'class': 'logging.StreamHandler',
        'formatter': 'json',
    },
    'file_debug': {
        'level': 'DEBUG',
        'class': 'logging.handlers.TimedRotatingFileHandler',
        'formatter': 'json',
        # ... 其余配置不变
    },
    # ... 其他 file handler 同理
}
```

原因:
- 容器部署下 console handler 的输出直接被 Docker json-file driver 捕获，JSON 格式不影响采集
- 假设有人 `docker logs` 查看，JSON 虽然不如纯文本友好，但已经习惯了（参考 Docker 自身对每条日志额外套一层 JSON 的行为）
- 统一后减少配置维护，调试时只需验证一种格式

### 4. `_logger` 同样迁移

项目中 `zrag/api/exception_handler.py` 使用 `_logger`（带下划线前缀）作为日志变量名，其余 13 个文件使用 `logger`。`_logger` 的日志调用同样会被 JsonFormatter 处理，无需特殊适配。JsonFormatter 作用于 handler 级别，与被记录者使用的变量名无关。

### 5. 测试不受影响

- 单元测试中通过 `caplog` 或 `assertLogs` 捕获的日志记录可以通过 `record.getMessage()` 获取纯文本 message 内容进行断言，不依赖日志格式
- 若测试中使用了自定义的 `logging.Handler` 且未配置 JsonFormatter，则不受任何影响
- 集成测试若通过文件读取日志进行断言，需更新断言逻辑以适应 JSON 格式

### 6. 项目无 f-string 日志调用

经审查，项目中所有日志调用均使用 `%` 风格（如 `logger.info("xxx %s", value)`），无 f-string 风格的 `logger.info(f"...")` 调用。这意味着:

- `record.getMessage()` 可以正确获取格式化后的 message 字符串
- 日志记录是惰性求值的，不会因 f-string 求值导致不必要的性能开销
- 改造无需解决 f-string 被 `logging` 框架惰性求值绕过的问题

### 7. extra key 命名规范

通过 `logging.extra` 传入的自定义字段使用**全拼 snake_case** 命名:

```python
logger.info(
    "检索完成 conversation_id=%s results_count=%d",
    conversation_id,
    len(results),
    extra={"conversation_id": conversation_id, "results_count": len(results)},
)
```

- 避免缩写（如 `req_id` 改为 `request_id`，`conv_id` 改为 `conversation_id`）
- 与项目中已有的 code style（Python 变量命名）保持一致
- 便于在日志系统中的字段名统一可读

现有日志调用中已通过 message 字符串携带的结构化信息（如 `conversation_id=xxx`、`task_id=xxx`），在改造时应同时将其以 `extra` 的方式透出，使日志系统可直接按字段过滤，无需解析 message 字符串。

### 8. 两阶段合并为一次改动

原计划分两阶段改造:
- Phase 1: 实现 JsonFormatter，替换 settings.py 中的 formatter 配置
- Phase 2: 逐文件改造 logger 调用点，在关键位置添加 extra

实际合为一次改动提交。理由:
- 两阶段改动涉及的文件完全相同，分开反而增加 merge 冲突风险
- 同步修改可以让 commits 构成原子变更，方便回滚
- 减少上下文切换成本

## 改造范围

### 基础设施文件（2 个）

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `zrag/settings.py` | 修改 | 替换 LOGGING formatter 配置，引用 JsonFormatter |
| `zrag/utils/logging.py` | 新建 | JsonFormatter 类实现 |

### Logger 调用点文件（13 个，74 处调用）

| 文件 | 调用次数 | 说明 |
|------|:-------:|------|
| `zrag/apps.py` | 1 | 启动预加载日志 |
| `zrag/api/views.py` | 24 | 主要日志输出点 |
| `zrag/api/task_manager.py` | 13 | 任务生命周期日志 |
| `zrag/api/exception_handler.py` | 1 | 兜底异常日志（`_logger`） |
| `zrag/ingest/pipeline.py` | 4 | 摄入管线日志 |
| `zrag/ingest/sources/mac_notes.py` | 4 | macOS Notes 源日志 |
| `zrag/retrieval/retriever.py` | 9 | 检索过程日志 |
| `zrag/retrieval/query_rewriter.py` | 4 | 查询改写日志 |
| `zrag/retrieval/prompt_builder.py` | 2 | Prompt 构建日志 |
| `zrag/retrieval/conversation_summarizer.py` | 4 | 对话摘要日志 |
| `zrag/utils/compress.py` | 5 | 异步压缩日志 |
| `zrag/store/sqlite_store.py` | 4 | FTS5 检索和迁移日志 |
| `zrag/store/vector_store.py` | 1 | 向量检索日志 |

> 注: 调用次数统计基于 `grep -rn 'logger\.'` 结果，不包含注释行。

总计: **15 个文件**（2 新建/修改基础设施 + 13 调用点文件），约 **74 处调用点**需添加 extra 或确认无需修改。

## 输出示例

改造后日志输出示例:

```json
{
  "timestamp": "2026-06-18T02:30:00.123456+00:00",
  "level": "INFO",
  "logger": "zrag.api.views",
  "thread": 12345,
  "funcName": "add_message",
  "lineno": 469,
  "message": "[req=abc-123] 检索完成 conversation_id=conv-001 results_count=10",
  "request_id": "abc-123",
  "conversation_id": "conv-001",
  "results_count": 10
}
```

异常日志示例:

```json
{
  "timestamp": "2026-06-18T02:35:00.123456+00:00",
  "level": "ERROR",
  "logger": "zrag.api.exception_handler",
  "thread": 12346,
  "funcName": "handle",
  "lineno": 109,
  "message": "未预期的异常: Connection refused",
  "exception": {
    "type": "ConnectionRefusedError",
    "message": "Connection refused"
  }
}
```
