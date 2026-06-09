# ZRAG 前端与部署运维 设计记录

> 分类索引: [QA 文档目录](index.md)

## Q33: Web UI 方案设计

**用户**: Web UI 要前后端分离，使用 Vue 实现 Apple 风格 UI。对前端不熟悉，需要多提供备选方案。

### 架构调整

原架构总览中的 `Jinja2 + Vanilla JS` 改为前后端分离：

```
浏览器                             Django 后端
┌──────────────────────────┐      ┌──────────────────┐
│ Vue 3 + Vite             │ HTTP │ DRF              │
│ ├─ Vue Router            │────→ │ ├─ REST API      │
│ ├─ Tailwind CSS          │ SSE  │ └─ SSE (Phase 2) │
│ └─ fetch / ReadableStream│←──── │                  │
└──────────────────────────┘      └──────────────────┘
```

### 技术栈选型

| 环节 | 方案 | 备选 | 理由 |
|------|------|------|------|
| 构建工具 | **Vite** | webpack | Vue 官方推荐，无争议 |
| CSS | **Tailwind CSS** | Element Plus, Naive UI | Apple 风格（毛玻璃/大圆角/柔和阴影）用 Tailwind 内置类名最自然。组件库默认风格偏企业，覆写成本高 |
| 图标库 | **Lucide Icons** | Heroicons | Apple 风格线性图标 |
| 路由 | **Vue Router** | — | 官方配套 |
| 状态管理 | **Vue 内置 reactive/ref** | Pinia | 场景简单，无需额外依赖 |
| HTTP 请求 | **fetch** | axios | 浏览器内置，零依赖 |
| Markdown 渲染 | **marked + highlight.js** | markdown-it | 轻量，代码高亮 |
| SSE 流式（Phase 2）| **fetch + ReadableStream** | EventSource | EventSource 仅支持 GET，无法传 POST body |
| UI 组件库 | **不使用** | Element Plus, Naive UI | Apple 风格极简，手写组件代码量小，不引入对抗式样式覆写 |

### Apple 风格关键实现

```css
/* 毛玻璃导航栏 */
nav { @apply bg-white/70 backdrop-blur-xl border-b border-gray-200/50; }

/* 圆角卡片 */
.card { @apply rounded-2xl shadow-sm bg-white; }

/* SF 系统字体 */
body { font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 
       'Helvetica Neue', sans-serif; }

/* 输入框 */
input { @apply rounded-xl border border-gray-200 bg-gray-50/50 
              focus:bg-white focus:ring-2 focus:ring-blue-500/20; }
```

### 页面设计

**聊天主页 `/`**：
- 左侧：会话历史列表（切换、删除，按最近消息时间排序）
- 中间：消息列表（AI 消息带 Markdown 渲染 + 来源标注）
- 底部：输入框 + 发送按钮 + 模型选择器
- 顶部：毛玻璃导航栏（聊天 / 源管理入口）

**源管理 `/sources`**：
- 源状态卡片 + 触发摄入按钮 + 最近导入记录

### 文件结构

```
frontend/
├── index.html
├── package.json
├── vite.config.js
├── src/
│   ├── main.js
│   ├── App.vue
│   ├── router/index.js
│   ├── api/index.js            # fetch 封装 + API 调用
│   ├── views/
│   │   ├── ChatView.vue
│   │   └── SourcesView.vue
│   ├── components/
│   │   ├── NavBar.vue          # 毛玻璃导航栏
│   │   ├── ChatInput.vue       # 输入框 + 模型选择器
│   │   ├── ChatMessage.vue     # 消息气泡 + Markdown 渲染
│   │   ├── ChatSidebar.vue     # 历史对话列表
│   │   └── SourceCard.vue      # 源状态卡片
│   ├── composables/
│   │   ├── useChat.js          # 聊天逻辑
│   │   └── useConversation.js  # 对话管理
│   └── assets/
│       └── style.css
```

### 依赖

