# ZRAG API 与会话管理 设计记录

> 分类索引: [QA 文档目录](index.md)

## Q30: 配置文件设计

**设计原则**:
- 不同环境使用同一份配置文件
- 每个模块独立配置文件，由加载器自动扫描合并
- 单层结构，不区分 defaults/local

**目录结构**:
```
config/
├── llm.yaml
├── embedding.yaml
├── ingest.yaml
├── api.yaml
├── storage.yaml
└── retrieval.yaml
```

**各模块配置**:

```yaml
# config/llm.yaml
# gateway 配置用于连接 LiteLLM Gateway
llm:
  provider: "gateway"
  timeout: 200
  gateway:
    base_url: "${LLM_GATEWAY_URL:-http://localhost:4000/v1}"
    api_key: "${LITELLM_MASTER_KEY:-sk-dummy}"
    model: "smart-router"
```

```yaml
# config/embedding.yaml
# 使用 BAAI/bge-small-zh-v1.5，输出 512 维向量
# cache_dir 在容器部署时默认为 /app/models（只读 volume 挂载点）
embedding:
  model_name: "BAAI/bge-small-zh-v1.5"
  cache_dir: "${MODELS_DIR:-/app/models}"
  device: "cpu"
```

```yaml
# config/ingest.yaml
ingest:
  batch_size: 5
```

```yaml
# config/api.yaml
api:
  key: "${ZRAG_API_KEY:-}"
  query_max_length: 2000
```

```yaml
# config/storage.yaml
# 路径为相对路径，相对于 Django manage.py 所在目录（即项目根）
# 容器部署时映射到 /app/data/ 持久化 volume
storage:
  sqlite_path: "data/zrag.db"
  chroma_path: "data/chroma_db"
```

```yaml
# config/retrieval.yaml
retrieval:
  top_k: 10
```

**配置加载器**:

```python
# zrag/config/loader.py
from pathlib import Path


def load_config(config_dir: str = "config") -> dict:
    """加载并合并配置文件中所有 YAML 文件

    扫描指定目录下所有 .yaml 文件，按 top-level key 进行深度合并。
    若多个文件存在相同 key，则按规则合并：dict 深度合并，非 dict 后覆盖前。
    合并完成后对配置项中的 ${ENV_VAR} 进行环境变量替换。

    @param config_dir: 配置文件的存放目录路径, defaults to "config"
    @type  config_dir: str, optional

    @raises: 当配置项中包含未定义的环境变量时抛出
    @type:   ValueError

    @return: 合并后的配置字典
    @type:   dict
    """
    config = {}
    config_path = Path(config_dir)
    if not config_path.exists():
        return config
    for yaml_file in sorted(config_path.glob("*.yaml")):
        data = _yaml.safe_load(yaml_file.read_text())
        if not data:
            continue
        for key, value in data.items():
            if key in config and isinstance(config[key], dict) and isinstance(value, dict):
                config[key] = {**config[key], **value}
            else:
                config[key] = value
    _resolve_env_vars(config)
    _override_from_env(config)
    return config


def _resolve_env_vars(config: dict) -> None:
    """递归替换配置中所有 ${ENV_VAR} 为环境变量实际值

    遍历配置字典的每一项，若值为字符串则查找 ${VAR} 模式并替换为 os.environ 中的变量值。
    若某个环境变量未定义，则抛出 ValueError 并提示该变量名。
    若值为 dict，递归处理其子项。

    @param config: 需要执行环境变量替换的配置字典。该字典会被原地修改。
    @type  config: dict

    @raises: 当 ${VAR} 中的 VAR 在环境变量中不存在时抛出
    @type:   ValueError
    """
    import os as _os
    import re as _re

    pattern = _re.compile(r'\$\{(\w+)(?::-([^}]*))?\}')

    def _resolve(value):
        if isinstance(value, str):
            def _replace(m):
                var_name = m.group(1)
                default_val = m.group(2)
                env_val = _os.environ.get(var_name)
                if env_val is not None:
                    return env_val
                if default_val is not None:
                    return default_val
                raise ValueError(f"环境变量 {var_name} 未定义且无默认值")
            return pattern.sub(_replace, value)
        if isinstance(value, dict):
            return {k: _resolve(v) for k, v in value.items()}
        return value

    for key in list(config.keys()):
        config[key] = _resolve(config[key])


def _override_from_env(config: dict, prefix: str = "") -> None:
    """使用环境变量覆盖配置项

    递归遍历配置字典的全部叶子节点，检查是否存在同名 UPPER_SNAKE 环境变量。
    若存在，则用环境变量的值覆盖配置项，并根据 YAML 原值类型做类型转换。

    扁平化规则: llm.timeout -> LLM_TIMEOUT, llm.gateway.base_url -> LLM_GATEWAY_BASE_URL
    类型转换规则:
      - YAML 原值是 int -> 环境变量值 int(var)，转换失败抛 ValueError
      - YAML 原值是 float -> 环境变量值 float(var)
      - YAML 原值是 bool -> 环境变量值 var.lower() in ('true', '1', 'yes')
      - YAML 原值是 str -> 直接使用环境变量值
      - YAML 原值是 None -> 直接使用环境变量值

    环境变量覆盖发生在 ${VAR:-default} 替换之后，
    因此 env override 可以覆盖 `${VAR:-default}` 解析后的结果。

    @param config: 已完成 ${VAR} 替换的配置字典。该字典会被原地修改。
    @type  config: dict
    @param prefix: 当前递归层级的前缀，内部使用
    @type  prefix: str
    """
    import os as _os

    for key, value in list(config.items()):
        env_key = f"{prefix}{key.upper()}" if not prefix else f"{prefix}_{key.upper()}"
        if isinstance(value, dict):
            _override_from_env(value, prefix=env_key)
            continue
        env_val = _os.environ.get(env_key)
        if env_val is None:
            continue
        if isinstance(value, bool):
            config[key] = env_val.lower() in ("true", "1", "yes")
        elif isinstance(value, int):
            try:
                config[key] = int(env_val)
            except ValueError:
                raise ValueError(
                    f"环境变量 {env_key} 的值 '{env_val}' 无法转换为 int"
                )
        elif isinstance(value, float):
            try:
                config[key] = float(env_val)
            except ValueError:
                raise ValueError(
                    f"环境变量 {env_key} 的值 '{env_val}' 无法转换为 float"
                )
        else:
            config[key] = env_val


try:
    import yaml as _yaml
except ImportError:
    import warnings as _w
    _w.warn("PyYAML not installed; load_config will fail at runtime")
    _yaml = None
```

