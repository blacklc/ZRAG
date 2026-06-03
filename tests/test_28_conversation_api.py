"""切片 26-30 — 会话 API 端点测试

覆盖 ConversationViewSet 的五个端点:
- 切片 26: POST   /v1/conversations                  — 创建会话并触发 RAG 问答
- 切片 27: POST   /v1/conversations/{id}/messages    — 在已有会话中追加问答
- 切片 28: GET    /v1/conversations                  — 会话列表
- 切片 29: GET    /v1/conversations/{id}/messages    — 消息列表
- 切片 30: DELETE /v1/conversations/{id}             — 删除会话 (幂等)
"""

import json
from unittest import mock

import pytest
from django.test.client import RequestFactory
from rest_framework.renderers import JSONRenderer

from zrag.api.response import APIResponse
from zrag.api.views import ConversationViewSet
from zrag.models.retrieval import SearchResult
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
        view = ConversationViewSet.as_view(
            actions={'get': 'list'}, store=store, authentication_classes=[], throttle_classes=[],
        )
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
        view = ConversationViewSet.as_view(
            actions={'get': 'list'}, store=store, authentication_classes=[], throttle_classes=[],
        )
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
        view = ConversationViewSet.as_view(
            actions={'get': 'get_messages'}, store=store, authentication_classes=[], throttle_classes=[],
        )
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
        view = ConversationViewSet.as_view(
            actions={'get': 'get_messages'}, store=store, authentication_classes=[], throttle_classes=[],
        )
        request = factory.get('/v1/conversations/non-existent/messages')
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
        view = ConversationViewSet.as_view(
            actions={'delete': 'destroy'}, store=store, authentication_classes=[], throttle_classes=[],
        )
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
        view = ConversationViewSet.as_view(
            actions={'delete': 'destroy'}, store=store, authentication_classes=[], throttle_classes=[],
        )
        response = view(request, conversation_id='never-existed')
        _render(response)
        body = json.loads(response.content)
        assert response.status_code == 200
        assert body['Data']['deleted'] == 'never-existed'