```json
{
  "dependencies": {
    "vue": "^3.4",
    "vue-router": "^4.3",
    "marked": "^12.0",
    "highlight.js": "^11.9"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.0",
    "vite": "^5.4",
    "tailwindcss": "^3.4"
  }
}
```

### 开发部署

- 开发时：`python manage.py runserver` + `npm run dev`（Vite proxy 转发 `/v1/*` 到 Django）
- 部署时：`npm run build` → `dist/` 静态文件

### 细化设计决策

以下是在 grill-me 流程中逐一确认的全部 Web UI 细节：

**深色模式**:
- 手动切换（方案 C），切换按钮 → 导航栏右侧 ☀️/🌙 图标
- 用户偏好存 localStorage，下次打开自动恢复
- 深色模式切换时，highlight.js 代码高亮主题跟随切换：浅色 → `github`，深色 → `github-dark`

**键盘快捷键**:
- `Enter` — 发送消息
- `Shift + Enter` — 换行
- `Cmd + K` — 新建对话
- `Cmd + /` — 聚焦输入框

**API Key**:
- 方案 A：构建时注入。`.env` 文件 `VITE_API_KEY=sk-xxxx`，Vite 构建时将 `import.meta.env.VITE_API_KEY` 替换为字面量
- 前端 JS 代码直接使用，无需用户手动输入

**输入框**:
- textarea 初始单行，内容多了自动增高（max 6 行）
- 占位符："向你的知识库提问"

**AI 回复加载状态**:
- 三个跳动的圆点（类似 ChatGPT 打字指示器），发完消息后显示，AI 回复返回后替换为实际内容

**首次打开/空状态**:
- 无对话时聊天区中间显示 ZRAG 标志 + "向你的知识库提问"
- 左侧会话列表为空时灰色小字"暂无对话，开始提问吧"
- 打开页面时显示空状态（不自动选中任何对话）

**消息气泡**:
- AI 消息右上角悬浮复制按钮
- AI 消息下方来源标注：`📎 来源: 机器学习笔记、深度学习入门`（方案 A 文字链接，灰字小号，来源只展示 doc_title）
- 点击来源暂不实现

**消息滚动**:
- 新消息/AI 回复时自动 scrollToBottom
- 用户手动上滚查看历史时不强制跳回

**删除对话**:
- 悬停显示删除按钮 → 弹出确认弹窗"确定删除此对话？"
- 确认删除后：如果删除的是当前正在查看的对话 → 跳转到空状态（方案 A）

**代码高亮**:
- marked.js 渲染 Markdown，highlight.js 做代码块语法高亮
- 深色/浅色模式切换时自动切换高亮主题

**404 页面**:
- Vue Router 兜底路由 `/:pathMatch(.*)*` → Apple 风格极简 404 组件（方案 B）

**Favicon**:
- 极简 SVG 或 📚 emoji 作为标签页图标（方案 B）

**浏览器标题**:
- 固定显示 "ZRAG"（方案 A）

**Vue Router 模式**:
- History 模式，URL 干净无 `#`，Nginx `try_files $uri /index.html`

**响应式布局**:
- 桌面端标准布局，移动端侧边栏可折叠、消息区弹性宽度（方案 B）

**源管理页交互**:
- 两个按钮："增量导入" + "全量导入"（方案 A）
- 全量导入：请求 `{"source_type": "mac_notes", "full": true}`，后端清空该 source_type 的 processed_docs 后重新处理
- 点击后显示不确定进度条（Apple 风格灰色流动条纹，方案 A）
- 摄入完成后用 IngestReport 直接更新 UI，失败时回退调 `GET /v1/sources`（方案 B + 兜底 A）

**API 调用失败处理**:
- 网络断/500 → Toast 通知（右上角短暂弹出）
- 对话相关错误 → 红色消息气泡插入聊天区

**设置面板**:
- 不需要。导航栏只放 ☀️/🌙 切换和 📊 源管理入口

**消息复制**:
- 气泡右上角悬浮复制图标，点击复制整条消息

### 部署架构