**三阶段配置加载流程**:

1. **YAML 文件合并**: 扫描 `config/` 目录下所有 `.yaml` 文件，按 top-level key 深度合并，dict 深度合并，非 dict 后覆盖前。
2. **${VAR:-default} 解析**: `_resolve_env_vars` 递归替换所有 `${ENV_VAR}` 占位符，支持 `${VAR:-default}` 默认值语法。
3. **环境变量覆盖**: `_override_from_env` 使用同名 UPPER_SNAKE 环境变量覆盖配置项的叶子节点。

**env override 规则说明**:

- **扁平化 key 命名规则**: 嵌套 key 的路径以 `_` 连接并转大写，例如:
  - `llm.timeout` -> `LLM_TIMEOUT`
  - `llm.gateway.base_url` -> `LLM_GATEWAY_BASE_URL`
  - `storage.sqlite_path` -> `STORAGE_SQLITE_PATH`
  - `embedding.cache_dir` -> `EMBEDDING_CACHE_DIR`
  - `api.query_max_length` -> `API_QUERY_MAX_LENGTH`
  - `retrieval.top_k` -> `RETRIEVAL_TOP_K`
  - `ingest.batch_size` -> `INGEST_BATCH_SIZE`

- **类型自动转换**: 根据 YAML 原值的类型自动将环境变量字符串转为对应的 Python 类型：
  - YAML 中为 int -> `int(env_val)`
  - YAML 中为 float -> `float(env_val)`
  - YAML 中为 bool -> `env_val.lower() in ('true', '1', 'yes')`
  - YAML 中为 str -> 直接使用环境变量字符串

- **覆盖优先级**: 环境变量覆盖发生在 `${VAR:-default}` 替换之后，因此 env override 可以覆盖 `${VAR:-default}` 解析后的结果。

- **容器部署场景**: 在 Docker 容器部署中，无需修改 YAML 配置文件，只需在 `docker-compose.yml` 的 `environment` 中或 `.env` 文件中添加对应的 UPPER_SNAKE 环境变量即可覆盖任意配置项。修改配置后执行 `docker compose restart` 使更改生效。

**settings.py 集成**:

```python
import os
from pathlib import Path

from zrag.config.loader import load_config

BASE_DIR = Path(__file__).resolve().parent.parent

_config = load_config("config")

ZRAG_API_KEY = _config.get("api", {}).get("key", "")
ZRAG_LLM = _config.get("llm", {})
ZRAG_EMBEDDING = _config.get("embedding", {})
ZRAG_STORAGE = _config.get("storage", {})
ZRAG_INGEST = _config.get("ingest", {})
ZRAG_RETRIEVAL = _config.get("retrieval", {})
```

