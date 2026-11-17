# ADR 0001: ChromaDB 迁移为独立 HTTP 服务

- **状态**: Proposed（提案，尚未实施）
- **日期**: 2026-06-19（取自原方案文档 `docs/chromadb-http-server.md` 的最后更新日期与文件系统修改时间；该文件此前未纳入 git 跟踪，`git log` 中无对应记录）
- **决策者**: 项目维护者
- **相关文档**: [design.md 第 3.2 节「ChromaDB 向量存储」](../design.md#32-chromadb-向量存储)、[QA/storage-embedding.md](../QA/storage-embedding.md)、[ADR 索引](README.md)
- **来源**: 本 ADR 由原方案文档 `docs/chromadb-http-server.md` 整理而来，原文件已由本记录取代并移除

---

## 背景

ZRAG 当前的向量存储采用 ChromaDB 的嵌入式模式。ChromaDB 版本为 1.5.9，运行在后端容器内部，由 `zrag/store/vector_store.py` 中的 `ChromaStore` 类通过 `chromadb.PersistentClient(path=..., settings=...)` 实例化客户端，直接读写本地 SQLite 文件。数据存储路径为 `data/chroma_db`，在容器内映射为 `/app/data/chroma_db`，持久化依赖 `docker-compose.yml` 中的 `./data/pro:/app/data` 卷声明。

Django 应用启动时，`zrag/apps.py` 的 `ZragConfig.ready()` 方法会调用 `get_chroma_store(persist_dir=chroma_path).init_collection()` 完成 Collection 初始化。结合 [design.md](../design.md) 第 1.4.4 节与第 3.2 节的说明，这套嵌入式方案是为「单用户、文档量低于 1000 篇、隐私优先」的定位刻意选择的：它不需要独立服务进程，复制目录即可备份，并且通过 `lazy-apps = true` 配合 Collection 延迟初始化，规避了 uWSGI prefork 模式下 SQLite 文件描述符跨进程共享的问题。

但嵌入式模式也带来了三项结构性限制：

- **无 HTTP 接口**：外部可视化工具（如 ChromaDB Viewer）无法连接查看向量数据。
- **与后端进程强耦合**：ChromaDB 的生命周期完全依赖于 Django 进程，后端重启或异常会同时影响向量库的可用性。
- **不利于独立运维**：无法单独对向量数据库进行监控、备份和扩缩容。

因此产生了「是否将 ChromaDB 拆分为独立 HTTP 服务」这一决策议题。需要强调的是，该迁移改变的是 ChromaDB 的部署形态与客户端连接方式，不涉及向量数据库产品的更换，也不改变 Collection 的数据结构。

---

## 决策

采用「新增独立 chroma 容器」的方案：新建一个 chroma 容器运行 ChromaDB Server，后端改用 `chromadb.HttpClient` 连接。该方案在架构上与 ChromaDB 官方推荐的 client/server 模式一致，使 chroma 与后端解耦，并便于接入可视化工具。

### 架构变化

**变更前容器拓扑：**

```
+-------------------+       +---------------------------+
|    frontend       |       |        backend            |
|                   |       |  (django + chromadb       |
|                   | <---> |   PersistentClient)       |
|                   |       |  直接读写 data/chroma_db  |
+-------------------+       +---------------------------+
```

**变更后容器拓扑：**

```
+-------------------+       +-------------------+       +-------------------+
|    frontend       |       |     backend       |       |     chroma        |
|                   |       | (django +         |       | (ChromaDB Server  |
|                   | <---> |  chromadb         | <---> |  PersistentClient)|
|                   |       |  HttpClient)      |       | 读写 data/chroma  |
+-------------------+       +-------------------+       |        _db        |
                                                        +-------------------+
```

### 核心变更点

| 组件 | 变更前 | 变更后 |
|------|--------|--------|
| ChromaDB 部署形式 | embedded（嵌入后端容器） | 独立 chroma 容器 |
| Python 客户端 | `chromadb.PersistentClient` | `chromadb.HttpClient` |
| 数据读写 | 直接操作 SQLite 文件 | 通过 HTTP API 调用 |
| Collection 初始化 | `apps.py` 中调用 `init_collection()` | ChromaDB Server 自动管理 |

### 数据兼容性

ChromaDB Server 底层同样使用 `PersistentClient` 加 SQLite 作为存储引擎，数据文件格式与嵌入式模式完全一致。因此只需将同一份 `data/chroma_db` 目录挂载到 chroma 容器，即可直接使用。

**现有数据无需任何迁移**。现有的 Collection（名称为 `zrag_docs`，距离函数为 Cosine）在迁移后无缝兼容。

### 关键约束

- **不能同时使用 `PersistentClient` 和 ChromaDB Server 访问同一 SQLite 文件**：SQLite 为进程级锁，同时访问会引发 `database is locked` 错误。
- 后端代码必须从 `PersistentClient` 完全切换为 `HttpClient`，不能同时保留两种客户端实例。
- 一个 ChromaDB Server 进程只能管理一个 `--path` 目录（当前场景只需一个 Collection，完全够用）。

### 实施方案

#### docker-compose.yml 变更

新增 `chroma` 服务配置：

```yaml
services:
  chroma:
    image: chromadb/chroma:1.5.9
    container_name: zrag-chroma
    volumes:
      - ./data/pro:/app/data
    command: chroma run --path /app/data/chroma_db --host 0.0.0.0 --port 8000
    expose:
      - "8000"
    ports:
      - "8000:8000"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v2/heartbeat"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 15s
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: "2"
```

需要在 backend 服务的 `depends_on` 中添加 chroma 容器，并等待其健康检查通过：

```yaml
services:
  backend:
    depends_on:
      chroma:
        condition: service_healthy
    # ... 其余配置不变
```

#### vector_store.py 变更

**`ChromaStore.__init__()` 修改**：删除 `persist_dir` 参数和 `chromadb.PersistentClient` 的创建逻辑，改为从环境变量读取连接信息，使用 `chromadb.HttpClient`。

```python
import os
import chromadb

class ChromaStore:
    """向量存储服务

    连接远程 ChromaDB Server 进行向量数据的写入和检索。
    通过环境变量 CHROMA_HOST 和 CHROMA_PORT 配置连接地址。
    """

    def __init__(self):
        """初始化 ChromaDB HTTP 客户端

        从环境变量读取 ChromaDB Server 的连接地址，
        默认连接 localhost:8000。
        """
        host = os.getenv("CHROMA_HOST", "localhost")
        port = int(os.getenv("CHROMA_PORT", "8000"))
        self.client = chromadb.HttpClient(host=host, port=port)
        self.collection = None
```

**`init_collection()` 保持原有逻辑不变**：

```python
    def init_collection(self, name: str = "zrag_docs") -> chromadb.Collection:
        """获取或创建 Collection

        @param name: Collection 名称，默认为 zrag_docs
        @return: chromadb.Collection 实例
        """
        self.collection = self.client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"}
        )
        return self.collection
```

**模块级单例 `get_chroma_store()` 修改**：移除 `persist_dir` 参数，改为直接读取环境变量。

```python
_store = None

def get_chroma_store() -> ChromaStore:
    """获取 ChromaStore 单例

    @return: ChromaStore 实例
    """
    global _store
    if _store is None:
        _store = ChromaStore()
    return _store
```

其他公共方法（`add` / `similarity_search` / `delete_by_source` / `count`）**无需改动**，因为 `HttpClient` 返回的 `Collection` API 与 `PersistentClient` 完全相同。

#### apps.py 变更

`ZragConfig.ready()` 方法中，将本地文件路径初始化改为纯 `HttpClient` 方式：

```python
from zrag.store.vector_store import get_chroma_store

class ZragConfig(AppConfig):
    # ...

    def ready(self):
        """应用启动初始化

        连接 ChromaDB Server 并初始化 Collection。
        chroma 容器必须在 backend 之前启动完成，
        否则 init_collection 会因连接失败而抛出异常。
        """
        store = get_chroma_store()
        store.init_collection()
```

**启动顺序说明**：chroma 容器必须在 backend 之前启动完成，否则 `init_collection()` 会因连接被拒绝而抛出异常。在 `docker-compose.yml` 中添加 `depends_on` 加健康检查等待机制可以确保这一点。

#### 环境变量

在 `docker-compose.yml` 中为 backend 服务新增环境变量：

```yaml
services:
  backend:
    environment:
      - CHROMA_HOST=chroma
      - CHROMA_PORT=8000
    # ... 其余配置不变
```

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `CHROMA_HOST` | `localhost` | ChromaDB Server 主机名 |
| `CHROMA_PORT` | `8000` | ChromaDB Server 端口号 |

#### 数据迁移

**无需迁移**。只需确保 `./data/pro/chroma_db` 目录在 chroma 容器启动前已存在即可。chroma 容器首次启动时会自动识别已有的 SQLite 数据文件和 Collection，无需任何人工干预。

#### 可视化工具连接

- chroma 容器的 8000 端口可通过 Docker 内部网络以 `chroma:8000` 访问。
- 上述 docker-compose 配置已通过 `ports: "8000:8000"` 对外暴露端口，允许从宿主机直接连接。
- 常用可视化工具：
  - ChromaDB 自带 CLI：`chroma browse`
  - 第三方 GUI 工具：ChromaDB Viewer（VS Code 扩展）、Chroma UI 等

---

## 备选方案

原方案文档系统比较了两种迁移路径，结论是选择方案一。此外，「维持嵌入式现状」是本次决策的基线，原文档未将其作为候选方案逐项对比，但 [design.md](../design.md) 第 3.1 至 3.2 节说明了当初选择嵌入式模式的理由（免部署、无需独立服务进程、契合个人使用规模）。

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| **方案一：新增独立容器（推荐，即本决策）** | 新建一个 chroma 容器运行 ChromaDB Server，后端改用 `HttpClient` 连接 | 架构清晰，官方推荐模式；chroma 与后端解耦；方便集成可视化工具 | 多维护一个容器；增加一个网络跳转 |
| **方案二：后端容器内启动 HTTP 服务** | 在后端容器内额外启动 `chroma run` 进程，通过同一个容器暴露 8000 端口 | 不改变容器拓扑 | 一个容器内跑两个进程，不符合最佳实践；进程管理复杂；Docker 健康检查难以覆盖两个进程 |

方案二被否决的核心原因是它只解决了「暴露 HTTP 接口」这一个问题，却引入了同容器多进程的管理负担，并且健康检查无法同时覆盖 Django 与 ChromaDB 两个进程。相比之下，方案一以多一个容器的代价换来了清晰的生命周期边界，这与 ChromaDB 官方的 client/server 部署方式也一致。

---

## 后果

### 正面

- 向量数据获得标准 HTTP 接口，ChromaDB Viewer、Chroma UI、`chroma browse` 等工具可以直接连接查看 `zrag_docs` Collection。
- ChromaDB 的生命周期与 Django 进程解耦，后端可以独立重启而向量库保持运行，反之亦然。
- 向量数据库具备了独立监控、备份与扩缩容的操作空间，不再被后端容器边界限制。
- 现有数据与 Collection 结构完全兼容，无需数据迁移，`add` / `similarity_search` / `delete_by_source` / `count` 等公共方法无需改动。
- 该方案是 ChromaDB 官方推荐的 client/server 模式，后续升级路径清晰。

### 负面 / 代价

- 需要多维护一个容器，部署拓扑从两个服务变为三个服务。
- 每次向量操作多一次网络跳转，延迟相比进程内文件访问有所增加；在个人使用规模下这一增量预计可接受，但原方案未给出量化数据。
- 新增容器带来固定的资源占用：原方案设定内存上限 `512M`、CPU 上限 `"2"`。
- backend 启动顺序被约束为「chroma 先就绪」；若 chroma 未通过健康检查，backend 会因连接被拒绝而启动失败，`depends_on` + `service_healthy` 是必要而非可选的配置。
- 嵌入式模式下「复制目录即备份」的简单性依然保留，但备份时机需要考虑 server 进程正在写入的情况，原方案未展开说明。

### 未决问题

以下问题在原方案文档中未被讨论，属于实施前需要补充确认的事项：

- **访问控制**：`ports: "8000:8000"` 会把 ChromaDB HTTP API 暴露到宿主机，原方案未涉及任何鉴权或仅绑定回环地址的配置；是否需要限制为 `127.0.0.1:8000:8000` 或增加认证层，尚未决定。
- **宿主机端口冲突**：是否已确认宿主机 8000 端口未被其他服务占用，原方案未提及。
- **连接可靠性**：多 worker 场景下的连接数上限、超时与重试策略未定义；原方案只依赖启动阶段的健康检查。
- **既有 prefork 防护是否保留**：迁移后 SQLite 文件仅由 chroma 服务进程持有，`lazy-apps = true` 与 Collection 延迟初始化的必要性下降，但是否简化这部分配置尚未决定（现状见 [design.md 第 1.4.4 节](../design.md#144-chromadb--embedding-单例)）。
- **镜像版本策略**：固定为 `chromadb/chroma:1.5.9` 与 Python 客户端版本保持一致，但升级流程与兼容性验证方式未定义。

---

## 实施验证

### 容器启动验证

```bash
docker compose up -d
docker compose ps
```

确认 chroma 服务状态为 `healthy`。

```bash
curl http://localhost:8000/api/v2/heartbeat
```

应返回类似以下响应：

```json
{"nanosecond heartbeat": 1718765432000000000}
```

### 功能验证

```bash
# 检查后端健康检查端点，内部会调用 store.count()（需通过 Nginx 反向代理或直接访问 backend:5965）
curl http://localhost:5965/v1/health/ready
```

- 执行一次文档摄入操作，确认向量能正常写入。
- 执行一次检索操作，确认向量能正常召回。

### 可视化工具验证

- 使用 ChromaDB Viewer（VS Code 扩展）或 Chroma UI 连接 `localhost:8000`。
- 确认能看到 `zrag_docs` Collection 及其中的向量数据。

---

## 回滚方案

如果需要回滚至嵌入式模式，按以下步骤操作：

1. 停止并移除 chroma 容器：`docker compose stop chroma && docker compose rm chroma`
2. 将 `zrag/store/vector_store.py` 恢复到 `PersistentClient` 版本
3. 将 `zrag/apps.py` 恢复到原有的 `get_chroma_store(persist_dir=chroma_path).init_collection()` 方式
4. 从 `docker-compose.yml` 中移除 `chroma` 服务及其相关配置（`depends_on`、环境变量等）
5. 重新构建并启动 backend：`docker compose up -d --build backend`

**数据不受影响**：变更前后使用同一份 SQLite 数据文件，回滚后后端可以直接继续读写。

---

## 当前状态

截至本 ADR 编写时（2026-11-17），该方案**尚未实施**：

- `zrag/store/vector_store.py` 中的 `ChromaStore.__init__()` 仍以 `chromadb.PersistentClient` 创建客户端，`get_chroma_store()` 仍接受 `persist_dir` 参数。
- `zrag/apps.py` 仍以本地路径方式调用 `get_chroma_store(persist_dir=chroma_path).init_collection()`。
- `docker-compose.yml` 中只有 `frontend` 与 `backend` 两个服务，没有独立的 `chroma` 服务，也没有 `CHROMA_HOST` / `CHROMA_PORT` 环境变量。
- 因此本文「决策」中的容器拓扑、`HttpClient` 用法与容器配置均描述的是**目标状态**，不代表现有系统状态。

若未来实施该方案，应执行以下文档维护动作：将本 ADR 状态改为 `Accepted`，补充实施日期与对应的提交/版本号；同步更新 [design.md 第 3.2 节](../design.md#32-chromadb-向量存储) 的存储层描述与 [docs/README.md](../README.md) 中的状态标注；若实施过程中调整了端口、镜像版本或访问控制策略，应在本 ADR 中追加「实施记录」小节说明偏离原方案之处，而不是直接改写原决策正文。
