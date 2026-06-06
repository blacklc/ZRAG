# uWSGI 容器化部署要点

> 本文将 uWSGI 在 Docker 容器中运行时需要特别注意的要点进行了总结。
> 最后更新: 2026-06-06

---

## 容器化要点清单

### 🔴 高优先级

#### 1. `die-on-term = true`（必须添加）

**问题：** uWSGI 默认将 `SIGTERM` 信号视为"暴力重载（brutal reload）"，而不是优雅关闭。这与 Docker 容器的生命周期管理冲突——Docker 在停止容器时发送 `SIGTERM`，期望进程优雅退出。

**解决：** 在 `uwsgi.ini` 中添加：

```ini
die-on-term = true
```

这样当容器收到 `SIGTERM` 时，uWSGI 会：
1. 停止接收新请求
2. 等待正在处理的请求完成（受 `harakiri` 超时保护）
3. 正常退出

如果不用配置文件，也可以在启动命令中添加：`uwsgi --die-on-term --ini uwsgi.ini`

> 参考: [uWSGI 官方文档 — Things to Know](https://uwsgi-docs.readthedocs.io/en/latest/ThingsToKnow.html)

#### 2. 确保 uWSGI 是容器的 PID 1

**问题：** 如果使用 shell 形式的 CMD（如 `CMD uwsgi ...`）且 entrypoint 是一个 shell 脚本，则 shell 进程是 PID 1，uWSGI 是子进程。Docker 发送的 `SIGTERM` 会被 shell 消费掉，不会传递给 uWSGI。

**解决：** 使用 `exec` 形式确保 uWSGI 进程替换 shell 成为 PID 1：

```dockerfile
# 方式一：CMD exec 形式（推荐）
CMD ["uwsgi", "--ini", "/app/uwsgi.ini"]

# 方式二：entrypoint.sh 中最后一行使用 exec
ENTRYPOINT ["/app/entrypoint.sh"]
# entrypoint.sh 内容:
#   exec uwsgi --ini /app/uwsgi.ini
```

同时，在 docker-compose 中设置合适的 `stop_grace_period`：

```yaml
services:
  backend:
    stop_grace_period: 30s
```

> 参考: [Docker 官方文档 — ENTRYPOINT](https://docs.docker.com/reference/dockerfile/#entrypoint)

---

### 🟡 中优先级

#### 3. 日志输出到 stdout/stderr

**背景：** uWSGI 默认输出日志到 stdout/stderr，但通过 `logto` 配置可以重定向到文件。在容器环境中，日志应该输出到 stdout/stderr，由 Docker 日志驱动统一捕获。

当前项目配置（`uwsgi.ini`）：

```ini
logto = /app/log/uwsgi.log         # 将日志写入文件
req-logger = file:/app/log/uwsgi-req.log  # 请求日志也写入文件
```

**建议：** 如果希望 `docker logs` 能看到日志，移除 `logto` 配置即可恢复默认的 stdout/stderr 输出。如果当前有基于文件挂载的日志采集方案（如 filebeat、fluent-bit 读取挂载卷中的日志文件），也可以保持现状。

以下配置可实现日志分流：
- uWSGI 内部日志 → stderr
- 请求日志 → stdout

```ini
[uwsgi]
; 移除 logto 配置，默认就是 stdout/stderr
; 如果需要明确指定：
logger = stderr
req-logger = stdout
log-master = true
```

> 参考: [uWSGI 官方文档 — Logging](https://uwsgi-docs.readthedocs.io/en/latest/Logging.html)

#### 4. 健康检查

Docker 的 `HEALTHCHECK` 可以让编排平台（Kubernetes、Docker Swarm）感知服务状态。

在 `Dockerfile.backend` 中添加：

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:5965/health/ || exit 1
```

或在 `docker-compose.yml` 中：

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:5965/health/"]
  interval: 30s
  timeout: 5s
  retries: 3
  start_period: 30s
```

前提是 Django 项目中存在 `/health/` 端点。

> 参考: [Docker 官方文档 — HEALTHCHECK](https://docs.docker.com/reference/dockerfile/#healthcheck)

#### 5. `http` vs `http-socket` 选型

**背景：** uWSGI 提供两种 HTTP 暴露方式：

| 选项 | 行为 | 适用场景 |
|------|------|---------|
| `http = 0.0.0.0:5965` | 启动一个**额外的 HTTP 路由/代理进程**作为"盾牌"挡在 worker 前面 | uWSGI **直接对外暴露**给公网 |
| `http-socket = 0.0.0.0:5965` | worker **直接原生解析 HTTP**，没有额外路由进程 | uWSGI 部署在**反向代理后面**（nginx、traefik、Kubernetes Ingress） |

官方原文：

> "The first one [`http`] spawns an additional process forwarding requests to a series of workers (think about it as a form of shield, at the same level of apache or nginx), while the second one [`http-socket`] sets workers to natively speak the http protocol."

**对当前项目的分析：** 你的 docker-compose 中已移除 nginx，uWSGI 直接暴露 5965 端口。因此当前使用 `http` 是正确的——多一层的"盾牌"进程在直接暴露的场景下能提供更好的安全性和稳定性。

如果未来在 uWSGI 前面加了一层反向代理（如 nginx、traefik），应根据反向代理的能力改用：

```ini
; 反向代理支持 uwsgi 协议（nginx uwsgi_pass）:
socket = 0.0.0.0:5965

; 反向代理只支持 HTTP（如 traefik、cloudflare tunnel）:
http-socket = 0.0.0.0:5965
```

> 参考: [uWSGI 官方文档 — HTTP 支持](https://uwsgi-docs.readthedocs.io/en/latest/HTTP.html)、[Things to Know](https://uwsgi-docs.readthedocs.io/en/latest/ThingsToKnow.html)

#### 6. `harakiri` 配置详解

**作用：** 当某个 worker 处理请求超过设定时间时，强制终止该 worker 并回收，防止 worker 永远卡死。

**当前值 `harakiri = 300`（5分钟）的合理性：**

| 场景 | 推荐值 | 说明 |
|------|--------|------|
| 通用 API 服务 | 30-60s | 常规请求不应超过 1 分钟 |
| 含长耗时操作（大文件上传、AI 推理） | 180-300s | ZRAG 涉及 LLM 调用属于这一类 |
| 含流式响应（SSE、WebSocket） | 不设置或单独处理 | harakiri 会中断长连接 |

ZRAG 涉及 RAG 查询和 LLM 调用，当前 300s 是合理的。但如果后期实现了**流式响应输出**，建议降到 60-120s。

**建议补充的配置：**

```ini
harakiri = 300
harakiri-verbose = true   ; 记录 harakiri 触发时的详细请求信息，便于排查慢请求
```

`harakiri-verbose` 在 harakiri 触发时会输出类似以下日志，帮助定位慢请求的端点：

```
HARAKIRI !!! worker 1 status !!!
HARAKIRI [core 0] 10.0.0.1 - GET /api/chat/stream since 1717600000
DAMN ! worker 1 (pid: 15) died, killed by signal 9 :(
```

**harakiri 与 `stop_grace_period` 的关系：**

```
stop_grace_period  >  harakiri + 少量缓冲
```

即 docker-compose 中的 `stop_grace_period` 必须大于 `harakiri` 的值，否则容器会在 harakiri 触发前被强制杀死。例如：

```yaml
services:
  backend:
    stop_grace_period: 60s   # > harakiri(30s) + 缓冲
```

对于当前 `harakiri = 300`，`stop_grace_period` 至少应设为 310s（约 5 分 10 秒）。

> 参考: [uWSGI 官方文档 — Options](https://uwsgi-docs.readthedocs.io/en/latest/Options.html)

#### 7. `buffer-size` 生产建议

虽然不是容器特有的要求，但生产环境建议增大默认的请求头缓冲区：

```ini
buffer-size = 32768
```

默认值 4096 字节可能不够，当请求头较大（如 Cookie 较长）时会导致截断。

> 参考: [uWSGI 官方文档 — Options](https://uwsgi-docs.readthedocs.io/en/latest/Options.html)

---

### ✅ 已就绪的配置

以下是当前项目中已经做对的容器化配置：

| 配置 | 值 | 说明 |
|------|-----|------|
| `master = true` | ✅ | master 进程模式，管理 worker 和信号 |
| `processes = 1` | ✅ | 单进程 + 水平扩展，适合容器部署 |
| `vacuum = true` | ✅ | 退出时自动清理 socket 和 pid 文件 |
| `harakiri = 300` | ✅ | 适合 LLM 调用等长耗时场景，建议补充 `harakiri-verbose = true` |
| `http = 0.0.0.0:5965` | ✅ | 当前无反向代理，`http` 提供额外的"盾牌"路由进程，选择正确 |
| 多阶段构建 | ✅ | builder 阶段编译 → runtime 阶段只复制产物 |
| `--no-install-recommends` | ✅ | 减小镜像体积 |

---

## 修正说明

本文档的初版曾包含以下错误，已于 2026-06-06 修正：

- ~~错误引用不存在的外部文档 URL~~ — 已全部替换为可访问的官方文档链接
- ~~错误认为 `master = true` 就能自动处理 SIGTERM~~ — 实际需要 `die-on-term = true` 显式配置
- ~~建议中混入非容器化特有的通用配置~~ — 已归类和标注

---

## 参考资料

1. [uWSGI 官方文档 — Things to Know](https://uwsgi-docs.readthedocs.io/en/latest/ThingsToKnow.html) — SIGTERM 默认行为说明，容器环境需 `die-on-term`；`http` vs `http-socket` 差异
2. [uWSGI 官方文档 — HTTP 支持](https://uwsgi-docs.readthedocs.io/en/latest/HTTP.html) — `http` 与 `http-socket` 的详细对比
3. [uWSGI 官方文档 — Logging](https://uwsgi-docs.readthedocs.io/en/latest/Logging.html) — 日志配置，默认 stdout/stderr
4. [uWSGI 官方文档 — Options](https://uwsgi-docs.readthedocs.io/en/latest/Options.html) — 全部配置参数说明，含 `harakiri`、`buffer-size` 等
5. [Docker 官方文档 — ENTRYPOINT](https://docs.docker.com/reference/dockerfile/#entrypoint) — exec 形式与信号传递
6. [Docker 官方文档 — HEALTHCHECK](https://docs.docker.com/reference/dockerfile/#healthcheck) — 健康检查
7. [Docker 官方文档 — Python 容器化指南](https://docs.docker.com/language/python/containerize/) — Docker 官方 Python 容器化通用指南
