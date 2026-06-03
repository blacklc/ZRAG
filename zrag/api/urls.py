"""API 路由配置

汇总所有 API 端点的 URL 映射。
"""
from django.urls import re_path

from zrag.api.views import ConversationViewSet, DocumentViewSet
from zrag.api.health import HealthViewSet

conversation_urls = [
    re_path(
        r'^v1/conversations$',
        ConversationViewSet.as_view({'get': 'list', 'post': 'create'}),
    ),
    re_path(
        r'^v1/conversations/(?P<conversation_id>[^/]+)/messages$',
        ConversationViewSet.as_view({'get': 'get_messages', 'post': 'add_message'}),
    ),
    re_path(
        r'^v1/conversations/(?P<conversation_id>[^/]+)$',
        ConversationViewSet.as_view({'delete': 'destroy'}),
    ),
]

document_urls = [
    re_path(r'^v1/documents/ingest$', DocumentViewSet.as_view({'post': 'ingest'})),
]

source_urls = [
    re_path(r'^v1/sources$', DocumentViewSet.as_view({'get': 'list_sources'})),
]

health_urls = [
    re_path(r'^v1/health/live$', HealthViewSet.as_view({'get': 'live'})),
    re_path(r'^v1/health/ready$', HealthViewSet.as_view({'get': 'ready'})),
]

urlpatterns = conversation_urls + document_urls + source_urls + health_urls