各模块读取配置的典型模式：模块构造函数参数默认 None，从 `settings.ZRAG_*` 自动读取，配置缺失时抛 `ValueError`（不静默兜底）。

---

## Q29: API 层设计

### SSE 概念

SSE（Server-Sent Events）是 HTTP 长连接，服务器逐块推送数据、客户端逐步接收。

**普通请求 vs SSE 对比**：
| 方式 | 用户体验 | 实现 |
|------|---------|------|
| `/api/chat` | 浏览器转圈 10 秒 → 一次性显示完整回答 | `return JSON` |
| `/api/chat/stream` | 每个 token 生成后立即逐字显示（像 ChatGPT） | `Iterator[str]` → SSE event |

### RESTful 端点（修正后）

| 端点 | 方法 | 说明 |
|------|:--:|------|
| `POST /api/conversations` | POST | 创建对话（RAG 问答）。通过 `Accept` header 区分：`application/json` → 非流式，`text/event-stream` → SSE |
| `POST /api/documents/ingest` | POST | 触发文档摄入。同上 Accept 区分流式 |
| `GET /api/sources` | GET | 列出 Source 及统计（SQLite 查询 processed_docs 实现）|

### 技术选型变更

**决策**: API 层使用 **Django REST Framework**（非原计划的 FastAPI）。

| 维度 | 原计划 (FastAPI) | 新方案 (DRF) |
|------|:---:|:---:|
| 同步/异步 | 原生 async | 同步为主 |
| 项目结构 | 自由 | Django 约定（settings, urls, views, serializers） |
| SSE | StreamingResponse | StreamingHttpResponse |

### 请求/响应模型

**`POST /api/conversations`**:
```json
// 请求
{ "query": "机器学习有哪些分类？" }

// 响应
{
  "answer": "...",
  "sources": [
    {"doc_title": "ML笔记", "content": "...", "score": 0.0328}
  ]
}
```

**`POST /api/documents/ingest`**:
```json
// 请求
{ "source_type": "mac_notes" }   // 可选，不传则全量导入

// 响应
{
  "status": "completed",
  "report": { "total": 42, "new": 3, "updated": 2, "skipped": 37, "failed": 0 }
}
```

**`GET /api/sources`**:
```json
{
  "sources": [
    {"type": "mac_notes", "processed_count": 42}
  ]
}
```

### API 层实现细节

**技术栈变更**: FastAPI → **Django REST Framework**

**路由风格**: ViewSet + re_path，参考 zonebank 模式

**API 版本化**: URL 加 `v1/` 前缀

---

#### 端点列表

| 端点 | 方法 | 说明 |
|------|:--:|------|
| `POST /v1/conversations` | POST | RAG 问答（非流式） |
| `POST /v1/conversations/stream` | POST | RAG 问答（SSE 流式，Phase 2） |
| `POST /v1/documents/ingest` | POST | 文档摄入（非流式） |
| `POST /v1/documents/ingest/stream` | POST | 文档摄入（SSE 流式，Phase 2） |
| `GET /v1/sources` | GET | Source 统计 |
| `GET /v1/health/live` | GET | Liveness（进程存活检查） |
| `GET /v1/health/ready` | GET | Readiness（依赖检查） |

---

#### 自定义 Response

```python
# zrag/api/response.py
from rest_framework.response import Response

class APIResponse(Response):
    def __init__(self, message=None, data=None, request_id=None,
                 http_status=200, headers=None):
        result = {}
        result['Message'] = message or 'ok'
        if data:
            result['Data'] = data
        if request_id:
            result['RequestID'] = request_id

        _headers = headers or {}
        if request_id:
            _headers['X-Request-ID'] = request_id

        super().__init__(data=result, status=http_status, headers=_headers)
```

成功响应: `{"Message": "ok", "Data": {...}, "RequestID": "xxx"}` (+ `X-Request-ID` Header)
失败响应: `{"ErrorCode": "ZRAG-LLM-502", "ErrorMessage": "...", "RequestID": "xxx"}`

---

#### 中间件

```python
# zrag/api/middleware.py
import uuid

class RequestIDMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.META["X-REQUEST-ID"] = str(uuid.uuid4())
        response = self.get_response(request)
        return response
```

---

#### 认证

```python
# zrag/api/auth.py
from rest_framework import authentication, exceptions
from django.conf import settings

class ApiKeyAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        api_key = request.headers.get("Authorization", "").removeprefix("Bearer ")
        if not api_key or api_key != settings.ZRAG_API_KEY:
            raise exceptions.AuthenticationFailed("Invalid API Key")
        return (None, None)
```

