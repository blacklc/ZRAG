import json
import logging
from datetime import datetime, timezone, timedelta

# 北京时间 (UTC+8) 时区常量
_CHINA_TZ = timezone(timedelta(hours=8))

# logging.LogRecord 标准字段，不应透出到 extra
_STANDARD_FIELDS = frozenset({
    "args", "asctime", "created", "exc_info", "exc_text", "filename",
    "funcName", "levelname", "levelno", "lineno", "module", "msecs",
    "message", "msg", "name", "pathname", "process", "processName",
    "relativeCreated", "stack_info", "thread", "threadName",
})


class JsonFormatter(logging.Formatter):
    """JSON 格式日志格式化器

    将日志记录序列化为 JSON 字符串，每条日志一行。
    固定输出字段：timestamp, level, thread, logger, function, line, message
    额外字段：通过 extra= 传入的自定义字段自动提升到 JSON 顶层
    异常时自动追加 traceback 字段
    不可序列化的值降级为 str()
    """

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=_CHINA_TZ
            ).isoformat(),
            "level": record.levelname,
            "thread": record.thread,
            "logger": record.name,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
        }
        # 透出 extra 自定义字段（如 request_id、conversation_id）
        for key, value in record.__dict__.items():
            if key not in _STANDARD_FIELDS and not key.startswith("_"):
                log_obj[key] = value
        # 异常时追加 traceback 字段
        if record.exc_info:
            log_obj["traceback"] = self.formatException(record.exc_info)
        # 兜底：对不可序列化的值做 str() 降级
        try:
            return json.dumps(log_obj, ensure_ascii=False)
        except TypeError:
            for key in list(log_obj.keys()):
                try:
                    json.dumps({key: log_obj[key]}, ensure_ascii=False)
                except TypeError:
                    log_obj[key] = str(log_obj[key])
            return json.dumps(log_obj, ensure_ascii=False)
