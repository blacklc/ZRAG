"""ZRAG API 序列化器

提供请求参数校验的 DRF Serializer 定义。
"""

from rest_framework import serializers


class IngestSerializer(serializers.Serializer):
    """摄入请求参数校验序列化器

    校验 POST /v1/documents/ingest 请求体中的参数。

    @param source_type: 来源类型, 如 "mac_notes", default None 表示使用默认来源
    @type  source_type: str, optional
    @param full: 是否全量导入, default False
    @type  full: bool, optional
    """
    source_type = serializers.CharField(
        max_length=100, default=None, required=False, allow_null=True,
    )
    full = serializers.BooleanField(default=False, required=False)


class ConversationQuerySerializer(serializers.Serializer):
    """会话/消息查询请求参数校验序列化器

    校验 POST /v1/conversations 和 POST /v1/conversations/{id}/messages
    请求体中的参数。

    @param query: 用户查询文本, 最长 2000 字符
    @type  query: str
    """
    query = serializers.CharField(
        max_length=2000, required=True, allow_blank=False,
    )