所有端点统一要求认证（`/v1/health/*` 除外）。

---

#### 速率限制

```python
# settings.py
REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_CLASSES': ['rest_framework.throttling.ScopedRateThrottle'],
    'DEFAULT_THROTTLE_RATES': {
        'chat': '10/minute',
        'ingest': '3/minute',
    },
}
```

| 端点 | scope | 限制 |
|------|-------|------|
| `/v1/conversations` | `chat` | 10 req/min |
| `/v1/documents/ingest` | `ingest` | 3 req/min |
| `/v1/sources` | — | 不限速 |
| `/v1/health/*` | — | 不限速 + 跳过认证 |

---

#### 请求验证

```python
# zrag/api/serializers.py
from rest_framework import serializers
from django.conf import settings

class ConversationSerializer(serializers.Serializer):
    query = serializers.CharField(required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        max_len = getattr(settings, 'ZRAG_QUERY_MAX_LENGTH', 2000)
        self.fields['query'].max_length = max_len


class IngestSerializer(serializers.Serializer):
    source_type = serializers.CharField(required=False)
```

---

#### 并发摄入保护

```sql
CREATE TABLE ingest_lock (
    id         INTEGER PRIMARY KEY CHECK (id = 1),
    is_running BOOLEAN NOT NULL DEFAULT 0,
    started_at TEXT,
    request_id TEXT
);
```

```python
# zrag/api/ingest_guard.py
class IngestGuard:
    def __init__(self, sqlite_store):
        self.store = sqlite_store
        self.acquired = False

    def acquire(self, request_id: str) -> bool:
        cursor = self.store.execute(
            "UPDATE ingest_lock SET is_running=1, started_at=datetime('now'), request_id=? "
            "WHERE is_running=0",
            (request_id,)
        )
        self.acquired = cursor.rowcount > 0
        return self.acquired

    def release(self):
        if self.acquired:
            self.store.execute(
                "UPDATE ingest_lock SET is_running=0, started_at=NULL, request_id=NULL WHERE id=1"
            )
            self.acquired = False
```

AppConfig.ready() 中清理残留锁:
```python
sqlite_store.execute("UPDATE ingest_lock SET is_running=0 WHERE id=1")
```

---

#### 异常体系

```python
# zrag/api/exceptions.py
class ZragBaseException(Exception):
    def __init__(self, error_code, message_detail, error_type,
                 mitigation, data, request_id, http_status=500):
        self.error_code = error_code
        self.message_detail = message_detail
        self.error_type = error_type
        self.mitigation = mitigation
        self.data = data
        self.request_id = request_id
        self.http_status = http_status

    def get_context(self) -> str:
        return f'{self.message_detail}({self.error_type}) --- {self.mitigation}'
```

异常子类:
```python
class UnauthorizedException(ZragBaseException):
    def __init__(self, request_id: str):
        super().__init__(
            error_code='ZRAG-AUTH-401',
            message_detail='Invalid or missing API Key',
            error_type='Authentication',
            mitigation='Provide a valid API Key in the Authorization header.',
            data={}, request_id=request_id, http_status=401
        )

class RetrievalException(ZragBaseException):
    def __init__(self, query: str, request_id: str, cause: Exception | None = None):
        data = {'query': query}
        if cause:
            data['Cause'] = {'Type': type(cause).__name__, 'Message': str(cause)}
        super().__init__(
            error_code='ZRAG-RETRIEVE-500',
            message_detail=f'Failed to retrieve documents for query: "{query[:100]}"',
            error_type='Retrieval',
            mitigation='Check if ChromaDB and SQLite are accessible and contain data.',
            data=data, request_id=request_id, http_status=500
        )

class LLMCallException(ZragBaseException):
    def __init__(self, model: str, request_id: str, cause: Exception | None = None):
        data = {'model': model}
        if cause:
            data['Cause'] = {'Type': type(cause).__name__, 'Message': str(cause)}
        super().__init__(
            error_code='ZRAG-LLM-502',
            message_detail=f'LLM call failed (model: {model})',
            error_type='LLM',
            mitigation='Verify LiteLLM Gateway is running and the model is available.',
            data=data, request_id=request_id, http_status=502
        )

class IngestionException(ZragBaseException):
    def __init__(self, source_type: str, request_id: str, cause: Exception | None = None):
        data = {'source_type': source_type}
        if cause:
            data['Cause'] = {'Type': type(cause).__name__, 'Message': str(cause)}
        super().__init__(
            error_code='ZRAG-INGEST-500',
            message_detail=f'Document ingestion failed (source: {source_type})',
            error_type='Ingestion',
            mitigation='Check the source configuration and try again.',
            data=data, request_id=request_id, http_status=500
        )

class SourceNotFoundException(ZragBaseException):
    def __init__(self, source_type: str, request_id: str):
        super().__init__(
            error_code='ZRAG-INGEST-404',
            message_detail=f'Unknown source type: "{source_type}"',
            error_type='Source',
            mitigation=f'Available sources: check SOURCE_REGISTRY',
            data={'source_type': source_type}, request_id=request_id, http_status=404
        )
```

