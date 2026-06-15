"""测试切片 25 — ingest API (异步) + task 管理 + source 列表

测试内容:
  - POST /v1/documents/ingest -> 返回 202 + task_id (异步)
  - GET /v1/sources -> 返回 source 列表
  - GET /v1/sources/available -> 返回已注册数据源类型列表
  - GET /v1/ingest/{id}/status -> 返回任务状态
  - POST /v1/ingest/{id}/cancel -> 取消任务
  - 缺少 API key -> 401
  - 请求体校验 -> 无效参数返回 400
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from django.test.utils import override_settings

from contextlib import contextmanager

from zrag.api.task_manager import IngestTask, TaskStatus
from zrag.embed.base import EmbeddingModel
from zrag.ingest.chunking.base import ChunkingStrategy


@contextmanager
def _mock_pipeline_deps():
    """mock 所有 Pipeline 依赖（避免 HuggingFace 模型下载）"""
    with (
        patch("zrag.embed.local.get_embedder") as mock_emb,
        patch("zrag.ingest.chunking.registry.get_chunker") as mock_chunk,
        patch("zrag.store.vector_store.get_chroma_store") as mock_chroma,
    ):
        mock_emb.return_value = MagicMock(spec=EmbeddingModel)
        mock_chunk.return_value = MagicMock(spec=ChunkingStrategy)
        mock_chroma.return_value = MagicMock()
        yield

TEST_API_KEY = "test-api-key-for-slice-25"


class TestIngestAPI:
    """POST /v1/documents/ingest API 测试类"""

    # ----------------------------------------------------------
    # 1. POST /v1/documents/ingest -> 202 + task_id
    # ----------------------------------------------------------

    @override_settings(ZRAG_API_KEY=TEST_API_KEY)
    @patch("zrag.api.views.TaskManager")
    def test_ingest_returns_task(self, mock_task_manager_cls, client):
        """正常摄入请求返回 202 和 task_id"""
        with _mock_pipeline_deps():
            mock_manager = MagicMock()
            mock_task = MagicMock()
            mock_task.id = "fake-task-id-001"
            mock_task.status = type('_', (), {'value': 'pending'})()
            mock_manager.create_task.return_value = mock_task
            mock_task_manager_cls.get_instance.return_value = mock_manager

            resp = client.post(
                "/v1/documents/ingest",
                data=json.dumps({"source_type": "mac_notes", "full": False}),
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {TEST_API_KEY}",
            )

            assert resp.status_code == 202
            body = resp.json()
            assert body["Message"] == "success"
            assert body["Data"]["task_id"] == "fake-task-id-001"
            assert body["Data"]["status"] == "pending"
            assert "RequestID" in body

    @override_settings(ZRAG_API_KEY=TEST_API_KEY)
    @patch("zrag.api.views.TaskManager")
    def test_ingest_with_full(self, mock_task_manager_cls, client):
        """full=True 时 task_type 为 full"""
        with _mock_pipeline_deps():
            mock_manager = MagicMock()
            mock_task = MagicMock()
            mock_task.id = "fake-task-id-002"
            mock_task.status = type('_', (), {'value': 'pending'})()
            mock_manager.create_task.return_value = mock_task
            mock_task_manager_cls.get_instance.return_value = mock_manager

            resp = client.post(
                "/v1/documents/ingest",
                data=json.dumps({"source_type": "mac_notes", "full": True}),
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {TEST_API_KEY}",
            )

            assert resp.status_code == 202
            body = resp.json()
            assert body["Data"]["task_id"] == "fake-task-id-002"
            mock_manager.create_task.assert_called_once_with(task_type="full")

    @override_settings(ZRAG_API_KEY=TEST_API_KEY)
    @patch("zrag.api.views.TaskManager")
    def test_ingest_default_full_false(self, mock_task_manager_cls, client):
        """未指定 full 时默认为 False"""
        with _mock_pipeline_deps():
            mock_manager = MagicMock()
            mock_task = MagicMock()
            mock_task.id = "fake-task-id-003"
            mock_task.status = type('_', (), {'value': 'pending'})()
            mock_manager.create_task.return_value = mock_task
            mock_task_manager_cls.get_instance.return_value = mock_manager

            resp = client.post(
                "/v1/documents/ingest",
                data=json.dumps({"source_type": "mac_notes"}),
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {TEST_API_KEY}",
            )

            assert resp.status_code == 202
            mock_manager.create_task.assert_called_once_with(task_type="incremental")

    # ----------------------------------------------------------
    # 2. GET /v1/sources -> source 列表
    # ----------------------------------------------------------

    @override_settings(ZRAG_API_KEY=TEST_API_KEY)
    @patch("zrag.api.views.SQLiteStore")
    def test_list_sources_empty(self, mock_store_cls, client):
        """空库时返回空 sources 列表"""
        mock_store = MagicMock()
        mock_store.fetch_all.return_value = []
        mock_store_cls.return_value = mock_store

        resp = client.get(
            "/v1/sources",
            HTTP_AUTHORIZATION=f"Bearer {TEST_API_KEY}",
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["Message"] == "success"
        assert body["Data"]["sources"] == []
        assert "RequestID" in body

    @override_settings(ZRAG_API_KEY=TEST_API_KEY)
    @patch("zrag.api.views.SQLiteStore")
    def test_list_sources_with_data(self, mock_store_cls, client):
        """有数据时返回 source 统计列表"""
        mock_store = MagicMock()
        mock_store.fetch_all.return_value = [
            {"source_type": "mac_notes", "doc_count": 5, "last_imported": "2026-01-15 10:00:00"},
            {"source_type": "local_file", "doc_count": 3, "last_imported": "2026-01-14 09:00:00"},
        ]
        mock_store_cls.return_value = mock_store

        resp = client.get(
            "/v1/sources",
            HTTP_AUTHORIZATION=f"Bearer {TEST_API_KEY}",
        )

        assert resp.status_code == 200
        body = resp.json()
        sources = body["Data"]["sources"]
        assert len(sources) == 2
        assert sources[0]["source_type"] == "mac_notes"
        assert sources[0]["doc_count"] == 5
        assert sources[1]["source_type"] == "local_file"
        assert sources[1]["doc_count"] == 3

    # ----------------------------------------------------------
    # 3. 缺少 API key -> 401
    # ----------------------------------------------------------

    @override_settings(ZRAG_API_KEY=TEST_API_KEY)
    def test_ingest_missing_api_key(self, client):
        """缺少 Authorization header 时返回 401"""
        resp = client.post(
            "/v1/documents/ingest",
            data=json.dumps({"source_type": "mac_notes"}),
            content_type="application/json",
        )

        assert resp.status_code == 401
        body = resp.json()
        assert "Message" in body

    @override_settings(ZRAG_API_KEY=TEST_API_KEY)
    def test_ingest_invalid_api_key(self, client):
        """无效 API Key 时返回 401"""
        resp = client.post(
            "/v1/documents/ingest",
            data=json.dumps({"source_type": "mac_notes"}),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer invalid-key-99999",
        )

        assert resp.status_code == 401

    @override_settings(ZRAG_API_KEY=TEST_API_KEY)
    def test_list_sources_missing_api_key(self, client):
        """GET /v1/sources 缺少 API Key 时返回 401"""
        resp = client.get("/v1/sources")
        assert resp.status_code == 401

    # ----------------------------------------------------------
    # 4. 请求体校验 -> 400
    # ----------------------------------------------------------

    @override_settings(ZRAG_API_KEY=TEST_API_KEY)
    def test_ingest_invalid_json(self, client):
        """无效 JSON 返回 400"""
        resp = client.post(
            "/v1/documents/ingest",
            data="not-json",
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {TEST_API_KEY}",
        )

        assert resp.status_code == 400

    @override_settings(ZRAG_API_KEY=TEST_API_KEY)
    def test_ingest_invalid_field_type(self, client):
        """字段类型错误返回 400"""
        resp = client.post(
            "/v1/documents/ingest",
            data=json.dumps({"source_type": 123}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {TEST_API_KEY}",
        )

        assert resp.status_code == 400
        body = resp.json()
        assert "Message" in body

    @override_settings(ZRAG_API_KEY=TEST_API_KEY)
    def test_ingest_unknown_source_type(self, client):
        """未知 source_type 返回 400"""
        resp = client.post(
            "/v1/documents/ingest",
            data=json.dumps({"source_type": "unknown_source"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {TEST_API_KEY}",
        )

        assert resp.status_code == 400

    # ----------------------------------------------------------
    # 5. GET /v1/sources/available -> 200 + sources list
    # ----------------------------------------------------------

    @override_settings(ZRAG_API_KEY=TEST_API_KEY)
    def test_list_available_sources(self, client):
        """GET /v1/sources/available 返回已注册的数据源类型列表"""
        resp = client.get(
            "/v1/sources/available",
            HTTP_AUTHORIZATION=f"Bearer {TEST_API_KEY}",
        )

        assert resp.status_code == 200
        body = resp.json()
        assert "sources" in body["Data"]
        # 至少包含 mac_notes
        assert "mac_notes" in body["Data"]["sources"]

    # ----------------------------------------------------------
    # 6. GET /v1/ingest/{id}/status -> task status
    # ----------------------------------------------------------

    @override_settings(ZRAG_API_KEY=TEST_API_KEY)
    @patch("zrag.api.views.TaskManager")
    def test_ingest_task_status(self, mock_task_manager_cls, client):
        """查询存在的任务时返回 200 + 任务详情"""
        mock_task = IngestTask(
            id="task-status-001",
            task_type="full",
            status=TaskStatus.PROCESSING,
            total=10,
            processed=5,
            created_at="2026-06-10T10:00:00",
            updated_at="2026-06-10T10:05:00",
        )
        mock_manager = MagicMock()
        mock_manager.get_task.return_value = mock_task
        mock_manager.to_dict.return_value = {
            "task_id": "task-status-001",
            "task_type": "full",
            "status": "processing",
            "total": 10,
            "processed": 5,
            "created_at": "2026-06-10T10:00:00",
            "updated_at": "2026-06-10T10:05:00",
        }
        mock_task_manager_cls.get_instance.return_value = mock_manager

        resp = client.get(
            "/v1/ingest/task-status-001/status",
            HTTP_AUTHORIZATION=f"Bearer {TEST_API_KEY}",
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["Data"]["task_id"] == "task-status-001"
        assert body["Data"]["status"] == "processing"
        assert body["Data"]["total"] == 10
        assert body["Data"]["processed"] == 5

    @override_settings(ZRAG_API_KEY=TEST_API_KEY)
    @patch("zrag.api.views.TaskManager")
    def test_ingest_task_status_not_found(self, mock_task_manager_cls, client):
        """查询不存在的任务时返回 404"""
        mock_manager = MagicMock()
        mock_manager.get_task.return_value = None
        mock_task_manager_cls.get_instance.return_value = mock_manager

        resp = client.get(
            "/v1/ingest/non-existent-task/status",
            HTTP_AUTHORIZATION=f"Bearer {TEST_API_KEY}",
        )

        assert resp.status_code == 404
        body = resp.json()
        assert "not found" in body["Message"].lower()

    # ----------------------------------------------------------
    # 7. POST /v1/ingest/{id}/cancel -> cancel task
    # ----------------------------------------------------------

    @override_settings(ZRAG_API_KEY=TEST_API_KEY)
    @patch("zrag.api.views.TaskManager")
    def test_ingest_task_cancel(self, mock_task_manager_cls, client):
        """取消存在的任务时返回 200"""
        mock_task = IngestTask(
            id="task-cancel-001",
            task_type="full",
            status=TaskStatus.PROCESSING,
        )
        mock_manager = MagicMock()
        mock_manager.get_task.return_value = mock_task
        mock_manager.to_dict.return_value = {
            "task_id": "task-cancel-001",
            "task_type": "full",
            "status": "cancelled",
        }
        mock_task_manager_cls.get_instance.return_value = mock_manager

        resp = client.post(
            "/v1/ingest/task-cancel-001/cancel",
            HTTP_AUTHORIZATION=f"Bearer {TEST_API_KEY}",
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["Data"]["task_id"] == "task-cancel-001"
        # 验证 cancel_task 被调用
        mock_manager.cancel_task.assert_called_once_with("task-cancel-001")

    @override_settings(ZRAG_API_KEY=TEST_API_KEY)
    @patch("zrag.api.views.TaskManager")
    def test_ingest_task_cancel_not_found(self, mock_task_manager_cls, client):
        """取消不存在的任务时返回 404"""
        mock_manager = MagicMock()
        mock_manager.get_task.return_value = None
        mock_task_manager_cls.get_instance.return_value = mock_manager

        resp = client.post(
            "/v1/ingest/non-existent-task/cancel",
            HTTP_AUTHORIZATION=f"Bearer {TEST_API_KEY}",
        )

        assert resp.status_code == 404
        body = resp.json()
        assert "not found" in body["Message"].lower()

    # ----------------------------------------------------------
    # 8. Auth check for task endpoints
    # ----------------------------------------------------------

    @override_settings(ZRAG_API_KEY=TEST_API_KEY)
    def test_task_status_missing_api_key(self, client):
        """查询任务状态缺少 API Key 时返回 401"""
        resp = client.get("/v1/ingest/some-task/status")
        assert resp.status_code == 401

    @override_settings(ZRAG_API_KEY=TEST_API_KEY)
    def test_task_cancel_missing_api_key(self, client):
        """取消任务缺少 API Key 时返回 401"""
        resp = client.post("/v1/ingest/some-task/cancel")
        assert resp.status_code == 401

    @override_settings(ZRAG_API_KEY=TEST_API_KEY)
    def test_available_sources_missing_api_key(self, client):
        """GET /v1/sources/available 缺少 API Key 时返回 401"""
        resp = client.get("/v1/sources/available")
        assert resp.status_code == 401


class TestIngestSerializer:
    """IngestSerializer 序列化器测试类"""

    def test_valid_data(self):
        """合法数据序列化"""
        from zrag.api.serializers import IngestSerializer
        serializer = IngestSerializer(data={"source_type": "mac_notes", "full": True})
        assert serializer.is_valid()
        assert serializer.validated_data["source_type"] == "mac_notes"
        assert serializer.validated_data["full"] is True

    def test_default_values(self):
        """未传参时使用默认值"""
        from zrag.api.serializers import IngestSerializer
        serializer = IngestSerializer(data={})
        assert serializer.is_valid()
        assert serializer.validated_data["source_type"] is None
        assert serializer.validated_data["full"] is False

    def test_invalid_source_type_type(self):
        """source_type 类型错误（列表类型不被 CharField 接受）"""
        from zrag.api.serializers import IngestSerializer
        serializer = IngestSerializer(data={"source_type": ["item1", "item2"]})
        assert not serializer.is_valid()
        assert "source_type" in serializer.errors

    def test_invalid_full_type(self):
        """full 类型错误"""
        from zrag.api.serializers import IngestSerializer
        serializer = IngestSerializer(data={"full": "not-a-bool"})
        assert not serializer.is_valid()
        assert "full" in serializer.errors