class TestConversationCreate:
    """切片 26 — POST /v1/conversations 创建会话并执行 RAG 问答测试"""

    def test_create_conversation(self):
        """正常创建会话应返回 201 及会话信息"""
        store = SQLiteStore(':memory:')
        store.init_db()

        mock_retriever = mock.Mock()
        mock_retriever.hybrid_search.return_value = [
            SearchResult(
                chunk_id='c1', content='test content', doc_title='Doc1',
                source_id='src1', source_type='mac_notes', score=0.9,
            ),
        ]
        mock_llm = mock.Mock()
        mock_llm.chat.return_value = "Mock LLM reply"

        view = ConversationViewSet.as_view(
            actions={'post': 'create'},
            store=store,
            retriever=mock_retriever,
            llm_provider=mock_llm,
            authentication_classes=[],
            throttle_classes=[],
        )
        factory = RequestFactory()
        request = factory.post(
            '/v1/conversations',
            {"query": "test query"},
            content_type='application/json',
        )
        response = view(request)
        _render(response)
        body = json.loads(response.content)

        assert response.status_code == 201
        assert body['Message'] == 'success'
        assert 'conversation_id' in body['Data']
        assert body['Data']['title'] == 'test query'
        assert body['Data']['user_message']['role'] == 'user'
        assert body['Data']['user_message']['content'] == 'test query'
        assert body['Data']['assistant_response']['role'] == 'assistant'
        assert body['Data']['assistant_response']['content'] == 'Mock LLM reply'
        assert len(body['Data']['assistant_response']['sources']) == 1
        assert body['Data']['assistant_response']['sources'][0]['doc_title'] == 'Doc1'

    def test_create_conversation_saves_messages(self):
        """创建会话时应将 user 和 assistant 消息保存到数据库"""
        store = SQLiteStore(':memory:')
        store.init_db()

        mock_retriever = mock.Mock()
        mock_retriever.hybrid_search.return_value = [
            SearchResult(
                chunk_id='c1', content='content', doc_title='D',
                source_id='s1', source_type='mac_notes', score=0.9,
            ),
        ]
        mock_llm = mock.Mock()
        mock_llm.chat.return_value = "Mock reply"

        view = ConversationViewSet.as_view(
            actions={'post': 'create'},
            store=store,
            retriever=mock_retriever,
            llm_provider=mock_llm,
            authentication_classes=[],
            throttle_classes=[],
        )
        factory = RequestFactory()
        request = factory.post(
            '/v1/conversations',
            {"query": "test query"},
            content_type='application/json',
        )
        response = view(request)
        _render(response)
        body = json.loads(response.content)

        conversation_id = body['Data']['conversation_id']
        messages = store.fetch_all(
            "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY created_at",
            (conversation_id,),
        )
        assert len(messages) == 2
        assert messages[0]['role'] == 'user'
        assert messages[0]['content'] == 'test query'
        assert messages[1]['role'] == 'assistant'
        assert messages[1]['content'] == 'Mock reply'

    def test_create_conversation_llm_failure(self):
        """LLM 调用失败 (返回 None) 时应转换为 502 响应"""
        store = SQLiteStore(':memory:')
        store.init_db()

        mock_retriever = mock.Mock()
        mock_retriever.hybrid_search.return_value = [
            SearchResult(
                chunk_id='c1', content='content', doc_title='D',
                source_id='s1', source_type='mac_notes', score=0.9,
            ),
        ]
        mock_llm = mock.Mock()
        mock_llm.chat.return_value = None

        view = ConversationViewSet.as_view(
            actions={'post': 'create'},
            store=store,
            retriever=mock_retriever,
            llm_provider=mock_llm,
            authentication_classes=[],
            throttle_classes=[],
        )
        factory = RequestFactory()
        request = factory.post(
            '/v1/conversations',
            {"query": "test query"},
            content_type='application/json',
        )
        response = view(request)
        _render(response)
        body = json.loads(response.content)

        assert response.status_code == 502
        assert body['Message'] == 'LLM returned no response'
        assert body['ErrorCode'] == 'LLM-CALL-ERROR'

    def test_create_conversation_invalid_query(self):
        """query 为空时应返回 400"""
        store = SQLiteStore(':memory:')
        store.init_db()

        view = ConversationViewSet.as_view(
            actions={'post': 'create'},
            store=store,
            authentication_classes=[],
            throttle_classes=[],
        )
        factory = RequestFactory()
        request = factory.post(
            '/v1/conversations',
            {"query": ""},
            content_type='application/json',
        )
        response = view(request)
        _render(response)
        body = json.loads(response.content)

        assert response.status_code == 400
        assert body['ErrorCode'] == 'VALIDATION-ERROR'

    def test_create_conversation_title_truncation(self):
        """query 超过 50 字符时 title 应截取前 50 字符"""
        store = SQLiteStore(':memory:')
        store.init_db()

        long_query = "A" * 100

        mock_retriever = mock.Mock()
        mock_retriever.hybrid_search.return_value = [
            SearchResult(
                chunk_id='c1', content='content', doc_title='D',
                source_id='s1', source_type='mac_notes', score=0.9,
            ),
        ]
        mock_llm = mock.Mock()
        mock_llm.chat.return_value = "Mock reply"

        view = ConversationViewSet.as_view(
            actions={'post': 'create'},
            store=store,
            retriever=mock_retriever,
            llm_provider=mock_llm,
            authentication_classes=[],
            throttle_classes=[],
        )
        factory = RequestFactory()
        request = factory.post(
            '/v1/conversations',
            {"query": long_query},
            content_type='application/json',
        )
        response = view(request)
        _render(response)
        body = json.loads(response.content)

        assert response.status_code == 201
        assert body['Data']['title'] == 'A' * 50
        assert len(body['Data']['title']) == 50


