"""测试切片 31-32 — 健康检查端点

验证 HealthViewSet 的 live 和 ready 端点的行为,
包括正常状态、异常状态和免认证行为。
"""
from unittest.mock import patch

from django.test import override_settings
from rest_framework.test import APIClient

from zrag.api.health import HealthViewSet


class TestHealthLive:
    """HealthViewSet.live 端点测试类"""

    def _make_client(self):
        """创建测试客户端

        @return: DRF 测试客户端实例
        @rtype:  rest_framework.test.APIClient
        """
        return APIClient()

    def test_live(self):
        """GET /v1/health/live 应返回 200 且 status=alive

        验证存活检查端点返回正确的状态信息。
        """
        resp = self._make_client().get("/v1/health/live")
        assert resp.status_code == 200
        assert resp.data["Data"] == {"status": "alive"}
        assert resp.data["Message"] == "success"


class TestHealthReady:
    """HealthViewSet.ready 端点测试类"""

    def _make_client(self):
        """创建测试客户端

        @return: DRF 测试客户端实例
        @rtype:  rest_framework.test.APIClient
        """
        return APIClient()

    @patch('zrag.api.health.get_sqlite_store')
    @patch('zrag.api.health.get_chroma_store')
    def test_ready_with_mock(self, mock_get_chroma, mock_get_sqlite):
        """SQLite 和 ChromaDB 都正常时返回 ready

        验证当两个依赖服务均正常工作时,
        /v1/health/ready 返回 200 且 status=ready。
        """
        mock_sqlite_store = mock_get_sqlite.return_value
        mock_chroma_store = mock_get_chroma.return_value

        resp = self._make_client().get("/v1/health/ready")
        assert resp.status_code == 200
        assert resp.data["Data"]["status"] == "ready"
        assert resp.data["Data"]["checks"]["sqlite"] == "ok"
        assert resp.data["Data"]["checks"]["chromadb"] == "ok"
        mock_sqlite_store.execute.assert_called_once_with("SELECT 1")
        mock_chroma_store.count.assert_called_once()

    @patch('zrag.api.health.get_sqlite_store')
    @patch('zrag.api.health.get_chroma_store')
    def test_ready_with_failure(self, mock_get_chroma, mock_get_sqlite):
        """SQLite 异常时返回 not_ready + 503

        验证当 SQLite 检查失败时,
        /v1/health/ready 返回 503 且 status=not_ready。
        """
        mock_sqlite_store = mock_get_sqlite.return_value
        mock_sqlite_store.execute.side_effect = Exception("SQLite connection failed")
        mock_chroma_store = mock_get_chroma.return_value

        resp = self._make_client().get("/v1/health/ready")
        assert resp.status_code == 503
        assert resp.data["Data"]["status"] == "not_ready"
        assert resp.data["Data"]["checks"]["sqlite"] == "SQLite connection failed"
        assert resp.data["Data"]["checks"]["chromadb"] == "ok"
        mock_sqlite_store.execute.assert_called_once_with("SELECT 1")
        mock_chroma_store.count.assert_called_once()

    @patch('zrag.api.health.get_sqlite_store')
    @patch('zrag.api.health.get_chroma_store')
    def test_health_skip_auth(self, mock_get_chroma, mock_get_sqlite):
        """健康检查不需要 API Key 认证

        验证即使未提供 API Key,
        健康检查端点仍能正常返回 200。
        """
        client = APIClient()
        resp = client.get("/v1/health/live")
        assert resp.status_code == 200
        assert resp.data["Data"] == {"status": "alive"}

        resp = client.get("/v1/health/ready")
        assert resp.status_code == 200
        assert resp.data["Data"]["status"] == "ready"