**三容器方案**（Nginx + Frontend + Backend）:
- Nginx 容器（80:80，唯一对外入口）→ `/` 代理到 Frontend 容器（内部 80，expose），`/v1/*` 代理到 Backend 容器（内部 5965，expose）
- Frontend 容器：`nginx:alpine + dist/`
- Backend 容器：`gunicorn :5965`
- 生产环境：`npm run build` → dist/ 打进 Frontend 镜像 → 容器化部署
- 开发环境：`npm run dev`（Vite Dev Server localhost:5173）+ `python manage.py runserver`（localhost:8000），Vite proxy 转发 `/v1/*`

### 待确认
- Vue 项目初始化方式（手动创建 vs 实现阶段自动生成）


---

## Q34: 部署与运维设计

**用户**: 部署方式是什么？需要 CI/CD 吗？

**决策**: 本机 Docker Desktop，三容器方案，不需要 CI/CD。手动 `docker compose build && up -d` 更新。

**用户**: 三容器之间怎么通信？

**决策**: docker-compose 默认创建网络，容器名即主机名。Nginx 通过 `proxy_pass http://backend:5965` 和 `proxy_pass http://frontend:80` 转发。Backend 不对外暴露端口（仅 expose），Frontend 同理，只有 Nginx 将 8080 映射到宿主机（避免 80 端口冲突）。

### 容器架构

```
┌──────────────────────────────────────────┐
│  Nginx (8080→80, 唯一对外入口)             │
│    ├── /     → Frontend (内部 80)          │
│    └── /v1/* → Backend (内部 5965)         │
├──────────────────────────────────────────┤
│  Frontend (expose 80)                    │
│    └── nginx:alpine + dist/              │
├──────────────────────────────────────────┤
│  Backend (expose 5965)                   │
│    ├── uWSGI + Django                    │
│    ├── volumes: data/, models/, logs/    │
│    └── entrypoint.sh                     │
└──────────────────────────────────────────┘
```

### docker-compose.yml

```yaml
services:
  nginx:
    image: nginx:alpine
    ports:
      - "8080:80"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
    depends_on:
      frontend:
        condition: service_healthy
      backend:
        condition: service_healthy
    restart: unless-stopped
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
    deploy:
      resources:
        limits:
          memory: 64M
          cpus: "0.5"

  frontend:
    build:
      context: .
      dockerfile: Dockerfile.frontend
    expose:
      - "80"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:80/"]
      interval: 10s
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
    deploy:
      resources:
        limits:
          memory: 64M
          cpus: "0.5"

  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    expose:
      - "5965"
    volumes:
      - ./data:/app/data
      - ./models:/app/models:ro
      - ./logs:/app/log
    environment:
      - LLM_GATEWAY_URL=${LLM_GATEWAY_URL}
      - LLM_GATEWAY_MODEL=${LLM_GATEWAY_MODEL}
      - ZRAG_API_KEY=${ZRAG_API_KEY}
      - DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY}
      - DJANGO_DEBUG=${DJANGO_DEBUG:-False}
      - DJANGO_ALLOWED_HOSTS=${DJANGO_ALLOWED_HOSTS:-localhost}
      - DJANGO_TIME_ZONE=${DJANGO_TIME_ZONE:-Asia/Shanghai}
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5965/v1/health/live"]
      interval: 10s
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: "2"
```

### .env 文件

```bash
ZRAG_API_KEY=sk-xxxx
LLM_GATEWAY_URL=http://host.docker.internal:4000/v1
LLM_GATEWAY_MODEL=smart-router
DJANGO_SECRET_KEY=<python -c "import secrets; print(secrets.token_urlsafe(50))">
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=localhost
DJANGO_TIME_ZONE=Asia/Shanghai
```

### entrypoint.sh

```bash
#!/bin/sh
set -e
python manage.py migrate --no-input
python manage.py collectstatic --no-input
exec "$@"
```

> 建表初始化（`CREATE TABLE IF NOT EXISTS`）由 AppConfig.ready() 自动执行，无需 management command。

