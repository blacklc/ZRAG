"""切片 28-30 — 会话 API 端点测试

覆盖 ConversationViewSet 的三个端点:
- 切片 28: GET /v1/conversations — 会话列表
- 切片 29: GET /v1/conversations/{id}/messages — 消息列表
- 切片 30: DELETE /v1/conversations/{id} — 删除会话 (幂等)
"""

import json

import pytest
from django.test.client import RequestFactory
from rest_framework.renderers import JSONRenderer

from zrag.api.response import APIResponse
from zrag.api.views import ConversationViewSet
from zrag.store.sqlite_store import SQLiteStore


def _render(response):
    """手动渲染 DRF Response 对象以便断言 response.data

    @param response: DRF Response 对象
    @type  response: rest_framework.response.Response
    """
    response.accepted_renderer = JSONRenderer()
    response.accepted_media_type = "application/json"
    response.renderer_context = {}
    response.render()


class TestConversationList:
    """切片 28 — GET /v1/conversations 会话列表测试"""

    def test_list_empty(self):
        """空会话列表应返回 total=0 和空列表"""
        store = SQLiteStore(':memory:')
        store.init_db()
        view = ConversationViewSet.as_view(actions={'get': 'list'}, store=store)
        factory = RequestFactory()
        request = factory.get('/v1/conversations')
        response = view(request)
        _render(response)
        body = json.loads(response.content)
        assert response.status_code == 200
        assert body['Data']['total'] == 0
        assert body['Data']['conversations'] == []

    def test_list_with_data(self):
        """有会话时应返回会话列表并按最近消息倒序"""
        store = SQLiteStore(':memory:')
        store.init_db()
        store.execute(
            "INSERT INTO conversations (id, title, created_at) VALUES (?, ?, datetime('now', '-1 day'))",
            ('conv-a', 'Older'),
        )
        store.execute(
            "INSERT INTO conversations (id, title, created_at) VALUES (?, ?, datetime('now'))",
            ('conv-b', 'Newer'),
        )
        # conv-b 有消息, conv-a 无消息
        store.execute(
            "INSERT INTO messages (id, conversation_id, role, content, created_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            ('msg-1', 'conv-b', 'user', 'hello'),
        )

        factory = RequestFactory()
        request = factory.get('/v1/conversations')
        view = ConversationViewSet.as_view(actions={'get': 'list'}, store=store)
        response = view(request)
        _render(response)
        body = json.loads(response.content)
        assert response.status_code == 200
        assert body['Data']['total'] == 2
        # conv-b 有最近消息, 应排在最前
        assert body['Data']['conversations'][0]['id'] == 'conv-b'
        assert body['Data']['conversations'][1]['id'] == 'conv-a'


class TestConversationMessages:
    """切片 29 — GET /v1/conversations/{id}/messages 消息列表测试"""

    def test_get_messages(self):
        """获取指定会话的消息列表应返回按时间正序的消息"""
        store = SQLiteStore(':memory:')
        store.init_db()
        store.execute(
            "INSERT INTO conversations (id, title) VALUES (?, ?)",
            ('conv-1', 'Test'),
        )
        store.execute(
            "INSERT INTO messages (id, conversation_id, role, content, created_at) "
            "VALUES (?, ?, ?, ?, datetime('now', '+1 minute'))",
            ('msg-2', 'conv-1', 'assistant', 'world',),
        )
        store.execute(
            "INSERT INTO messages (id, conversation_id, role, content, created_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            ('msg-1', 'conv-1', 'user', 'hello'),
        )

        factory = RequestFactory()
        request = factory.get('/v1/conversations/conv-1/messages')
        view = ConversationViewSet.as_view(actions={'get': 'get_messages'}, store=store)
        response = view(request, conversation_id='conv-1')
        _render(response)
        body = json.loads(response.content)
        assert response.status_code == 200
        assert body['Data']['conversation_id'] == 'conv-1'
        assert len(body['Data']['messages']) == 2
        # 按 created_at 正序: msg-1(user/hello) 在前, msg-2(assistant/world) 在后
        assert body['Data']['messages'][0]['id'] == 'msg-1'
        assert body['Data']['messages'][1]['id'] == 'msg-2'

    def test_get_messages_not_found(self):
        """不存在的会话 ID 应返回 404"""
        store = SQLiteStore(':memory:')
        store.init_db()

        factory = RequestFactory()
        request = factory.get('/v1/conversations/non-existent/messages')
        view = ConversationViewSet.as_view(actions={'get': 'get_messages'}, store=store)
        response = view(request, conversation_id='non-existent')
        _render(response)
        body = json.loads(response.content)
        assert response.status_code == 404
        assert body['Message'] == 'conversation not found'


class TestConversationDelete:
    """切片 30 — DELETE /v1/conversations/{id} 删除测试"""

    def test_delete(self):
        """删除会话应同时清除其所有消息"""
        store = SQLiteStore(':memory:')
        store.init_db()
        store.execute(
            "INSERT INTO conversations (id, title) VALUES (?, ?)",
            ('conv-del', 'To Delete'),
        )
        store.execute(
            "INSERT INTO messages (id, conversation_id, role, content) "
            "VALUES (?, ?, ?, ?)",
            ('msg-del', 'conv-del', 'user', 'bye'),
        )

        factory = RequestFactory()
        request = factory.delete('/v1/conversations/conv-del')
        view = ConversationViewSet.as_view(actions={'delete': 'destroy'}, store=store)
        response = view(request, conversation_id='conv-del')
        _render(response)
        body = json.loads(response.content)
        assert response.status_code == 200
        assert body['Data']['deleted'] == 'conv-del'
        # 验证会话和消息已被删除
        conv = store.fetch_one("SELECT id FROM conversations WHERE id = ?", ('conv-del',))
        assert conv is None
        msgs = store.fetch_all("SELECT id FROM messages WHERE conversation_id = ?", ('conv-del',))
        assert len(msgs) == 0

    def test_delete_idempotent(self):
        """删除不存在的会话也应返回成功 (幂等性)"""
        store = SQLiteStore(':memory:')
        store.init_db()

        factory = RequestFactory()
        request = factory.delete('/v1/conversations/never-existed')
        view = ConversationViewSet.as_view(actions={'delete': 'destroy'}, store=store)
        response = view(request, conversation_id='never-existed')
        _render(response)
        body = json.loads(response.content)
        assert response.status_code == 200
        assert body['Data']['deleted'] == 'never-existed'
