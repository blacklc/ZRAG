"""日志级别精确过滤器

提供 ExactLevelFilter，用于将日志记录限制到单个指定的日志级别。
配合 Django LOGGING 配置使用，实现不同级别日志写入不同文件。

@see settings.py LOGGING.filters
"""

import logging


class ExactLevelFilter(logging.Filter):
    """精确日志级别过滤器

    默认的 logging handler 级别是包容的（如 level=INFO 的 handler 也会收到
    WARNING、ERROR 记录）。本过滤器实现精确匹配，只放行指定级别的记录。

    用法示例（Django LOGGING 配置）:

        'filters': {
            'level_info': {
                '()': 'zrag.log_filter.ExactLevelFilter',
                'level': 'INFO',
            },
        },

    然后 handler 引用此 filter 即可只接收 INFO 级别的消息。

    @param level: 允许通过的日志级别名称 (DEBUG/INFO/WARNING/ERROR/CRITICAL)
    @type  level: str
    """

    def __init__(self, level: str):
        """构造 ExactLevelFilter

        @param level: 日志级别名称字符串
        @type  level: str
        """
        super().__init__()
        self._level = getattr(logging, level, logging.NOTSET)

    def filter(self, record: logging.LogRecord) -> bool:
        """判断日志记录是否匹配指定级别

        @param record: 日志记录对象
        @type  record: logging.LogRecord

        @return: 当 record.levelno 等于目标级别时返回 True
        @type:   bool
        """
        return record.levelno == self._level