### nginx.conf

```nginx
server {
    listen 80;
    gzip on;
    gzip_types text/css application/javascript;

    location / {
        proxy_pass http://frontend:80;
        proxy_set_header Host $host;
    }

    location /v1/ {
        proxy_pass http://backend:5965;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Request-ID $request_id;
        proxy_read_timeout 180s;
        proxy_connect_timeout 10s;
    }
}
```

### uwsgi.ini

```ini
[uwsgi]
module = zrag.wsgi:application
master = true
processes = 1
http = 0.0.0.0:5965
harakiri = 180
vacuum = true
```

### Dockerfile.backend

```dockerfile
FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY zrag/ ./zrag/
COPY config/ ./config/
COPY manage.py .
COPY uwsgi.ini .
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

EXPOSE 5965
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uwsgi", "--ini", "/app/uwsgi.ini"]
```

### Dockerfile.frontend

```dockerfile
FROM node:22-alpine AS builder
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ARG VITE_API_KEY
ENV VITE_API_KEY=$VITE_API_KEY
RUN npm run build

FROM nginx:alpine
COPY --from=builder /src/dist/ /usr/share/nginx/html/
EXPOSE 80
```

### .dockerignore

```
node_modules/
.git/
data/
__pycache__/
*.pyc
.venv/
venv/
.env
.DS_Store
*.log
models/
logs/
```

### Embedding 模型管理

部署前宿主机预下载模型：

```bash
pip install sentence-transformers
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-zh-v1.5', cache_folder='./models')"
```

容器通过只读 volume 加载：

```yaml
volumes:
  - ./models:/app/models:ro
```

配置指定路径：

```yaml
# config/embedding.yaml
embedding:
  model_name: "BAAI/bge-small-zh-v1.5"
  cache_dir: "/app/models"
```

### 启动流程

```bash
# 首次部署
# 1. 预下载模型
pip install sentence-transformers
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-zh-v1.5', cache_folder='./models')"

# 2. 创建 .env 并填入配置
# 3. 启动
docker compose up -d

# 更新代码后
docker compose build backend && docker compose up -d     # 只改后端
docker compose build frontend && docker compose up -d    # 只改前端
docker compose build && docker compose up -d             # 全部重建
```

### 日志管理

| 日志类型 | 处理方式 |
|----------|---------|
| uWSGI 访问/错误日志 | stdout/stderr → docker logs |
| Django 业务日志 | stdout + volume `./logs:/app/log` 持久化 |
| Nginx 入口日志 | stdout → docker logs |
| Frontend Nginx 日志 | stdout → docker logs |
| Vue 客户端 JS 错误 | 浏览器 console，服务端不管理 |
| 日志轮转 | json-file, 10MB × 3 file |

### 运维决策汇总

| 决策项 | 结论 |
|--------|------|
| 部署目标 | 本机 Docker Desktop |
| CI/CD | 不需要，手动构建更新 |
| 容器架构 | 三容器：Nginx + Frontend + Backend |
| 对外端口 | 8080（避免 80 冲突） |
| Backend 端口 | 5965（内部 expose） |
| 启动顺序 | health check + depends_on，Frontend 和 Backend 就绪后 Nginx 才接受请求 |
| WSGI Server | uWSGI（与 zonebank 一致） |
| Worker 数量 | 1（个人工具，无并发需求） |
| Harakiri 超时 | 180 秒（LLM 调用可能慢） |
| Nginx 代理 | proxy_read_timeout 180s, proxy_connect_timeout 10s |
| 环境变量 | .env 文件 + docker-compose `${VAR}` 引用 |
| Django DEBUG | .env 控制，默认 False |
| ALLOWED_HOSTS | .env 控制，默认 localhost |
| SECRET_KEY | .env 管理，`secrets.token_urlsafe(50)` 生成 |
| 时区 | Asia/Shanghai |
| 数据库迁移 | entrypoint.sh 自动执行 migrate，建表由 AppConfig.ready() 自动完成（`CREATE TABLE IF NOT EXISTS`） |
| 静态文件 | entrypoint.sh 自动执行 collectstatic |
| 日志限制 | json-file，10MB × 3 |
| 重启策略 | unless-stopped |
| 资源限制 | Backend 512M/2CPU，Frontend 64M/0.5CPU，Nginx 64M/0.5CPU |
| 业务日志 | stdout + volume 持久化到 ./logs/ |
| 前端日志 | 全部 stdout → docker logs |
| Docker 网络 | compose 默认自动管理 |
| 数据持久化 | ./data:/app/data（zrag.db + chroma_db + django.db） |
| 模型管理 | 宿主机预下载 → ./models:/app/models:ro |
| 镜像更新 | docker compose build \<service\> && docker compose up -d |
| Gunicorn | 替换为 uWSGI（用户指定） |