异常体系总览:
```
ZragBaseException
├── UnauthorizedException      401 认证失败
├── RetrievalException         500 检索失败（含 Cause）
├── LLMCallException           502 LLM 调用失败（含 Cause）
├── IngestionException         500 摄入失败（含 Cause）
└── SourceNotFoundException    404 未知 Source
```

---

#### 异常 Handler

```python
# zrag/api/exception_handler.py
class BaseExceptionHandler(ABC):
    def __init__(self, exc, context):
        self.exc = exc
        self.context = context

    @abstractmethod
    def handle(self) -> Response: ...

class DefaultErrorHandler(BaseExceptionHandler):
    def handle(self):
        logger.error(...)
        return Response({
            'ErrorCode': 'ZRAG-SERVER-500',
            'ErrorMessage': 'Internal server error',
            'RequestID': 'unknown',
        }, status=500)

# 注册表: exception → handler 映射
error_type = [
    {'exception': ZragBaseException, 'handler': ZragErrorHandler},
    {'exception': AuthenticationFailed, 'handler': AuthErrorHandler},
    {'exception': ValidationError, 'handler': SerializerErrorHandler},
    {'exception': ParseError, 'handler': RequestParseErrorHandler},
]

def api_exception_handler(exc, context):
    for entry in error_type:
        if isinstance(exc, entry['exception']):
            return entry['handler'](exc, context).handle()
    return DefaultErrorHandler(exc, context).handle()
```

配置:
```python
# settings.py
REST_FRAMEWORK['EXCEPTION_HANDLER'] = 'zrag.api.exception_handler.api_exception_handler'
```

---

#### 健康检查

```python
# zrag/api/urls.py (health)
re_path(r'^v1/health/live$',  HealthViewSet.as_view({'get': 'live'})),
re_path(r'^v1/health/ready$', HealthViewSet.as_view({'get': 'ready'})),

# zrag/api/views.py
class HealthViewSet(GenericViewSet):
    permission_classes = []
    throttle_classes = []

    def live(self, request):
        return APIResponse(data={'status': 'alive'})

    def ready(self, request):
        checks = {}
        try:
            get_sqlite_store().execute("SELECT 1")
            checks['sqlite'] = 'ok'
        except Exception as e:
            checks['sqlite'] = str(e)
        try:
            get_chroma_store().collection.count()
            checks['chromadb'] = 'ok'
        except Exception as e:
            checks['chromadb'] = str(e)

        all_ok = all(v == 'ok' for v in checks.values())
        return APIResponse(
            data={'status': 'ready' if all_ok else 'not_ready', 'checks': checks},
            http_status=200 if all_ok else 503,
        )
```

---

#### ViewSet + URL 汇总

```python
# zrag/api/urls.py
from django.urls import re_path
from zrag.api.views import ConversationViewSet, DocumentViewSet, SourceViewSet, HealthViewSet

conversation_urls = [
    re_path(r'^v1/conversations$',        ConversationViewSet.as_view({'post': 'create'})),
    re_path(r'^v1/conversations/stream$', ConversationViewSet.as_view({'post': 'create_stream'})),
]
document_urls = [
    re_path(r'^v1/documents/ingest$',        DocumentViewSet.as_view({'post': 'ingest'})),
    re_path(r'^v1/documents/ingest/stream$', DocumentViewSet.as_view({'post': 'ingest_stream'})),
]
source_urls = [
    re_path(r'^v1/sources$', SourceViewSet.as_view({'get': 'list'})),
]
health_urls = [
    re_path(r'^v1/health/live$',  HealthViewSet.as_view({'get': 'live'})),
    re_path(r'^v1/health/ready$', HealthViewSet.as_view({'get': 'ready'})),
]
urlpatterns = conversation_urls + document_urls + source_urls + health_urls
```

---

#### CORS

```python
# settings.py
INSTALLED_APPS = ['corsheaders', ...]
MIDDLEWARE = ['corsheaders.middleware.CorsMiddleware', ...]
CORS_ALLOW_ALL_ORIGINS = True  # Phase 1 开发阶段，后续收紧
```

---

#### 日志

