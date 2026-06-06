# ZRAG 系统架构设计文档

> 最后更新: 2026-06-06

## 1. 请求链路

```
Browser → znginx (80) → zrag-frontend (80, 静态资源)
                      → zrag-backend (5965, uWSGI → Django)
                              → LLM Gateway (host.docker.internal:4000)
```

## 2. 容器化部署

### 2.1 容器清单

| 容器 | 镜像 | 端口 | 资源限制 |
|------|------|------|----------|
| znginx | nginx:alpine | 80 | — |
| zrag-frontend | nginx:alpine (多阶段构建) | 80 (内部) | 64M / 0.5 CPU |
| zrag-backend | python:3.10-slim (多阶段构建) | 5965 (内部) | 768M / 2 CPU |

### 2.2 uWSGI 配置

参照 `docs/uwsgi-containerization.md`，关键配置：

```ini
[uwsgi]
http-socket = 0.0.0.0:5965   # znginx 反向代理 → http-socket 模式
lazy-apps = true              # fork 后加载 app，避免 SQLite 连接损坏
die-on-term = true            # Docker SIGTERM 优雅退出
harakiri = 300                # LLM 长耗时保护
harakiri-verbose = true       # 记录 HARAKIRI 详情
```

### 2.3 Volumes

| 宿主机路径 | 容器路径 | 用途 |
|-----------|----------|------|
| `./data/pro` | `/app/data` | SQLite + ChromaDB |
| `/Users/lichen/.../models` | `/app/models:ro` | BGE 模型文件 |
| `./logs/pro` | `/app/log` | 应用日志 |

## 3. Trace ID 全程追踪

```
znginx $request_id → X-Request-ID header → uWSGI → RequestIDMiddleware
  → request.META["X-Request-ID"]
  → APIResponse.RequestID (响应体)
  → Response Header X-Request-ID
  → Django logger: [req=xxx] 前缀
```

### 3.1 各层日志关联

| 层级 | 日志位置 | Trace ID 字段 |
|------|----------|-------------|
| znginx | access.log | `$request_id` (末尾) |
| uWSGI | uwsgi-req.log | 请求时间+状态 |
| Django | info.log | `[req=xxx]` 前缀 |
| API 响应 | Response Body | `RequestID` 字段 |

## 4. 日志体系

### 4.1 日志级别分流

按级别拆分文件（`zrag/log_filter.py` ExactLevelFilter）：

| 文件 | 级别 | 内容 |
|------|------|------|
| `debug.log` | DEBUG | 详细调试信息 |
| `info.log` | INFO | 业务节点日志 |
| `warning.log` | WARNING | 可恢复异常 |
| `error.log` | ERROR | 需关注错误 |
| `uwsgi.log` | — | uWSGI 进程日志 |
| `uwsgi-req.log` | — | uWSGI HTTP 请求日志 |

### 4.2 业务节点日志

所有 API 方法在关键节点完成时记录 INFO 日志，含 `[req=xxx]` 前缀。

示例（创建会话）：
```
[req=b9eeb85e] 检索完成 conversation_id=xxx results_count=0
[req=b9eeb85e] LLM 调用完成 conversation_id=xxx reply_len=93
[req=b9eeb85e] 消息已保存 conversation_id=xxx
```

通过日志时间戳差值可计算各节点耗时。

## 5. API 设计

### 5.1 端点列表

| 方法 | 路径 | 说明 | 限流 |
|------|------|------|------|
| GET | `/v1/conversations` | 会话列表 | chat 60/min |
| POST | `/v1/conversations` | 创建会话 + RAG 问答 | chat 60/min |
| DELETE | `/v1/conversations/{id}` | 删除会话 | chat 60/min |
| GET | `/v1/conversations/{id}/messages` | 消息列表 | chat 60/min |
| POST | `/v1/conversations/{id}/messages` | 追加消息 | chat 60/min |
| GET | `/v1/sources` | 来源列表 | — |
| POST | `/v1/documents/ingest` | 文档摄入 | ingest 3/min |
| GET | `/v1/health/live` | 存活探针 | — |
| GET | `/v1/health/ready` | 就绪探针 | — |
| GET | `/v1/docs/` | Swagger UI (DEBUG only) | — |
| GET | `/v1/schema/` | OpenAPI Schema (DEBUG only) | — |

### 5.2 认证

所有 API（除健康检查）需要 `Authorization: Bearer <api_key>` 请求头。

`zrag/api/auth.py` — APIKeyAuthentication

### 5.3 响应格式

```json
{
    "Message": "success",
    "Data": { ... },
    "RequestID": "b9eeb85e..."
}
```

错误时额外包含 `ErrorCode`：
```json
{
    "Message": "错误描述",
    "Data": null,
    "RequestID": "...",
    "ErrorCode": "UNAUTHORIZED"
}
```

### 5.4 ErrorCode 体系

| ErrorCode | HTTP | 说明 |
|-----------|------|------|
| UNAUTHORIZED | 401 | 认证失败 |
| NOT-FOUND | 404 | 资源不存在 |
| PARSE-ERROR | 400 | 请求体解析失败 |
| VALIDATION-ERROR | 400 | 参数校验失败 |
| LLM-CALL-ERROR | 502 | LLM 调用失败 |
| RETRIEVAL-ERROR | 500 | 检索失败 |
| INGESTION-ERROR | 500 | 摄入失败 |
| INTERNAL-ERROR | 500 | 未知异常 |
| API-ERROR | varies | DRF 通用异常 |

## 6. 前端错误处理

### 6.1 双层反馈

1. **Toast 通知**（右上角，5 秒消失）：简短错误描述
2. **内联错误气泡**（聊天区，永久显示）：红色气泡 + ⚠️ 图标 + 详细错误 + Trace ID

### 6.2 错误消息映射

`frontend/src/api/index.js` — `getUserMessage()` 根据 ErrorCode/HTTP status 映射用户友好消息：

- 401 → "认证失败，请刷新页面重试"
- 502 → "AI 服务暂时不可用，请稍后重试"
- TIMEOUT → "请求超时，请稍后重试"（60s AbortController）
- 错误消息末尾追加 ` (错误ID: {requestId})`

## 7. ChromaDB Fork-Safety

**问题**：uWSGI master 进程 fork worker 前已初始化 ChromaDB（SQLite 连接），fork 后 worker 继承损坏的文件描述符，导致 `similarity_search` 死锁。

**解决方案**：
1. `lazy-apps = true` — Django app 在 worker fork 后加载
2. ChromaStore 单例（`get_chroma_store()`）
3. BgeSmallEmbedder 单例（`get_embedder()`）

## 8. Swagger API 文档

- `drf-spectacular==0.28.0`
- `DEBUG=True` 时自动开启，生产环境自动关闭
- 访问地址：`/v1/docs/` (Swagger UI), `/v1/schema/` (OpenAPI Schema)

## 9. 时区统一

- 所有容器 `TZ=Asia/Shanghai`
- Django `TIME_ZONE=Asia/Shanghai`, `USE_TZ=True`
- znginx log_format 含 `+0800`
- 前端 ChatMessage `formattedTime` 追加 `Z` 后缀修正 UTC 偏差
- `utils/time.js` `formatRelativeTime` 同样修正