---

## Q36: 容器镜像跨平台构建失败问题

**用户**: Docker 构建 `zrag-backend` 反复失败，pip install `requirements.txt` 依赖冲突。

**现象**: macOS `pip freeze` 生成的 `requirements.txt`（105 行全 `==` 锁定）拷贝进 Linux Docker 构建时：
1. `sentence-transformers==5.5.1` 在 Linux 上依赖 `torch>=2.12.0`（~532 MB），但 pip 又回溯到 `sentence-transformers 3.1.0`（要求 `numpy<2.0.0`，与锁定的 `numpy==2.2.6` 冲突）→ `ResolutionImpossible`
2. 同时拉取了 nvidia-cublas（423 MB）、cudnn（366 MB）、triton（201 MB）等 CUDA 库，合计约 2 GB，且全部为 CPU-only 部署不需要的包
3. `aiohttp` 下载不完整导致 hash 校验失败（间歇性网络问题）

**根因**:

requirements.txt 中 40+ 个 Python 包包含 C/Rust/Fortran 原生编译扩展（如 `torch`、`onnxruntime`、`tokenizers`、`orjson`、`grpcio`）。根据 PEP 427（Wheel 二进制分发格式规范）和 PEP 425（兼容性标签规范），wheel 文件名的 `platform tag` 字段决定了该 wheel 的适用平台：

- macOS arm64: `torch-2.2.2-cp310-cp310-macosx_11_0_arm64.whl`（链接 Apple MPS/Accelerate）
- Linux x86_64: `torch-2.2.2-cp310-cp310-manylinux_2_28_x86_64.whl`（链接 CUDA/cuBLAS）

同一个 `==` 版本号在两个平台上对应**不同的 .whl 文件**，且各自声明的传递依赖列表不同（Linux 版需要 nvidia-cublas 等，macOS 版不需要）。

`pip freeze` 锁定的是**版本号字符串**，而非平台特定的 wheel 指纹。它无法捕捉同一版本号在不同平台上依赖链的差异。

**决策**:

1. **精简 `requirements.txt`**: 从 105 行全锁定改为 7 个核心生产直接依赖 `==` 锁定：
   ```
   djangorestframework==3.17.1
   django-cors-headers==4.9.0
   chromadb==1.5.9
   sentence-transformers==5.5.1
   openai==2.40.0
   uwsgi==2.0.31
   PyYAML==6.0.3
   ```
   传递依赖（torch、numpy、tokenizers、grpcio 等 80+ 包）交由 `pip install` 在 Linux 容器内根据目标平台自行解析版本。

2. **Dockerfile.backend 安装 curl**: `python:3.10-slim` 基础镜像不含 curl，导致 docker-compose healthcheck 的 `curl -f` 命令失败。在 runtime 阶段 `apt-get install curl`。

3. **日志路径修正**: `zrag/settings.py` LOGGING 配置中 `filename` 从 `BASE_DIR / 'logs'` 改为 `BASE_DIR / 'log'`，与 Dockerfile 的 `mkdir -p /app/log` 对齐。