```python
# settings.py
import logging

LOGGER = logging.getLogger('zrag')
LOGGER.propagate = False
LOGGER.setLevel(logging.INFO)

# 业务日志分层: log/apps/info.log, error.log, warning.log
# Django 框架日志分层: log/django/info.log, error.log (LOGGING dict 配置)
```

```python
# zrag/tools/utils.py
def format_log_record(action, message, request_id, data=None, internal_error=None) -> str:
    info = {'RequestID': request_id, 'Action': action, 'Message': message}
    if data:
        info['Data'] = data
    if internal_error:
        info['InternalError'] = str(internal_error)
    return json.dumps(info, ensure_ascii=False, cls=DjangoJSONEncoder)
```

---

#### 数据库

Django 自身用 `data/django.db`（session/migration），业务数据用 `data/zrag.db`，两个独立 SQLite 文件。

---

#### 依赖管理

- 基础层全局单例（AppConfig.ready() 初始化）: Embedder、SQLiteStore、ChromaDB
- 组合层按需组装: Retriever、IngestionPipeline、LLMProvider

---

#### 已确认细节清单

| 细节 | 决策 |
|------|------|
| 框架 | DRF（非 FastAPI） |
| 路由 | ViewSet + re_path，v1/ 前缀 |
| 响应 | APIResponse（Message + Data + RequestID） |
| 认证 | API Key，Authorization Header，所有端点统一要求 |
| CSRF | 禁用 |
| CORS | django-cors-headers，Phase 1 全放通 |
| request_id | RequestIDMiddleware 自动生成 UUID |
| 流式 | 独立 /stream 端点，Phase 2 实现 |
| 速率限制 | ScopedRateThrottle，chat 10/min，ingest 3/min |
| 验证 | query max_length=2000，配置项 |
| 并发保护 | SQLite ingest_lock 表 |
| 异常 | BaseZragException + 注册表 handler，多层 Cause 不丢失 |
| 日志 | LOGGER on settings，业务/框架分层，format_log_record |
| 健康检查 | Liveness + Readiness，跳过认证和限速 |
| 数据库 | django.db（框架）+ zrag.db（业务）分离 |
| 检索无结果 | 200 + LLM 自然回复 |

| 模块 | 状态 |
|------|:----:|
| API 层（DRF） | ✅ |


## Q31: 会话存储设计

**用户**: 会话记录应该存在哪里？

**决策**: 在已有 `zrag.db` 中新增两张表，复用 SQLite 存储层。

### 表结构

```sql
CREATE TABLE conversations (
    id         TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role            TEXT NOT NULL,        -- 'user' | 'assistant'
    content         TEXT NOT NULL,
    sources         TEXT,                 -- JSON: [{"doc_title":"...","chunk_id":"..."}]
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);

CREATE INDEX idx_messages_conv_id ON messages(conversation_id);
CREATE INDEX idx_messages_created ON messages(conversation_id, created_at);
```

### 关键决策

| 决策点 | 结论 | 理由 |
|--------|------|------|
| updated_at 字段 | 删除 | 用子查询 `(SELECT MAX(m.created_at) FROM messages m WHERE m.conversation_id = c.id) AS last_msg_at` 获取最近消息时间，避免数据冗余和不一致 |
| sources 字段存储内容 | 只存 `[{"doc_title":"...","chunk_id":"..."}]` | 前端渲染来源标注的最少信息。不存 chunk 原文，原文始终走 chunks 表 |
| 模型名 | 不存 | UI 上的"当前模型"放前端状态管理 |
| 删除级联 | 先 `DELETE FROM messages WHERE conversation_id = ?`，再 `DELETE FROM conversations WHERE id = ?` | 同一 SQLite 事务中 |
| 数据库选型 | 使用已有 SQLite，不引入 NoSQL | 数据量小、结构固定、SQLite 足够 |

---

## Q32: 会话 API 设计

**用户**: 需要支持会话的 CRUD 操作。

### 端点汇总

| 端点 | 方法 | 说明 |
|------|:--:|------|
| `POST /v1/conversations` | POST | 新建会话 + 首条问答 |
| `POST /v1/conversations/{id}/messages` | POST | 在已有会话中继续问答 |
| `GET /v1/conversations` | GET | 会话列表（含 total 总数，按最近消息时间倒序） |
| `GET /v1/conversations/{id}/messages` | GET | 获取某会话的所有消息 |
| `DELETE /v1/conversations/{id}` | DELETE | 删除会话及其所有消息（幂等） |

> 流式端点（`/stream`）属于 Phase 2，暂不实现。

### 核心设计决策

