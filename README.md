# ZRAG — 个人 RAG 知识库系统

个人知识库问答系统。通过自然语言检索 macOS 备忘录等本地文档中的知识，由 LLM 生成带来源标注的回答。

## 架构

```
         ┌──────────────────────────────────┐
         │           Nginx :80              │
         │    (宿主机 :8080 → 容器 :80)      │
         │    URL: http://host:8080/zrag/   │
         └──────┬───────────────┬───────────┘
                ▼               ▼
         ┌──────────┐    ┌─────────────┐
         │ Frontend │    │  Backend    │
         │ :80      │    │  :5965      │
         │ Vue 3    │    │ Django+WSGI │
         └──────────┘    └──────┬──────┘
                                   │
                     ┌─────────────┼─────────────┐
                     ▼             ▼              ▼
               ┌─────────┐  ┌──────────┐  ┌──────────┐
               │  SQLite │  │ ChromaDB │  │ LLM Gate │
               │  FTS5   │  │ Vector   │  │ way      │
               └─────────┘  └──────────┘  └──────────┘
```

- **语言**: Python 3.10（后端）+ Vue 3（前端）
- **框架**: Django REST Framework + Vite
- **存储**: SQLite（FTS5 全文索引）+ ChromaDB（向量数据库）
- **Embedding**: BAAI/bge-small-zh-v1.5（512 维）
- **LLM**: LiteLLM Gateway（smart-router 负载均衡）

## 目录结构

```
ZRAG/
├── config/              # YAML 配置文件
│   ├── llm.yaml         # LLM Provider 配置
│   ├── embedding.yaml   # Embedding 模型配置
│   ├── ingest.yaml      # 文档摄入配置
│   ├── api.yaml         # API 鉴权配置
│   ├── storage.yaml     # 存储路径配置
│   └── retrieval.yaml   # 检索参数配置
├── zrag/                # 后端 Python 代码
├── frontend/            # 前端 Vue 3 项目
├── tests/               # 后端测试 (pytest)
├── data/                # 运行时数据 (SQLite + ChromaDB)
├── config/              # YAML 配置文件
├── Dockerfile.backend   # 后端容器构建
├── Dockerfile.frontend  # 前端容器构建
├── nginx.conf           # Nginx 反向代理配置
├── docker-compose.yml   # 三容器编排
├── entrypoint.sh        # 容器入口脚本
├── uwsgi.ini            # uWSGI 配置
└── requirements.txt     # Python 依赖
```

## 配置系统

### 三层加载

配置值按以下优先级确定（高覆盖低）：

1. **环境变量** — 运行时通过 `.env` 或 `docker compose run -e` 注入
2. **YAML 文件** — `config/*.yaml`，合并后加载
3. **代码默认值** — 构造函数的参数默认值

### YAML 配置文件

`config/` 目录下的 6 个文件按模块拆分，在 Django 启动时由 `load_config()` 合并为一个字典。

```yaml
# config/llm.yaml
llm:
  provider: "gateway"
  timeout: 200
  gateway:
    base_url: "${LLM_GATEWAY_URL:-http://localhost:4000/v1}"
    api_key: "${LITELLM_MASTER_KEY}"
    model: "smart-router"
```

### 环境变量覆盖

配置中的每个叶子节点都可被同名 UPPER_SNAKE 环境变量覆盖：

| 配置路径 | 环境变量 |
|---------|---------|
| `llm.timeout` | `LLM_TIMEOUT` |
| `llm.gateway.base_url` | `LLM_GATEWAY_BASE_URL` |
| `llm.gateway.api_key` | `LITELLM_MASTER_KEY` |
| `llm.gateway.model` | `LLM_GATEWAY_MODEL` |
| `embedding.cache_dir` | `EMBEDDING_CACHE_DIR` |
| `embedding.model_name` | `EMBEDDING_MODEL_NAME` |
| `storage.sqlite_path` | `STORAGE_SQLITE_PATH` |
| `storage.chroma_path` | `STORAGE_CHROMA_PATH` |
| `api.key` | `ZRAG_API_KEY` |
| `api.query_max_length` | `API_QUERY_MAX_LENGTH` |
| `ingest.batch_size` | `INGEST_BATCH_SIZE` |
| `retrieval.top_k` | `RETRIEVAL_TOP_K` |

环境变量值会根据 YAML 中该配置项的类型自动转换（int/float/bool/str）。

配置变更 === 改 `.env` → 重启（无需重建镜像）。

### 环境变量清单