class TestConversationAddMessage:
    """切片 27 — POST /v1/conversations/{id}/messages 在已有会话中追加问答测试"""

    def test_add_message(self):
        """在已有会话中追加消息应返回 201 及问答信息"""
        store = SQLiteStore(':memory:')
        store.init_db()
        store.execute(
            "INSERT INTO conversations (id, title) VALUES (?, ?)",
            ('conv-27', 'Test Conv'),
        )

        mock_retriever = mock.Mock()
        mock_retriever.hybrid_search.return_value = [
            SearchResult(
                chunk_id='c1', content='follow-up content', doc_title='Doc1',
                source_id='src1', source_type='mac_notes', score=0.85,
            ),
        ]
        mock_llm = mock.Mock()
        mock_llm.chat.return_value = "Follow-up reply"

        view = ConversationViewSet.as_view(
            actions={'post': 'add_message'},
            store=store,
            retriever=mock_retriever,
            llm_provider=mock_llm,
            authentication_classes=[],
            throttle_classes=[],
        )
        factory = RequestFactory()
        request = factory.post(
            '/v1/conversations/conv-27/messages',
            {"query": "follow-up"},
            content_type='application/json',
        )
        response = view(request, conversation_id='conv-27')
        _render(response)
        body = json.loads(response.content)

        assert response.status_code == 201
        assert body['Data']['conversation_id'] == 'conv-27'
        assert body['Data']['user_message']['role'] == 'user'
        assert body['Data']['user_message']['content'] == 'follow-up'
        assert body['Data']['assistant_response']['role'] == 'assistant'
        assert body['Data']['assistant_response']['content'] == 'Follow-up reply'
        assert len(body['Data']['assistant_response']['sources']) == 1

    def test_add_message_not_found(self):
        """不存在的会话 ID 应返回 404"""
        store = SQLiteStore(':memory:')
        store.init_db()

        view = ConversationViewSet.as_view(
            actions={'post': 'add_message'},
            store=store,
            authentication_classes=[],
            throttle_classes=[],
        )
        factory = RequestFactory()
        request = factory.post(
            '/v1/conversations/non-existent/messages',
            {"query": "hello"},
            content_type='application/json',
        )
        response = view(request, conversation_id='non-existent')
        _render(response)
        body = json.loads(response.content)

        assert response.status_code == 404
        assert 'non-existent' in body['Message']
        assert body['ErrorCode'] == 'NOT-FOUND'

    def test_add_message_carries_history(self):
        """追加消息时历史消息应被传入 LLM 调用"""
        store = SQLiteStore(':memory:')
        store.init_db()
        store.execute(
            "INSERT INTO conversations (id, title) VALUES (?, ?)",
            ('conv-hist', 'History Test'),
        )
        store.execute(
            "INSERT INTO messages (id, conversation_id, role, content, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ('m1', 'conv-hist', 'user', 'first question', '2025-01-01T00:00:00'),
        )
        store.execute(
            "INSERT INTO messages (id, conversation_id, role, content, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ('m2', 'conv-hist', 'assistant', 'first answer', '2025-01-01T00:01:00'),
        )

        mock_retriever = mock.Mock()
        mock_retriever.hybrid_search.return_value = [
            SearchResult(
                chunk_id='c1', content='some content', doc_title='D',
                source_id='s1', source_type='mac_notes', score=0.9,
            ),
        ]
        mock_llm = mock.Mock()
        mock_llm.chat.return_value = "follow-up answer"

        view = ConversationViewSet.as_view(
            actions={'post': 'add_message'},
            store=store,
            retriever=mock_retriever,
            llm_provider=mock_llm,
            authentication_classes=[],
            throttle_classes=[],
        )
        factory = RequestFactory()
        request = factory.post(
            '/v1/conversations/conv-hist/messages',
            {"query": "follow-up question"},
            content_type='application/json',
        )
        response = view(request, conversation_id='conv-hist')
        _render(response)
        body = json.loads(response.content)

        assert response.status_code == 201

        # 验证 LLM 调用时历史消息被传入
        call_args = mock_llm.chat.call_args
        full_messages = call_args[0][0]

        # full_messages 结构: [system, history_user, history_assistant, new_user]
        assert len(full_messages) == 4
        # 第 0 条为 RAG system message
        assert full_messages[0]['role'] == 'system'
        # 第 1 条为历史 user 消息
        assert full_messages[1]['role'] == 'user'
        assert full_messages[1]['content'] == 'first question'
        # 第 2 条为历史 assistant 消息
        assert full_messages[2]['role'] == 'assistant'
        assert full_messages[2]['content'] == 'first answer'
        # 第 3 条为新用户 query
        assert full_messages[3]['role'] == 'user'
        assert full_messages[3]['content'] == 'follow-up question'

    def test_add_message_saves_messages(self):
        """追加消息时应将 user 和 assistant 消息保存到数据库"""
        store = SQLiteStore(':memory:')
        store.init_db()
        store.execute(
            "INSERT INTO conversations (id, title) VALUES (?, ?)",
            ('conv-save', 'Save Test'),
        )

        mock_retriever = mock.Mock()
        mock_retriever.hybrid_search.return_value = [
            SearchResult(
                chunk_id='c1', content='content', doc_title='D',
                source_id='s1', source_type='mac_notes', score=0.9,
            ),
        ]
        mock_llm = mock.Mock()
        mock_llm.chat.return_value = "saved reply"

        view = ConversationViewSet.as_view(
            actions={'post': 'add_message'},
            store=store,
            retriever=mock_retriever,
            llm_provider=mock_llm,
            authentication_classes=[],
            throttle_classes=[],
        )
        factory = RequestFactory()
        request = factory.post(
            '/v1/conversations/conv-save/messages',
            {"query": "save this"},
            content_type='application/json',
        )
        response = view(request, conversation_id='conv-save')
        _render(response)
        body = json.loads(response.content)

        assert response.status_code == 201

        # 验证数据库中新消息已保存
        messages = store.fetch_all(
            "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY created_at",
            ('conv-save',),
        )
        assert len(messages) == 2
        assert messages[0]['role'] == 'user'
        assert messages[0]['content'] == 'save this'
        assert messages[1]['role'] == 'assistant'
        assert messages[1]['content'] == 'saved reply'

    def test_add_message_llm_failure(self):
        """LLM 调用失败 (返回 None) 时应转换为 502 响应"""
        store = SQLiteStore(':memory:')
        store.init_db()
        store.execute(
            "INSERT INTO conversations (id, title) VALUES (?, ?)",
            ('conv-fail', 'Fail Test'),
        )

        mock_retriever = mock.Mock()
        mock_retriever.hybrid_search.return_value = [
            SearchResult(
                chunk_id='c1', content='content', doc_title='D',
                source_id='s1', source_type='mac_notes', score=0.9,
            ),
        ]
        mock_llm = mock.Mock()
        mock_llm.chat.return_value = None

        view = ConversationViewSet.as_view(
            actions={'post': 'add_message'},
            store=store,
            retriever=mock_retriever,
            llm_provider=mock_llm,
            authentication_classes=[],
            throttle_classes=[],
        )
        factory = RequestFactory()
        request = factory.post(
            '/v1/conversations/conv-fail/messages',
            {"query": "will fail"},
            content_type='application/json',
        )
        response = view(request, conversation_id='conv-fail')
        _render(response)
        body = json.loads(response.content)

        assert response.status_code == 502
        assert body['Message'] == 'LLM returned no response'
        assert body['ErrorCode'] == 'LLM-CALL-ERROR'