| 决策点 | 结论 | 理由 |
|--------|------|------|
| 会话创建方式 | **方案 B** — 首条消息即创建会话 | 打开页面直接提问即可，无需"先创建空会话" |
| 对话 ID 传递 | URL 路径参数 | RESTful 标准。本地工具无安全隐患 |
| LLM 调用位置 | 数据库事务**外** | LLM 失败 → 零写入；LLM 成功 → 事务快速写入 |
| 分页 | 不需要 | 个人工具数据量小 |
| 对话总数 | `GET /v1/conversations` 返回 `{"total": N, "conversations": [...]}` | 前端需要显示总数和列表 |
| 对话不存在 | `NotFoundException` → 404 | 给用户明确提示 |
| DELETE 幂等 | 删除不存在的对话也返回成功 | 目标状态（资源不存在）已满足 |
| sources 返回粒度 | 只返回 `doc_title` + `chunk_id` | 前端渲染来源标注所需的最少字段 |

### 请求/响应示例

**POST `/v1/conversations`**:
```json
// 请求
{ "query": "什么是过拟合？", "model": "smart-router" }

// 响应
{
  "Data": {
    "conversation_id": "abc-123",
    "title": "什么是过拟合？",
    "answer": "过拟合是指模型在训练数据上表现很好但在测试数据上表现差的现象...",
    "sources": [
      {"doc_title": "机器学习笔记", "chunk_id": "xxx_chunk_3"}
    ]
  }
}
```

**GET `/v1/conversations`**:
```json
{
  "Data": {
    "total": 23,
    "conversations": [
      {"id": "abc-123", "title": "什么是过拟合？", "created_at": "...", "last_msg_at": "..."}
    ]
  }
}
```

### 代码实现

**ChatSerializer**:
```python
class ChatSerializer(serializers.Serializer):
    query = serializers.CharField(max_length=2000)
    model = serializers.CharField(max_length=100, required=False, default="smart-router")
```

**NotFoundException**（新增异常类）:
```python
class NotFoundException(BaseZragException):
    def __init__(self, message, error_code="NOT-FOUND"):
        super().__init__(http_status=404, message=message, error_code=error_code)
```

**ConversationViewSet**:
```python
class ConversationViewSet(viewsets.ViewSet):

    def create(self, request):
        """POST /v1/conversations — 新建会话 + 首条问答"""
        serializer = ChatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        query = serializer.validated_data['query']
        model = serializer.validated_data.get('model', 'smart-router')

        # 1. RAG + LLM（事务外，失败则零副作用）
        try:
            results = get_retriever().hybrid_search(query, k=10)
            prompt_messages = get_prompt_builder().build(query, results)
            answer = get_llm_provider().chat(prompt_messages)
        except Exception as e:
            raise RetrievalException(str(e))

        # 2. 事务写入：会话 + 用户消息 + AI 回复
        sources_json = json.dumps([
            {"doc_title": r.doc_title, "chunk_id": r.chunk_id} for r in results
        ])
        conv_id = str(uuid4())
        now = datetime.utcnow().isoformat()
        with sqlite_store.transaction() as db:
            db.execute("INSERT INTO conversations (id, title, created_at) VALUES (?, ?, ?)",
                       (conv_id, query[:50], now))
            db.execute("INSERT INTO messages (id, conversation_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
                       (str(uuid4()), conv_id, 'user', query, now))
            db.execute("INSERT INTO messages (id, conversation_id, role, content, sources, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                       (str(uuid4()), conv_id, 'assistant', answer, sources_json, now))
        return APIResponse(data={
            "conversation_id": conv_id, "title": query[:50],
            "answer": answer, "sources": json.loads(sources_json),
        })

    def send_message(self, request, conversation_id=None):
        """POST /v1/conversations/{id}/messages — 继续对话"""
        conv = sqlite_store.fetch_one("SELECT id FROM conversations WHERE id = ?", (conversation_id,))
        if not conv:
            raise NotFoundException(
                message="Conversation not found: %s" % conversation_id,
                error_code="CONVERSATION-NOT-FOUND")
        serializer = ChatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        query = serializer.validated_data['query']
        model = serializer.validated_data.get('model', 'smart-router')
        try:
            results = get_retriever().hybrid_search(query, k=10)
            prompt_messages = get_prompt_builder().build(query, results)
            answer = get_llm_provider().chat(prompt_messages)
        except Exception as e:
            raise RetrievalException(str(e))
        sources_json = json.dumps([
            {"doc_title": r.doc_title, "chunk_id": r.chunk_id} for r in results
        ])
        now = datetime.utcnow().isoformat()
        with sqlite_store.transaction() as db:
            db.execute("INSERT INTO messages (id, conversation_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
                       (str(uuid4()), conversation_id, 'user', query, now))
            db.execute("INSERT INTO messages (id, conversation_id, role, content, sources, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                       (str(uuid4()), conversation_id, 'assistant', answer, sources_json, now))
        return APIResponse(data={"answer": answer, "sources": json.loads(sources_json)})

    def list(self, request):
        """GET /v1/conversations"""
        rows = sqlite_store.fetch_all("""
            SELECT c.id, c.title, c.created_at,
                   (SELECT MAX(m.created_at) FROM messages m WHERE m.conversation_id = c.id) AS last_msg_at
            FROM conversations c ORDER BY last_msg_at DESC
        """)
        conversations = [{"id": r['id'], "title": r['title'], "created_at": r['created_at'], "last_msg_at": r['last_msg_at']} for r in rows]
        return APIResponse(data={"total": len(conversations), "conversations": conversations})

    def get_messages(self, request, conversation_id=None):
        """GET /v1/conversations/{id}/messages"""
        conv = sqlite_store.fetch_one("SELECT id FROM conversations WHERE id = ?", (conversation_id,))
        if not conv:
            raise NotFoundException(message="Conversation not found: %s" % conversation_id, error_code="CONVERSATION-NOT-FOUND")
        rows = sqlite_store.fetch_all(
            "SELECT id, role, content, sources, created_at FROM messages WHERE conversation_id = ? ORDER BY created_at",
            (conversation_id,))
        messages = []
        for r in rows:
            msg = {"id": r['id'], "role": r['role'], "content": r['content'], "created_at": r['created_at']}
            if r['sources']:
                msg['sources'] = json.loads(r['sources'])
            messages.append(msg)
        return APIResponse(data={"messages": messages})

    def destroy(self, request, conversation_id=None):
        """DELETE /v1/conversations/{id} — 幂等删除"""
        with sqlite_store.transaction() as db:
            db.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            db.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        return APIResponse(data={"deleted": conversation_id})
```

