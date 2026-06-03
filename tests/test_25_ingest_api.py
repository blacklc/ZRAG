"""测试切片 25 — POST /v1/documents/ingest + GET /v1/sources

测试内容:
  - POST /v1/documents/ingest -> 返回 200 + IngestReport
  - GET /v1/sources -> 返回 source 列表
  - 缺少 API key -> 401
  - 请求体校验 -> 无效参数返回 400
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from django.test.utils import override_settings

from zrag.ingest.pipeline import IngestReport

TEST_API_KEY = "test-api-key-for-slice-25"


def _make_report(
    total=3, new=2, updated=0, skipped=1, failed=0, errors=None
) -> IngestReport:
    """创建 IngestReport 测试辅助方法

    @param total: 文档总数, defaults to 3
    @type  total: int
    @param new: 新导入数, defaults to 2
    @type  new: int
    @param updated: 更新数, defaults to 0
    @type  updated: int
    @param skipped: 跳过数, defaults to 1
    @type  skipped: int
    @param failed: 失败数, defaults to 0
    @type  failed: int
    @param errors: 错误详情列表, defaults to None
    @type  errors: list | None

    @return: 模拟的 IngestReport 实例
    @rtype:  IngestReport
    """
    report = IngestReport(
        total=total,
        new=new,
        updated=updated,
        skipped=skipped,
        failed=failed,
    )
    if errors:
        report.errors = errors
    return report


class TestIngestAPI:
    """POST /v1/documents/ingest API 测试类"""

    # ----------------------------------------------------------
    # 1. POST /v1/documents/ingest -> 200 + report
    # ----------------------------------------------------------

    @override_settings(ZRAG_API_KEY=TEST_API_KEY)
    @patch("zrag.api.views.IngestionPipeline")
    def test_ingest_returns_report(self, mock_pipeline_cls, client):
        """正常摄入请求返回 200 和 IngestReport"""
        # 准备 mock pipeline
        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = _make_report(
            total=3, new=2, skipped=1,
        )
        mock_pipeline_cls.return_value = mock_pipeline

        resp = client.post(
            "/v1/documents/ingest",
            data=json.dumps({"source_type": "mac_notes", "full": False}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {TEST_API_KEY}",
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["Message"] == "success"
        assert body["Data"]["total"] == 3
        assert body["Data"]["new"] == 2
        assert body["Data"]["skipped"] == 1
        assert body["Data"]["updated"] == 0
        assert body["Data"]["failed"] == 0
        assert body["Data"]["errors"] == []
        assert "RequestID" in body

    @override_settings(ZRAG_API_KEY=TEST_API_KEY)
    @patch("zrag.api.views.IngestionPipeline")
    def test_ingest_with_errors(self, mock_pipeline_cls, client):
        """摄入出现错误时, report 中包含 errors 列表"""
        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = _make_report(
            total=2, new=1, failed=1,
            errors=[
                MagicMock(source_id="doc_err", error="处理失败"),
            ],
        )
        mock_pipeline_cls.return_value = mock_pipeline

        resp = client.post(
            "/v1/documents/ingest",
            data=json.dumps({"source_type": "mac_notes"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {TEST_API_KEY}",
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["Data"]["failed"] == 1
        assert len(body["Data"]["errors"]) == 1
        assert body["Data"]["errors"][0]["source_id"] == "doc_err"
        assert body["Data"]["errors"][0]["error"] == "处理失败"

    @override_settings(ZRAG_API_KEY=TEST_API_KEY)
    @patch("zrag.api.views.IngestionPipeline")
    def test_ingest_default_full_false(self, mock_pipeline_cls, client):
        """未指定 full 时默认为 False"""
        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = _make_report()
        mock_pipeline_cls.return_value = mock_pipeline

        resp = client.post(
            "/v1/documents/ingest",
            data=json.dumps({"source_type": "mac_notes"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {TEST_API_KEY}",
        )

        assert resp.status_code == 200
        # 验证 run 的 full 参数为 False
        _, kwargs = mock_pipeline.run.call_args
        assert kwargs.get("full") is False

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