| 变量 | 必需 | 默认值 | 说明 |
|------|:----:|--------|------|
| `ZRAG_API_KEY` | 是 | — | API 鉴权 Key |
| `LITELLM_MASTER_KEY` | 是 | — | LiteLLM Gateway Key |
| `DJANGO_SECRET_KEY` | 否 | dev-only-key | Django Secret Key |
| `LLM_GATEWAY_URL` | 否 | `http://localhost:4000/v1` | Gateway 地址 |
| `MODELS_DIR` | 否 | `/app/models` | Embedding 模型目录 |
| `LLM_GATEWAY_MODEL` | 否 | `smart-router` | 默认模型 |
| `DJANGO_DEBUG` | 否 | `True` | 调试模式 |
| `DJANGO_ALLOWED_HOSTS` | 否 | `localhost` | 允许的主机 |
| `DJANGO_TIME_ZONE` | 否 | `Asia/Shanghai` | 时区 |

## 本地开发

### 后端

```bash
# 1. 创建虚拟环境
python3.10 -m venv .venv
source .venv/bin/activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 设置 API Key（从你的配置获取）
export ZRAG_API_KEY=your-key
export LITELLM_MASTER_KEY=your-key

# 4. 初始化数据库
python manage.py migrate
python manage.py runserver 0.0.0.0:5965
```

### 前端

```bash
# 1. 安装依赖
cd frontend
npm install

# 2. 启动开发服务器（自动代理 API 到 :5965）
npm run dev
```

前端开发服务器默认在 `http://localhost:5173`，API 请求自动代理到后端 `:5965`。

### 测试

```bash
# 后端测试（pytest）
source .venv/bin/activate
python -m pytest tests/ -v

# 前端测试（vitest）
cd frontend && npm run test
```

## 容器部署

### 前提条件

1. Docker Engine >= 24.0
2. Embedding 模型已下载到本地（见下方说明）

### 模型下载

```bash
python -c "from sentence_transformers import SentenceTransformer; \
SentenceTransformer('BAAI/bge-small-zh-v1.5', cache_folder='./models')"
```

### 启动

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 ZRAG_API_KEY、LITELLM_MASTER_KEY 等

# 2. 构建并启动
docker compose up -d --build

# 3. 访问
open http://localhost:8080/zrag/
```

### 配置变更

任何配置变更只需修改 `.env` 文件后重启：

```bash
docker compose restart
```

无需重建镜像。如需变更 YAML 默认值（如 `batch_size`、`top_k`），则在 `.env` 中增加对应环境变量即可。

### 容器架构

| 容器 | 镜像 | 内部端口 | 说明 |
|------|------|:--------:|------|
| `nginx` | `nginx:alpine` | 80（容器内）→ 宿主机 :8080 | 反向代理 `/zrag/` → frontend:80, `/zrag/v1/` → backend:5965 |
| `frontend` | 自定义 `Dockerfile.frontend` | 80 | Vue 静态文件 |
| `backend` | 自定义 `Dockerfile.backend` | 5965 | Django + uWSGI |

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/v1/conversations` | 新建会话 + RAG 问答 |
| `POST` | `/v1/conversations/{id}/messages` | 继续对话 |
| `GET` | `/v1/conversations` | 会话列表 |
| `GET` | `/v1/conversations/{id}/messages` | 消息列表 |
| `DELETE` | `/v1/conversations/{id}` | 删除会话（幂等） |
| `POST` | `/v1/documents/ingest` | 触发文档摄入 |
| `GET` | `/v1/sources` | 来源列表 |
| `GET` | `/v1/health/live` | 存活检查 |
| `GET` | `/v1/health/ready` | 就绪检查 |

> **注意**: 生产环境通过 nginx 代理时，实际的 API 路径为 `http://localhost:8080/zrag/v1/...`，nginx 会自动将 `/zrag/` 前缀重写为后端路径。
> 开发环境直接通过 `http://localhost:5173/v1/...` 访问（Vite 代理自动转发到后端 `:5965`）。

所有 API 端点（除 health 外）需要在请求头中携带 `Authorization: Bearer <ZRAG_API_KEY>`。

## 技术栈

| 类别 | 选择 |
|------|------|
| 后端框架 | Django REST Framework |
| 前端框架 | Vue 3 + Vite + Tailwind CSS |
| 数据库 | SQLite (FTS5) + ChromaDB |
| Embedding | sentence-transformers (bge-small-zh-v1.5, 512d) |
| LLM Gateway | LiteLLM Gateway |
| 部署 | Docker 三容器 (Nginx + Frontend + Backend) |
| 配置 | YAML + 环境变量覆盖 |