**路由**:
```python
# zrag/api/urls.py（与原 conversation_urls 合并）
conversation_urls = [
    re_path(r'^v1/conversations$', ConversationViewSet.as_view({'post': 'create', 'get': 'list'})),
    re_path(r'^v1/conversations/(?P<conversation_id>[^/]+)/messages$',
            ConversationViewSet.as_view({'post': 'send_message', 'get': 'get_messages'})),
    re_path(r'^v1/conversations/(?P<conversation_id>[^/]+)$',
            ConversationViewSet.as_view({'delete': 'destroy'})),
]
```

---

## Q35: BgeSmallEmbedder 实际维度与模型离线加载问题

**用户**: 继续切片 7 的实现。

**决策**: 实现 `BgeSmallEmbedder(EmbeddingModel)`，使用 sentence-transformers 加载 `BAAI/bge-small-zh-v1.5` 模型。

### 发现 1：模型实际输出维度

bge-small-zh-v1.5 的 `hidden_size` 实际为 **512**，而非 HuggingFace 模型页面标注的 384。

| 项目 | 设计阶段假设 | 实际验证结果 |
|------|:----------:|:----------:|
| 维度 | 384 | **512** |
| 验证方式 | 查阅文档 | `len(model.encode(["test"]))` 实际运行 |

**影响**: 所有引用 384 维度的设计文档需要更新为 512 维。ChromaDB Collection 配置不受影响（Cosine 距离兼容任意维度）。

### 发现 2：TRANSFORMERS_OFFLINE 环境变量

**问题**: 在不执行 `export HF_ENDPOINT=https://hf-mirror.com` 的环境中运行 `BgeSmallEmbedder` 时, sentence-transformers 会尝试连接 huggingface.co 进行在线验证。
由于网络环境无法访问 huggingface.co，连接超时导致进程无限卡住。

**日志特征**:
```
HTTPSConnectionPool(host='huggingface.co', port=443): Max retries exceeded
(Caused by ConnectTimeoutError, 'Connection to huggingface.co timed out.')
```

**解决方案**: 在 `zrag/embed/local.py` 中强制设置离线模式:

```python
import os
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
```

**模型缓存验证**:
```bash
# 模型已缓存到如下目录
~/.cache/huggingface/hub/models--BAAI--bge-small-zh-v1.5/
# 权重文件约 91MB

# 首次下载方式
HF_ENDPOINT=https://hf-mirror.com pip install sentence-transformers
HF_ENDPOINT=https://hf-mirror.com python -c "
from sentence_transformers import SentenceTransformer
SentenceTransformer('BAAI/bge-small-zh-v1.5')
"
```

---
