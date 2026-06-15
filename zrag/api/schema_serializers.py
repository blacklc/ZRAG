"""Swagger Schema Serializers

为 drf-spectacular 提供请求/响应数据结构定义，
使 Swagger UI 能展示完整的请求体和响应体 Schema。
"""
from drf_spectacular.utils import OpenApiExample, extend_schema_serializer
from rest_framework import serializers


# ---- 通用 ----
class ErrorResponseSerializer(serializers.Serializer):
    Message = serializers.CharField(help_text="错误描述")
    Data = serializers.CharField(allow_null=True, default=None)
    RequestID = serializers.CharField(help_text="请求追踪 ID")
    ErrorCode = serializers.CharField(help_text="业务错误码")


# ---- 会话 ----
class ConversationItemSerializer(serializers.Serializer):
    id = serializers.CharField(help_text="会话 ID")
    title = serializers.CharField(help_text="会话标题")
    created_at = serializers.CharField(help_text="创建时间 (ISO 8601)")
    last_msg_at = serializers.CharField(help_text="最近消息时间", allow_null=True)


class ConversationListResponseSerializer(serializers.Serializer):
    total = serializers.IntegerField(help_text="会话总数")
    conversations = ConversationItemSerializer(many=True)


# ---- 消息 ----
class SourceItemSerializer(serializers.Serializer):
    doc_title = serializers.CharField(help_text="来源文档标题")
    source_id = serializers.CharField(help_text="来源 ID")
    source_type = serializers.CharField(help_text="来源类型")
    score = serializers.FloatField(help_text="相似度分数")


class MessageItemSerializer(serializers.Serializer):
    id = serializers.CharField(help_text="消息 ID")
    role = serializers.CharField(help_text="角色: user / assistant")
    content = serializers.CharField(help_text="消息内容 (Markdown)")
    created_at = serializers.CharField(help_text="创建时间 (ISO 8601)")
    sources = SourceItemSerializer(many=True, required=False, help_text="来源引用 (仅 assistant)")


class MessageListResponseSerializer(serializers.Serializer):
    conversation_id = serializers.CharField(help_text="会话 ID")
    messages = MessageItemSerializer(many=True)


class CreateConversationResponseSerializer(serializers.Serializer):
    conversation_id = serializers.CharField(help_text="新创建的会话 ID")
    title = serializers.CharField(help_text="会话标题 (query 前 50 字符)")
    user_message = MessageItemSerializer()
    assistant_response = MessageItemSerializer()


class AddMessageResponseSerializer(serializers.Serializer):
    conversation_id = serializers.CharField(help_text="会话 ID")
    user_message = MessageItemSerializer()
    assistant_response = MessageItemSerializer()


class DeleteConversationResponseSerializer(serializers.Serializer):
    deleted = serializers.CharField(help_text="已删除的会话 ID")


# ---- 文档摄入 ----
class IngestionErrorSerializer(serializers.Serializer):
    source_id = serializers.CharField(help_text="出错来源 ID")
    error = serializers.CharField(help_text="错误描述")


class IngestionReportSerializer(serializers.Serializer):
    total = serializers.IntegerField(help_text="处理总数")
    new = serializers.IntegerField(help_text="新增数")
    updated = serializers.IntegerField(help_text="更新数")
    skipped = serializers.IntegerField(help_text="跳过数")
    failed = serializers.IntegerField(help_text="失败数")
    errors = IngestionErrorSerializer(many=True, help_text="错误详情列表")


# ---- 来源 ----
class SourceSummarySerializer(serializers.Serializer):
    source_type = serializers.CharField(help_text="来源类型")
    doc_count = serializers.IntegerField(help_text="文档数量")
    last_imported = serializers.CharField(help_text="最后摄入时间", allow_null=True)


class SourceListResponseSerializer(serializers.Serializer):
    sources = SourceSummarySerializer(many=True)


# ---- 摄入任务 ----
class AvailableSourcesResponseSerializer(serializers.Serializer):
    sources = serializers.ListField(
        child=serializers.CharField(), help_text="已注册的数据源类型列表"
    )


class TaskCreateResponseSerializer(serializers.Serializer):
    task_id = serializers.CharField(help_text="任务 ID")
    status = serializers.CharField(help_text="任务状态")


class TaskStatusResponseSerializer(serializers.Serializer):
    task_id = serializers.CharField(help_text="任务 ID")
    task_type = serializers.CharField(help_text="任务类型: full | incremental")
    status = serializers.CharField(help_text="任务状态: pending | waiting | processing | done | cancelled | failed")
    total = serializers.IntegerField(help_text="文档总数")
    processed = serializers.IntegerField(help_text="已处理数")
    created_at = serializers.CharField(help_text="创建时间")
    updated_at = serializers.CharField(help_text="更新时间")