4. **views.py 延迟导入**: `BgeSmallEmbedder` 和 `ChromaStore` 从文件顶部 import 改为函数内懒加载，避免 Django 启动时加载 `sentence-transformers`（重依赖）导致模块导入失败。

**验证结果**:

```
$ docker ps --format "table {{.Names}}\t{{.Status}}" | grep zrag
zrag-backend     Up (healthy)
zrag-frontend    Up (healthy)

$ curl -s -o /dev/null -w "%{http_code}" http://localhost/zrag/v1/health/live
200
```

**相关提交**: `(待提交)`

---

## Q37: 后端日志分级拆分

**用户**: 后端日志按级别拆分为独立文件，文件名去掉项目前缀。

**需求来源**:
1. `@.claude/rules/python-code-style.md` 第 184 行: "不同级别的日志应该存储在独立的日志文件中"
2. 用户要求文件名去掉 `zrag-` 前缀

**实现**: `zrag/settings.py` 的 `LOGGING` 配置拆分为 4 个文件 handler + 1 个 console handler:

| 文件 | 级别 | Handler |
|------|------|---------|
| console (stdout) | DEBUG+ | `logging.StreamHandler` |
| `debug.log` | 仅 DEBUG | `TimedRotatingFileHandler` + `ExactLevelFilter` |
| `info.log` | 仅 INFO | `TimedRotatingFileHandler` + `ExactLevelFilter` |
| `warning.log` | 仅 WARNING | `TimedRotatingFileHandler` + `ExactLevelFilter` |
| `error.log` | 仅 ERROR+CRITICAL | `TimedRotatingFileHandler` + `ExactLevelFilter` |

**新建文件**: `zrag/log_filter.py` — `ExactLevelFilter` 类，继承 `logging.Filter`，实现精确日志级别匹配。Django LOGGING 配置不支持内联 lambda，必须独立文件。

**验证结果**: 容器启动后 `/app/log/` 下 4 个文件全部创建。`debug.log` 包含 chromadb 初始化 DEBUG 日志，其余文件初始为空。

**镜像体积注意**: 本次构建耗时约 18 分钟（torch 532MB + nvidia 系列 CUDA 包 ~2GB），镜像较大。CPU-only 部署场景可后续改为 CPU-only torch（`--index-url https://download.pytorch.org/whl/cpu`）以减少约 2GB 体积。

---

## Q37: Prompt 模板引擎选型

**日期**: 2026-06-08

**用户**: prompt 模版定义在何处？推荐一种常用的模版形式。

**分析**:
- 当前 SYSTEM_PROMPT 硬编码在 `zrag/retrieval/prompt_builder.py` 中，使用 Python 字符串拼接
- 业界主流方案是 Jinja2：LangChain、LlamaIndex、vLLM 的 chat template 均基于 Jinja2
- Jinja2 支持条件渲染、循环、过滤器，可读性和可维护性远优于字符串拼接
- 将模板文件独立存放，方便非开发人员调试和调整 prompt

**决策**: 采用 **Jinja2** 作为 prompt 模板引擎

**实现**:
```
zrag/prompts/
└── chat_system.j2          # 系统提示词模板

zrag/retrieval/prompt_builder.py  # 改为 FileSystemLoader + template.render()
```

**模板内容** (`chat_system.j2`):
```jinja2
你是一个个人知识库助手。请基于以下参考材料回答用户问题。
如果参考材料中没有相关信息，请如实告知。

参考材料:
{% if reference_materials -%}
{% for doc in reference_materials -%}
[来源: {{ doc.doc_title }}]
{{ doc.content }}

{% if not loop.last -%}
---
{% endif %}
{%- endfor %}
{%- else -%}
（暂无参考材料）
{%- endif %}
```

**关键点**:
- `reference_materials` 传入检索结果列表，每条含 `doc_title` 和 `content`
- 无结果时显示「暂无参考材料」，LLM 知晓知识库为空
- 多条记录间用 `---` 分隔
- Jinja2 随 Django 内置可用，无需额外安装

---
