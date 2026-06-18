# ZRAG 系统设计文档

> 个人 RAG 知识库系统 — 本地优先、隐私保护的智能知识检索与问答

---

# 目录

[1. 概述](#1-概述)

[2. 核心概念](#2-核心概念)

[2.1 文档摄入管道](#21-文档摄入管道)

[2.2 混合检索器](#22-混合检索器)

[2.3 RAG 问答流程](#23-rag-问答流程)

[2.4 会话管理](#24-会话管理)

[3. 存储层设计](#3-存储层设计)

[3.1 SQLite 存储](#31-sqlite-存储)

[3.2 ChromaDB 向量存储](#32-chromadb-向量存储)

[3.3 数据一致性策略](#33-数据一致性策略)

[4. Embedding 模型](#4-embedding-模型)

[5. 文档摄入](#5-文档摄入)

[5.1 DocumentSource ABC](#51-documentsource-abc)

[5.2 MacNotesSource](#52-macnotessource)

[5.3 ChunkingStrategy ABC](#53-chunkingstrategy-abc)

[5.4 IngestionPipeline](#54-ingestionpipeline)

[6. 检索层](#6-检索层)

[6.1 Retriever（混合检索 + RRF 融合）](#61-retriever混合检索--rrf-融合)

[6.2 PromptBuilder（Jinja2 模板渲染）](#62-promptbuilderjinja2-模板渲染)

[6.3 QueryRewriter（查询改写与上下文感知）](#63-queryrewriter查询改写与上下文感知)

[6.4 ConversationSummarizer（对话压缩）](#64-conversationsummarizer对话压缩)

[6.5 CompressService（异步压缩调度）](#65-compressservice异步压缩调度)

[7. LLM 集成](#7-llm-集成)

[8. API 设计](#8-api-设计)

[8.1 统一响应格式](#81-统一响应格式)

[8.2 认证机制](#82-认证机制)

[8.3 异常处理体系](#83-异常处理体系)

[8.4 API 端点设计](#84-api-端点设计)

[8.5 Swagger 文档](#85-swagger-文档)

[9. 前端设计](#9-前端设计)

[9.1 组件架构](#91-组件架构)

[9.2 数据流与状态管理](#92-数据流与状态管理)

[9.3 错误处理双层反馈](#93-错误处理双层反馈)

[10. Trace ID 全链路追踪](#10-trace-id-全链路追踪)

[11. 配置管理](#11-配置管理)

[12. 日志体系](#12-日志体系)

[13. 扩展点](#13-扩展点)

[13.1 新增数据源](#131-新增数据源)

[13.2 新增分块策略](#132-新增分块策略)

[13.3 新增 LLM Provider](#133-新增-llm-provider)

---

# 1. 概述

## 1.1 问题陈述

知识工作者的日常工作中，有价值的信息通常散落在多个彼此隔离的应用和文件系统中。以本项目所面向的场景为例：macOS 备忘录中存有大量的笔记和摘录，本地文件系统中还有各类 Markdown、PDF 和 DOCX 文档。每当需要查找某个知识点时，用户必须在不同应用之间来回切换，凭借记忆和关键词猜测去逐一翻阅——这种手动搜索的方式存在几个根本性的局限。

首先，知识碎片化意味着信息分布在不同的"孤岛"中，没有一个统一的入口来搜索全部内容。其次，基于关键词的搜索无法处理"语义相近但用词不同"的查询场景——例如用户查询"怎么提升代码执行速度"，而原文中描述的是"性能优化方法"，仅靠关键词匹配会漏掉这类高度相关但用词不同的内容。第三，即便找到了相关的原始文档片段，用户仍然需要自己阅读、理解、归纳这些分散的信息——无法直接获得一个基于多来源信息综合而成的自然语言回答。

因此，ZRAG 需要解决的核心问题是：为个人用户提供一个**本地运行的、隐私保护的知识库系统**，该系统能够自动摄入散落在各处的文档内容，支持用自然语言进行语义级别的检索，并基于检索到的相关材料生成附有来源标注的可信回答。

## 1.2 设计背景与考量

在设计 ZRAG 的总体方案时，面临以下几个关键设计问题的抉择：

**本地语义检索 vs 云端服务**。RAG 系统的核心环节之一是 Embedding 和向量检索。将文档上传到云端服务（如 OpenAI Embeddings API）会引入隐私风险——用户的个人笔记内容会离开本地设备。此外，云端服务还涉及网络延迟和 API 调用成本。基于上述考虑，ZRAG 选择将所有 Embedding 计算和向量检索放在本地执行：使用开源模型 BAAI/bge-small-zh-v1.5 在本地完成文本向量化，使用 ChromaDB 作为嵌入式向量数据库在本地持久化存储向量。这种方案保证了用户数据从始至终不会离开本机。

**隐私保护与 LLM 调用的平衡**。向量化和检索可以在本地完成，但最终生成回答的 LLM 推理则受限于本地算力。ZRAG 采用了一个折中方案：检索环节完全本地化以保证隐私，LLM 调用环节通过自托管的 LiteLLM Gateway 统一管理——LLM 请求虽然会发送到外部模型服务商，但由于用户可自行选择模型和配置 Gateway，能够灵活控制哪些数据流向哪些模型。检索结果作为上下文发送给 LLM 时，已经经过分块和排序筛选，并非完整的原始文档。

**灵活的摄入管道 vs 硬编码单一来源**。个人用户的知识来源是多样化的：macOS 备忘录、本地文件、未来可能还有浏览器书签、RSS 订阅等。如果在摄入管道中硬编码对特定数据源的处理逻辑，每新增一种数据源就需要大量修改管道代码。从这一点可以看出，摄入管道必须与具体数据源解耦。因此，ZRAG 在摄入管道中采用 DocumentSource 抽象基类作为数据源的统一接口，不同的数据源只需实现 `fetch_batch()` 方法即可接入管道。同理，不同类型文档（纯文本、Markdown、代码文件）的最优分块方式不同，因此将分块策略也抽象为 ChunkingStrategy 基类。

**个人使用规模**。ZRAG 面向的是单用户、文档量级小于 1000 篇的场景。这个规模定位直接影响了技术选型方向：不需要分布式架构、不需要消息队列、不需要负载均衡的检索集群。SQLite 足以满足个人场景的结构化存储需求，ChromaDB 的单机持久化模式也完全够用。这也意味着可以大幅简化部署流程——一条 `docker compose up -d` 命令完成全部服务的启动，无需预先配置数据库服务器或向量检索集群。

> 注意：上述规模定位也划定了 ZRAG 当前阶段的边界——不处理多用户隔离、不引入消息队列做异步摄入、不部署分布式向量检索集群。这些能力如果有需要可以在后续版本中引入，但当前设计不以它们为前提。

## 1.3 系统架构全景

基于上述考量，ZRAG 的整体架构由一个独立的反向代理层、一个后端 API 服务、一个前端静态资源服务，以及外部的 LLM 网关服务组成。组件之间的通信关系如下：

```
┌─────────────────────────────────────────────────────────────┐
│                        Browser                              │
└──────────┬──────────────────────────────────────────────────┘
           │ HTTP :80
           ▼
┌──────────────────────┐
│   znginx (nginx)     │  ← 独立容器，反向代理 + 结构化日志
│   0.5 CPU / 64MB     │
└────┬────────────┬────┘
     │            │
     │ /zrag/*    │ / (静态资源)
     ▼            ▼
┌──────────────┐  ┌──────────────────┐
│ zrag-backend │  │  zrag-frontend   │
│ uWSGI+Django │  │  nginx:alpine    │
│ CPU:2/M:768M │  │  CPU:0.5/M:64M   │
│ :5965        │  │  :80 (内部)       │
└──────┬───────┘  └──────────────────┘
       │
       │ OpenAI SDK
       ▼
┌──────────────────────────────┐
│  LiteLLM Gateway (外部服务)   │
│  host.docker.internal:4000   │
└──────────────────────────────┘

数据存储:
┌──────────┐  ┌──────────────┐  ┌──────────────────┐
│ SQLite   │  │  ChromaDB    │  │  Models Volume   │
│ zrag.db  │  │  chroma_db/  │  │  BGE-small-zh    │
│ (ACID)   │  │  (Cosine)    │  │  (只读挂载)       │
└──────────┘  └──────────────┘  └──────────────────┘
```

**znginx 为何独立部署**。在设计之初，曾考虑将 nginx 作为 docker-compose 的一部分与 frontend 和 backend 统一管理。但从实际使用场景来看，nginx 作为反向代理通常需要服务于同一宿主机上的多个项目（例如 zonebank 的内网穿透、其他内部工具等）。将 nginx 放入 ZRAG 的 docker-compose 中意味着 nginx 的生命周期与 ZRAG 项目绑定——ZRAG 的重启或下线会波及同一 nginx 代理的其他项目。因此，将 znginx 设计为独立容器，由宿主机上的独立脚本管理其生命周期，ZRAG 仅通过约定的路径前缀（`/zrag/*`）接入反向代理。这样 znginx 可以同时代理多个项目，互不干扰。

**backend 如何与 LiteLLM Gateway 通信**。Backend 不直接调用各 LLM 厂商的 API，而是通过 OpenAI SDK 以标准的 OpenAI 兼容接口向 LiteLLM Gateway 发送请求。LiteLLM Gateway 运行在宿主机上（通过 `host.docker.internal:4000` 从容器内访问），负责统一的模型路由、负载均衡和 API Key 管理。Backend 只需要指定一个模型名（如 `smart-router`、`glm-5` 或 `deepseek-v4-pro`），Gateway 会将其映射到实际的模型端点。这种设计使得切换底层 LLM 模型或增加新的模型厂商时，Backend 代码完全不需要修改——所有模型路由变更仅在 Gateway 的 YAML 配置中完成。

> Tips: LiteLLM Gateway 的配置位于 `~/.claude/litellm/config.yaml`，其中已配置了 `smart-router` 负载均衡组，可以根据各模型的实时可用性和延迟自动选择最优模型。

Backend 和 Frontend 作为两个独立的容器运行，通过 docker-compose 统一管理。Frontend 容器内使用 nginx:alpine 提供编译后的 Vue 静态资源，内部监听 80 端口；Backend 容器内运行 uWSGI + Django，内部监听 5965 端口。znginx 根据请求路径前缀将 `/zrag/*` 的 API 请求代理到 Backend，将根路径 `/` 的静态资源请求代理到 Frontend。

## 1.4 设计原则的形成过程

ZRAG 的五条核心设计原则不是预先设定的教条，而是在对一个一个具体设计问题进行深入分析后，逐步归纳出来的指导方针。以下逐条展开说明每条原则所对应的问题、分析过程和最终决策。

### 1.4.1 纯 Python 原生实现（不使用 LangChain / LlamaIndex）

**面临的问题**。在项目启动阶段，首先需要决定的是是否引入 LangChain 或 LlamaIndex 作为 RAG 框架。这两个框架在 RAG 领域具有很高的知名度，提供了开箱即用的文档加载器、分块器、向量存储适配器和 Prompt 模板等功能。初学者可以在几十行代码内搭建出一个 RAG Demo。

**分析过程**。LangChain 的问题在社区已有大量讨论：框架的抽象层数过多，追查一个问题往往需要跨越 3-4 层嵌套的 Runnable 链；框架内部的回调机制和序列化逻辑在某些场景下行为不可预测，调试成本极高。更关键的是，这些框架为"通用性"做了大量设计让步，导致引入的传递依赖极其庞大——一个简单的 RAG 流程可能需要安装 20 个以上的第三方包。对于 ZRAG 这样的个人项目而言，这种复杂性是得不偿失的。从个人使用规模来看，ZRAG 的文档摄入流程、检索流程和 Prompt 构建流程都是高度定制化的——MacNotesSource 需要通过 AppleScript 读取 macOS 备忘录，这种特定数据源的接入逻辑用框架的通用 Loader 反而难以适配。

**决策**。基于上述分析，ZRAG 选择纯 Python 原生实现所有核心逻辑。不引入 LangChain、LlamaIndex 或任何 RAG 框架。文档分块、向量存储交互、检索融合、Prompt 构建均由项目自身代码完成，只依赖必要的底层库（sentence-transformers、chromadb、jinja2、openai）。这种选择的代价是需要自行实现一些框架已封装好的功能（如文本分块器），但换来的是一览无余的调用链路、可预测的行为以及极小的依赖体积。从长久维护的角度看，理解一段 200 行的自有代码远比理解一个框架的黑盒行为容易。

> 注意：不使用框架并不意味着不学习框架的设计思想。ZRAG 在自行实现过程中广泛参考了 LangChain 和 LlamaIndex 的文档加载器、Text Splitter 和 Retriever 等组件的接口设计，取其精华而非引入依赖。

### 1.4.2 依赖注入

**面临的问题**。在构思核心模块的协作方式时，遇到两个具体挑战。第一，单元测试需要 mock 外部依赖——例如测试 IngestionPipeline 时不应该真的调用 ChromaDB 和 LLM，应该替换为假实现；如果在 Pipeline 内部直接实例化 `ChromaStore()`，测试代码将无法介入替换。第二，不同的数据源可能对应不同的分块策略——Markdown 文档适合按标题层级分块，纯文本适合按段落分块，代码文件可能根本不需要分块——如果 Pipeline 内部硬编码了分块策略，就无法做到"按数据源类型动态绑定不同分块策略"。

**分析过程**。将组件的依赖（如 ChromaStore、Embedder、Chunker）从外部通过构造方法传入，而不是在组件内部自行创建，这就是依赖注入的核心思想。以 IngestionPipeline 为例，其构造方法接收各协作组件作为参数：

```python
class IngestionPipeline:
    def __init__(self, sqlite_store, chroma_store, embedder, chunker, ...):
        self.sqlite_store = sqlite_store
        self.chroma_store = chroma_store
        self.chunker = chunker
        self.embedder = embedder
```

这样一来，测试时可以直接传入 mock 对象：`IngestionPipeline(sqlite_store=mock_store, chroma_store=mock_chroma, ...)`。生产环境中，针对 Markdown 文档可传入 `MarkdownHeadingChunker`，针对纯文本可传入 `ParagraphChunker`，Pipeline 本身不需要知道分块策略的具体实现细节——它只知道调用 `self.chunker.chunk(doc)`。

**决策**。ZRAG 在所有核心组件（IngestionPipeline、Retriever、ViewSet）中全面采用构造方法注入依赖。此外，在 ViewSet 层面还提供了可覆盖的 `_get_store()`、`_get_retriever()` 等工厂方法，使得测试代码可以在不修改 ViewSet 类定义的情况下替换依赖实例。这种设计保证了每个组件对外部依赖的"无知"——组件只需要声明它需要什么能力（由 ABC 定义），而不需要知道这个能力是由谁、以何种方式实现的。

### 1.4.3 核心模块 ABC（抽象基类）

**面临的问题**。在设计摄入管道时，最初只有一个具体的数据源实现：MacNotesSource。此时将数据源的逻辑直接写在代码中是可行的。但从扩展性的角度看，未来必然会增加新的数据源（本地文件、RSS 订阅、浏览器书签等）。如果每个数据源的接口不一致——例如有的返回 RawDocument 列表，有的返回生成器，有的直接写数据库——那么 IngestionPipeline 将不得不为每个数据源编写专属的处理逻辑，随着数据源类型增加，Pipeline 代码会迅速膨胀为难以维护的 if-else 分支森林。

**分析过程**。抽象基类（ABC）在 Python 中提供了一种定义接口契约的机制：父类声明抽象方法，子类必须实现。当所有数据源都遵循同一接口时，Pipeline 不需要关心当前处理的是哪种数据源——它只需要调用 `source.fetch_batch()` 和访问 `source.source_type` 即可。同样的道理适用于分块策略、Embedding 模型和 LLM Provider：虽然各自的内部实现差异很大，但对外暴露的操作接口是可以标准化的。从系统架构的角度看，ABC 实现了"依赖倒置"——高层模块（Pipeline）不依赖低层模块（具体的数据源），两者都依赖抽象（DocumentSource）。

**决策**。ZRAG 为核心模块全部定义了 ABC：

- `DocumentSource`：定义 `fetch_batch()` 和 `source_type`
- `ChunkingStrategy`：定义 `chunk(document) -> list[Chunk]`
- `EmbeddingModel`：定义 `embed()`、`embed_query()` 和 `dimension`
- `LLMProvider`：定义 `chat()` 和 `chat_stream()`

新增一种数据源或分块策略，只需实现对应的 ABC 并在注册表（Registry）中登记即可，IngestionPipeline 和其他调用方代码无需任何修改。这实现了"对扩展开放，对修改封闭"的设计目标。

> Tips: 注册表模式（Registry）是 ABC 的自然补充。ABC 定义了接口契约，而注册表（如 `SOURCE_REGISTRY` 字典）建立类型标识符到实现类的映射，使得 API 层可以通过字符串参数动态选择具体实现。例如，`SOURCE_REGISTRY.get("mac_notes")` 返回 `MacNotesSource` 类，调用方不需要硬编码类名。

### 1.4.4 ChromaDB / Embedding 单例

**面临的问题**。ZRAG 使用 uWSGI 作为 WSGI Server，uWSGI 的默认工作模式是 `prefork`——主进程先加载 Python 应用代码，然后 fork 出多个 worker 进程来处理请求。这里存在一个隐蔽但严重的问题：ChromaDB 底层使用 SQLite 作为存储引擎，而 SQLite 的数据库连接在 fork 之后不能跨进程共享——子进程如果继承了父进程中已打开的 SQLite 文件句柄，多个进程通过同一个文件描述符操作 SQLite，会导致数据损坏或 `database is locked` 等难以排查的异常。

**分析过程**。这个问题在 ChromaDB 社区和 uWSGI 文档中都有提及。根本原因在于：Python 对象在 fork 时会复制到子进程的内存空间，但底层的文件描述符（包括 SQLite 的 WAL 文件句柄）在两个进程间是共享的，而 SQLite 对并发写入有严格的锁机制。如果主进程在 fork 前就已经初始化了 ChromaDB 的 PersistentClient，子进程继承了同一个 client 对象，两个进程通过同一个文件句柄操作 SQLite，就会触发各种不可预期的行为。同理，Embedding 模型内部也涉及共享内存和文件句柄，在 fork 后同样可能出现问题。

**决策**。ZRAG 采用了两层保护机制来应对这个问题：

第一层，uWSGI 配置侧：启用 `lazy-apps = true`，这意味着 Django 应用模块在 worker fork **之后**才加载，而不是在主进程中预先加载。这确保了每个 worker 进程独立执行模块初始化逻辑，避免在主进程中预初始化 ChromaDB 或 Embedding 模型。

第二层，应用代码侧：ChromaDB 的 PersistentClient 和 Embedding 模型实例采用模块级单例模式管理。每个进程内部维护唯一的实例引用，通过工厂函数 `get_chroma_store()` 和 `get_embedder()` 提供访问。工厂函数在进程生命周期内只在首次调用时创建实例，后续调用返回同一实例，既避免了重复初始化的开销（模型加载是昂贵的操作），也确保了每个进程内只有一个数据库连接。

> 注意：这里的"单例"是进程级别的，不是全局级别的。在多 worker 模式下，每个 worker 进程各有一个独立的单例实例——这正是所期望的行为：每个进程管理自己与 SQLite 的连接，互不干扰。

### 1.4.5 先 SQLite，后 ChromaDB

**面临的问题**。文档摄入的最终结果需要同时写入两个存储：SQLite（存储 chunk 原文和 FTS5 全文索引）和 ChromaDB（存储向量和元数据）。这两个存储系统的写入操作无法放在同一个数据库事务中——SQLite 的事务只覆盖 SQLite 自身的表，ChromaDB 的写入是完全独立的操作。如果在写入 SQLite 成功后 ChromaDB 写入失败，或者反过来，就会出现双库数据不一致：一个库中有某篇文档的数据，另一个库中没有。

**分析过程**。在分布式系统中，跨存储系统的事务一致性通常通过两阶段提交（2PC）或 Saga 模式来解决。但 ZRAG 是单机个人系统，引入分布式事务协调器显然是过度设计。需要找到一个更务实的方案。关键观察是：SQLite 拥有完整的 ACID 事务支持，而 ChromaDB 的写入操作没有事务保证。这意味着 SQLite 写入的结果是可靠的——只要 SQLite 事务提交成功，数据就不会丢失。而 ChromaDB 的写入是"尽力而为"的——它可能因各种原因失败（进程崩溃、磁盘空间不足等），但从个人系统的角度看，这类失败是低频且可恢复的。

**决策**。基于上述分析，ZRAG 采用了"SQLite 先行"的策略：

1. 每篇文档先在 SQLite 事务中完成完整写入（删除旧数据、插入新 chunks），提交事务。这一步通过 SQLite 的 ACID 保证了 chunks 数据的完整性。
2. SQLite 事务成功后，再向 ChromaDB 写入向量。这一步的失败不会影响 SQLite 中已完成的数据。
3. 只有双库都写入成功后，才更新 `processed_docs` 表中的记录（标记为"已处理"）。

如果 ChromaDB 写入失败，`processed_docs` 中不会留下已处理标记。下次执行摄入时，系统会检测到该文档的 `content_hash` 未变化但 `processed_docs` 中无记录，自动重新执行 ChromaDB 的写入——这实际上是一种基于补偿的最终一致性策略。写入顺序之所以选择"先 SQLite 再 ChromaDB"而非反过来，是因为 SQLite 作为可信数据源（Source of Truth），其写入成功是整个摄入流程的锚点——只要 SQLite 中有完整的 chunks 数据，哪怕 ChromaDB 数据全部丢失，也可以通过重新向量化 SQLite 中的 chunks 原文来完整恢复。

## 1.5 技术选型理由

在确定了设计原则之后，需要对各层的具体技术栈做出选择。以下逐项说明每个技术选型背后的考量。

**Django REST Framework + uWSGI**。API 框架的选择受到了参考项目 zonebank 实践经验的直接影响。zonebank 在 DRF + uWSGI 的组合上已经验证了稳定性和开发效率。DRF 提供了 ViewSet 路由、Serializer 校验、认证类和异常处理等开箱即用的基础设施——这些能力如果换用 FastAPI 或 Flask 需要额外引入多个扩展库才能实现同等的开发体验。配合 `drf-spectacular` 可以基于代码中的装饰器注解自动生成 OpenAPI 文档（Swagger UI），在开发阶段极大地方便了 API 的手动测试。uWSGI 作为 WSGI Server 在单进程/少进程场景下性能充裕、配置简洁，且与 Django 的集成非常成熟。这一组合使得 ZRAG 可以复用 zonebank 中经过验证的异常处理体系（Handler Registry 模式）、中间件设计（RequestIDMiddleware）和配置管理思路，减少从零摸索的成本。

**SQLite + ChromaDB 双库**。存储层的设计出发点是"嵌入免部署"——对于个人项目，如果数据库需要单独安装和启动一个服务进程（如 PostgreSQL Server、Milvus 集群），运维复杂度会显著增加。SQLite 和 ChromaDB（PersistentClient 模式）都是嵌入式数据库：前者是进程内文件数据库，将全部数据存储在一个 `.db` 文件中；后者将向量数据持久化到本地目录。它们都不需要独立的服务进程，通过文件系统就可完成数据的持久化和容器间卷挂载共享。SQLite 负责结构化数据和全文检索，通过内置的 FTS5 扩展提供 BM25 评分——零额外依赖即可实现高质量的关键词检索，无需手写 BM25 算法或引入 Elasticsearch。ChromaDB 负责向量存储和 Cosine 相似度检索，作为嵌入式向量数据库的典型代表，其 Python API 简洁直观，`add()`、`similarity_search()`、`delete_by_source()` 等方法覆盖了 ZRAG 所需的全部向量操作。两者在功能上互补：SQLite 提供精确的结构化查询和关键词匹配，ChromaDB 提供模糊的语义检索。

**Vue 3 + Vite**。前端框架的选择遵循"轻量前后分离"的原则。Vue 3 的 Composition API 和 Vite 的极速开发体验使得前端开发保持高效。ZRAG 的前端状态管理需求并不复杂——核心就是几个会话列表和消息列表——使用 Vue 3 原生的 Composable 模式（`useChat`、`useMarkdown`）即可满足，不需要引入 Vuex 或 Pinia 这类集中式状态管理库，减少了前端依赖体积。Vue Router 以 History 模式管理两个页面的路由（聊天主页 `/` 和源管理页 `/sources`），Tailwind CSS 通过 utility-first 的方式处理样式，避免了手写大量 CSS。最终编译产物为一组纯静态文件（HTML + JS + CSS），由 nginx:alpine 镜像提供，与后端完全分离部署，前后端各自独立构建、独立扩容。

**LiteLLM Gateway**。LLM 调用的核心挑战是模型多样性管理。ZRAG 不需要绑定到某一个特定模型，用户可能在不同场景下选择不同模型——速度优先时用 `deepseek-v4-flash`，质量优先时用 `deepseek-v4-pro`，特定任务可能用 `glm-5` 或 `kimi-k2.6`。如果 Backend 代码中直接集成每个厂商的 SDK，API Key 管理、模型切换和负载均衡的逻辑将散布在代码各处，维护成本随着接入的模型数量线性增长。LiteLLM Gateway 解决了这些问题：它以 OpenAI 兼容接口统一暴露多种模型，Backend 只需要使用 OpenAI SDK 通过单一基地址与 Gateway 通信。模型路由（smart-router 负载均衡组）、故障降级策略、速率控制全部由 Gateway 的 YAML 配置文件管理，与 Backend 代码完全解耦。Gateway 运行在宿主机上，以独立进程形式存在，ZRAG 容器通过 `host.docker.internal:4000` 访问——这意味着 Gateway 的启停和升级不影响 ZRAG 容器的生命周期。

## 1.6 核心能力

基于上述设计原则和技术选型，ZRAG 当前阶段提供了以下核心能力：

- **文档摄入**：从 macOS Notes 等数据源自动拉取原始文档，经过内容去重（`content_hash` SHA256 增量对比）、智能分块（支持段落、Markdown 标题、递归字符等多种分块策略，可通过 CompositeChunker 组合使用）、本地向量化（BGE-small-zh-v1.5，512 维，normalize_embeddings=True），最终写入 SQLite（chunks 原文 + FTS5 全文索引）和 ChromaDB（向量 + 元数据）双库。支持增量模式（默认，跳过未变更文档）和全量模式（`full=true`，强制重处理全部文档）切换。每篇文档独立事务，单篇失败不影响同一批次的其他文档。

- **混合检索**：融合语义检索和关键词检索两条互补路径。语义检索通过 ChromaDB 的 Cosine 相似度找到"意思相近"的文档片段；关键词检索通过 SQLite FTS5 内置的 BM25 评分找到"包含相同关键词"的文档片段。两者结果通过 RRF（Reciprocal Rank Fusion，常数 k=60）算法融合排序——RRF 的核心优势在于不需要对不同检索方式的原始分数做归一化，仅基于排名位置进行融合，同时自然地实现去重。

- **RAG 问答**：将混合检索的结果通过 Jinja2 模板引擎渲染为结构化的 system prompt，连同用户问题一起构建为 OpenAI 格式的消息列表，通过 OpenAI SDK 发送给 LiteLLM Gateway，由 Gateway 路由到实际模型。LLM 基于检索到的参考材料生成回答，回答中附带来源标注（文档标题 + 相关度分数）。支持多轮对话——在已有会话基础上继续追问时，系统加载最近 10 条历史消息作为上下文，保持对话的连贯性。

- **会话管理**：会话在首条消息时自动创建（title 取自 query 前 50 字符），不需要预先创建空会话。支持会话列表按最近消息时间倒序排列（通过 messages 表的子查询获取 `last_msg_at`）、切换会话继续对话、删除会话及其全部消息。删除操作采用级联策略（同一事务中 DELETE messages → DELETE conversations），且幂等——会话不存在时仍返回 200 成功。

- **知识源管理**：按数据源类型（当前支持 `mac_notes`）统计已摄入文档数量（total/new/updated/failed），提供一键增量导入和全量导入触发按钮。导入过程中展示不确定进度条，导入完成后自动刷新统计数据和会话列表。通过 IngestGuard（基于 SQLite 原子 UPDATE）保证同一时刻只有一个摄入任务在执行。

- **全链路追踪**：每个请求从 nginx 入口生成 `$request_id`，通过 `X-Request-ID` 请求头透传到 Django Backend（RequestIDMiddleware），贯穿检索、LLM 调用、消息持久化的全部环节，最终回写到 API 响应体（`RequestID` 字段）和响应头（`X-Request-ID`）。各层级日志均携带 `[req=xxx]` 前缀，可通过一个 RequestID 串联整个请求在 nginx access.log、uwsgi-req.log、Django info.log/error.log 中的所有记录。

- **Web UI**：Vue 3 聊天界面，左侧会话列表 + 右侧聊天区。核心交互特性包括：Markdown 渲染（marked.js + highlight.js 代码高亮，主题跟随深色/浅色模式切换）、深色/浅色模式手动切换（偏好存 localStorage）、消息气泡悬停复制、Enter 发送 / Shift+Enter 换行、自动扩展 textarea（最大 6 行）、AI 回复加载动画（三个跳动圆点）、空状态引导提示。错误处理提供双层反馈机制——页面级 Toast 通知（右上角，5 秒消失）和对话区红色错误气泡（永久显示，含 Trace ID）。

> 注意：流式 SSE 端点（chat_stream）延后至 Phase 2 实现。当前阶段所有 LLM 调用均为同步非流式，通过 uWSGI 的 180 秒 harakiri 超时兜底。

---

# 2. 核心概念

## 2.1 文档摄入管道

文档摄入是将外部知识源（如 macOS 备忘录）中的原始文档转换为可供检索的结构化数据的过程。

数据流：`Source → RawDocument → Chunk → Embed → SQLite → ChromaDB → processed_docs`

```
┌──────────┐    ┌──────────────┐    ┌──────────┐    ┌───────────┐
│  Source  │───▶│  RawDocument  │───▶│  Chunks  │───▶│  Vectors  │
│ fetch    │    │  content_hash │    │  max_size │    │  512-dim  │
│ batch    │    │  metadata     │    │  overlap  │    │  Cosine   │
└──────────┘    └──────────────┘    └──────────┘    └───────────┘
                                                        │
                    ┌───────────────────────────────────┤
                    ▼                                   ▼
            ┌──────────────┐                  ┌──────────────┐
            │   SQLite      │                  │   ChromaDB   │
            │ chunks + FTS5 │                  │  zrag_docs   │
            │ ACID 保证     │                  │  Cosine 距离  │
            └──────────────┘                  └──────────────┘
```

### 设计理念

**为何抽象出 IngestionPipeline**。文档摄入从端到端来看，涉及 Source（数据获取）→ Chunk（文本分块）→ Embed（向量化）→ Store（双库持久化）四个阶段。其中每一个阶段都是可变的——数据源可能是 macOS 备忘录、本地文件、RSS 订阅中的任意一种；分块策略可能是按段落、按 Markdown 标题层级或按语义边界；Embedding 模型可能从 BGE-small 切换到其他模型；存储层也可能扩展为其他数据库组合。如果在管道中硬编码对特定数据源或特定分块策略的处理逻辑，那么每当需要新增一种数据源或调整分块方式时，就必须修改管道的核心代码，这违背了"对扩展开放、对修改封闭"的原则。从这一点可以看出，摄入管道需要一个编排器（Orchestrator）来将各阶段解耦。因此，ZRAG 将 IngestionPipeline 设计为一个编排器——它本身不实现任何具体的数据获取、分块或向量化逻辑，而是通过构造方法依赖注入接收各组件实例（DataSource、Chunker、Embedder、SQLiteStore、ChromaStore），Pipeline 只负责按固定顺序调用这些组件的方法，从而将"做什么"与"怎么做"彻底分离。基于上述设计，新增一种数据源时只需实现 DocumentSource ABC 并在注册表中登记，Pipeline 代码完全不需要修改。

**为何逐篇处理而非批量事务**。ZRAG 面向的是单用户、文档量级小于 1000 篇的个人场景。在这个规模下，逐篇处理（per-document transaction）的优势大于批量事务。每一篇文档在 SQLite 中开启独立事务完成写入，一篇文档的处理失败不会导致整个批次回滚——失败文档被记录到 IngestReport.errors 中，后续可通过 on_error 回调执行自定义的补偿逻辑。如果采用批量事务模式，任一篇文档的分块或向量化阶段出现异常，整个批次的所有文档写入都需要回滚，这在文档来源质量参差不齐（如包含损坏的 PDF 或空正文的备忘录）的场景中会带来不必要的重处理开销。因此，逐篇处理在保证数据完整性的同时，提供了更细粒度的错误隔离能力。

**content_hash 增量检测**。增量摄入是个人知识库场景中的高频操作——用户每天都可能新增或修改几条备忘录，但 1000 篇文档中绝大多数是未变更的。如果每次摄入都对全部文档执行分块、向量化和双库写入，处理时间会线性增长到不可接受的程度。因此，ZRAG 在 RawDocument 中引入 `content_hash` 字段（SHA256 摘要），Pipeline 在摄入每篇文档前先将其 content_hash 与 SQLite 中 `processed_docs` 表已记录的 hash 进行比对：如果 hash 一致，说明该文档自上次摄入后未发生变更，直接跳过；如果 hash 不同或 processed_docs 中无记录，说明是新增或已更新的文档，进入完整处理流程。基于上述机制，增量模式下仅处理实际变更的文档，摄入耗时从"全量 O(n)"降低为"实际变更数 O(k)，k << n"。

核心类协作关系：

```python
class IngestionPipeline:
    """文档摄入编排器
    
    通过依赖注入接收各组件实例，编排完整的摄入流程。
    单篇文档独立事务：失败不影响其他文档。
    
    @param sqlite_store: SQLite 持久化存储
    @param chroma_store: ChromaDB 向量存储  
    @param embedder: Embedding 模型
    @param chunker: 文档分块策略
    @param batch_size: Source 批次大小
    @param on_error: 错误回调 (ErrorEvent) -> None
    """
    
    def run(self, source, full=False, on_progress=None) -> IngestReport:
        for doc in all_docs:
            # 增量模式: content_hash 对比跳过未变更文档
            if not full and self._is_unchanged(doc):
                report.skipped += 1
                continue
            
            # 分块 → 向量化 → 双库存储
            chunks = self.chunker.chunk(doc)
            vectors = self.embedder.embed([c.content for c in chunks])
            
            # SQLite 事务: 先删旧数据 → 写新块 → 提交
            with self.sqlite_store.transaction():
                self.sqlite_store.delete_by_source(doc.source_id)
                self.sqlite_store.add_chunks(chunks)
            
            # ChromaDB: 删旧向量 → 写新向量
            self.chroma_store.delete_by_source(doc.source_id)
            self.chroma_store.add(ids, vectors, metadatas)
            
            # 标记已处理
            self.sqlite_store.upsert_processed(doc)
```

摄入结果报告数据结构：

```python
@dataclass
class IngestReport:
    total: int = 0      # 从 Source 获取到的文档总数
    new: int = 0         # 新导入的文档数量
    updated: int = 0     # 内容更新后重新导入的文档数量
    skipped: int = 0     # 因 hash 未变而跳过的文档数量
    failed: int = 0      # 处理失败的文档数量
    errors: list[ErrorEvent]  # 失败文档的详细错误列表
```

## 2.2 混合检索器

Retriever 融合两种互补的检索方式：语义相似度检索（ChromaDB Cosine）和关键词匹配检索（SQLite FTS5 BM25），通过加权 RRF（Reciprocal Rank Fusion）算法合并排序结果。检索前通过查询改写（QueryRewriter）将用户口语化查询转化为关键词列表和精炼查询，分别传入两条检索路径。

```
用户查询 "怎么让 Python 跑得更快"
        │
        ▼
    QueryRewriter.rewrite(query)
        │
        ├──▶ keywords: "Python 性能优化 加速"
        └──▶ refined_query: "Python 程序性能优化方法"
        │
        ├──▶ embed_query(refined_query) → 查询向量 (512-dim)
        │         │
        │         ▼
        │    ChromaDB.similarity_search(k=20, 候选池×2)
        │         │
        │         ▼
        │    [chunk_A: dist=0.12, chunk_B: dist=0.34, ...]
        │         │
        │         ▼
        │    rank_vector: {A:1, B:2, ...}
        │
        ├──▶ SQLite FTS5 bm25("Python 性能优化 加速", k=20)
        │         │
        │         ▼
        │    [chunk_B: bm25=-4.2, chunk_C: bm25=-3.1, ...]
        │         │
        │         ▼
        │    rank_keyword: {B:1, C:2, ...}
        │
        ▼
    加权 RRF 融合: score(d) = w_vector/(60+rank_vector) + w_keyword/(60+rank_keyword)
        │
        ▼
    按 RRF score 降序 → 截取 top-10 结果
```

### 设计理念

**为何需要混合检索**。知识库中的文档内容包含两类截然不同的信息：一类是可以用近义词、同义表达来描述的语义概念（如"代码优化方法"和"提升程序效率"指向相同含义）；另一类是人名、地名、技术术语、错误码等专有名词，这些词汇没有同义词，必须通过精确匹配才能定位。纯向量检索（基于 Embedding 的 Cosine 相似度）的优势在于捕捉语义相近但用词不同的内容，但对于专有名词和精确编码——如"ERR_CONN_REFUSED"、函数名"acquire_scaling_lock"——Embedding 模型对这些短文本的向量表示区分度有限，检索效果往往不如直接的关键词匹配。纯关键词检索（SQLite FTS5 BM25）对专有名词的匹配非常精准，但无法处理"用户查询用词与文档用词不同但语义相同"的情况。从这两种检索方式的特性可以看出，它们天然互补——语义检索覆盖面广但精确度有上限，关键词检索精度高但覆盖面窄。因此，ZRAG 将两者并行执行，然后通过融合算法整合结果，使最终返回的 top-k 文档片段同时受益于两条检索路径的各自优势。

**为何选择 RRF 而非加权求和**。在融合两种检索方式的结果时，最直观的方案是为语义检索的结果分数和关键词检索的结果分数各自分配一个权重，然后加权求和进行排序（score = alpha * cosine_score + beta * bm25_score）。然而，向量检索的 Cosine 距离和 BM25 分数的量纲完全不同——Cosine 距离在 0.1 的差异就可能意味着高度相关与无关的区别，而 BM25 分数从 -5 到 -10 的跨度在同一次查询中属于正常波动。在这种量纲不一致的前提下，无论 alpha 和 beta 如何取值，融合结果都会偏向其中一侧——本质上是两种分数的"不可比性"导致的必然问题。基于上述分析，RRF（Reciprocal Rank Fusion）提供了一种不依赖原始分数绝对值、仅依赖排名位置的融合方案：将每种检索方式的结果按相关性降序排列后，每个文档的 RRF 分数仅由它在各检索路径中的排名决定，与原始分数的数值大小无关。这就天然消除了量纲差异问题。

在 RRF 基础上，ZRAG 进一步引入了可配置的路径权重——`score(d) = w_vector/(k+rank_vector) + w_keyword/(k+rank_keyword)`。权重通过 `config/retrieval.yaml` 中的 `rrf_weights.vector` 和 `rrf_weights.keyword` 配置（默认等权 1.0）。引入查询改写后，两条路径的输入各自针对其检索方式做了优化（关键词→FTS5，精炼查询→向量），但不同知识库语料特征下两类检索的贡献度可能不同——技术文档密集的语料关键词检索贡献更大，随笔记录居多的语料向量检索贡献更大。可配置权重使运维者能按语料特征调整融合偏向，而不改变等权默认值下的标准 RRF 行为。

**常数 k=60 的依据**。RRF 公式中使用常数 k 的目的是平滑极端排名差异——如果某文档在向量检索中排名第 1（rank=1），但在关键词检索中未出现（rank 视为 infinity），如果没有 k 的缓冲，该文档的 RRF 分数完全由 1/1 主导，与排名第 2 的文档（1/2=0.5）差距过大。k=60 使排名第 1 的项分数为 1/(60+1)≈0.0164，排名第 2 为 1/(60+2)≈0.0161，差距被平滑到合理范围。k=60 这个取值来源于 RRF 原论文（Cormack et al., 2009）的实验结果——论文在 TREC 数据集上测试了 k 从 0 到 1000 的多个取值，k=60 在大多数查询场景下取得最优效果。ZRAG 直接采用这一业界经验值，不做额外的参数调优。

RRF 的核心特点：
- 不需要对不同检索方式的原始分数做归一化
- 自动融合排名信息，两种检索方式的结果自然去重
- 常数 k=60 用于平滑极端排名差异
- 可配置权重 w_vector / w_keyword，按语料特征调整融合偏向，默认等权
- 候选池扩大至 k×2，避免遗漏单路径认可的优质结果

## 2.3 RAG 问答流程

一次完整的 RAG 问答请求经历以下阶段：

```
POST /v1/conversations  {"query": "什么是装饰器？"}
        │
        ▼
  1. 参数校验 (ConversationQuerySerializer, max_length=2000)
        │
        ▼
  2. 创建会话 (UUID → conversations 表, title = query[:50])
        │
        ▼
  3. 混合检索 (Retriever.hybrid_search, k=10)
        │
        ▼
  4. Prompt 构建 (Jinja2 模板渲染 → system message + user message)
        │
        ▼
  5. LLM 调用 (OpenAI SDK → LiteLLM Gateway → 模型回复)
        │
        ▼
  6. 消息持久化 (user + assistant → messages 表, sources 字段记录引用)
        │
        ▼
  7. 返回响应 {conversation_id, user_message, assistant_response}
```

### 设计理念

**为何 LLM 调用在 DB 事务之外**。从流程图中可以看出，RAG 问答的步骤顺序是：参数校验 → 创建会话 → 混合检索 → Prompt 构建 → LLM 调用 → 消息持久化。其中"创建会话"步骤（写入 conversations 表和 user message）与"消息持久化"步骤（写入 assistant message）之间夹着 LLM 调用。如果将整个流程包裹在一个数据库事务中——即从"创建会话"到"消息持久化"都处于同一个 SQLite 事务内——那么 LLM 调用（耗时通常在 2~20 秒，复杂 Query 可能超过 30 秒）期间事务会持续持有 SQLite 的写锁。SQLite 的写锁是数据库级别的，同一时间只允许一个写事务执行，其他并发的读请求（如会话列表查询）将被阻塞，直到当前事务提交或回滚。对于一个个人项目来说，这种长时间持锁会直接导致前端感知到的"卡顿"。更严重的是，LLM 调用是流程中最不可靠的环节——它依赖外部网络和远端模型服务，超时、失败的概率远高于数据库写入操作。如果在事务内调用 LLM，一旦 LLM 调用失败，已经写入的 conversations 记录和 user message 是否需要回滚就成为一个两难选择：回滚意味着用户的输入也丢失了，不回滚意味着数据库中留下了没有 assistant 回复的"半截对话"。基于上述分析，ZRAG 将 LLM 调用放在 DB 事务之外——会话创建和 user message 写入在独立事务中完成并立即提交，然后执行 LLM 调用，最后在另一个独立事务中持久化 assistant message。这样，LLM 调用期间不持有任何数据库锁，其他请求可以正常访问数据库；LLM 调用失败时，已有的 user message 已经安全落地，不需要回滚，系统只需返回错误信息，且前端可以在错误气泡中保留用户的原始输入，用户可以选择重试。

> 注意：这种设计意味着 LLM 调用失败后，数据库中会存在一条没有对应 assistant reply 的 user message。这不会影响系统的正常运行——会话列表查询和消息列表查询不需要依赖 assistant 消息的存在，前端展示时也能正确处理"只有用户消息"的情况。

**多轮对话为何取最近 10 条**。在多轮对话场景中，需要在已有会话基础上追加消息，此时系统会将历史消息作为上下文发送给 LLM，以保持对话的连贯性。历史消息的数量需要通过限定来平衡对话连贯性和上下文窗口容量。如果取全部历史消息，对于长对话来说消息列表会迅速膨胀——每条消息的 content 字段可能包含数百字——最终导致发送给 LLM 的 token 数超出模型的上下文窗口上限（如 deepseek-v4-flash 的上下文窗口为 128K token），LLM 调用会因 token 超限而失败。如果取历史消息过少（如 2~3 条），多轮对话的"记忆"过于短暂，用户稍微追问几轮后系统就忘记了前文背景，失去了多轮对话的意义。ZRAG 选择取最近 10 条历史消息（即 5 轮完整对话，每轮包含 1 条 user + 1 条 assistant），这个数量的设计依据是：10 条消息加上 system prompt（Jinja2 模板渲染后约 500~1000 token，取决于检索结果的材料数量）和当前 user query，总 token 数通常在 3K~4K 之间，远低于主流模型的上下文窗口下限，留出了充足的余量给 LLM 生成回复。此外，10 条消息大约对应 5 个问答来回，足以覆盖大多数个人知识库场景中的连续追问深度——用户通常在进行 3~5 轮追问后已经得到满意回答，极少需要连续追问超过 10 轮。

多轮对话扩展（在已有会话中追加消息）：
- 加载该会话最近 10 条历史消息
- 构建消息列表：`[system_msg] + [history...] + [user_msg]`
- 后续流程与新会话相同

## 2.4 会话管理

会话（Conversation）是用户与系统交互的上下文容器，记录了完整的多轮对话历史。

数据模型：

```sql
CREATE TABLE conversations (
    id              TEXT PRIMARY KEY,  -- UUID
    title           TEXT NOT NULL,      -- 首条 query 前 50 字符
    summary         TEXT NOT NULL DEFAULT '',          -- 对话压缩摘要（自然语言文本）
    summary_updated_at TEXT NOT NULL DEFAULT '',       -- 摘要最后更新时间
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE messages (
    id              TEXT PRIMARY KEY,    -- UUID
    conversation_id TEXT NOT NULL,       -- FK → conversations.id
    role            TEXT NOT NULL,       -- 'user' | 'assistant'
    content         TEXT NOT NULL,       -- 消息正文
    sources         TEXT,                -- JSON, 仅 assistant 消息
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);

-- messages 表索引
CREATE INDEX idx_messages_conv_id ON messages(conversation_id);
CREATE INDEX idx_messages_created ON messages(conversation_id, created_at);
```

### 设计理念

**为何会话在首条消息时自动创建**。在很多聊天类系统中，会话的创建和消息的发送是两个独立的操作——用户需要先点击"新建会话"按钮创建一个空的 conversation 记录，然后才能在该会话中发送第一条消息。这种两步操作的交互模式在本项目的设计考量中有两个缺点。第一，空会话状态需要前端额外处理：会话列表中会出现 title 为空的"未命名会话"条目，增加了前端的展示复杂度（需要处理 title 缺失的兜底显示逻辑）和用户的操作负担（需要对新创建的会话进行命名管理）。第二，空会话没有实际的信息价值——一个不包含任何消息的 conversation 记录在数据库中只是占位符，不承载任何对话上下文，却需要在前端、后端和数据库三层都进行"空会话"的状态管理。从个人知识库产品简洁直观的交互理念出发，ZRAG 选择在首条消息发送时自动创建会话——用户只需输入一个问题并发送，系统在收到 query 的同时创建 conversation 记录（title 取自 query 的前 50 个字符），然后继续执行检索和 LLM 调用的后续流程。这种设计使"创建会话"和"发送消息"合并为一个原子操作，前端不需要维护空会话状态，用户也不需要在开始对话之前执行额外的创建步骤。

**为何删除是幂等的**。删除会话的 API（`DELETE /v1/conversations/{id}`）设计要求是：即使请求的 conversation_id 在数据库中不存在（可能已被之前的删除操作移除，或因前端网络延迟导致重复发送 DELETE 请求），服务端仍然返回 200 成功响应。这种设计背后的考量来自前端网络环境的不可靠性——在移动网络或弱网环境下，前端的 DELETE 请求可能在服务端已成功执行删除（数据已从数据库中移除），但响应包在网络传输中丢失，前端未收到成功反馈后自动重试 DELETE 请求。如果删除非幂等（即会话不存在时返回 404 或 500），前端会将该错误视为"删除失败"，持续重试并向用户展示错误提示，造成用户困惑——会话明明已经删除了，为什么还提示删除失败。因此，将删除设计为幂等操作——无论会话存在与否，服务端始终返回成功——前端可以简单地忽略所有 DELETE 的响应状态，不需要设计复杂的重试和错误处理逻辑。

**为何用子查询而非冗余字段**。会话列表需要按最近消息时间倒序排列（最近有活动的会话排在最前）。实现这个排序有两种方案。方案一是在 conversations 表中增加 `last_msg_at` 冗余字段，每次插入新消息时同步更新该字段——这种方式查询简单（直接 ORDER BY last_msg_at DESC），但引入了写扩散问题：每次插入 messages 记录都需要额外更新 conversations 表，且 messages 的插入和 conversations 的更新需要放在同一个事务中，增加了写入操作的复杂度和锁竞争。方案二是通过子查询从 messages 表中动态获取每个会话的最近消息时间——SQL 为 `SELECT c.*, (SELECT MAX(m.created_at) FROM messages m WHERE m.conversation_id = c.id) AS last_msg_at FROM conversations c ORDER BY last_msg_at DESC`。这种方案不引入冗余字段，不产生写扩散，messages 的写入和 conversations 的查询完全解耦。在个人使用规模下（会话总数通常在几十到几百个，每个会话的消息数在几十到上百条），SQLite 对这种子查询的执行性能完全够用——子查询走 messages 表的 `conversation_id` 索引，耗时在毫秒级，前端用户无法感知任何延迟。基于上述分析，ZRAG 选择子查询方案——避免冗余字段带来的写扩散，利用 SQLite 的索引能力保证查询性能。

设计要点：
- 会话在首条消息时自动创建，不需要预先创建空会话
- 删除会话采用级联策略：同一事务中 DELETE messages → DELETE conversations
- 会话列表按最近消息时间倒序排列（通过子查询获取 last_msg_at）
- 删除操作幂等：会话不存在时仍返回成功

### 对话摘要与上下文感知检索

**为何需要对话摘要**。当前系统的多轮对话中，检索阶段（QueryRewriter 和 hybrid_search）完全不感知对话上下文。用户追问 "那它的性能怎么样？" 时，QueryRewriter 收到的只有这句不完整的追问，"它" 无法被解析为前一问的核心实体（如 "Kubernetes 默认调度器"）。更隐蔽的问题出现在追问内容由上一轮 assistant 回复引入的场景中——如用户问 "打分具体是怎么做的"，"打分" 这个词在用户历史查询序列中从未出现，而是在上一轮 assistant 回复中首次提及。这种问题在信息检索领域被称为上下文缺失查询，即查询语句本身不含足够的信息来判断用户的真实意图，必须结合前文上下文才能理解。解决方式是引入对话摘要机制——系统在每轮对话结束后将 Q&A 压缩为一段简洁的自然语言摘要，下一轮追问时将摘要注入 QueryRewriter 的输入中，使改写模型能够理解 "当前在讨论什么"。

**为何采用增量压缩**。将多轮对话压缩为摘要有两种策略：全量压缩（传入全部历史 Q&A 重新生成摘要）和增量压缩（传入已有摘要 + 最新一轮 Q&A）。ZRAG 选择增量压缩。全量压缩的问题在于，随着对话轮数增长，输入 prompt 会线性膨胀——第 10 轮对话的压缩需要传入前 9 轮的所有 Q&A 文本，对本地 9B 模型而言 prompt 可能超过 5000 字符，推理延迟显著增加。增量压缩则将输入限定为已有摘要（最多 200 字）+ 最新一轮 Q&A（截断到 500 字），输入长度恒定。此外，增量压缩天然实现了信息衰减——早期对话内容在反复重压缩中被逐步泛化，第 1 轮的详细讨论在第 8 轮后可能退化为一个简述词，这种衰减与人类对话中话题漂移的认知模式一致。不需要显式限制对话轮次，200 字的硬上限迫使 LLM 自行取舍优先级，更重要、更新的话题会自然挤掉旧话题。

**为何摘要存储在 conversations 表中**。一个会话只有一个摘要，是一对一关系。摘要跟随 conversations 记录的创建而初始化（空字符串），跟随对话的进行而被逐轮更新。会话删除时摘要自动级联清理，无需额外维护。`summary_updated_at` 字段记录最后一次摘要更新时间，用于运维阶段判断摘要是否因异步压缩失败而长期未更新（即降级状态持续时长）。

**为何摘要也要注入 LLM 生成阶段**。摘要最初仅设计用于查询改写阶段（QueryRewriter）。但分析发现，LLM 生成阶段同样面临长对话的信息截断问题——SQL 查询 `LIMIT 10` 意味着超过 10 轮后，第 1 轮到第 6 轮的消息被丢弃，LLM 无法感知早期对话内容。而摘要通过增量压缩保存了从第 1 轮开始的完整上下文（压缩在 200 字内），即使在长对话中也始终可用。将摘要注入 `full_messages` 后，即使历史消息只剩最近几轮，LLM 仍能从摘要中了解更早的对话背景。

**摘要注入位置为何放在 rag system prompt 之后**。`full_messages` 的消息顺序经过了仔细考量。摘要作为第 2 条 system 消息（位于 rag system prompt 之后、历史消息之前），而非放在最前面。理由：rag system prompt 定义了 LLM 的角色、回答规则和对参考材料的使用方式——这是最高优先级的指导信息，必须放在最前面。摘要作为补充上下文紧跟其后，语义位置自然——LLM 先拿到 "你是知识库助手，参考材料如下"，再了解 "之前讨论了什么"，最后读到历史消息和当前问题。如果反过来把摘要放在最前面，LLM 先看到的是一段没头没尾的对话背景，角色认知和回答规则到后面才出现，优先级被稀释。此外，摘要是独立的 system 消息而非混入 rag system prompt 中——避免与参考材料混在一起导致 LLM 难以区分"系统角色指令"、"背景知识"和"参考文档"三种不同信息源。

**为何缩减历史消息数量**。既然摘要提供了完整上下文，历史消息只需保留最近几轮以保证口语连贯性即可。`LIMIT` 从 10 缩减为 3（约 1.5 轮 Q&A）。缩减历史消息减少了 prompt token 消耗，对于对话较长时的 API 模型消费有直接收益。同时，摘要承担了"长期记忆"的职责，历史消息退化为"短期语流连贯"，职责分离清晰。

---

# 3. 存储层设计

ZRAG 的存储层由两个互补的数据库组成：SQLite 负责结构化数据和全文检索，ChromaDB 负责向量存储和语义检索。两者都是嵌入式数据库，数据存储在本地文件系统中，无需独立部署服务进程。以下逐节展开各存储模块的设计细节和决策理由。

> 注意：本章中"双库"指 SQLite 和 ChromaDB 的组合使用。"可信数据源"（Source of Truth）指 SQLite，因为它是唯一具备 ACID 事务保证的存储。

## 3.1 SQLite 存储

SQLiteStore 是系统的**可信数据源**（Source of Truth），负责 chunks、FTS5 全文索引、processed_docs、conversations 和 messages 的全部持久化管理。

### 设计理念

**为何选择 SQLite 而非 PostgreSQL/MySQL**。在设计存储层时，首先面临的问题是选择哪种关系型数据库。PostgreSQL 拥有最完善的功能集（全文搜索 tsvector、向量扩展 pgvector、丰富的索引类型），MySQL 在 Web 应用领域有广泛的生态支持。但两者都需要独立部署服务进程——这意味着用户在使用 ZRAG 前必须先安装并配置数据库服务器，还需要管理数据库用户权限、端口监听、定期备份等运维任务。对于个人使用场景而言，这种运维开销是不可接受的。此外，SQLite 内置的 FTS5 扩展提供了原生 BM25 全文检索能力，零额外依赖即可实现高质量的关键词搜索——无需引入 Elasticsearch、无需安装 PostgreSQL 的额外扩展。SQLite 的嵌入式特性——将全部数据存储在一个 `.db` 文件中——与 ZRAG"本地优先、零运维"的理念高度一致：备份只需复制一个文件，迁移只需移动一个文件。基于上述分析，SQLite 是个人 RAG 场景下的最优选择。

> 注意：SQLite 在当前规模（< 1000 文档）下性能充裕。如果未来文档量级增长到数万篇以上，可以考虑迁移到 PostgreSQL，届时 SQLiteStore 的接口封装使得替换底层数据库不需要修改调用方代码。

**为何启用 WAL 模式**。在 SQLite 的默认模式（DELETE journal mode）下，读操作会阻塞写操作——当一个连接正在写入时，其他连接的读请求必须等待写入完成。在 RAG 场景中，检索操作（读密集）和摄入操作（写操作）可能同时发生：用户在 Web UI 中发起提问，后端正在进行向量检索；与此同时，后台可能正在执行增量摄入写入新 chunk。如果读被写阻塞，用户的问答体验会受到影响。WAL（Write-Ahead Logging）模式解决了这个问题：写操作不直接修改主数据文件，而是写入独立的 WAL 文件，读操作则从主数据文件和 WAL 文件的快照中读取。这使得读写可以并发进行——读操作不阻塞写操作，写操作也不阻塞读操作。对于 RAG 场景中检索占主导的读写比例，WAL 模式带来的并发读性能提升是显著的。

```python
def _get_conn(self) -> sqlite3.Connection:
    if self._conn is None:
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row       # 列名访问
        self._conn.execute("PRAGMA journal_mode=WAL")  # 读写并发
        self._conn.isolation_level = None          # 手动事务管理
    return self._conn
```

**为何使用 sqlite3.Row 作为 row_factory**。SQLite 默认的查询结果返回的是元组（tuple），访问字段只能通过索引位置——`row[0]` 代表第一列、`row[1]` 代表第二列。这种方式在查询涉及多列时，代码可读性极差：一个月后回头看 `row[3]`，完全不知道它对应哪个字段。更重要的是，如果表结构发生变化（例如在某列前插入新列），所有基于索引位置的代码都会出现逻辑错误，而 Python 不会给出任何类型层面的提示。将 `row_factory` 设置为 `sqlite3.Row` 后，查询结果可通过列名访问——`row['content']`、`row['source_id']`——代码的意图一目了然，且不随列顺序的改变而受影响。这是一个零成本的改进：sqlite3.Row 是 Python 标准库内置的类，不需要安装任何第三方依赖。

**为何用触发器而非代码同步 FTS5**。FTS5 虚拟表需要与 chunks 表保持同步：chunks 表中新增或删除一行时，FTS5 索引必须同步更新。有两种实现方式可选：在应用代码中同步（即每次 `INSERT INTO chunks` 之后手动执行 `INSERT INTO chunks_fts`），或在数据库层通过触发器自动同步。如果在应用代码中同步，存在一个风险：如果 `INSERT INTO chunks` 成功但后续的 FTS5 INSERT 因代码异常（如程序崩溃、网络中断导致的连接断开）而未执行，chunks 表和 FTS5 索引之间就产生了不一致——chunks 表中有该数据但 FTS5 搜不到。将同步逻辑放在数据库层的触发器（trigger）中，可以保证原子性：触发器与触发它的 INSERT/DELETE 语句在同一个事务内执行，要么一起生效，要么一起回滚。此外，触发器还消除了应用代码中的重复逻辑——所有调用 `add_chunks()` 或 `delete_by_source()` 的地方都不需要关心 FTS5 的同步问题。

**为何 processed_docs 是独立表而非 chunks 表的字段**。processed_docs 表记录的是文档级别的处理状态（每篇文档一行），而 chunks 表记录的是分块级别的存储数据（每篇文档的多行分块）。两者的粒度不同——一个是"文档是否已处理"，一个是"文档被切成了哪些分块"。如果将处理状态作为字段（如 `is_processed`）加到 chunks 表的每一行，会产生数据冗余：一篇文档的 20 个 chunk 都存储同一个处理状态标记。更关键的是语义混淆——处理状态是文档层的信息，不应该与 chunk 层的数据合并。在查询"某篇文档是否已处理"时，独立表只需一次主键查找（`SELECT * FROM processed_docs WHERE source_id = ?`），而合并在 chunks 表中则需要 `SELECT DISTINCT` 或 `LIMIT 1` 查询，效率更低。此外，processed_docs 拥有独立的结构演化空间——未来如果需要增加处理状态字段（如 `last_error`、`retry_count`、`chunk_count`），修改独立表不影响 chunks 表的结构和所有基于 chunks 的查询代码。

### 核心设计与 Schema

SQLiteStore 封装了连接管理、CRUD 操作、事务管理和 FTS5 全文搜索的全部能力。

```python
class SQLiteStore:
    """SQLite 存储操作封装
    
    懒加载连接, 自动启用 WAL 模式提升并发读性能。
    提供参数化查询防止 SQL 注入, 事务上下文管理器自动管理 BEGIN/COMMIT/ROLLBACK。
    """
    
    def __init__(self, db_path: str | None = None):
        # db_path 可从参数显式传入或从 Django settings 读取
        # 测试场景可传入 ':memory:' 创建内存数据库
    
    def _get_conn(self) -> sqlite3.Connection:
        # 懒加载: 首次调用时创建连接, 启用 WAL 模式
        # row_factory = sqlite3.Row 使查询结果可通过列名访问
        
    def execute(self, sql, params=()) -> sqlite3.Cursor: ...
    def fetch_one(self, sql, params=()) -> dict | None: ...
    def fetch_all(self, sql, params=()) -> list[dict]: ...
    
    @contextmanager
    def transaction(self):
        """事务上下文管理器, 异常时自动回滚"""
        conn.execute("BEGIN")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
```

FTS5 全文搜索通过 SQLite 内置的 BM25 评分实现，零外部依赖：

```python
def search_fts5(self, query: str, k: int = 10) -> list[dict]:
    """使用 FTS5 全文搜索引擎进行关键词检索
    
    BM25 评分由 SQLite FTS5 内置提供, 零额外依赖。
    """
    return self.fetch_all(
        """SELECT c.*, bm25(chunks_fts) AS bm25_score
           FROM chunks_fts
           JOIN chunks c ON c.rowid = chunks_fts.rowid
           WHERE chunks_fts MATCH ?
           ORDER BY bm25(chunks_fts)
           LIMIT ?""",
        (query, k),
    )
```

FTS5 数据同步通过 SQLite 触发器自动维护，保证原子性：

```sql
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, content) VALUES (new.rowid, new.content);
END;

CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, content) VALUES('delete', old.rowid, old.content);
END;
```

- FTS5 中文分词：写入时对 content 调用 `_tokenize_text()`（jieba 分词后空格连接），查询时 `search_fts5()` 对 query 同样做分词处理，保证写入和查询端令牌粒度一致
- `_sanitize_fts5_query()` 清洗 FTS5 特殊字符，`_tokenize_text()` 做 jieba 分词，两者按序组合后传入 MATCH

数据库完整 Schema：

```sql
-- 文档分块表
CREATE TABLE chunks (
    chunk_id     TEXT PRIMARY KEY,
    source_id    TEXT NOT NULL,
    source_type  TEXT NOT NULL,
    doc_title    TEXT,
    content      TEXT NOT NULL,
    chunk_index  INTEGER,
    created_at   TEXT DEFAULT (datetime('now'))
);

-- FTS5 全文索引 (虚拟表)
CREATE VIRTUAL TABLE chunks_fts USING fts5(
    content, content=chunks, content_rowid=rowid
);

-- chunks 表索引
CREATE INDEX idx_chunks_source_id ON chunks(source_id);
CREATE INDEX idx_chunks_source_type ON chunks(source_type);

-- 文档处理进度追踪表 (独立于 chunks, 文档级粒度)
CREATE TABLE processed_docs (
    source_id     TEXT PRIMARY KEY,
    source_type   TEXT NOT NULL,
    content_hash  TEXT NOT NULL,
    imported_at   TEXT NOT NULL
);

-- ingest_tasks 用于追踪摄入任务进度
CREATE TABLE ingest_tasks (
    id         TEXT PRIMARY KEY,
    task_type  TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'pending',
    total      INTEGER DEFAULT 0,
    processed  INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ingest_lock 用于并发摄入保护（IngestGuard），
-- 通过 CHECK (id = 1) 确保单行，原子 UPDATE 实现分布式锁
CREATE TABLE ingest_lock (
    id         INTEGER PRIMARY KEY CHECK (id = 1),
    is_running BOOLEAN NOT NULL DEFAULT 0,
    started_at TEXT,
    request_id TEXT
);

-- processed_docs 表索引
CREATE INDEX idx_processed_source_type ON processed_docs(source_type);
```

## 3.2 ChromaDB 向量存储

ChromaStore 封装 ChromaDB 的 PersistentClient 和 Collection，负责文档向量的持久化与相似度检索。

### 设计理念

**为何选择 ChromaDB 而非 Pinecone/Qdrant/Milvus**。向量数据库领域有多种成熟的产品：Pinecone 是托管云服务，搜索性能优秀但数据必须上传到云端（用户文档离开本地）；Qdrant 性能极高且提供丰富的过滤查询能力，但需要独立部署服务进程；Milvus 是为十亿级向量规模设计的分布式系统，功能强大但部署和运维复杂度极高——需要协调 etcd、MinIO、Pulsar 等多个组件。对于 ZRAG 的个人使用场景（< 1000 文档、单用户、隐私优先），上述方案均过度设计。ChromaDB 的定位恰好匹配：嵌入式向量数据库，通过 PersistentClient 模式将向量数据和元数据持久化到本地文件系统，无需独立服务进程。其 Python API 简洁直观——`add()`、`query()`、`delete()` 等核心方法覆盖了 ZRAG 所需的全部向量操作。数据直接存储在 `data/chroma_db/` 目录中，备份和迁移与 SQLite 一样简单——复制整个目录即可。

> 注意：ChromaDB 底层使用 SQLite 存储元数据，使用 HNSW（Hierarchical Navigable Small World）索引结构存储向量。在大规模场景（百万级以上向量）下，ChromaDB 的查询延迟会显著上升——但这对 ZRAG 当前规模完全不是问题。

**为何使用 Cosine 距离而非欧氏距离**。向量检索中衡量两个向量"相似程度"的最常用距离度量有三种：欧氏距离（Euclidean / L2）、余弦相似度（Cosine Similarity）和内积（Inner Product / IP）。欧氏距离衡量的是空间中的直线距离，取值受向量长度影响——即使两个向量方向完全一致，只要其中一个向量长度是另一个的两倍，欧氏距离就会很大。余弦相似度只关注向量之间的夹角方向，不受向量长度影响。BGE 模型在训练时使用 L2 Normalize 处理输出向量——所有向量的模长为 1。在向量已归一化的前提下，余弦相似度等价于内积，且与欧氏距离存在严格的单调数学关系（欧氏距离^2 = 2 - 2 * 余弦相似度）。因此对于 normalize 后的向量，选择 Cosine 和 Euclidean 在排序上是等价的——但 Cosine 的内积计算（点乘）比 Euclidean 的平方差计算快约 30%。更重要的是，业界主流的 RAG 系统（包括 LangChain 和 LlamaIndex 的默认配置）均采用 Cosine 距离，使用主流约定可以避免后续接入其他组件时产生距离度量不一致的隐性 bug。

**为何 Collection 延迟初始化而非 `__init__` 中创建**。这个问题与 [1.4.4 节](#144-chromadb--embedding-单例) 中讨论的 uWSGI prefork 问题密切相关。ChromaDB 底层使用 SQLite 作为元数据存储引擎。如果 `ChromaStore.__init__()` 中调用 `get_or_create_collection()`，ChromaDB 内部会立即建立 SQLite 连接。在 uWSGI 的 prefork 模式下，如果应用模块在主进程中加载（默认行为），这个 SQLite 连接的文件描述符会在 fork 时被复制到所有 worker 进程——多个进程通过同一个文件描述符操作 SQLite，导致 `database is locked` 或数据损坏。延迟初始化（lazy init）将 Collection 的创建推迟到首次调用 `add()`、`similarity_search()` 等公共方法时。配合 `lazy-apps = true`（应用模块在 worker fork 之后才加载），确保每个 worker 进程在独立的内存空间中初始化自己的 ChromaDB PersistentClient 和 SQLite 连接，互不干扰。同时，延迟初始化也避免了 ChromaDB 在不需要它的场景（如运行数据库迁移、运行测试时 mock 了 ChromaStore）中无谓地初始化。

```python
class ChromaStore:
    def __init__(self, persist_dir: str | None = None):
        self._client = chromadb.PersistentClient(
            path=self._persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = None  # 延迟初始化: 不在此创建 Collection

    def _get_collection(self):
        """内部方法: 首次调用时自动触发 Collection 初始化"""
        if self._collection is None:
            self.init_collection()
        return self._collection
```

**为何 `add()` 方法在 ids 为空时直接 return**。ChromaDB 的 Collection.add() 不允许传入空的 ids 列表——如果传入空列表会抛出异常。在业务场景中，出现空的 ids 列表并非不可能：例如某篇文档分块后的所有 chunk 内容都是空字符串（被分块策略过滤掉），导致没有内容需要写入 ChromaDB。如果在调用侧（IngestionPipeline 中）每次调用 `add()` 前都先检查 ids 是否为空，会导致这类空值判断散布在多个调用点，代码分散且容易遗漏。将这个保护逻辑封装在 ChromaStore 的 `add()` 方法内部（空列表直接 return，无副作用），调用方只需调用 `store.add(ids, embeddings, metadatas)` 即可，无需关心边界条件。

```python
def add(self, ids: list[str], embeddings: list[list[float]], metadatas: list[dict]) -> None:
    if not ids:
        return  # 空列表直接返回, 避免 ChromaDB 底层抛异常
    col = self._get_collection()
    col.add(ids=ids, embeddings=embeddings, metadatas=metadatas)
```

### 核心设计与 API

```python
class ChromaStore:
    """ChromaDB 向量存储操作封装
    
    __init__ 只建立 client, 不自动创建 collection。
    Collection 通过 init_collection() 或首次调用公共方法时延迟初始化。
    使用 Cosine 距离度量, Collection 名固定为 'zrag_docs'。
    """
    
    def init_collection(self):
        """幂等: 重复调用不覆盖已有数据"""
        self._collection = self._client.get_or_create_collection(
            name="zrag_docs",
            metadata={"hnsw:space": "cosine"},
        )
    
    def add(self, ids, embeddings, metadatas): ...
    def similarity_search(self, query_vector, k=10) -> list[dict]: ...
    def delete_by_source(self, source_id): ...
```

- similarity_search 结果中 metadata 为 None 时记录 WARNING 日志，不复用 `or {}` 静默替换，确保异常可追溯

uWSGI prefork 兼容性设计——双重保护机制：

1. `lazy-apps = true` — Django 应用在 worker fork **之后**加载，避免 ChromaDB 在主进程中初始化
2. 模块级单例（`get_chroma_store()`）— 每个 worker 进程内只有一个 PersistentClient 实例，避免重复创建和 SQLite 连接冲突

```python
# 模块级单例工厂
_chroma_store_instance = None

def get_chroma_store(persist_dir=None) -> ChromaStore:
    global _chroma_store_instance
    if _chroma_store_instance is None:
        _chroma_store_instance = ChromaStore(persist_dir=persist_dir)
    return _chroma_store_instance
```

## 3.3 数据一致性策略

文档摄入需要将数据同时写入 SQLite 和 ChromaDB 两个独立存储系统。这两个系统不具备跨库事务支持——SQLite 的 `BEGIN/COMMIT` 只覆盖自身的数据表，ChromaDB 的写入操作完全在事务语义之外。如何在无法使用分布式事务协调的前提下保证双库数据的一致性，是存储层设计中最核心的问题。

### 设计理念

**为何先 SQLite 后 ChromaDB 而非相反**。两种写入顺序对应的故障场景完全不同。如果先写 ChromaDB 后写 SQLite，当 ChromaDB 写入成功但 SQLite 写入失败时：SQLite 中缺少了 chunks 原文，ChromaDB 中却有对应的向量——未来检索可能搜到这条向量结果，但无法通过 `source_id` + `chunk_index` 从 SQLite 中查到对应的原文内容，检索结果出现"空指针"式的断链。反过来，如果先写 SQLite 后写 ChromaDB：SQLite 写入成功意味着完整的 chunks 数据已经安全持久化，即使 ChromaDB 写入失败，系统只需要重新为 SQLite 中已有的 chunks 计算向量并补写入 ChromaDB 即可完全恢复——无需担心原文丢失。这种不对称性来源于 SQLite 拥有 ACID 事务保证而 ChromaDB 不具备事务保证这一根本差异——SQLite 写入成功是一个可靠的状态锚点，ChromaDB 的写入只是"尽力而为"的补充。因此选择以 SQLite 作为可信数据源，写入顺序为"先 SQLite，后 ChromaDB"。

> 注意：`processed_docs` 表中记录的标记含义是"双库均已就绪"。如果 ChromaDB 写入失败，`processed_docs` 不会被更新。下次摄入时，系统检测到该文档的 `content_hash` 未变化但 `processed_docs` 中无记录，会自动重新执行 ChromaDB 的写入——这本质上是一种基于补偿的最终一致性策略。

**为何每篇文档独立事务而非整个批次一个事务**。IngestionPipeline 每次摄入的文档来源于一个批次（默认 5 篇/批，可配置）。如果将整个批次的全部操作放在同一个 SQLite 事务中，那么任一篇文档的处理失败（如分块阶段遇到格式错误、向量化阶段 OOM、ChromaDB 写入失败）都会导致整个事务回滚——所有 5 篇文档（包括已经成功处理的文档）的写入成果全部丢失。而文档来源的质量是不可控的——macOS 备忘录中可能存在空正文或包含仅图片无文字的笔记——这类文档的处理失败是正常的业务场景，不应牵连同一批次中的其他有效文档。每篇文档独立事务意味着每篇文档的 SQLite 写入在自己的 `BEGIN/COMMIT` 边界内完成，一篇失败仅影响该篇自身，成功处理的文档结果不受影响。失败文档被记录到 `IngestReport.errors` 中，后续可通过 `on_error` 回调进行补偿处理。

> 参考 QA: storage-embedding.md Q19 和 data-ingestion.md Q23-Q24。

**为何 ChromaDB 写入在 SQLite 事务之外**。这看似反直觉——直觉上应该把尽可能多的操作放在事务保护之下。但 ChromaDB 不支持事务（其底层操作是即时提交的），无法纳入 SQLite 的 `BEGIN/COMMIT` 边界。如果将 ChromaDB 写入放在 SQLite 事务内部（即 `with transaction()` 块内），当 SQLite 事务回滚时，ChromaDB 的写入操作已经物理生效且无法撤销——这造成了更严重的不一致：SQLite 回滚后 chunks 数据消失，但 ChromaDB 中残留了旧版本的向量数据（因为先执行了 `delete_by_source` 再 `add` 新向量）。将 ChromaDB 写入放在 SQLite 事务外部明确了两层操作的边界：SQLite 事务保证 chunks 数据的一致性；ChromaDB 写入在 SQLite 事务成功后执行，失败了可以重试——下一次摄入检测到 processed_docs 缺失时自动触发重写。

**完整写入流程与异常恢复**。以下流程图展示了每篇文档从开始处理到双库就绪的完整路径，以及每一步失败时的恢复策略：

```
每篇文档处理:
  ┌─────────────────────────────────────────┐
  │ 1. Embedder.embed() — 前置向量化计算    │
  │    失败 → 跳过该文档, 零副作用           │
  ├─────────────────────────────────────────┤
  │ 2. SQLite 事务 (ACID 保证)              │
  │    ├─ delete_by_source                  │
  │    ├─ add_chunks                        │
  │    └─ COMMIT                            │
  │    失败 → 事务回滚, 下次同步重试         │
  ├─────────────────────────────────────────┤
  │ 3. ChromaDB 写入 (非事务)               │
  │    ├─ delete_by_source                  │
  │    └─ add                               │
  │    失败 → SQLite 数据完好, 下次同步重试   │
  ├─────────────────────────────────────────┤
  │ 4. 更新 processed_docs                  │
  │    upsert_processed (标记双库已就绪)     │
  │    失败 → 数据已就绪但标记滞后, 下次重试  │
  └─────────────────────────────────────────┘
```

各步骤失败的原因和恢复路径：

| 步骤 | 失败后果 | 恢复方式 |
|------|---------|---------|
| Embedder 失败 | 零副作用, 无数据写入 | 跳过该文档, 记录到 IngestReport.errors |
| SQLite 事务失败 | 事务内 DELETE+INSERT 全部回滚, chunks 数据未变更 | 下次同步 content_hash 不匹配, 自动重试 |
| ChromaDB 写入失败 | SQLite 数据已就绪, 向量缺失 | processed_docs 未更新, 下次同步检测缺失, 自动写入 ChromaDB |
| processed_docs 更新失败 | 双库数据已就绪, 但标记滞后 | 下次同步 content_hash 相同但无记录, 等同 ChromaDB 失败的恢复路径（浪费一次向量化但结果安全）|

> 核心理念：SQLite 是可信锚点，ChromaDB 是可重建层。只要 SQLite 中存有完整的 chunks 原文，即使 ChromaDB 的全部数据丢失，也可以通过重新向量化全部 chunks 来完整恢复。写入顺序和 processed_docs 的设计都建立在"SQLite 是 Source of Truth"这一基础上。

---

# 4. Embedding 模型

Embedding 模型是 RAG 系统中将自然语言文本转换为数学向量表示的核心组件。文本在经过 Embedding 后，语义上相似的内容在向量空间中距离更近，这是语义检索能够工作的基础。ZRAG 选择在本地完成全部 Embedding 计算，以保证用户文档内容不会离开本机。

本章从模型选型开始，逐层深入到抽象接口设计、方法分离、归一化策略、部署方式和单例管理，说明每个设计决策所对应的具体问题和考量。

## 4.1 模型选型：BAAI/bge-small-zh-v1.5

### 设计理念

**为何选择 BAAI/bge-small-zh-v1.5**。在本地 Embedding 模型的选型中，核心权衡维度有三个：向量维度（影响检索精度和存储开销）、模型体积（影响加载速度和内存占用）、语言适配性（针对中文场景的优化程度）。

在候选模型中，bge-small-zh-v1.5 在这三个维度上都处于适合个人场景的平衡位置。维度方面，512 维在嵌入质量和计算开销之间取得了良好平衡——相比 bge-base-zh-v1.5 的 768 维和 BGE-M3 的 1024 维，512 维向量在 ChromaDB 存储和 Cosine 距离计算中开销更低，但中文语义表达能力的下降幅度很小（C-MTEB 中文基准约 58 分，bge-base 约 62 分，两者差距在多数检索场景中不可感知）。体积方面，模型大小约 100MB（33M 参数），CPU 加载仅需约 5 秒，内存占用低于 200MB，在无 GPU 的个人机器上完全可运行。语言适配方面，BGE 系列专门针对中文场景进行了训练优化，对中文文本的语义区分能力优于同等规模的多语言模型。

此外，sentence-transformers 库作为 HuggingFace 生态中最为成熟的 Embedding 推理库，提供了简洁的 `encode()` 接口，自动处理 tokenization、batch inference 和输出后处理。该库经过多年社区验证，稳定性远高于自行调用底层 transformers 模型。

| 模型 | 维度 | 参数量 | C-MTEB 中文平均 | 特点 |
|------|------|--------|:-:|------|
| **bge-small-zh-v1.5** | 512 | ~33M | ~58 | 轻量快速，CPU 友好 |
| **bge-base-zh-v1.5** | 768 | ~110M | ~62 | 均衡之选 |
| **BGE-M3** | 1024 | ~568M | ~69 | 多语言+多粒度，质量最高但需 GPU |
| **Qwen3-Embedding** | 2048 | ~700M | ~69 | 最新最强，也需 GPU |

> 注意：上表中的数据来源于 [C-MTEB Leaderboard](https://huggingface.co/spaces/mteb/leaderboard) 和 BGE 官方仓库。bge-small-zh-v1.5 作为起步模型，后续可根据实际检索效果升级到 bge-base 或在线 API——EmbeddingModel ABC（见 4.2 节）的设计使得模型切换不影响下游代码。

## 4.2 抽象接口：EmbeddingModel ABC

### 设计理念

**为何定义 EmbeddingModel 抽象基类**。与 [1.4.3 节](#143-核心模块-abc抽象基类) 中讨论的 DocumentSource 和 ChunkingStrategy ABC 同理，Embedding 模型也存在"具体实现可能变化"的问题。当前阶段使用本地 BGE-small 模型，但未来可能切换到更大的 BGE-large 模型（提升检索精度）、M3E 模型（不同的中文训练数据），或云端 Embedding API（如 OpenAI text-embedding-3-small）以利用更强的 GPU 推理能力。

如果在调用方代码（如 IngestionPipeline、Retriever）中直接实例化 `BgeSmallEmbedder`，那么每次切换模型都需要修改所有调用点。通过定义 `EmbeddingModel` ABC，所有下游组件依赖的是抽象接口（`embed()`、`embed_query()`、`dimension`）而非具体实现类。新增一种 Embedding 实现只需继承 ABC 并实现三个抽象方法，然后在工厂函数中切换返回类型，IngestionPipeline 和 Retriever 的代码完全不需要修改。这与依赖注入原则（1.4.2 节）配合使用——Pipeline 和 Retriever 通过构造方法接收 `EmbeddingModel` 类型参数，测试时可传入 mock 实现。

Abstract base class definition:

```python
class EmbeddingModel(ABC):
    """Embedding 模型抽象基类

    定义文本嵌入模型的统一接口。
    所有具体的嵌入模型实现（如 BgeSmallEmbedder）必须继承此类并实现全部抽象方法。

    embed() 用于批量文本向量化, embed_query() 用于单条用户查询的向量化,
    两者分离是为了支持某些模型对查询和文档使用不同的编码策略。
    """

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """将批量文本转换为向量表示

        @param texts: 待向量化的文本列表
        @type  texts: list[str]

        @return: 向量列表, 每个元素对应一个输入文本的向量表示
        @type:   list[list[float]]
        """
        ...

    @abstractmethod
    def embed_query(self, query: str) -> list[float]:
        """将单条用户查询转换为向量表示

        某些模型对查询和文档使用不同的编码策略,
        因此与 embed() 分离为独立方法。

        @param query: 用户输入的查询字符串
        @type  query: str

        @return: 查询向量的表示
        @type:   list[float]
        """
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        """获取嵌入向量的维度

        @return: 该模型输出的向量维度
        @type:   int
        """
        ...
```

## 4.3 方法分离：embed() 与 embed_query()

### 设计理念

**为何 embed() 和 embed_query() 要分开设计**。在直觉上，两者都是"将文本转为向量"，似乎可以合并为一个方法——调用方传单个字符串就编码单条，传列表就批量编码。但这种设计忽略了两个真实场景中存在的关键差异。

第一，性能差异。文档摄入阶段（见第 5 章）需要对一个批次中所有 chunk 的文本内容进行向量化。如果将 embed_query 当作通用接口，逐条调用 `encode()` 编码每条 chunk，每一条调用都需要独立的 tokenization、模型前向传播和结果后处理——以 100 个 chunk 为例，就是 100 次模型推理。而批量调用 `embed(texts)` 将多条文本合并为 batch，模型在一个 batch 内完成矩阵运算——GPU 上的并行优势明显，CPU 上也因为 NumPy/SciPy 的底层 BLAS 优化而比逐条循环快数倍。对于摄入流程来说，这个性能差距直接决定了处理 500 篇文档需要 2 分钟还是 10 分钟。

第二，语义差异。BGE 系列模型对查询（query）和文档（document）使用不同的编码策略——查询侧需要添加指令前缀以引导模型产生更合适的查询向量表示。官方推荐的中文指令前缀为 `"为这个句子生成表示以用于检索相关文章："`，英文指令前缀为 `"Represent this sentence for searching relevant passages: "`。这套不对称编码策略的设计意图是：查询通常是简短的自然语言问题，而文档是较长的段落正文——两者在语言结构上存在天然差异。指令前缀告知模型当前输入的"角色"是查询而非文档，使模型在向量空间中为同一语义概念的不同表达形式（查询 vs 文档）生成更接近的向量表示，从而提升语义检索的召回质量。

BGE v1.5 系列相较于 v1.0 大幅降低了对指令前缀的依赖——不使用指令时检索质量下降约 1-5%，而非 v1.0 中的显著下降。但对于 ZRAG 的 s2p（short query to long passage）检索场景，指令前缀仍有正向收益且零额外成本——它仅是一个字符串拼接操作。文档侧（`embed()`）不添加任何前缀，因为文档块在训练阶段本身就是无前缀编码的。

因此，ABC 中将两者定义为独立方法：`embed(texts)` 接收列表批量编码，用于摄入流程，不加前缀；`embed_query(query)` 接收单条字符串编码，拼接指令前缀后向量化，用于检索流程。

```python
class BgeSmallEmbedder(EmbeddingModel):
    """基于 BAAI/bge-small-zh-v1.5 的本地 Embedding 实现

    使用 sentence-transformers 库加载 BGE 小型中文嵌入模型。
    输出 512 维向量, 已启用 normalize_embeddings=True 以便后续使用 Cosine 距离。

    @param model_name: HuggingFace 模型名称, defaults to "BAAI/bge-small-zh-v1.5"
    @type  model_name: str, optional
    @param cache_dir: 模型缓存目录, 用于指定预下载模型的存放位置, defaults to None
    @type  cache_dir: str, optional
    """

    def __init__(
        self, model_name: str | None = None, cache_dir: str | None = None
    ):
        """构造 BgeSmallEmbedder

        若 model_name 或 cache_dir 未显式传入，则从 Django settings.ZRAG_EMBEDDING 配置中读取。
        配置中也缺失时抛出 ValueError。

        @param model_name: HuggingFace 模型名称, defaults to None
                            未传入则从配置读取
        @type  model_name: str, optional
        @param cache_dir: 模型缓存目录, defaults to None
                          未传入则从配置读取
        @type  cache_dir: str, optional

        @raises ValueError: model_name 或 cache_dir 在参数和配置中均未提供时抛出
        """
        if model_name is not None and cache_dir is not None:
            m_name, c_dir = model_name, cache_dir
        else:
            from django.conf import settings
            emb_cfg = getattr(settings, "ZRAG_EMBEDDING", {})
            m_name = model_name or emb_cfg.get("model_name")
            c_dir = cache_dir or emb_cfg.get("cache_dir")
            if not m_name or not c_dir:
                raise ValueError(
                    "配置缺失: embedding.model_name 或 embedding.cache_dir, "
                    "请检查 config/embedding.yaml 或设置 MODELS_DIR 环境变量"
                )
        self._model = SentenceTransformer(m_name, cache_folder=c_dir)

    def embed(self, texts: list[str]) -> list[list[float]]:
        """将批量文本转换为 512 维向量

        @param texts: 待向量化的文本列表
        @type  texts: list[str]

        @return: 每个文本对应的 512 维向量列表
        @type:   list[list[float]]

        @raises: 模型加载失败或显存不足
        @type:   Exception
        """
        return self._model.encode(texts, normalize_embeddings=True).tolist()

    def embed_query(self, query: str) -> list[float]:
        """将单条查询转换为 512 维向量

        对查询文本拼接 BGE 中文指令前缀后编码，
        文档侧 embed() 不添加前缀，实现不对称编码。

        @param query: 用户输入查询
        @type  query: str

        @return: 查询的 512 维向量
        @type:   list[float]

        @raises: 同 embed()
        @type:   Exception
        """
        instruction = "为这个句子生成表示以用于检索相关文章："
        return self.embed([instruction + query])[0]

    @property
    def dimension(self) -> int:
        """嵌入向量维度

        @return: 512
        @type:   int
        """
        return 512
```

## 4.4 向量归一化：normalize_embeddings=True

### 设计理念

**为何设置 normalize_embeddings=True**。sentence-transformers 的 `encode()` 方法提供了 `normalize_embeddings` 参数，设为 True 时会将输出的每个向量进行 L2 归一化——即每个向量的模长被统一缩放为 1。启用归一化之后，两个向量的 Cosine 相似度（方向夹角）在数学上完全等价于内积（点乘），因为 `cos(a,b) = dot(a,b) / (|a| * |b|) = dot(a,b)`（分母已变为 1）。

这个设计的价值体现在两个层面。第一，计算性能。归一化后的 Cosine 距离计算退化为内积——即两个向量对应元素相乘再求和，这是 CPU 上最高效的向量运算之一（利用 SIMD 指令加速）。相比未归一化时需要额外计算模长和除法，内积的运算量减少约 30%。第二，BGE 官方推荐。BGE 模型在训练过程中使用对比学习损失函数，其训练目标天然倾向于让输出向量在归一化后直接比较方向。BGE 官方文档明确建议在推理时启用 `normalize_embeddings=True`。第三，与 ChromaDB 的一致性。ChromaDB Collection 的距离度量为 Cosine（见 3.2 节），ChromaDB 内部在接收到 embedding 后会计算 Cosine 距离。如果输入的向量已经是归一化的，ChromaDB 的 Cosine 计算等价于内积，不会因为向量长度差异引入数值精度损失。

> 注意：normalize_embeddings=True 是在模型推理输出后执行的数学变换（将向量投影到单位超球面上），不改变模型的推理过程。它是一个零成本的数学后处理操作，不增加推理耗时。

## 4.5 模型文件部署：只读 Volume 挂载

### 设计理念

**为何模型文件通过只读 Volume 挂载而非在容器内下载**。sentence-transformers 库在首次调用 `SentenceTransformer("BAAI/bge-small-zh-v1.5")` 时，如果本地缓存目录中不存在该模型，会自动从 HuggingFace Hub 下载模型文件（约 100MB）。如果在 Dockerfile 中或者容器启动时触发这个下载行为，会引入几个问题。

第一，重复下载。每次重建容器镜像或重新创建容器时，模型文件都会重新下载——以 bge-small-zh-v1.5 约 100MB 的体积计算，即使在良好网络条件下也需要几十秒至数分钟，在 HuggingFace 访问受限的网络环境中可能根本无法下载。第二，版本漂移。HuggingFace 上的模型文件可能会因维护者更新而产生细微变化（如 config.json 调整默认参数），这导致不同时间构建的容器可能加载到微妙不同的模型版本，产生的向量结果不完全一致——对于已持久化在 ChromaDB 中的向量数据，这种不一致会导致检索质量下降。第三，多项目冗余。同一宿主机上如果运行多个使用 BGE 模型的项目，每个项目的容器都在内部独立下载一份模型文件，造成磁盘空间浪费。

基于上述分析，ZRAG 将模型文件存放在宿主机上的统一目录（`${MODELS_DIR}/bge-small-zh-v1.5/`），通过 docker-compose 的只读 Volume（`:ro`）挂载到容器内的模型缓存路径。宿主机管理员负责一次性下载模型文件到该目录，之后无论容器重建多少次，模型文件都不需要重新下载。同时，只读挂载确保了容器内的代码无法修改或删除模型文件，避免了误操作导致模型损坏的风险。多项目可以共享同一份模型文件——每个项目的容器各自挂载到同一个宿主机目录即可。

```yaml
# docker-compose.yml (模型文件挂载片段)
services:
  backend:
    volumes:
      - ${MODELS_DIR}/bge-small-zh-v1.5:/app/models/bge-small-zh-v1.5:ro
```

> 注意：首次部署时，需要先在宿主机上执行模型下载脚本（`scripts/download_models.sh`），将所需的模型文件提前下载到 `${MODELS_DIR}`。容器启动后，`TRANSFORMERS_OFFLINE=1` 环境变量确保不会尝试从网络下载（见 4.7 节）。

## 4.6 单例模式：get_embedder()

### 设计理念

**为何使用单例模式管理 Embedder 实例**。SentenceTransformer 模型的加载是一个昂贵操作——涉及从磁盘读取模型权重文件（约 100MB）、解析 JSON 配置文件、构建 PyTorch/TensorFlow 计算图。即使在 SSD 上，这个过程的耗时也在 5~10 秒左右。如果在每次处理请求时都创建一个新的 BgeSmallEmbedder 实例，不仅响应延迟会膨胀到数十秒，反复的模型加载还会持续消耗内存，严重时触发 OOM。

单例模式确保在整个进程生命周期内只执行一次模型加载。工厂函数 `get_embedder()` 在首次调用时创建 BgeSmallEmbedder 实例并保存到模块级变量，后续调用直接返回该实例。这与 ChromaDB 的单例策略（3.2 节中的 `get_chroma_store()`）基于完全相同的考量。

但需要澄清的是：这里的"单例"是进程级别的，不是全局（跨进程）级别的。ZRAG 使用 uWSGI 的 prefork 模式运行，每个 worker 是一个独立进程。结合 `lazy-apps = true` 配置（Django 应用在 worker fork 之后才加载），每个 worker 进程在首次处理请求时各自独立调用 `get_embedder()`，各自加载一份模型到自己的内存空间。最终，如果配置了 2 个 worker，宿主机上会同时存在两份模型的内存副本（每份约 200MB）——这是 prefork 模式的固有代价，但换来了请求处理的隔离性（一个 worker 的模型 OOM 不影响另一个 worker）。

> 注意：`get_embedder()` 的 `model_name` 和 `cache_dir` 参数仅在首次调用时生效——这是单例的标准行为。如果需要运行时切换模型（例如从 bge-small 热切换到 bge-base），需要在切换逻辑中显式将模块级变量重置为 None，然后重新调用 `get_embedder()` 触发重新加载。当前阶段 ZRAG 不支持运行时热切换模型，因为这会短暂中断服务（模型加载期间无法处理 Embedding 请求）。

模块级单例工厂函数：

```python
# 模块级单例, 由 get_embedder() 管理
_embedder_instance = None


def get_embedder(
    model_name: str | None = None, cache_dir: str | None = None,
) -> BgeSmallEmbedder:
    """获取 BgeSmallEmbedder 模块级单例

    避免在 uWSGI worker 中重复创建 SentenceTransformer 实例,
    防止模型重复加载导致请求挂死。

    @param model_name: 模型名称, 仅首次调用时生效, defaults to None
    @type  model_name: str, optional
    @param cache_dir: 模型缓存目录, 仅首次调用时生效, defaults to None
    @type  cache_dir: str, optional

    @return: BgeSmallEmbedder 全局唯一实例
    @rtype:  BgeSmallEmbedder
    """
    global _embedder_instance
    if _embedder_instance is None:
        _embedder_instance = BgeSmallEmbedder(
            model_name=model_name, cache_dir=cache_dir,
        )
    return _embedder_instance
```

## 4.7 离线模式：TRANSFORMERS_OFFLINE=1

### 设计理念

**为何设置 TRANSFORMERS_OFFLINE=1 环境变量**。sentence-transformers 底层依赖 HuggingFace 的 `transformers` 库和 `huggingface_hub` 库。这些库的默认行为是：在加载模型时，如果本地缓存中未找到模型文件，会自动尝试通过 HTTPS 从 HuggingFace Hub 下载。在容器化部署场景中，模型文件应该已经通过只读 Volume 挂载到位（见 4.5 节），不需要也不应该触发网络下载。

如果没有设置 `TRANSFORMERS_OFFLINE=1`，会出现以下风险场景：某个环节的配置错误导致模型文件未正确挂载到容器的预期路径，sentence-transformers 在加载时未找到本地文件，自动发起对 HuggingFace Hub 的网络请求。由于 HuggingFace Hub 在中国大陆的访问可能不稳定（延迟高、偶发性连接超时），容器启动过程会卡在网络等待中——用户看到的表现为"容器启动了但一直没响应"，而日志中可能只是静默地等待一个 TCP 连接，没有任何明确的错误提示。排查这种问题往往需要查看网络抓包，成本远高于排查一个文件缺失错误。

设置 `TRANSFORMERS_OFFLINE=1` 后，transformers 库进入离线模式：它只会从本地缓存路径查找模型文件，不会发起任何网络请求。如果模型文件不存在，直接抛出明确的 `OSError` 或 `ValueError`，描述信息中包含期望的文件路径——这使得问题根因一目了然：模型文件未下载或挂载路径不正确。排查从"猜谜"变成"按错误信息修复"。

该环境变量在模块文件的最顶部设置（在任何 import 之前），确保所有依赖库在导入阶段就生效：

```python
import os
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from sentence_transformers import SentenceTransformer
from zrag.embed.base import EmbeddingModel
```

> 注意：`os.environ.setdefault()` 而非 `os.environ[...] =` 的写法是刻意为之——如果容器编排层（如 docker-compose environment 配置）中已经设置了该环境变量，代码中的 `setdefault` 不会覆盖已有值。这保证了运行环境可以通过环境变量覆盖离线模式（例如在首次部署、需要下载模型的场景中临时设置为 `TRANSFORMERS_OFFLINE=0`），而后代码中的默认值不会干扰这个覆盖。

---

# 5. 文档摄入

文档摄入是将外部知识源中的原始文档转换为可供检索的结构化数据的过程。本章从数据源抽象（DocumentSource）、具体数据源实现（MacNotesSource）、分块策略（ChunkingStrategy）到摄入编排器（IngestionPipeline），自下而上地说明每一层的设计理念、关键决策和代码结构。

## 5.1 DocumentSource ABC

### 设计理念

**为何抽象 DocumentSource**。知识来源是多样的——macOS 备忘录、本地 Markdown 和 PDF 文件、网页收藏、RSS 订阅，未来还可能增加更多来源。这些来源的获取方式截然不同：备忘录需要调用 AppleScript 或通过文件桥接读取，本地文件需要遍历文件系统，网页需要 HTTP 请求和 HTML 解析。如果在 Pipeline 中直接嵌入对每种来源的处理逻辑，代码将迅速膨胀为一个充满 if-else 分支的"上帝函数"——每新增一种来源，就要在 Pipeline 的多个位置添加新的分支判断，同时还需要保证不影响已有的来源处理逻辑。这种修改模式极易引入回归 bug。

DocumentSource ABC 提供了一种约束：所有数据源必须实现 `fetch_batch()` 方法和 `source_type` 属性。Pipeline 不需要知道当前处理的是哪种来源——它只需要调用 `source.fetch_batch()` 获取 RawDocument 列表，通过 `source.source_type` 记录来源类型。基于这种抽象，新增一种数据源只需新建一个类、实现 ABC 的两个方法、在注册表中登记即可——Pipeline 代码完全不需要修改。这就是 ABC + 注册表模式的核心价值："新增来源不改 Pipeline"。

**为何 fetch_batch 使用生成器而非一次性返回列表**。这是内存控制的考量。以 macOS 备忘录为例，用户可能有 3000+ 条笔记。如果 `fetch_batch()` 一次性将所有笔记加载为 RawDocument 对象列表返回，每个 RawDocument 包含完整的 Markdown 正文和元数据，3000 条笔记的内存占用可能达到数百 MB。更关键的是，Pipeline 在接收这批文档后还需要逐篇执行分块、向量化、双库写入——这些操作本身也需要内存。如果所有数据同时驻留内存，对于容器化部署中通常只有 768MB 内存的 backend 容器来说，存在 OOM 风险。

生成器（Iterator）模式允许 Source 逐批产出文档：每次 yield 一个包含 `batch_size` 条的列表，Pipeline 处理完这一批后再请求下一批。这样内存中同时存在的 RawDocument 数量始终不超过 `batch_size` 条（默认 5 条），内存使用量是可控的常量而非随文档总数线性增长的变量。

**为何 SOURCE_REGISTRY 放在 `__init__.py` 而非配置文件**。注册表中存储的是 Python 类的引用（`MacNotesSource` 类本身），而不是类名的字符串。这意味着注册表必须在代码中编写——`import` 是获取类引用的前提，无法通过 YAML 或 JSON 配置文件来建立"字符串到类"的映射（虽然可以通过反射实现，但那会引入不必要的不透明性和安全隐患）。将注册表放在 `__init__.py` 中是最简单的显式方案：新增 Source 时，创建对应的 Python 文件，然后在 `__init__.py` 中 `import` 并注册。代码即配置，一目了然，IDE 也能提供自动补全和跳转支持。

DocumentSource 定义从外部数据源获取原始文档的统一接口。所有数据源实现必须继承此类。

```python
class DocumentSource(ABC):
    """文档数据源抽象基类
    
    定义从不同来源获取原始文档的统一接口。
    fetch_batch() 使用生成器模式, 支持分批处理以控制内存占用。
    """
    
    @abstractmethod
    def fetch_batch(self, batch_size: int = 10) -> Iterator[list[RawDocument]]:
        """分批获取原始文档 (生成器模式)"""
        yield []
    
    @property
    @abstractmethod
    def source_type(self) -> str:
        """数据源类型标识, 如 "mac_notes" """
        ...
```

数据源通过注册表（`SOURCE_REGISTRY`）统一管理：

```python
# zrag/ingest/sources/__init__.py
SOURCE_REGISTRY = {
    "mac_notes": MacNotesSource,
}
```

注册表的使用方式（在 API 层）：

```python
source_cls = SOURCE_REGISTRY.get(source_type)
if source_cls is None:
    return error("Unknown source_type")
source = source_cls()
```

## 5.2 MacNotesSource

### 设计理念

**为何选择 AppleScript 读取 Notes.app**。macOS 上获取备忘录数据的主要方式有三种：读取 Notes.app 底层使用的 SQLite 数据库（位于 `~/Library/Group Containers/` 中）、通过 AppleScript 调用 Notes.app 的脚本接口、以及使用 EventKit API（需要 Objective-C/Swift 桥接）。三种方案的对比分析如下：

第一种方案直接读取 SQLite 数据库，看起来最直接——不需要与 GUI 应用交互，读写速度也最快。但这种方式的致命缺陷在于数据库的内部 Schema 不对外公开且不受兼容性保证——Apple 在任何 macOS 小版本或大版本更新中都可能修改表结构、字段名、编码方式，甚至切换到完全不同的存储后端（Core Data / CloudKit 的存储格式在历史上曾多次变更）。如果 ZRAG 依赖数据库内部结构，每次 macOS 更新都可能需要紧急适配，对于个人项目来说这种维护成本是不可接受的。

第二种方案使用 AppleScript，通过 macOS 内置的原生脚本接口与 Notes.app 通信。AppleScript 调用的是 Notes.app 对外暴露的脚本字典（Scripting Dictionary），这个接口是 Apple 官方文档化且承诺兼容的——即使底层存储格式改变，AppleScript 接口也能继续工作。`body of theNote` 属性直接返回笔记的富文本正文，无需关心底层数据库 Schema。AppleScript 的缺点是需要 shell 调用 `osascript` 命令（子进程方式），性能不如直接读取文件，但对于单次摄入几百到几千条笔记的场景，多花费几秒到十几秒完全可以接受。

第三种方案 EventKit 需要 Objective-C/Swift 桥接，引入了额外的语言依赖和编译步骤，对 Python 项目的集成复杂度显著增加，不考虑。

基于上述分析，选择 AppleScript 方案——macOS 原生、零权限配置（不需要辅助功能权限即可读取备忘录）、接口稳定、纯 Python 子进程调用即可使用。

```python
class MacNotesSource(DocumentSource):
    """macOS 备忘录数据源
    
    通过合并 AppleScript 批量获取每个文件夹内所有笔记：
    - 一次 osascript 调用获取整个文件夹的 ID/名称/正文
    - 使用分隔符 §§§ (字段间) 和 ¶¶¶ (记录间) 解析返回值
    - HTML 正文通过纯正则表达式转换为 Markdown（零依赖）
    """
    
    @property
    def source_type(self):
        return "mac_notes"
```

RawDocument 数据结构：

```python
@dataclass
class RawDocument:
    source_id: str       # 源文档唯一标识 (如 Notes 的 note_id)
    source_type: str     # 数据源类型
    content: str         # 文档正文 (Markdown)
    content_hash: str    # SHA256 内容摘要 (增量检测)
    metadata: dict       # 附加元数据 (如 folder, name)
```

### 文件桥接方案

**面临的问题**。MacNotesSource 的设计基于 AppleScript 直接调用 macOS Notes.app 获取备忘录内容。这种方案在开发环境中运行良好，但在容器化部署中遇到了根本性限制：Docker 容器内无法执行 `osascript` 调用宿主机的 Notes.app。AppleScript 需要通过 macOS 的 Apple Event 机制与 GUI 应用通信，而 Docker 容器与宿主机之间不存在这种通信通道——容器是一个独立的、隔离的运行环境，内部运行的 Linux 进程无法访问宿主机的 macOS 专属 API。

**分析过程**。解决这个问题的关键在于将"与 macOS 系统交互"和"处理数据"这两个职责分离。与 macOS 系统交互（执行 AppleScript、调用 Notes.app）必须在宿主机上完成；而数据处理（解析、分块、向量化、入库）在容器内完成。因此需要一种"桥接"机制：宿主机上的导出脚本负责读取 Notes 数据并写入文件系统，容器内的 MacNotesSource 改为从这些预先导出的文件中读取数据。

这种方案的设计焦点是**文件协议**——双方通过约定的文件格式和目录结构进行数据交换。协议需要满足以下需求：

- 导出脚本需要告知后端导出了多少条笔记、是否成功完成；
- 后端需要能够将导出结果与之前创建的任务关联起来；
- 导出失败的笔记不应阻塞整个流程（跳过即可）；
- 文件结构需要简洁、易于解析和人工排查。

**决策**。采用 `result.json` 作为导出任务的结果汇总文件，每条笔记的详细内容存储在独立的 `<note_id>.json` 文件中。导出脚本将结果写入容器挂载的共享 Volume 目录，后端通过轮询检查 `result.json` 是否存在来判断导出是否完成。

#### result.json 结构

```json
{
  "status": "ok",
  "task_id": "abc-123-def",
  "expected": 150,
  "success": 128,
  "exported_at": "2026-06-09T10:30:00+08:00"
}
```

#### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | string | `"ok"` 表示导出完成。脚本异常退出时不生成此文件，后端通过文件存在性判断导出是否成功 |
| `task_id` | string | 与后端创建的任务 ID 对应，用于关联导出脚本的执行与后端任务记录 |
| `expected` | int | 本次导出计划导出的笔记数量，由导出脚本在遍历前统计得出 |
| `success` | int | 最终成功写入文件的数量。`expected - success` 即为导出失败的笔记数 |
| `exported_at` | string | 导出完成时间，ISO 8601 格式，含时区信息 |

#### 设计要点

**不包含逐条元信息**。每条笔记的元信息（标题、所属文件夹、内容摘要等）存储在对应 `<note_id>.json` 文件中，`result.json` 仅作为全局结果汇总。这样设计的考虑是：如果 `result.json` 包含了全部笔记的元信息，文件体积会随笔记数量线性增长，且在笔记数量较多时解析负担增大。将元信息分散到各个笔记文件中，后端可以按需逐条读取，内存占用可控。

**不包含错误列表**。导出失败的笔记直接跳过，不写入任何文件。后端通过 `expected - success` 即可判断失败数量。不记录详细错误列表的原因是：导出失败的常见原因包括笔记内容为空、格式异常等，这些信息对后端后续处理没有实际价值——后端只需要知道有多少条成功、多少条失败，以便在摄入任务完成时向用户反馈统计结果。如果需要排查具体哪些笔记导出失败，可以查看宿主机上的导出脚本日志。

**total 的语义**。`IngestReport` 中的 `total` 字段始终表示"本次实际导出数"。在增量模式下，如果所有笔记都无变更，导出数为 0——这被视为正常情况，而非错误。后端在更新摄入统计时，对应 `total=0` 的任务在 sources 统计中显示为"0 条新增"，但任务状态标记为成功。

**单条笔记文件结构**。每个 `<note_id>.json` 文件直接沿用 RawDocument 的 5 个字段，使容器侧可逐字段构造 RawDocument 对象而无需翻译：

```json
{
  "source_id": "note-uuid-xxxx",
  "source_type": "mac_notes",
  "content": "Markdown正文...",
  "content_hash": "sha256...",
  "metadata": {}
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `source_id` | string | Apple Notes 的 note_id（UUID），对应 RawDocument.source_id |
| `source_type` | string | 固定为 `"mac_notes"` |
| `content` | string | 笔记正文，Markdown 格式。由导出脚本负责 HTML→Markdown 转换 |
| `content_hash` | string | SHA256 哈希值，由导出脚本在导出时预计算 |
| `metadata` | dict | 笔记元信息，包含 `title`（笔记标题）、`folder`（所属文件夹）、`tags`（标签列表）。后续可扩展更多字段 |

设计要点：
- 与 RawDocument 字段一一对应，MacNotesSource 读取后可直接构造 RawDocument，无需手动映射
- `content_hash` 由导出脚本预计算并填入，避免容器侧重复 I/O
- `content` 为 Markdown 格式（由导出脚本的 HTML→Markdown 转换保证），容器侧接收后可直接分块
- `metadata` 中包含 `title`（笔记标题）、`folder`（所属文件夹）和 `tags`（标签列表）。title 用于构建 chunk 的 `doc_title` 字段，tags 参与 FTS5 全文索引以增强关键词检索覆盖面

#### manifest.json 结构

```json
{
  "task_id": "abc-123-def",
  "source_type": "mac_notes",
  "processed_docs": [
    {"source_id": "note-1", "content_hash": "sha256..."},
    {"source_id": "note-2", "content_hash": "sha256..."}
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` | string | 与 result.json 中的 task_id 对应，用于关联 |
| `source_type` | string | 固定为 `"mac_notes"` |
| `processed_docs` | array | 已处理文档列表。全量模式为空数组 `[]`；增量模式包含已有文档的 source_id + content_hash |

`processed_docs` 数组项：

| 字段 | 类型 | 说明 |
|------|------|------|
| `source_id` | string | 已处理笔记的唯一标识 |
| `content_hash` | string | SHA256 哈希值 |

设计要点：
- 后端负责写入，从 SQLite processed_docs 表读取已有记录
- 导出脚本仅凭 source_id + content_hash 即可完成增量比对，无需访问数据库
- 全量/增量语义由 processed_docs 隐含：空数组即全量，非空即增量，无需额外字段

#### 数据目录结构

文件桥接模式下的完整数据目录布局：

```
data/pro/export/<task_id>/
  ├── manifest.json         # 后端写入：task_id + source_type + processed_docs 列表
  ├── result.json           # 导出脚本写入的结果汇总
  └── <note_id>.json        # 单条笔记（每篇笔记一个文件）
```

`manifest.json` 由后端在创建摄入任务时写入，包含 `task_id`、`source_type` 和 `processed_docs` 列表。`processed_docs` 从 SQLite 的 processed_docs 表读取，每条记录包含 `source_id` 和 `content_hash`。导出脚本通过读取 `manifest.json` 获知本次导出的上下文：若 `processed_docs` 为空数组则表示全量模式（导出全部笔记），非空则表示增量模式（逐一比对 hash 决定是否需要重新导出）。执行完成后在相同目录下写入 `result.json`。

> 注意：文件桥接方案是容器化部署的适配层。在非容器化的开发环境中，MacNotesSource 仍然可以直接通过 AppleScript 调用 Notes.app，两种模式通过配置项切换，共享同一套后续处理流程（分块、向量化、双库写入）。

### Unicode 规范化

**为何需要 NFC 规范化**。Unicode 标准中，同一个字符可以有多种编码方式：NFC（Normalization Form Canonical Composition，组合形式）将字符表示为单个码点，NFD（Normalization Form Canonical Decomposition，分解形式）将字符拆分为基础字符加组合用附加符号。例如 `é` 在 NFC 下为单个码点 `U+00E9`，在 NFD 下为 `e`（`U+0065`）+ 重音符（`U+0301`）两个码点。两种编码人眼看到的文字完全一致，但字节序列不同。

对于 ZRAG，编码不一致会引发三个链路问题。第一，`content_hash`（SHA256）基于字节序列计算——内容相同但编码形式不同的两篇文章，摘要完全不同，增量摄入时会被错误判定为"已修改"，触发不必要的重新处理。第二，FTS5 全文索引对令牌（token）的匹配依赖于字节级的精确相等——用 NFC 形式的关键词搜不到 NFD 形式索引的同一内容，导致 Path A 关键词检索漏召回。第三，Embedding 模型对语义相同但字节序列不同的文本会产生在高维空间中距离增大的向量表示（虽非完全无关，但相似度低于预期），影响 Path B 语义检索的召回精度。

**macOS 的 NFD 倾向**。macOS 的 HFS+ 文件系统历史上默认使用 NFD 编码存储文件名和文本，而 web 页面复制的内容通常是 NFC。这意味着同一篇备忘录中可能混入两种编码——用户从网页粘贴的部分是 NFC，在 macOS 原生环境中创建的部分可能是 NFD。导出阶段是统一编码形式的最佳时机——在此节点统一转换后，下游的哈希计算、FTS5 索引和 Embedding 都使用一致的 NFC 文本。

**决策**。在 `export_notes.py` 获取文本内容后，统一调用 `unicodedata.normalize('NFC', text)` 将全部文本（content、title、folder、tags）转为 NFC 组合形式。与直接使用 `locale.strxfrm`（部分 Unix/Linux 系统中采用 NFD 作为默认规范化形式，可能与 macOS 的 NFD 默认倾向一致但在容器 Linux 环境中行为不同）相比，显式的 NFC 规范化可以消除跨平台差异。这是一个零成本的数学变换，不改变文本的语义内容，不损失任何信息。

## 5.3 ChunkingStrategy ABC

### 设计理念

**为何抽象 ChunkingStrategy**。不同格式的文档有不同的最优分块方式。Markdown 文档天然带有标题层级结构（`#`、`##`、`###`），按标题分块可以将同一主题下的内容作为一个语义连贯的整体，有利于检索时返回的信息完整性。纯文本文档（如备忘录导出内容）没有标题结构，适合按段落（`\n\n` 分割）分块，以自然段作为语义边界。代码文件则完全不适合按段落或标题分块——它们需要按函数/类边界分割，或者简单按固定字符数切割。

如果 Pipeline 中硬编码了某一种分块方式（例如"始终按段落分块"），那么处理 Markdown 文档时就会出现问题——一篇《机器学习笔记》中"监督学习"这个小节下有 5 段内容，按段落分块后这 5 段被切成了 5 个独立 chunk，它们之间的层级关系（都属于"监督学习"这一标题下）完全丢失。检索时可能只能匹配到其中某一段，而丢失了该标题下的其他相关内容。

ChunkingStrategy ABC 将分块操作抽象为统一接口 `chunk(document) -> list[Chunk]`。不同的文档类型可以绑定不同的策略实现，Pipeline 只需知道调用 `self.chunker.chunk(doc)`，而不需要知道当前使用的是哪种分块策略。这种可替换性使得分块策略的选择逻辑可以由 Source 通过 RawDocument.metadata 中的 `chunk_strategy` 字段声明，Pipeline 据此从 `CHUNKER_REGISTRY` 中查找并加载对应的策略。

**为何设计 CompositeChunker**。实际场景中，单一的分块策略往往不够。以 Markdown 文档为例：先按标题层级分块（一级标题切分、二级标题切分），分块后某个标题下的内容可能仍然超过 Embedding 模型的最大输入长度（如 512 token）。此时需要一个"兜底"策略——对超出 max_size 的块进行递归切割，按分隔符优先级（`\n\n` → `\n` → `。` → 字符）逐级尝试，直到所有块的尺寸都在限制之内。

CompositeChunker 将"结构策略"（如按标题、按段落）和"兜底策略"（递归字符切割）组合在一起：先用结构策略切分，然后将超出 max_size 的块交给兜底策略递归处理。这种组合模式避免了在每一种结构策略中重复实现超长块切割的逻辑，也使得结构策略和兜底策略可以独立演化和调优。

> 参考 QA: data-ingestion.md Q3, Q10。

**HeadingChunker 实现设计**。HeadingChunker 是专为 Markdown 格式文档设计的语义分块策略，按 Markdown 标题层级（H1-H3）作为切分边界。

1. 按标题层级切分文档为语义段，每个标题下的内容作为一个候选块
2. 候选块内容 ≤ max_size 时直接作为一个完整 chunk
3. 候选块超过 max_size 时降级使用 RecursiveCharacterChunker 二次切分
4. 二次切分后的子 chunk 携带父标题路径作为前缀，保留上下文连贯性
5. 过短的相邻 chunk 合并至 min_size 阈值
6. 首段未达 min_size 时，不会被丢弃或创建独立短 chunk，而是缓存为 `pending_prefix`，追加到下一个正常段之前

参数：
- **levels**: [1, 2, 3] — H1-H3 作为切分边界
- **max_size**: 1000 字符 — 单 chunk 上限。统一设为 1000（含 HeadingChunker、CompositeChunker、RecursiveCharacterChunker），使最终入库的 chunk 既充分利用 BGE-small 模型 512 token（≈800-1000 中文字符）的上下文窗口，又不至于因过长而被截断向量化导致尾部信息丢失
- **overlap**: 100 字符 — 超长段二次切分时的重叠字符数
- **min_size**: 200 字符 — 过短相邻 chunk 的合并阈值

HeadingChunker 通过 CompositeChunker 与 RecursiveCharacterChunker 组合使用：`CompositeChunker(HeadingChunker, RecursiveCharacterChunker, max_size=1000)`。首先由 HeadingChunker 按标题层级切分，超出 max_size 的段由 RecursiveCharacterChunker 递归切割。当文档不含任何 Markdown 标题时，HeadingChunker 回退到 RecursiveCharacterChunker 作为默认行为。CompositeChunker 的 max_size 必须与 HeadingChunker 对齐——若 CompositeChunker 的 max_size 小于 HeadingChunker 的 max_size，则 HeadingChunker 切出的几乎所有段都会被判定为"超长"并触发回退切分，标题切分结果名存实亡。

该策略当前仅适用于 `mac_notes` 数据源。

**为何需要规避代码围栏内的 `#`**。HeadingChunker 使用正则表达式 `^(#{1,3})\s+`（`re.MULTILINE` 模式）来检测 Markdown 标题边界。但 Markdown 代码围栏（`` ``` `` 包裹的代码块）内可能包含注释行——例如 Python 中的 `# this is a comment`、Shell 中的 `#!/bin/bash`、YAML 中的 `# key: value`——这些行的 `#` 在源代码语义中并非标题，但在正则表达式的视角下与 Markdown H1 标题完全不可区分。如果在代码围栏内产生虚假标题检测，会导致代码块被错误截断，产生无意义的 chunk。因此在扫描标题前，先识别并跳过代码围栏区域，仅对非围栏区域的文本行执行标题检测。

**为何 chunk_index 是必填字段**。chunk_index 记录了当前分块在原始文档中的位置序号（从 0 开始递增）。这个字段的用途不止于排序展示——在检索结果中，如果同一篇文档的多个 chunk 被匹配到（如 chunk[2] 和 chunk[5]），检索层可以通过 chunk_index 将它们按原文顺序重建，使发送给 LLM 的上下文材料保持原文的叙事逻辑。另一个场景是：用户要求"查看原文上下文"，系统可以通过 chunk_index 加载该 chunk 前后相邻的几个 chunk 作为扩展上下文返回。如果没有 chunk_index，分块就失去了在原文中的位置信息，上述两个场景都无法实现。

文档分块是将长文本拆分为适合 Embedding 模型处理的小段的过程。

```python
class ChunkingStrategy(ABC):
    """文档分块策略抽象基类
    
    chunk() 接收 RawDocument, 返回 Chunk 列表。
    具体的分块算法（段落分割、递归字符分割等）由子类实现。
    """
    
    @abstractmethod
    def chunk(self, document: RawDocument) -> list[Chunk]:
        """将原始文档切分为多个 Chunk"""
        ...
```

分块结果数据结构：

```python
@dataclass
class Chunk:
    chunk_id: str       # UUID, 全局唯一
    source_id: str      # 源文档 ID
    source_type: str    # 数据源类型
    doc_title: str      # 文档标题
    content: str        # 分块文本内容
    chunk_index: int    # 在文档内的序号
```

- 所有 Chunker 均实现 `_resolve_title(document)` 方法：优先取 `metadata.title`，null 或缺失时 fallback 为 `"{source_type}_{source_id}"`，保证 doc_title 非空
- 合并场景（短段合并到前一个 chunk）沿用已解析的 doc_title，避免重复 fallback

## 5.4 IngestionPipeline

### 设计理念

**为何 Pipeline 只管编排不做具体工作**。这是单一职责原则在摄入流程中的直接体现。Pipeline 的责任是知道流程的执行顺序——先分块、再向量化、再写入 SQLite、再写入 ChromaDB、最后更新 processed_docs。但 Pipeline 不应该知道如何分块（那是 ChunkingStrategy 的职责）、如何向量化（那是 EmbeddingModel 的职责）、如何写入数据库（那是 SQLiteStore 和 ChromaStore 的职责）。

这种职责划分带来了两个直接的好处。第一，每个组件可以独立测试——测试 ChunkingStrategy 时不需要启动 ChromaDB，测试 ChromaStore 时不需要真实的 Embedding 模型。第二，每个组件可以独立替换——换一个 Embedding 模型只需要更换注入 Pipeline 的 EmbeddingModel 实例，Pipeline 代码完全不变。如果 Pipeline 内部混合了分块、向量化和存储的具体实现逻辑，上述两个能力都不存在。

从数据流的角度看，Pipeline 是一个编排器（Orchestrator）：它接收上游产出的文档（来自 Source），依次调用各处理组件，将结果写入下游存储。编排器本身不生成任何数据，只是传递和调度。这种编排器模式在系统工程中被广泛使用——Kubernetes 的 Controller、Airflow 的 DAG、CI/CD 的 Pipeline——都是只管编排不做具体工作的例子。

> 参考 QA: data-ingestion.md Q8, Q25。

**为何 batch_size 从配置读取且可覆盖**。不同数据源有不同的合理批次大小，这个差异来源于文档的平均长度。macOS 备忘录的单条笔记可能篇幅较长（几百到几千字），分块和向量化每篇的耗时较多，如果 batch_size 设为 10，连续 10 篇大笔记的处理可能导致单次处理的峰值内存偏高——适合将 batch_size 设小一些（如 5）。而本地 Markdown 文件大多较短（几百字），分块和向量化很快，batch_size 可以设大一些（如 10 甚至 20），减少循环开销。

为了同时兼顾灵活性和便利性，batch_size 采用两层配置策略：第一层是全局配置文件 `config/ingest.yaml` 中的 `ingest.batch_size`（默认 5），作为所有 Source 的默认值；第二层是 Pipeline 构造方法的 `batch_size` 参数——如果调用方显式传入了一个值，则优先使用传入值，覆盖全局配置。调用方不需要关心 batch_size 时，Pipeline 自动从配置读取；需要特殊定制时，直接在构造时传入即可。

**为何 on_document_done 和 should_cancel 替代了 on_progress**。在原设计中，Pipeline 使用 `on_progress` 回调配合 `ProgressEvent` 数据类，在每个处理阶段的开始和结束时各触发一次回调（每篇文档产生 6 次事件）。这个设计有两个问题：一、过于详细的阶段划分使得消费方需要处理大量事件；二、实际上没有消费方——`views.py` 调用 `pipeline.run()` 时从未传入 `on_progress`，`ProgressEvent` 是一个未被消费的设计。

在异步摄入方案中，TaskManager 需要在每篇文档处理完成后更新 `ingest_tasks.processed` 计数。因此将 `on_progress` + `ProgressEvent` 替换为两个极简回调：

- `on_document_done`（无参）：每篇文档处理完成后（不论成功或失败）调用一次，在 try-except 的 finally 块中触发。TaskManager 通过此回调更新 `ingest_tasks.processed` 计数。
- `should_cancel`（返回 bool）：每篇文档处理开始前检查一次。返回 True 时中断后续文档处理。取消不在文档处理中途发生，仅在文档间检查。

**为何 on_total_known 是可选回调**。`on_total_known(total: int)` 在 `fetch_batch()` 完成后、处理开始前调用一次，用于回写 `task.total` 以支持前端百分比进度。

**为何 on_error 是可选回调**。`on_error` 决定了 Pipeline 对待失败文档的行为。提供回调时进入容错模式（失败跳过继续），未提供时进入严格模式（异常直接抛出中断流程）。

Pipeline 是摄入流程的编排器，负责串联 Source → Chunk → Embed → Store 的全流程。

关键设计决策：

1. **依赖注入**：所有组件（SQLiteStore、ChromaStore、EmbeddingModel、ChunkingStrategy）通过构造方法注入，Pipeline 不创建任何组件实例。便于测试时 mock 替换，也使得不同数据源可以绑定不同的 ChunkingStrategy
2. **逐篇独立事务**：每篇文档在 SQLite 中开启独立事务完成写入，一篇失败不影响同批次其他文档。失败文档记录到 IngestReport.errors，通过 on_error 回调通知调用方
3. **错误隔离（on_error）**：调用方可自定义错误处理逻辑。提供回调时进入容错模式（失败跳过继续），未提供时进入严格模式（任何异常直接抛出）
4. **文档完成通知（on_document_done）**：每篇文档处理完成后（不论成败）调用一次。替换原设计中未被消费的 `on_progress` + `ProgressEvent`
5. **取消信号（should_cancel）**：每篇文档处理开始前检查取消信号，返回 True 时中断后续处理。取消不在文档处理中途发生，保证数据一致性
6. **增量/全量模式**：通过 `full` 参数控制。增量模式（默认）基于 `content_hash` 与 `processed_docs` 表对比跳过未变更文档；全量模式（`full=True`）忽略缓存，强制重处理全部文档
7. **batch_size 双层配置**：默认从 `config/ingest.yaml` 的 `ingest.batch_size` 读取，构造方法的 `batch_size` 参数可覆盖。不同 Source 类型可根据文档平均长度选择合适的批次大小
8. **先 SQLite 后 ChromaDB**：SQLite 作为可信数据源（Source of Truth），先完成事务写入；ChromaDB 在 SQLite 事务成功后写入。只有双库都写入成功后，才更新 `processed_docs` 标记（详细写入流程和异常恢复策略见 [3.3 节](#33-数据一致性策略)）

---

# 6. 检索层

检索层是 ZRAG 运行时在线服务的核心环节，负责将用户的自然语言问题转化为结构化的参考材料，为下游 LLM 问答提供信息基础。检索层由两个组件协作完成：Retriever 负责从双库（ChromaDB + SQLite）中检索相关文档片段并融合排序，PromptBuilder 负责将检索结果通过 Jinja2 模板渲染为符合 OpenAI 消息格式的 Prompt。

两者之间的数据流：

```
用户提问
  → QueryRewriter.rewrite(query) → {keywords, refined_query}  ← 新增: 查询改写
  → Retriever.hybrid_search(keywords, refined_query, k=10)      ← k×2 候选池
  → PromptBuilder.build_rag_prompt(query, results) → list[dict]
  → LLMProvider.chat(messages) → 回答
```

这种分拆设计遵循了单一职责原则——Retriever 只关心"找到哪些材料"，PromptBuilder 只关心"如何组织材料呈现给 LLM"，两者各自独立演化，互不干扰。

## 6.1 Retriever（混合检索 + RRF 融合）

Retriever 融合两种互补的检索路径——ChromaDB 向量检索（语义相似度）和 SQLite FTS5 关键词检索（BM25 精确匹配）——通过 RRF（Reciprocal Rank Fusion）算法合并排序，返回统一的 `SearchResult` 列表。

### 设计理念

**为何混合检索优于纯向量或纯关键词**。知识库中的文档内容包含两类性质不同的信息。一类是可以借助近义词、同义表达来描述的语义概念——例如"代码优化方法"和"性能调优技巧"指向相同含义，用户用不同措辞提问时，语义检索能够跨越用词差异找到相关内容。另一类是专有名词、技术术语、错误码、函数名等精确标识符——例如"K8s"和"Kubernetes"在语义模型看来高度相近，但由于 Embedding 模型对短文本的向量区分度有限，纯向量检索反而可能漏掉这些精确匹配；再如"ERR_CONN_REFUSED"、"acquire_scaling_lock"这类字符串，Embedding 模型无法为其生成有区分度的向量表示，但关键词检索可以精确命中。纯向量检索的优势在于语义覆盖面广但对精确标识符区分度不足，纯关键词检索的优势在于对专有名词匹配精准但无法处理措辞不同的同义表达。从这两种检索方式的特性可以看出，它们天然互补——语义检索覆盖面广但精确度有上限，关键词检索精度高但覆盖面窄。将两者并行执行后融合，最终返回的 top-k 文档片段同时受益于两条检索路径的各自优势。

**为何使用 RRF 而非分数加权融合**。融合两种检索方式结果的最直观方案是为各自的原始分数分配权重后加权求和（score = alpha * cosine_score + beta * bm25_score）。但这种方案存在一个根本问题：向量检索的 Cosine 距离（取值通常在 [0, 1] 范围，因为 BGE 模型输出已做 L2 Normalize）和 BM25 分数（取值无上界，受文档长度和词频影响极大，可在 [-10, 10] 甚至更宽范围波动）的量纲和分布完全不可比——Cosine 距离在 0.1 的差异就可能意味着高度相关与无关的界限，而 BM25 分数从 -5 到 -10 的跨度在同一次查询中属于正常波动。在这种量纲不一致的前提下，无论权重系数如何调整，融合结果都会偏向其中一侧——本质上是两种分数的"不可比性"导致的必然问题。虽然可以通过先对每种分数做归一化（如 min-max 归一化到 [0, 1]）再进行加权求和，但归一化需要额外引入归一化区间的上界和下界参数，参数调优又引入了新的复杂度。RRF（Reciprocal Rank Fusion）提供了一种更简洁的方案：不依赖原始分数的绝对值，仅依赖每种检索方式内部的排名位置。无论 Cosine 距离是 0.01 还是 0.99，也无论 BM25 分数是 -2 还是 -20，它们只通过排名位置参与融合。这就天然消除了量纲差异问题。此外，RRF 在融合过程中自然实现了去重——同一个 chunk 如果同时出现在两条检索路径的结果中，它在两边的排名列表中各有一个位置，最终 RRF 分数是两边排名倒数之和，排名越靠前（同时被两种检索方式认可），融合后的分数越高。

RRF 公式：

$$score(d) = \frac{1}{60 + rank_{vector}(d)} + \frac{1}{60 + rank_{keyword}(d)}$$

其中，若文档 d 仅出现在某一条检索路径中，另一路径的 rank 视为无穷大（对应分数项为 0）。

**为何 k=60 而非其他值**。RRF 公式中常数 k 的作用是平滑极端排名差异——如果某文档在向量检索中排名第 1（rank=1），但在关键词检索中未出现（rank 视为无穷大），没有 k 的缓冲时该文档的 RRF 分数完全由 1/1=1.0 主导，与排名第 2 的文档（1/2=0.5）差距过大。k=60 使排名第 1 的项分数为 1/(60+1)≈0.0164，排名第 2 为 1/(60+2)≈0.0161，差距被平滑到合理范围。k=60 这个取值来源于 RRF 原论文（Cormack et al., 2009）的实验结果——论文在多个 TREC 数据集上测试了 k 从 0 到 1000 的多个取值，k=60 在大多数查询场景下取得了最优的排序质量。k 值越大，排名差异越平滑但区分度越低；k 值越小，排名差异越突出但极端值的敏感度越高。ZRAG 直接采用这一经过学术实验验证的业界经验值，不做额外的参数调优。

**为何在检索前引入查询改写（Query Rewriting）**。用户日常输入的自然语言问题往往带有口语化特征——简称、省略、非正式表达（如"怎么让 Python 跑得更快"而非"Python 程序性能优化方法"）。如果直接将原始查询原样传入向量检索和关键词检索，检索系统面对的是非标准化的表达，召回质量受用户措辞习惯影响很大。

查询改写（Query Rewriting）在检索之前引入一次轻量 LLM 调用，将用户的口语化问题改写为两种互补的产出物：（1）**关键词列表**，抽取出用于精确匹配的专有名词、技术术语和核心概念，直接拼接后传入 FTS5 MATCH 做关键词检索——不再走 jieba 分词，因为 LLM 已经按语义边界拆分好了干净的搜索词；（2）**精炼自然语言查询**，将口语化表达提炼为完整规范的自然语言表述，传给 `embed_query()` 做语义向量检索。改写采用 Jinja2 模板（`query_rewrite.j2`），LLM 返回结构化 JSON `{"keywords": "...", "refined_query": "..."}`，全部查询均执行改写（不做复杂度判断以保持逻辑简洁统一）。

查询改写增加了约 0.5-1 秒的额外 LLM 调用延迟，但通过提升两条检索路径的输入质量，换取的召回精度提升远超过延迟代价。QueryRewriter 通过依赖注入传入 Retriever，与 LLM Provider 解耦。

**为何候选池扩大至 k×2**。在原始设计中，两条检索路径各取 k 个候选直接进行 RRF 融合。这意味着若某 chunk 在路径 A 排名第 11、路径 B 排名第 3，它在 RRF 融合时路径 A 贡献为 0（排名超出前 k），整体 RRF 分数可能进不了最终 top-k——即使它在其中一条路径上被高度认可。将各路径的候选数扩大为 k×2（即各取 top-20），RRF 在更宽的候选池上计算排名分数后再截取最终 top-k（10 个），不遗漏"只有一条路径认可"的优质结果。k×2 是经验值——再大（如 k×3）的边际收益递减且增加不必要的计算和存储开销，再小（如 k×1.5）则候选池扩宽效果不足。

**为何引入 RRF 可配置权重**。引入查询改写后，关键词路径的输入从原始口语化查询变为 LLM 提炼的关键词列表，向量路径的输入变为精炼自然语言查询——两条路径的输入质量都得到了提升，且各自更适配对应检索方式的特点。但在不同知识库语料特征下，两类检索方式的贡献度可能不完全相等——例如文档内容偏重技术文档（术语密度高）时关键词检索贡献更大，偏重随笔记录（语义松散）时向量检索贡献更大。因此将 RRF 融合公式扩展为加权形式：

$$score(d) = w_{vector} \cdot \frac{1}{60 + rank_{vector}(d)} + w_{keyword} \cdot \frac{1}{60 + rank_{keyword}(d)}$$

权重通过 `config/retrieval.yaml` 中的 `rrf_weights.vector` 和 `rrf_weights.keyword` 配置，默认等权（均为 1.0），与原始 RRF 行为一致。需要时调整比例即可，无需修改代码。

**为何 vector_results 中独有的 chunk 需回查 SQLite**。在构建最终检索结果时，_build_results 方法需要为每个 chunk 填充完整的 content 和元数据。keyword_results 来自 SQLite FTS5 的 JOIN 查询，结果中直接包含了 content、doc_title、source_id 等完整字段，可以直接使用。但 vector_results 来自 ChromaDB 的 similarity_search，其返回的 metadata 中仅存储了 source_id、source_type、doc_title 和 chunk_index——**不包含 content 字段**。这是因为 ChromaDB 的 Collection 设计上 metadata 用于过滤和展示辅助信息，将大段的 chunk 原文存入 metadata 会显著增加 ChromaDB 的存储开销和序列化成本。chunk 的原文（content）仅在 SQLite 的 chunks 表中持久化存储。因此，对于仅在 vector_results 中出现但不在 keyword_results 中的 chunk（即被语义检索发现但未被关键词检索命中的 chunk），必须通过其 chunk_id 回查 SQLite 的 chunks 表获取 content。这是一个"以 SQLite 为可信数据源"的设计原则在检索环节的自然延伸。

> 注意：_build_results() 路径 C——当向量检索结果在 SQLite 中找不到对应 chunk 时，跳过而非创建空壳 SearchResult，避免 `[来源: ]` 空标注

**为何返回 SearchResult 而非原始 dict**。检索结果在 Retriever 内部产出后，会传递给下游的 PromptBuilder 和 API 响应序列化层。如果返回的是原始 dict（`{"chunk_id": ..., "content": ..., "doc_title": ...}`），下游代码需要通过字符串键来访问字段——`r['doc_title']`。这种方式有两个问题：第一，IDE 无法提供字段名的自动补全提示，开发过程中容易因拼写错误（如 `r['doc_titel']`）引入难以发现的 bug；第二，如果未来 SearchResult 增加或修改字段，所有基于字符串键的访问代码都需要逐一检查和修改，没有编译期的类型检查来保证修改的完整性。将检索结果封装为 `SearchResult` dataclass，下游代码通过属性访问——`r.doc_title`——IDE 可以自动补全字段名，类型检查器可以捕获字段名拼写错误。此外，dataclass 还天然支持默认值（如 score 字段默认为 0.0），避免了 dict 访问时因键不存在而抛出 `KeyError` 的防御性编码负担。

```python
@dataclass
class SearchResult:
    """单条检索结果
    
    @ivar chunk_id:   分块唯一标识, 格式为 "{source_id}_chunk_{index}"
    @ivar content:     分块正文内容
    @ivar doc_title:   所属文档标题
    @ivar source_id:   来源文档标识
    @ivar source_type: 数据源类型, 如 "mac_notes"
    @ivar score:       RRF 融合分数, 值越大表示综合排名越靠前
    """
    chunk_id: str
    content: str
    doc_title: str
    source_id: str
    source_type: str
    score: float = 0.0
```

### 核心实现

```python
class Retriever:
    """混合检索器

    融合向量检索（ChromaDB）与关键词检索（SQLite FTS5）的结果,
    使用 RRF（Reciprocal Rank Fusion）算法进行结果融合与重排序。
    通过依赖注入接收 sqlite_store、chroma_store 和 embedder 三个协作组件。

    @param sqlite_store: SQLite 持久化存储实例
    @param chroma_store: ChromaDB 向量存储实例
    @param embedder:     Embedding 模型实例
    """

    def __init__(self, sqlite_store, chroma_store, embedder):
        self.sqlite_store = sqlite_store
        self.chroma_store = chroma_store
        self.embedder = embedder

    def hybrid_search(self, query: str, k: int = 10) -> list[SearchResult]:
        """混合检索: 查询改写 → 向量检索 + FTS5 关键词检索 → 加权 RRF 融合

        流程:
        1. query_rewriter.rewrite(query) 获取 {keywords, refined_query}
        2. embedder.embed_query(refined_query) 获取查询向量（已含指令前缀）
        3. chroma_store.similarity_search(query_vector, k * 2) 获取向量候选
        4. sqlite_store.search_fts5(keywords, k * 2) 获取关键词候选
        5. 构建两路排名映射: chunk_id -> rank
        6. 加权 RRF 融合: score = w_vector/(k_rrf+rank_vector) + w_keyword/(k_rrf+rank_keyword)
        7. 构建 SearchResult 列表, 按 RRF score 降序排列, 截取 top-k

        @param query: 用户输入的原始查询字符串（口语化）
        @param k:     最终返回结果的最大数量, defaults to 10

        @return: 按加权 RRF 融合分数降序排列的检索结果列表
        """
        rewritten = self.query_rewriter.rewrite(query)
        query_vector = self.embedder.embed_query(rewritten['refined_query'])
        vector_results = self.chroma_store.similarity_search(query_vector, k * 2)
        keyword_results = self.sqlite_store.search_fts5(rewritten['keywords'], k * 2)

        vector_ranks = self._build_vector_ranks(vector_results)
        keyword_ranks = self._build_keyword_ranks(keyword_results)
        rrf_scores = self._compute_rrf_scores(vector_ranks, keyword_ranks)

        return self._build_results(
            vector_results, keyword_results, rrf_scores, k,
        )

    @staticmethod
    def _build_vector_ranks(vector_results: list[dict]) -> dict[str, int]:
        """为向量检索结果分配排名

        向量结果按 distance 升序排列（distance 越小越相似）, 排名从 1 开始。
        """
        return {
            vr['id']: i + 1
            for i, vr in enumerate(vector_results)
        }

    @staticmethod
    def _build_keyword_ranks(keyword_results: list[dict]) -> dict[str, int]:
        """为关键词检索结果分配排名

        SQLite FTS5 结果已按 bm25_score 升序排列, 排名从 1 开始。
        """
        return {
            kr['chunk_id']: i + 1
            for i, kr in enumerate(keyword_results)
        }

    @staticmethod
    def _compute_rrf_scores(
        vector_ranks: dict[str, int],
        keyword_ranks: dict[str, int],
    ) -> dict[str, float]:
        """计算 RRF 融合分数

        RRF 公式: score(d) = 1/(60 + rank_vector) + 1/(60 + rank_keyword)
        若某篇文档仅出现在一个检索方式中, 另一个 rank 视为无穷大,
        对应分数项为 0。
        """
        all_chunk_ids = set(vector_ranks.keys()) | set(keyword_ranks.keys())
        scores: dict[str, float] = {}
        for chunk_id in all_chunk_ids:
            rank_v = vector_ranks.get(chunk_id, float('inf'))
            rank_k = keyword_ranks.get(chunk_id, float('inf'))
            scores[chunk_id] = 1.0 / (60.0 + rank_v) + 1.0 / (60.0 + rank_k)
        return scores

    def _build_results(
        self,
        vector_results: list[dict],
        keyword_results: list[dict],
        rrf_scores: dict[str, float],
        k: int,
    ) -> list[SearchResult]:
        """构建最终检索结果列表

        优先从 keyword_results 获取 chunk 的完整信息（含 content/doc_title）;
        对仅在 vector_results 中出现的 chunk, 通过 SQLite 补充文档信息;
        若 SQLite 中也无记录, 从 ChromaDB metadata 提取基本信息兜底。
        最后按 RRF score 降序排列, 截取 top-k。
        """
        result_map: dict[str, SearchResult] = {}

        # 优先从 keyword_results 获取完整信息
        for kr in keyword_results:
            cid = kr['chunk_id']
            result_map[cid] = SearchResult(
                chunk_id=cid,
                content=kr['content'],
                doc_title=kr['doc_title'],
                source_id=kr['source_id'],
                source_type=kr['source_type'],
                score=rrf_scores.get(cid, 0.0),
            )

        # 对仅在 vector_results 中出现的 chunk_id, 回查 SQLite 补充信息
        for vr in vector_results:
            cid = vr['id']
            if cid not in result_map:
                row = self.sqlite_store.fetch_one(
                    "SELECT * FROM chunks WHERE chunk_id = ?",
                    (cid,),
                )
                if row is not None:
                    result_map[cid] = SearchResult(
                        chunk_id=cid,
                        content=row['content'],
                        doc_title=row['doc_title'],
                        source_id=row['source_id'],
                        source_type=row['source_type'],
                        score=rrf_scores.get(cid, 0.0),
                    )
                else:
                    meta = vr['metadata']
                    result_map[cid] = SearchResult(
                        chunk_id=cid,
                        content='',
                        doc_title=meta.get('doc_title', ''),
                        source_id=meta.get('source_id', ''),
                        source_type=meta.get('source_type', ''),
                        score=rrf_scores.get(cid, 0.0),
                    )

        results = sorted(result_map.values(), key=lambda r: r.score, reverse=True)
        return results[:k]
```

### 设计特点总结

1. **双路并行检索**：向量检索（语义相似度）和关键词检索（BM25 精确匹配）并行执行，各自获取 top-10 结果
2. **RRF 排名融合**：不依赖原始分数的量纲，仅基于排名位置融合，天然去重并平滑极端排名差异，常数 k=60 来自原论文实验最优值
3. **SQLite 为可信数据源**：ChromaDB 不存储 content 原文，仅在 vector_results 中独有的 chunk 需通过 chunk_id 回查 SQLite 获取完整信息
4. **类型安全输出**：返回 `SearchResult` dataclass 而非原始 dict，下游通过属性访问获得 IDE 自动补全和类型检查
5. **依赖注入**：通过构造方法注入 sqlite_store、chroma_store 和 embedder，便于单元测试时替换为 mock 对象

## 6.2 PromptBuilder（Jinja2 模板渲染）

PromptBuilder 负责将混合检索产出的 `SearchResult` 列表通过 Jinja2 模板引擎渲染为符合 OpenAI Chat Completions API 格式的消息列表（system message + user message），供下游 LLMProvider 调用。

### 设计理念

**为何选择 Jinja2 而非 Python f-string**。在项目早期原型阶段，曾使用 Python f-string 直接在代码中拼接 Prompt 文本——`f"参考材料:\n{context}"`。这种方式的便利性只存在于最初几次使用时。当 Prompt 需要调整时（例如修改角色描述、调整参考材料格式、增加回答约束条件），f-string 方案要求修改 Python 源代码、重新运行测试（如果 Prompt 调整影响了上游调用方的行为）、重新构建部署。一个纯文本层面的 Prompt 措辞修改，却触发了完整的代码变更-测试-部署链路，变更成本被不成比例地放大。此外，f-string 中的 Prompt 文本与 Python 代码混在一起，IDE 无法对 Jinja2 模板语法（如条件判断和循环）提供语法高亮和错误提示，维护体验差。Jinja2 方案将 Prompt 模板作为独立文件存放在 `zrag/prompts/` 目录中，修改 Prompt 只需编辑模板文件并重启服务——不需要改动任何 Python 代码，不需要重新运行测试，部署也仅需复制模板文件。模板与代码的物理分离也使得非开发人员（如领域专家）可以直接审阅和调整 Prompt 措辞，而不需要理解 Python 代码逻辑。

> 注意：`Environment` 和 `FileSystemLoader` 在模块加载时创建（模块级变量），意味着模板目录在应用启动时即被扫描。如果需要在运行时动态新增模板文件而不重启服务，可将 `Environment` 创建移到函数内部并禁用缓存（`auto_reload=True`），但会带来每次调用都重新解析模板的性能开销。ZRAG 当前阶段 Prompt 模板在部署时确定，启动时加载一次是合理的默认选择。

**为何系统提示和用户消息分开构建**。OpenAI Chat Completions API 的消息格式要求每条消息携带 `role` 字段，取值为 `system`、`user` 或 `assistant`。system 消息用于设定 AI 的角色、行为边界和提供参考材料；user 消息用于表达用户的具体提问。这两者在语义上承担完全不同的职责——system 消息是"背景信息"，user 消息是"当前问题"。PromptBuilder 的职责是在构建阶段就明确区分这两种消息类型，返回结构化的 `[system_msg, user_msg]` 列表。这样下游的 LLMProvider 无需理解消息内部结构，只需原样转发给 LLM API 即可。如果 system 和 user 的内容混合在一条消息中（例如全部塞入 user 消息），LLM 无法区分哪些是指令约束、哪些是需要回答的问题，可能导致 LLM 忽略或不重视 system 层面的角色设定。分开构建也方便未来扩展多轮对话——在多轮对话场景中，system 消息保持不变（参考材料在一次检索中已确定），只需在消息列表末尾追加新的 user 消息和历史的 assistant 消息即可。

**为何在模板中处理空材料场景**。知识库在初始状态或清除数据后，检索结果可能为空列表。如果模板不做条件判断，直接将空列表渲染为 Prompt，会生成类似"参考材料：（空）"的无意义文本——这段文本对 LLM 没有任何信息量，但占据了 token 预算，且可能让 LLM 困惑于"参考材料"字段存在但内容为空的情况。Jinja2 的 `{% if %}` 条件渲染能力可以在模板层面处理这一边界情况：当 `reference_materials` 为空时输出"（暂无参考材料）"，LLM 接收到的是一句明确的自然语言提示，可以据此如实告知用户"当前知识库中没有相关信息"。将空材料处理逻辑放在模板中而非 Python 代码中（例如在 `build_rag_prompt` 函数中先判断 `results` 是否为空再构建不同的 system_msg），使得 Prompt 的完整语义由模板文件一手掌控——模板的编写者（可能是 Prompt 工程师）可以看到"参考材料有值时的模板"和"参考材料为空时的模板"在同一个文件中，避免了两段逻辑分散在不同层级导致的维护不一致。

**为何在 PromptBuilder 中按同源合并**。在 RRF 混合检索结果中，同一篇文档的多个 chunk 可能同时出现在 top-k 结果中（例如文档《机器学习笔记》的 chunk[2] 和 chunk[5] 分别被语义检索和关键词检索命中）。如果直接将所有 chunk 作为独立的 `reference_materials` 传入模板，LLM 接收到的是一组无序的、可能相互重叠的文本片段——LLM 需要自行推断哪些 chunk 属于同一篇文档、它们之间的先后顺序是什么。这增加了 LLM 的认知负担，且跨 chunk 的信息关联依赖 LLM 的短期记忆，容易产生幻觉或遗漏。因此，PromptBuilder 在构建 `reference_materials` 之前，先按 `doc_title` 合并同源 chunks，同源内容按 `chunk_index` 排序后以 `\n\n` 拼接为一段连续文本。每个来源在 system prompt 中仅出现一次，`[来源: {doc_title}]` 标注保持唯一性。LLM 接收到的是按文档组织后的参考材料，结构清晰，信息完整。

### 核心实现

模板文件 `zrag/prompts/chat_system.j2`：

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

模板设计要点：
- `{% if reference_materials -%}` 条件分支：有材料时遍历渲染，无材料时输出明确的"暂无参考材料"提示
- `{% if not loop.last -%}` 分隔符：材料之间用 `---` 分隔（Jinja2 内置的 `loop.last` 变量判断是否为最后一项），避免最后一个材料后面多出一个多余的分隔符
- `{%-` 和 `-%}` 空白控制：去除 Jinja2 标签产生的多余空行，保证渲染输出的整洁
- `chat_system.j2` 模板末尾包含引用来源指令，要求 LLM 在回答末尾列出所用参考材料

调用方式（`zrag/retrieval/prompt_builder.py`）：

```python
"""RAG Prompt 构建器

基于 Jinja2 模板引擎将检索结果拼接到 system prompt 中,
生成 OpenAI 格式的消息列表，供下游 LLM Provider 调用。

模板文件位于 zrag/prompts/ 目录。
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

_prompts_dir = Path(__file__).resolve().parent.parent / "prompts"
_env = Environment(loader=FileSystemLoader(str(_prompts_dir)))


def build_rag_prompt(query: str, results: list) -> list[dict]:
    """构建 RAG 问答 Prompt

    加载 chat_system.j2 模板, 将检索结果传入 reference_materials 变量,
    每个结果需包含 doc_title 和 content 字段。
    返回 OpenAI 格式的消息列表。

    @param query:   用户提问
    @param results: 检索结果列表, 元素需包含 doc_title 和 content 属性

    @return: [{"role": "system", "content": "..."}, {"role": "user", "content": query}]
    """
    materials = [
        {"doc_title": r.doc_title, "content": r.content}
        for r in results
    ]
    template = _env.get_template("chat_system.j2")
    system_msg = template.render(reference_materials=materials)
    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": query},
    ]
```

### 设计特点总结

1. **模板与代码物理分离**：Prompt 模板作为独立文件存放在 `zrag/prompts/` 目录，修改 Prompt 无需改动 Python 代码、无需重新测试、无需重新构建——只需编辑模板文件并重启服务
2. **System 与 User 消息分开构建**：符合 OpenAI Chat Completions API 的消息格式规范，system 用于角色设定和提供参考材料，user 用于表达提问，职责明确
3. **模板层处理空材料场景**：通过 `{% if %}` 条件渲染，知识库为空时输出"（暂无参考材料）"，LLM 可据此如实告知用户，避免生成无意义的"参考材料：（空）"文本
4. **Jinja2 空白控制**：通过 `{%-` 和 `-%}` 去除模板标签产生的多余空行，保证渲染输出的整洁性
5. **模块级 Environment 单例**：`_env` 在模块加载时创建并缓存，后续每次 `build_rag_prompt` 调用复用同一个 `Environment` 实例，避免重复解析模板文件

## 6.3 QueryRewriter（查询改写与上下文感知）

QueryRewriter 在检索之前执行一次轻量 LLM 调用，将用户的口语化问题改写为两个互补产出物——**关键词列表**（空格分隔，传入 FTS5 做关键词检索）和**精炼自然语言查询**（传入 `embed_query()` 做语义向量检索）——使两条检索路径各自获得适配其特性的输入。

多轮对话场景下，QueryRewriter 接收对话摘要（`summary` 参数），结合摘要进行指代消解（将 "它""这个" 解析为具体实体）和上下文感知改写，使检索结果始终针对当前的对话上下文。

查询改写通过 Jinja2 模板（`zrag/prompts/query_rewrite.j2`）引导 LLM 完成，LLM 返回结构化 JSON `{"keywords": "...", "refined_query": "..."}`。QueryRewriter 通过依赖注入传入 Retriever，与 LLM Provider 解耦。输出格式需去除可能包裹的 markdown 代码块（` ```json ` 标记），JSON 解析失败或任何 LLM 调用异常时降级返回原始查询，不阻断检索主流程。

### 设计理念

**为何需要查询改写**。用户日常输入的自然语言问题往往带有口语化特征——简称、省略、非正式表达（如"怎么让 Python 跑得更快"而非"Python 程序性能优化方法"）。如果直接将原始查询原样传入向量检索和关键词检索，检索系统面对的是非标准化的表达，召回质量受用户措辞习惯影响很大。查询改写将口语化输入标准化——关键词列表专为 FTS5 精确匹配而提炼，精炼查询专为向量语义检索而规范化。

**为何全部查询都执行改写**。查询改写的替代方案是先对查询做复杂度判断（例如通过规则或分类器）——对简单查询跳过改写直接检索，对复杂查询才执行改写。这种方案在意图上是为了节省改写开销，但在实践中引入了一个新的故障模式：复杂度判断本身可能出错——一个看似简单的查询可能恰好因为措辞差异导致关键文档无法被检索到。此外，复杂度判断增加了代码路径的分支，使系统行为在不同查询上不一致，增大了调试和问题复现的难度。对全部查询执行改写使得系统行为统一可预测，改写的 LLM 调用延迟（约 0.5-1 秒）在 RAG 问答的整体耗时（检索 + LLM 生成，通常 5-20 秒）中占比有限，换取的输入质量提升是确定性的。

**为何对 keywords 输出做 FTS5 直传而非再分词**。LLM 输出的 keywords 是经过语义边界拆分后的搜索词（如 `Kubernetes 默认调度器 工作原理`），每个词已经是一个完整的语义单元。如果将 keywords 再经 jieba 分词拆分，可能会破坏 LLM 已完成的语义提炼——例如 LLM 输出的 `默认调度器` 是一个精确的技术术语，jieba 可能将其拆为 `默认` + `调度器` 两个独立 token。目前 `search_fts5()` 仍对 keywords 执行 jieba 分词——因为 FTS5 索引时已用 jieba 对 chunk content 做过分词，保持写入端和查询端的分词粒度一致是必要的。但 LLM 已承担了"提取核心语义单元"的职责，jpba 在此处的作用主要是做最后的 token 清洗和格式化，而非重新切分语义结构。

**为何采用"替换"而非"追加"同义词策略**。Keywords 中生成的搜索词，经 jieba 分词后多个 token 以空格连接后传入 FTS5 MATCH。SQLite FTS5 对空格分隔的 barewords 使用隐式 AND 语义——文档必须同时包含所有 token 才算命中。这意味着在 keywords 中追加同义词 token 会收紧而非放宽匹配约束。

以真实案例说明：用户查询「详细讲解Kubernetes默认调度器的实现原理」，若 LLM 将 keywords 同时包含用户原始术语和文档侧替代表述，输出 `Kubernetes 默认调度器 实现原理 工作原理`。经 jieba 分词后为 `Kubernetes 默认 调度器 实现 原理 工作`（FTS5 隐式 AND）。文档章节标题「工作原理」（分词后 `工作 原理`）包含了 `工作` 和 `原理`，但缺少 `实现`；另一 chunk「pod调度的实现原理」（分词后 `实现 原理`）包含了 `实现` 和 `原理`，但缺少 `工作`。结果两条 chunk 都因缺少其中一个 AND 项而双双落选——追加同义词反而让原本能命中的 chunk 也无法命中。

因此，LLM 在生成 keywords 时需执行的是**替换**而非追加——将用户查询中口语化或特定化术语替换为文档侧更常见的同义表达。例如「实现原理」替换为「工作原理」，使 FTS5 查询变为 `Kubernetes 默认 调度器 工作 原理`，从而命中标题为「工作原理」的章节 chunk。替换策略通过 `query_rewrite.j2` 模板中的指令实现——模板中新增同义词替换规则，引导 LLM 在提炼关键词时主动识别并替换用户术语为文档侧更常见的表达，关键词总数保持在 5 个以内，不无意义扩充。

> 注意：替换策略依赖于 LLM 的语义理解能力来识别同义/近义表达。对于需要多个同义词覆盖不同文档措辞的场景（如文档中既使用了「实现原理」也使用了「工作原理」），当前 AND 语义下无法用单一 keywords 字符串同时覆盖。这类场景需未来升级 FTS5 OR 语法支持或实现多路 FTS5 查询——这些扩展涉及 `sqlite_store.py` 的代码改动，当前阶段仅通过模板指令优化来提升改写质量。

**为何 refined_query 不做同义词替换**。Refined_query 传入 `embed_query()` 后走向量语义检索路径，Embedding 模型对同义表达具有天然的语义容忍度——「实现原理」和「工作原理」在 BGE 模型的向量空间中距离相近，即使不替换也能召回语义相关的 chunk。因此同义词替换策略仅应用于 keywords（FTS5 精确匹配路径），refined_query 保持原样以保证语义检索覆盖面的完整性。

**为何同义词扩展仅通过模板指令实现而不引入词库**。引入配置化的领域同义词映射表（如 `synonyms.yaml`，将「实现原理」映射到 `[工作原理, 设计原理, 算法原理]`）在工程上是更精确的方案——不依赖 LLM 的语义理解能力，映射是确定性的。但这种方案引入了一个新的需要维护的数据资产（词库文件），且词库的覆盖度随着文档领域变化需要持续更新。对于 ZRAG 的个人使用规模，通过 LLM 模板指令实现同义词替换已能满足当前需求——LLM 在生成 kewords 时具备上下文语义理解能力，可以根据具体的查询语境选择最优替换词，无需预定义映射表。模板指令方案的维护成本为零——修改模板中的规则措辞或示例即可调整行为，不需要额外维护数据文件或代码逻辑。

**为何引入上下文感知改写**。当前 QueryRewriter 仅接收当前 query，在多轮对话中不感知上下文。这导致两个问题。其一是指代消解——追问 "那它的性能怎么样？" 时，"它" 无法被解析为前一问的实体。其二是上下文缺失——追问 "打分怎么做的" 中的 "打分" 由上一轮 assistant 回复首次引入，用户历史查询序列中从未出现这个词。在多轮对话中，用户的后继查询高度依赖前文提供的信息背景，检索系统如果不能理解这个背景，就会在模糊查询上产生偏题检索结果。解决方式是将对话摘要注入 QueryRewriter——`rewrite()` 方法新增 `summary` 参数，Summary 为 null 时保持原有行为（向后兼容），Summary 不为 null 时将摘要文本注入 user message 前缀（格式为 `"对话上下文摘要：{summary}\n\n当前用户查询：{query}"`），引导 LLM 结合上下文做指代消解和改写。

**为何摘要注入在 user message 而非 system prompt**。System prompt 在 QueryRewriter 中用于定义角色和输出格式约束，是固定的模板内容。摘要（上下文信息）是动态数据，随着每轮对话更新。将摘要注入 user message 而非 system prompt 有两层考虑。第一，保持 system prompt 简洁稳定——system prompt 变更后需要重新评估 LLM 对角色指令的遵循程度，而 user message 的变更是预期中的动态输入，LLM 更容易适应。第二，语义位置——将摘要与当前 query 放在一起（`摘要\n\n当前查询`）让 LLM 自然地理解 "先有上下文、后有当前问题" 的信息结构，这是人类处理追问时的信息组织方式。

**为何同义词替换改为核心词提取**。之前的同义词替换策略（"实现原理"→"工作原理"）经过验证，LLM 未能遵循指令。根因在于 LLM 无法从自身训练数据中预测特定文档库实际使用的术语——"实现原理" 是有效的技术术语，LLM 没有任何依据将其替换为 "工作原理"。即使模板中给出了明确示例，LLM 仍然以自身知识为最高优先级来完成 "改写成更精准表达" 这个任务。这是一个根本性的局限——术语映射需要领域知识，而 LLM 的领域知识无法覆盖用户的私有文档库。修正方案是将指令从 "使用技术文档中更常见的同义表达" 改为 "只保留最核心的名词，去掉修饰性前缀"——例如 "实现原理" 提取为 "原理"。"核心词提取" 策略的核心优势在于降低了任务对 LLM 领域知识的依赖——LLM 不需要知道文档中实际使用的术语是什么，只需识别并剥离复合词中的修饰成分。这是一项纯语言学任务，不涉及任何领域知识，7B-9B 级别的模型完全胜任。模板中对应指令更新为：`对于复合概念术语，只保留最核心的名词，去掉修饰性前缀。例如 "实现原理" 提取为 "原理"。`

### 核心实现

模板文件 `zrag/prompts/query_rewrite.j2` 作为 system prompt 发送给 LLM：

```
你是一个查询优化助手。你的任务是将用户的日常口语化查询改写为更适合检索的结构化格式。

任务说明:
1. 从用户查询中提取核心关键词，用空格分隔，用于全文检索
2. 将用户查询精炼改写为简洁、规范的自然语言查询，用于语义检索
3. 如果用户查询中包含指代词（如"它"、"这个"、"上面提到的"等），
   请结合提供的对话上下文摘要，将指代词替换为具体的概念或实体。
   例如：上下文摘要提到"Kubernetes默认调度器"，
   用户问"它的性能怎么样"，应将"它"替换为"Kubernetes默认调度器"。
4. 关键词提取时注意：对于复合概念术语，只保留最核心的名词，去掉修饰性前缀。
   例如 "实现原理" 提取为 "原理"。
   关键词总数保持在 5 个以内，不要无意义扩充。
5. 输出必须是纯 JSON 格式，不要使用 markdown 代码块包裹

示例:
用户查询: "怎么在k8s里配自动伸缩啊"
输出: {"keywords": "Kubernetes 自动伸缩 配置", "refined_query": "如何在 Kubernetes 中配置自动伸缩"}

用户查询: "详细讲解Kubernetes默认调度器的实现原理"
输出: {"keywords": "Kubernetes 默认调度器 原理", "refined_query": "详细讲解 Kubernetes 默认调度器的实现原理"}
```

QueryRewriter 类的核心逻辑：

```python
class QueryRewriter:
    """查询改写器
    
    通过 Jinja2 模板构建 system prompt, 引导 LLM 将口语化查询改写为
    结构化 JSON {keywords, refined_query}。
    解析失败时降级返回原始查询, 不阻断检索主流程。
    
    @param llm_provider: LLM Provider 实例, 需实现 chat(messages) -> str | None
    @param prompts_dir:  Prompt 模板目录路径
    """

    def rewrite(self, query: str, summary: str | None = None) -> dict[str, str]:
        """改写用户查询，结合对话摘要进行指代消解和上下文感知改写

        @param query:   用户输入的原始口语化查询
        @param summary: 对话上下文摘要，null 表示首轮对话，此时行为与旧版一致（向后兼容）
        @return: {"keywords": "...", "refined_query": "..."}
                 异常时降级: {"keywords": query, "refined_query": query}
        """
        # 构建消息: system 放指令, user 放查询（如有摘要则注入为前缀）
        system_prompt = self._template.render()
        user_content = query
        if summary:
            user_content = f"对话上下文摘要：{summary}\n\n当前用户查询：{query}"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        response = self._llm.chat(messages)
        if response is None:
            logger.warning("LLM chat returned None, falling back to original query")
            return {"keywords": query, "refined_query": query}

        return self._parse_response(response, query)

    def _parse_response(self, response: str, query: str) -> dict[str, str]:
        """解析 LLM 返回的 JSON, 去除可能包裹的 markdown 代码块
        
        解析成功后记录改写结果日志, 缺失字段或解析失败时降级返回原始查询。
        """
```

### 设计特点总结

1. **改写与检索解耦**：QueryRewriter 通过依赖注入传入 Retriever，改写逻辑不嵌入检索流程，便于独立测试和替换
2. **模板驱动改写**：改写规则和示例集中在 `query_rewrite.j2` 模板中，修改改写策略无需改动 Python 代码
3. **同义词替换策略**：针对 FTS5 隐式 AND 语义，LLM 输出关键词时执行术语替换（而非追加），避免同义词扩充导致 AND 约束加严
4. **双路差异化输入**：keywords 走 FTS5 精确匹配路径（可替换用户术语），refined_query 走向量语义检索路径（保留语义完整性），各取所长
5. **降级不阻断**：LLM 调用失败、返回 None、JSON 解析失败等所有异常场景下静默降级为使用原始查询，不影响检索主流程的正常运行
6. **上下文感知改写**：多轮对话中通过 `summary` 参数注入对话摘要，LLM 结合上下文解析指代并精炼查询。摘要为 null 时向后兼容，首轮对话行为不变
7. **核心词提取取代同义词替换**：从 "替换为文档侧术语" 改为 "剥离修饰性前缀只保留核心名词"，降低对 LLM 领域知识的依赖，依赖纯粹的语言学能力

## 6.4 ConversationSummarizer（对话压缩）

ConversationSummarizer 将多轮对话中的每轮 Q&A 压缩为简洁的自然语言摘要，摘要注入 QueryRewriter 后用于上下文感知检索。它与 QueryRewriter 共享同一个本地 LLM 后端，但职责独立——压缩和改写是两种不同的语言任务，各自有独立的 prompt 模板（`compress.j2` 和 `query_rewrite.j2`）和错误处理策略。

### 设计理念

**为何压缩与改写分属不同的类**。压缩和改写虽然都调用 LLM，但任务性质不同：改写需要输出结构化 JSON（`{keywords, refined_query}`），对输出格式有严格约束；压缩输出纯文本（自然语言摘要），清理前缀后即可使用。两者的 prompt 模板独立迭代——调整压缩策略（如改变摘要粒度或长度限制）不应影响改写模板，反之亦然。此外，压缩在请求响应后异步执行，改写紧跟查询请求同步执行——两个调用在时间线上分离，属于不同的调用上下文。将两者分离为独立的类使得各自的 mock 测试和错误处理互不干扰。

**为何采用增量压缩**。增量压缩每次传入已有摘要 + 最新一轮 Q&A（助手回复截断到 500 字符），LLM 输出更新后的摘要（最大 200 字）。这种策略下输入长度恒定，不随对话轮数增加而膨胀。全量压缩（每次传入全部历史 Q&A）在第 10 轮对话时 prompt 可能超过 5000 字符，对本地 9B 模型的推理延迟是显著负担。增量压缩的另一优势是信息自然衰减——早期对话内容在反复重压缩中被逐步泛化，第 1 轮的详细讨论在第 8 轮后可能退化为一个简述词，这种衰减与人类对话中话题漂移的认知模式一致。200 字的硬上限迫使 LLM 自行取舍优先级，不需要显式限制对话轮次。

**为何对摘要输出做清理**。本地小模型（7B-9B 级别）的指令跟随能力不如 API 模型（IFEval 91.5 分表示仍有约 8.5% 概率未能完美遵循指令）。常见的不良输出模式包括在摘要前添加前缀词（"好的，对话摘要如下"、"更新后的摘要："）。虽然在 prompt 中通过严格输出规则（"你只能输出摘要文本本身，禁止输出任何其他内容"）作为第一道防线约束 LLM，但 9B 模型的不完全确定性使得这道防线不能做到 100% 可靠。因此 `ConversationSummarizer._clean_summary()` 作为第二道防线，匹配并移除常见废话前缀（"好的，"、"以下是"、"更新后的摘要："、"摘要："、"总结："、"："），并截断到 `max_chars`。两道防线比单靠 prompt 更可靠。

**为何助手回复截断到 500 字符**。LLM 生成的完整回答可能超过 2000 字符，但摘要不需要所有细节。500 字符足够覆盖回答中的核心论点和关键实体。过度截断可能导致摘要丢失重要上下文（如回答中后半部分引入的新概念），截断不足则让 prompt 膨胀。500 字符是基于本地 9B 模型典型输出风格和 ZRAG 问答场景的经验值。

### 核心实现

模板文件 `zrag/prompts/compress.j2` 作为 system prompt：

```
你是一个对话摘要助手。请根据已有的对话摘要和最新一轮的问答内容，生成更新后的对话摘要。

摘要要求:
1. 用一段自然语言概括对话主题、用户关注的核心概念以及已讨论过的具体问题
2. 摘要长度不超过{{ max_chars }}字
3. 如果已有摘要为空，说明这是首轮对话，只概括本轮内容即可
4. 如果已有摘要不为空，需要将本轮新内容融入已有摘要中，保持摘要的整体连贯

严格输出规则:
- 你只能输出摘要文本本身，禁止输出任何其他内容
- 禁止添加"好的"、"以下是"、"更新后的摘要"、"总结："等任何前缀文字
- 禁止添加解释、评价或补充说明
- 违反此规则将导致摘要无法被系统处理
```

User message 格式为 `已有摘要：{summary 或 "（首轮对话，无已有摘要）"}\n\n最新一轮对话：\n用户提问：{user_query}\n助手回答：{assistant_reply[:500]}`。

ConversationSummarizer 核心接口：

```python
class ConversationSummarizer:
    """对话摘要压缩器

    将多轮对话内容压缩为简洁的自然语言摘要，用于注入查询改写阶段。
    采用增量压缩策略：每次传入已有摘要 + 最新一轮 Q&A，生成更新后的摘要。
    """

    _MAX_REPLY_CHARS = 500  # 助手回复截断长度

    def __init__(self, llm_provider, template_dir=None, max_chars=200):
        ...

    def summarize(self, old_summary: str, user_query: str, assistant_reply: str) -> str:
        """生成更新后的对话摘要

        @param old_summary:     已有摘要（空字符串表示首轮）
        @param user_query:      本轮用户查询文本
        @param assistant_reply: 本轮助手回复文本（内部截断到 _MAX_REPLY_CHARS）
        @return: 更新后的摘要文本
        """
        truncated_reply = assistant_reply[:self._MAX_REPLY_CHARS]
        messages = self._render_messages(old_summary, user_query, truncated_reply)
        response = self._call_llm(messages)
        return self._clean_summary(response)

    def _clean_summary(self, raw_text: str) -> str:
        """清理 LLM 输出的废话前缀，截断到 max_chars"""
```

### 设计特点总结

1. **增量压缩**：每次仅处理已有摘要 + 最新一轮 Q&A，输入长度恒定，不随对话轮数膨胀
2. **双层防护输出清理**：prompt 约束（第一道防线）+ `_clean_summary()`（第二道防线兜底），最大化保障摘要文本干净可用
3. **与 QueryRewriter 解耦**：共享一个本地 LLM 后端，但各自独立的类、模板和错误处理
4. **纯文本输出**：压缩输出为纯文本（非 JSON），降低对 9B 模型输出格式的约束要求

## 6.5 CompressService（异步压缩调度）

CompressService 封装异步压缩的调度逻辑。每轮对话的回答生成后，CompressService 将压缩任务提交到项目全局线程池，不等待结果即返回，用户感知不到压缩的延迟。

### 设计理念

**为何复用项目全局线程池**。ZRAG 在 `settings.py` 中已有一个 `ZRAG_INGEST_EXECUTOR`（默认 2 workers），用于摄入任务的异步执行。压缩任务同样属于"在请求响应后可异步执行的轻量工作"。复用现有线程池避免创建第二个线程池——减少线程管理的复杂度，且压缩任务（秒级 LLM 调用 + 一次 DB 写入）的负载极低，不会与摄入任务（分钟级）产生资源竞争。CompressService 通过构造器注入 `executor` 参数，注入方式与 `TaskManager` 一致。

**为何静默失败**。压缩失败的可能原因包括：本地模型不可用（Ollama 容器宕机）、LLM 调用超时、数据库写入失败、模型输出异常（摘要为空或格式错误）。这些失败不影响当前轮次的回答质量——用户已经收到了正常的 AI 回复。如果压缩失败时向上抛出异常或向用户展示错误，会破坏用户的核心交互体验。正确的故障边界是：压缩在后台静默失败，仅记录错误日志，不重试（避免连续失败的资源浪费）。下一轮追问时，QueryRewriter 降级使用旧摘要（或 null），改写质量轻微下降但不影响回答流程的完整性。

**为何模块级单例**。压缩服务需要在 Django 应用的多个 ViewSet 方法间共享——`create()` 和 `add_message()` 都需要访问同一个 CompressService 实例。每次请求创建新实例会导致线程池引用混乱。采用模块级单例（DoLC 懒加载），`get_compress_service()` 为唯一入口，首次调用时从 Django settings 读取 `rewriter_model` 和 `ZRAG_INGEST_EXECUTOR` 并初始化，后续调用直接返回已有实例。

**为何不传 db_path**。压缩任务运行在线程池工作线程中，线程运行在同一 Django 进程内，可以直接读取 `django.conf.settings.ZRAG_STORAGE`。`SqliteStore()` 无参数构造内部从 settings 读取 `sqlite_path`，因此无需在 CompressService 接口中传递 `db_path` 参数。且每个压缩任务创建独立的 `SqliteStore` 实例（获得独立 SQLite 连接），WAL 模式支持读写并发。

### 核心实现

```python
class CompressService:
    """异步压缩服务 — 复用项目全局线程池异步执行对话压缩"""

    def __init__(self, executor, llm_provider):
        self._executor = executor
        self._summarizer = ConversationSummarizer(llm_provider=llm_provider)

    def submit(self, conversation_id, old_summary, user_query, assistant_reply):
        """提交异步压缩任务，立即返回（不等待结果）"""
        self._executor.submit(
            self._run, conversation_id, old_summary, user_query, assistant_reply,
        )

    def _run(self, conversation_id, old_summary, user_query, assistant_reply):
        """压缩线程主逻辑：summarize → 写入 DB（独立 SqliteStore 连接）"""
        # LLM 调用失败和 DB 写入失败均静默，仅写日志
```

### 设计特点总结

1. **复用全局线程池**：与摄入任务共享，注入方式与 TaskManager 一致
2. **静默失败**：任何异常仅记日志，不重试，不阻塞请求，不影响下一轮对话
3. **模块级单例**：DoLC 懒加载，从 Django settings 自动读取配置
4. **独立 DB 连接**：每个压缩任务创建独立 SqliteStore 实例，WAL 支持并发写

---

# 7. LLM 集成

LLM 集成采用抽象基类 + 具体实现模式。上层调用方（ViewSet、CLI）只依赖 `LLMProvider` ABC 定义的接口契约——`chat()` 和 `chat_stream()`——不感知底层是 LiteLLM Gateway、直接调用 OpenAI API 还是本地 Ollama。具体实现通过注册表 `LLM_PROVIDER_REGISTRY` 按配置中的 `provider` 字段动态选择，所有 LLM 请求统一通过 OpenAI SDK 发送，temperature 固定为 0.4 以保证 RAG 场景的回答忠实性。

核心接口定义：

```python
class LLMProvider(ABC):
    """LLM 调用抽象基类

    定义与大语言模型通信的统一接口。
    所有具体的 LLM Provider 实现必须继承此类并实现全部抽象方法。

    chat() 用于同步非流式对话, chat_stream() 用于流式对话。

    on_error 回调策略:
      - 回调函数已提供 -> 通知回调, 不抛异常 (chat 返回 None, chat_stream 生成器空)
      - 回调函数未提供 -> 抛 BaseZragException

    @param model: 模型名称, defaults to None
    @type  model: str, optional
    @param timeout: 请求超时时间(秒), defaults to 200
    @type  timeout: float, optional
    @param on_error: 错误回调函数, 接收 ErrorEvent, defaults to None
    @type  on_error: callable, optional
    """

    def __init__(
        self,
        model: str | None = None,
        timeout: float | None = None,
        on_error: Callable | None = None,
    ):
        """构造 LLMProvider

        若 model 或 timeout 未显式传入，则从 Django settings.ZRAG_LLM 配置中读取。
        配置中也缺失时抛出 ValueError。

        @param model: 模型名称, 未传入则从配置读取, defaults to None
        @type  model: str, optional
        @param timeout: 请求超时时间(秒), 未传入则从配置读取, defaults to None
        @type  timeout: float, optional
        @param on_error: 错误回调函数, 接收 ErrorEvent, defaults to None
        @type  on_error: callable, optional

        @raises ValueError: model 或 timeout 在参数和配置中均未提供时抛出
        """
        from django.conf import settings
        llm_cfg = getattr(settings, "ZRAG_LLM", {})
        self._model = model if model is not None else llm_cfg.get("gateway", {}).get("model")
        if not self._model:
            raise ValueError("配置缺失: llm.gateway.model")
        self._timeout = timeout if timeout is not None else llm_cfg.get("timeout")
        if self._timeout is None:
            raise ValueError("配置缺失: llm.timeout")
        self._on_error = on_error

    @abstractmethod
    def chat(self, messages: list[dict]) -> str | None:
        """同步非流式对话

        @param messages: 消息列表, 格式为 [{"role": "user", "content": "..."}]
        @type  messages: list[dict]

        @return: 模型回复文本; 若发生错误且 on_error 已提供则返回 None
        @type:   str | None

        @raises: 当 on_error 未提供且调用失败时抛出
        @type:   BaseZragException
        """
        ...

    def chat_stream(self, messages: list[dict]) -> Iterator[str]:
        """流式对话

        Phase 1 默认实现: 调用 chat() 后将结果作为单次 yield 返回。
        子类在 Phase 2 可 override 实现真正的流式输出。

        @param messages: 消息列表
        @type  messages: list[dict]

        @return: 生成器, 逐 token yield 回复文本
        @type:   Iterator[str]
        """
        result = self.chat(messages)
        if result is not None:
            yield result
```

LiteLLM Gateway 具体实现：

```python
class LLMGatewayProvider(LLMProvider):
    """LiteLLM Gateway LLM 实现

    使用 OpenAI SDK 连接自托管的 LiteLLM Gateway。
    支持 smart-router 负载均衡和多种模型切换。

    @param model: 模型名称, defaults to "smart-router"
    @type  model: str, optional
    @param timeout: 请求超时秒数, defaults to 200
    @type  timeout: float, optional
    @param base_url: LiteLLM Gateway 地址, defaults to "http://localhost:4000/v1"
    @type  base_url: str, optional
    @param on_error: 错误回调函数, 接收 ErrorEvent
    @type  on_error: callable, optional
    """

    def __init__(
        self,
        model: str | None = None,
        timeout: float | None = None,
        base_url: str | None = None,
        on_error: Callable | None = None,
    ):
        """构造 LLMGatewayProvider

        若 model、timeout 或 base_url 未显式传入，则从 Django settings.ZRAG_LLM 配置中读取。
        配置中也缺失时抛出 ValueError。

        @param model: 模型名称, 未传入则从配置读取, defaults to None
        @type  model: str, optional
        @param timeout: 请求超时秒数, 未传入则从配置读取, defaults to None
        @type  timeout: float, optional
        @param base_url: LiteLLM Gateway 地址, 未传入则从配置读取, defaults to None
        @type  base_url: str, optional
        @param on_error: 错误回调函数, 接收 ErrorEvent
        @type  on_error: callable, optional

        @raises ValueError: 必要配置项在参数和配置中均未提供时抛出
        """
        from django.conf import settings
        llm_cfg = getattr(settings, "ZRAG_LLM", {})
        gateway_cfg = llm_cfg.get("gateway", {})

        self._model = model if model is not None else gateway_cfg.get("model")
        if not self._model:
            raise ValueError("配置缺失: llm.gateway.model, 请检查 config/llm.yaml")

        self._timeout = timeout if timeout is not None else llm_cfg.get("timeout")
        if self._timeout is None:
            raise ValueError("配置缺失: llm.timeout, 请检查 config/llm.yaml")

        base_url_val = base_url if base_url is not None else gateway_cfg.get("base_url")
        if not base_url_val:
            raise ValueError("配置缺失: llm.gateway.base_url, 请检查 config/llm.yaml")

        api_key_val = gateway_cfg.get("api_key")
        if not api_key_val:
            raise ValueError("配置缺失: llm.gateway.api_key, 请检查 config/llm.yaml 或设置 LITELLM_MASTER_KEY")

        super().__init__(model=self._model, timeout=self._timeout, on_error=on_error)
        self.client = OpenAI(base_url=base_url_val, api_key=api_key_val)

    def chat(self, messages: list[dict], timeout: float | None = None) -> str | None:
        """同步非流式对话

        通过 OpenAI SDK 调用 LiteLLM Gateway。

        @param messages: 消息列表
        @type  messages: list[dict]
        @param timeout: 超时覆盖, defaults to None（使用构造时的超时）
        @type  timeout: float, optional

        @return: 模型回复文本; 失败且 on_error 已提供时返回 None
        @type:   str | None

        @raises: on_error 未提供时抛 LLMCallException
        @type:   LLMCallException
        """
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.4,
                timeout=timeout or self.timeout,
            )
            return resp.choices[0].message.content
        except Exception as e:
            if self._on_error:
                self._on_error(ErrorEvent(
                    source_id="llm_gateway",
                    error=f"LLM call failed: {e}",
                    exception=e,
                ))
                return None
            raise LLMCallException(str(e))

    def chat_stream(
        self, messages: list[dict], timeout: float | None = None
    ) -> Iterator[str]:
        """流式对话

        Phase 2 实现真正的 SSE 流式。

        @param messages: 消息列表
        @type  messages: list[dict]

        @return: 生成器, 逐 token yield
        @type:   Iterator[str]
        """
        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.4,
                stream=True,
                timeout=timeout or self.timeout,
            )
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            if self._on_error:
                self._on_error(ErrorEvent(
                    source_id="llm_gateway",
                    error=f"LLM stream failed: {e}",
                    exception=e,
                ))
            else:
                raise LLMCallException(str(e))
```

LLM Provider 注册表与工厂函数：

```python
LLM_PROVIDER_REGISTRY: dict[str, type[LLMProvider]] = {
    "gateway": LLMGatewayProvider,
}

def create_llm(config: dict) -> LLMProvider:
    provider_type = config["llm"]["provider"]
    cls = LLM_PROVIDER_REGISTRY[provider_type]
    provider_cfg = config["llm"].get(provider_type, {})
    return cls(**provider_cfg)
```

### 设计理念

**为何抽象 LLMProvider**。LLM 服务的后端存在多种可能性：当前使用自托管 LiteLLM Gateway，但未来可能切换为直接调用 OpenAI API、本地运行 Ollama、接入 Anthropic Claude API 或其他厂商。如果在 ViewSet 或 CLI 层直接实例化 `LLMGatewayProvider`，每当切换 LLM 后端时，所有调用方代码（ViewSet 中的 `_get_llm_provider()` 方法、CLI 中的 query 命令、测试代码中的 mock 配置）都需要逐个修改——分散的修改点多且容易遗漏。ABC 的核心作用是将"做什么"（调用 LLM 获取回答）与"怎么做"（通过 Gateway 还是 OpenAI API 还是 Ollama）分离。上层调用方只持有 `LLMProvider` 类型的引用，通过抽象的 `chat(messages)` 方法发送请求，完全不需要知道底层是哪个具体实现。切换 LLM 后端时，只需修改配置文件中的 `provider` 字段和注册表中的映射关系，ViewSet 和 CLI 代码不受任何影响。配合注册表 `LLM_PROVIDER_REGISTRY` 和工厂函数 `create_llm()`，新增一个 LLM Provider 只需实现 `LLMProvider` ABC 并在注册表中登记，无需改动任何已有调用方代码——这正是"对扩展开放、对修改封闭"原则在 LLM 集成层的体现。

**为何选择 LiteLLM Gateway 而非直接调用模型 API**。如果 Backend 代码直接集成各家模型厂商的 SDK——DeepSeek 用 DeepSeek SDK、GLM 用智谱 SDK、Kimi 用 Moonshot SDK——那么 API Key 管理、模型切换和负载均衡的逻辑将散布在代码各处，每接入一个新厂商就需要编写一套新的 SDK 调用代码，维护成本随模型数量线性增长。LiteLLM Gateway 从三个层面解决了这个问题。第一，Gateway 以 OpenAI 兼容接口统一暴露多种模型——无论后端实际模型是 DeepSeek、GLM 还是 Kimi，Backend 只需要使用 OpenAI SDK 通过单一基地址（`http://localhost:4000/v1`）发送 `chat/completions` 请求，Gateway 内部完成协议转换。第二，Gateway 内置 smart-router 负载均衡和故障转移——配置一个 `smart-router` 虚拟模型名，Gateway 会根据各底层模型的实时可用性和延迟自动选择最优模型路由请求，某一模型不可用时自动 fallback 到备用模型，Backend 代码无感知。第三，Gateway 统一管理 API Key 和成本追踪——所有厂商的 API Key 存放在 Gateway 的 YAML 配置文件中，Backend 和前端均不接触任何 API Key，消除了 Key 泄漏的风险面。Gateway 以独立进程形式运行在宿主机上，ZRAG 容器通过 `host.docker.internal:4000` 访问——Gateway 的启停和升级不影响 ZRAG 容器的生命周期。

> 注意：LiteLLM Gateway 的配置位于宿主机 `~/.claude/litellm/config.yaml`，其中已配置了 `smart-router` 负载均衡组（含 glm-5、kimi-k2.6、deepseek-v4-flash、minimax-m2.7、deepseek-v4-pro 等模型）。Backend 仅需指定模型名为 `smart-router`，Gateway 自动路由到最优可用模型。

**为何 LLM 错误处理采用双模式（on_error 回调 vs 抛异常）**。LLM 调用可能在两种截然不同的上下文中被使用：Web API 请求（ViewSet 中处理 HTTP 请求）和 CLI 命令（命令行工具直接调用）。这两种上下文对错误处理的需求不同。在 Web API 场景中，调用方（ViewSet）需要严格控制 HTTP 响应的格式——即使 LLM 调用失败，也必须返回一个合法的 JSON 响应体（含 `code`、`message` 和 `request_id` 字段），而不是让框架层捕获一个裸异常后返回格式不一致的 500 页面。此时调用方传入 `on_error` 回调，LLM 调用失败时 `chat()` 返回 `None`（不抛异常），ViewSet 检测到 `None` 返回值后自行构建包含错误信息的标准 API 响应。在 CLI 场景中，调用方（CLI 命令）需要立即感知错误并终止执行——如果 `chat()` 返回 `None`，CLI 需要额外编写一层判断逻辑来将 `None` 解释为失败，代码冗余且语义不直观。此时调用方不传 `on_error`，LLM 调用失败时直接抛出 `LLMCallException`，CLI 在最外层用 try/except 捕获后打印错误信息并退出。双模式设计让调用方可以按自身需求选择错误传播方式——需要控制响应格式的场景选回调模式，需要简单直接报错的场景选异常模式——同一个 `LLMProvider` 实现同时满足两种需求，不给任何一方增加无谓的适配代码。

```python
# Web API 场景: on_error 回调 → 返回 None → ViewSet 自行构建错误响应
provider = LLMGatewayProvider(on_error=my_error_handler)
reply = provider.chat(messages)
if reply is None:
    return api_error_response("LLM 调用失败")

# CLI 场景: 不传 on_error → 抛异常 → CLI 统一捕获
provider = LLMGatewayProvider()
try:
    reply = provider.chat(messages)
except LLMCallException as e:
    print(f"LLM 调用失败: {e}")
    sys.exit(1)
```

> 注意：`on_error` 回调的注入时机在 LLMProvider 的 `__init__` 构造方法中，而非每次 `chat()` 调用时传递。这是因为同一个 LLMProvider 实例在多次调用中复用的错误处理逻辑应该是相同的——在 Web API 场景中 ViewSet 持有的 provider 实例在进程生命周期内始终使用同一个 error handler。这一点与 IngestionPipeline 不同——IngestionPipeline 的 `on_error` 在 `run()` 方法参数中传入，因为每次 `run()` 可能由不同的调用方触发，对应不同的错误处理需求。

**为何 temperature=0.4**。temperature 参数控制 LLM 输出的随机性：值越低（趋近 0）输出越确定、越可复现；值越高（趋近 1 或更高）输出越多样、越有"创意"。RAG 场景的核心要求是 LLM 基于检索到的参考材料回答问题，而非进行创意写作或头脑风暴——如果 temperature 过高（如 0.8 或 1.0），LLM 可能脱离参考材料自行发挥，在回答中引入不存在于检索结果中的虚构信息（幻觉）。如果 temperature 过低（如 0.0 或 0.1），回答虽然严格忠实但读起来机械僵硬，缺乏自然的语言变化，用户体验差。ZRAG 选择 0.4，这个值在忠实性和自然度之间取得了一个经验平衡：保留了足够低的随机性以防止脱离材料进行幻想，同时给予了足够的语言表达灵活性，使回答读起来不像模板拼接。这一取值并非随意设定——在多个 RAG 系统的工程实践中，0.3~0.5 是对抗幻觉与保持自然语言的常用区间，0.4 是这个区间中偏保守的取值，优先保证忠实性。

**为何 chat_stream 在 Phase 2 实现而非 Phase 1**。流式输出（SSE, Server-Sent Events）的实现需要前后端协同改造。后端侧：Django 需要实现 SSE 端点，这意味着 ViewSet 的方法不能使用 DRF 标准的 `Response` 返回方式，而需要改用 `StreamingHttpResponse` 并保持连接持续推送数据块；uWSGI 的配置也需要调整——harakiri 超时对 SSE 长连接不适用，需要为 SSE 端点单独配置超时策略或移出 harakiri 监控范围。前端侧：需要将现有的"一次性接收完整回复"改为"逐 token 增量渲染"模式——请求通过 EventSource 或 fetch + ReadableStream 发起，UI 需要在消息气泡中实时追加每个新到达的 token，并处理流中断、重连、部分消息丢失等边界情况。前后端协同意味着两边的改动相互依赖——后端改了 SSE 但前端没适配，前端无法消费；前端改了流式渲染但后端没提供 SSE，请求直接失败。Phase 1 的目标是验证核心 RAG 链路的正确性——检索是否准确、Prompt 是否有效、回答是否有来源标注——这些验证不依赖流式输出。在核心链路稳定后，Phase 2 再切入 SSE 优化用户体验，可以降低并行变更的风险——如果 Phase 1 中同时引入 SSE，一旦出问题很难区分是 RAG 逻辑错误还是 SSE 传输错误。

> 注意：Phase 1 中 `chat_stream()` 的默认实现是调用 `chat()` 后将结果作为单次 yield 返回——上层调用方代码可以写成 `for token in provider.chat_stream(messages)` 的流式调用形式，但实际效果等同于非流式（生成器只产生一个元素）。这种设计使调用方代码在 Phase 1 就可以按流式调用的形式编写，Phase 2 只需替换底层 provider 实现，调用方代码无需修改。

**为何超时设为 200s**。LLM 调用是整个 RAG 链路中最耗时的环节，其耗时波动取决于多个因素：底层模型的推理速度（不同模型的首 token 延迟和生成速度差异可达数倍）、Gateway smart-router 的排队策略（模型繁忙时请求可能在队列中等待）、以及 Gateway 内部的多模型重试和 fallback 逻辑（某个模型失败后自动切换到备用模型重新请求）。LiteLLM Gateway 的默认 request_timeout 为 180s，如果 Backend 的超时小于 180s 且 Gateway 正在内部进行 fallback 重试，Backend 会提前断开连接——而此时 Gateway 可能刚刚切换到备用模型并准备返回结果。因此 Backend 的超时必须略大于 Gateway 的超时，为内部的 fallback 链路预留缓冲时间。200s 的取值逻辑是：在 Gateway 的 180s 基础上额外保留 20s 的缓冲，覆盖最坏情况下的网络往返延迟和 Gateway 内部多模型切换的开销。同时，200s 也是一个合理的上限——如果 200s 内仍未返回结果，说明要么所有模型均不可用，要么请求参数有误陷入了无限等待（如 stream=True 但网络中断后被 TCP keepalive 保持连接），继续等待没有意义。此外，uWSGI 配置的 harakiri 为 180s——实际生效的硬限制是 uWSGI 层面的 180s harakiri，Backend 的 200s 超时在 harakiri 之前触发，可在被 harakiri 强制杀死前自行完成资源清理和错误日志记录。

**为何 LLM 调用失败时返回 None 而非空字符串**。在"on_error 回调已提供"的错误处理模式下，`chat()` 方法不抛异常，而是通过返回值向调用方传达失败信号。此时需要在"无结果"的可选返回值中区分两种本质不同情况：LLM 确实处理了请求但回复内容为空（极小概率，如模型输出了零长度的 content），以及 LLM 调用过程中发生了异常（网络超时、Gateway 不可用、API Key 无效等）。如果统一使用空字符串 `""` 来表示这两种情况，调用方无法区分"正常调用但模型返回了空内容"与"调用本身失败了"——前者可能是合法的业务结果（模型判断不需要回复），后者是需要处理的错误（需要记录日志、返回错误响应给前端）。`None` 是 Python 中表示"不存在"的惯用方式——`if reply is None` 的语义是一目了然的：没有拿到任何回复。调用方可以精确地判断：`None` 意味着错误发生（记录错误日志、返回错误响应），空字符串 `""` 意味着模型成功调用但未产出内容（可作为正常结果转发给前端）。这个区分在 Web API 场景中尤为重要——ViewSet 需要根据 `None` 来返回正确的 HTTP 状态码和错误信息，而空字符串应作为 200 成功响应返回。

LLM 配置结构（YAML，支持多 Provider 扩展）：

```yaml
# config/llm.yaml
llm:
  provider: "gateway"              # 分辨器: gateway | ollama | openai | claude
  timeout: 200                      # 请求超时(秒)
  gateway:
    base_url: "http://localhost:4000/v1"
    api_key: "${LITELLM_MASTER_KEY}"
    model: "smart-router"
```

模型路由通过 LiteLLM Gateway 的 `smart-router` 配置实现负载均衡，可用的底层模型包括 glm-5、kimi-k2.6、deepseek-v4-flash、minimax-m2.7、deepseek-v4-pro 等。Backend 不需要知道这些底层模型的存在——它只请求 `smart-router`，由 Gateway 根据各模型的实时状态自动选择最优路由。

### 本地 LLM 部署（Ollama + Qwen3.5-9B）

查询改写（QueryRewriter）和对话压缩（ConversationSummarizer）这类高频率、低语义难度的任务，从 API 模型切换到本地部署的小模型，既可以节省 API 消费，又可以获得更稳定的延迟（本地无排队）。

**为何选择 Ollama 作为推理引擎**。Ollama 基于 llama.cpp 构建，是最简化的本地 LLM 部署方案——一行命令下载量化模型并启动 OpenAI 兼容的 HTTP API。它对 CPU 推理做了深度优化（Q4_K_M 量化格式、内存映射加载），对 macOS 和 Linux 均有良好支持。虽然 vLLM 在 GPU 高并发场景下吞吐量更高（连续批处理），但 ZRAG 是单用户、CPU 推理场景，Ollama 的简洁性远超 vLLM 的复杂性收益。且本地模型和其他云 API 模型均通过 LiteLLM Gateway 统一路由——Gateway 中新增 `ollama/qwen3.5:9b` 模型定义，指向 Ollama 的 `/v1` 端点，Backend 代码只需切换 `model` 参数即可在 API 模型和本地模型间切换。

**为何选择 Qwen3.5-9B**。模型选型过程中评估了多个方案。Qwen2.5-7B-Instruct（7B 参数）在中文指代消解和 JSON 输出约束上均有可靠表现，CPU Q4 推理约 4-7s，是 7B 级别的最优选择。Qwen3.5 系列跳过了 7B-8B 区间——Qwen3.5-4B（5B 参数）参数偏少，中文指代消解质量存疑；Qwen3.5-9B（10B 参数）参数偏多但指令跟随能力更强（IFEval 91.5 分，BFCL-V4 66.1 分显示可靠的 JSON 输出能力）。Qwen3.5-9B-Base 为纯基座模型，未经指令微调，无法直接用于对话——Base 模型会将系统 prompt 视为待续写的文本而非指令。最终选择 Qwen3.5-9B，权衡多出的 3-4s CPU 延迟换取更可靠的中文语义理解、指令跟随和 JSON 输出质量。模型 Q4_K_M 量化后约 6GB 磁盘，CPU 推理延迟约 7-11s/次。

**为何通过 LiteLLM Gateway 统一路由而非跳过 Gateway 直连 Ollama**。如果 QueryRewriter 和 ConversationSummarizer 直连 Ollama（`base_url=http://host.docker.internal:11434/v1`），则这些调用将游离于 LiteLLM Gateway 的监控、日志和告警体系之外，形成监控真空。所有 LLM 调用——无论本地还是云端——统一经 Gateway 路由，可获得统一维度的可观测性（调用量、延迟分布、失败率）。Gateway 中本地模型的 API base 指向 `http://host.docker.internal:11434`（Ollama 和 LiteLLM 不在同一 Docker compose 网络，通过宿主机端口通信）。

**Ollama 部署方式**。Ollama 与 LiteLLM 属于同一级别的独立基础设施——不入 ZRAG 的 `docker-compose.yml`，独立 Docker 容器部署（`docker run -d --name ollama -p 11434:11434 -v ollama_data:/root/.ollama -e OLLAMA_KEEP_ALIVE=24h --memory="10g" ollama/ollama:0.9.0`）。`OLLAMA_KEEP_ALIVE=24h` 使模型加载后在内存中保持 24 小时，避免每次请求冷启动重新加载 6GB 权重（耗时数十秒）。内存限制 10GB：模型 6GB + 推理时 KV cache 等额外开销。模型文件持久化在 Docker volume `ollama_data` 中，更换电脑时拷贝 volume 即可。

**BGE embedding 模型不受 Ollama 管理**。BGE 和 LLM 是两类完全不同的模型。BGE 属于 embedding 模型（encoder-only 架构），输入文字输出固定维度向量，由 `SentenceTransformer` 库加载。LLM 属于生成模型（decoder-only 架构），输入文字逐 token 输出新文字，由 Ollama/llama.cpp 加载。两者在架构、输入输出、推理库上完全不同，不存在"统一管理"的必要。BGE 继续通过 `SentenceTransformer` 在 `zrag/embed/local.py` 中进程内加载，保持零网络开销的毫秒级响应。

**配置文件更新**。在 `config/llm.yaml` 的 `gateway` 段下新增 `rewriter_model` 字段，指定本地模型名称。`base_url` 不变（统一指向 LiteLLM Gateway），仅 `model` 参数不同实现路由区分：

```yaml
llm:
  gateway:
    base_url: "${LLM_GATEWAY_URL:-http://localhost:4000/v1}"
    api_key: "${LITELLM_MASTER_KEY:-sk-dummy}"
    model: "smart-router"
    rewriter_model: "${REWRITER_LLM_MODEL:-ollama/qwen3.5:9b}"
```

同时 `config/retrieval.yaml` 中新增 `summary_max_chars: 200` 控制摘要最大长度。

**降级策略**。Ollama 容器不可用时（宕机、冷启动中），QueryRewriter 调用失败。此时 `retriever.py` 的 `hybrid_search()` 中 catch 异常，降级为使用原始 query 继续检索。回答请求不中断，仅检索质量可能因缺少改写而下降。运维层面依赖 LiteLLM Gateway 的监控告警发现本地模型异常。

## 8.1 统一响应格式

ZRAG 所有 API 响应均遵循统一的三字段格式（`Message + Data + RequestID`），由自定义 `APIResponse` 包装器强制执行。

### 设计决策：为何自定义 APIResponse 而非用 DRF 原生 Response

DRF 原生的 `Response` 类对响应体结构不做约束——开发者可以在 `data` 中放入任意结构的字典或列表。缺乏统一的响应外壳会导致前端需要针对不同端点编写不同的解析逻辑。自定义 `APIResponse` 强制每一笔响应都遵循三字段格式，构造方法自动读取 `RequestID` 确保 Trace ID 可追溯。

### 设计决策：为何用 Message 而非 message（大写 M）

字段名采用大写 `Message`，是参考 zonebank 项目的既有惯例。保持同一团队多个项目间的响应格式一致，降低前后端对接的心智成本。

```python
class APIResponse(Response):
    """自定义 DRF Response 包装器
    
    统一格式:
    {
        "Message": "success" | error_description,
        "Data": { ... } | None,
        "RequestID": "uuid"
    }
    
    自动从 request.META 读取 RequestID（优先 HTTP_X_REQUEST_ID，回退 X-Request-ID）。
    """
    def __init__(self, data=None, message="success", http_status=200, request=None):
        request_id = ""
        if request:
            request_id = request.META.get("HTTP_X_REQUEST_ID", "")
            if not request_id:
                request_id = request.META.get("X-Request-ID", "")
        body = {"Message": message, "Data": data, "RequestID": request_id}
        super().__init__(body, status=http_status)
```

> 注意：`RequestID` 来自 `RequestIDMiddleware` 中间件自动生成的 UUID，确保每个请求从入口到响应都有唯一标识。

成功响应示例：

```json
{
    "Message": "success",
    "Data": {
        "conversation_id": "...",
        "assistant_response": {
            "content": "装饰器是 Python 中...",
            "sources": [{"doc_title": "...", "score": 0.032}]
        }
    },
    "RequestID": "a1b2c3d4..."
}
```

错误响应额外包含 `ErrorCode`，由异常处理体系自动注入：

```json
{
    "Message": "AI 服务暂时不可用，请稍后重试",
    "Data": null,
    "RequestID": "a1b2c3d4...",
    "ErrorCode": "LLM-CALL-ERROR"
}
```

## 8.2 认证机制

### 设计决策：为何选择固定 API Key 而非 JWT/OAuth

| 方案 | 适用场景 | ZRAG 的实际情况 |
|------|---------|:---:|
| JWT | 多用户系统，需要区分角色和权限，Token 有过期刷新机制 | 单用户系统，无此需求 |
| OAuth 2.0 | 第三方授权、多客户端接入 | 无第三方集成场景 |
| 固定 API Key | 个人工具、内部服务、简单可信环境 | 完全匹配 |

ZRAG 是一个**个人单用户 RAG 知识库系统**——没有多用户登录、角色分级、权限细分的需求。引入 JWT 或 OAuth 只会增加实现复杂度，引入不必要的 Token 签发/刷新/撤销机制。

API Key 方案的实现极简：从 `Authorization: Bearer <key>` 请求头提取 Key，与 `settings.ZRAG_API_KEY` 做字符串比对。Key 通过环境变量注入（`ZRAG_API_KEY`），不在代码中硬编码，实现"配置即认证"。

```python
class APIKeyAuthentication(BaseAuthentication):
    """API Key 认证
    
    从 Authorization header 中提取 Bearer token 作为 API Key,
    与 settings.ZRAG_API_KEY 进行比对。
    Phase 1: Key 从配置或环境变量读取。
    """
    def authenticate(self, request):
        auth = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth.startswith("Bearer "):
            raise AuthenticationFailed("Missing or invalid Authorization header")
        api_key = auth[7:]
        if not self._validate_key(api_key):
            raise AuthenticationFailed("Invalid API key")
        return (None, None)

    def _validate_key(self, api_key):
        expected = getattr(settings, "ZRAG_API_KEY", None)
        if not expected:
            expected = os.environ.get("ZRAG_API_KEY", "")
        if not expected:
            raise ValueError(
                "配置缺失: api.key, 请检查 config/api.yaml 或设置 ZRAG_API_KEY 环境变量"
            )
        return api_key == expected
```

所有业务 API 端点均要求认证（健康检查端点除外）：
- `authentication_classes = [APIKeyAuthentication]`
- `return (None, None)` 表示认证通过，遵循 DRF 单用户系统约定

## 8.3 异常处理体系

异常处理采用 **Handler Registry** 模式（参考 zonebank 设计），整体流程如下：

```
异常抛出
    │
    ▼
api_exception_handler(exc, context)
    │
    ▼
遍历 error_type 注册表 (按优先级匹配)
    ├─ DRF AuthenticationFailed → DRFAuthenticationFailedHandler → 401 {ErrorCode: "UNAUTHORIZED"}
    ├─ UnauthorizedException → UnauthorizedHandler → 401 {ErrorCode: "UNAUTHORIZED"}
    ├─ DRF ParseError → DRFParseErrorHandler → 400 {ErrorCode: "PARSE-ERROR"}
    ├─ DRF ValidationError → DRFValidationErrorHandler → 400 {ErrorCode: "VALIDATION-ERROR"}
    ├─ NotFoundException → NotFoundHandler → 404 {ErrorCode: "NOT-FOUND"}
    ├─ RetrievalException → RetrievalHandler → 500 {ErrorCode: "RETRIEVAL-ERROR"}
    ├─ LLMCallException → LLMCallHandler → 502 {ErrorCode: "LLM-CALL-ERROR"}
    ├─ IngestionException → IngestionHandler → 500 {ErrorCode: "INGESTION-ERROR"}
    ├─ DRF APIException(其他子类) → DRFGenericAPIExceptionHandler → status_code 来自 exc
    └─ 其他未知异常 → DefaultErrorHandler → 500 {ErrorCode: "INTERNAL-ERROR"}
```

### 设计决策：为何采用 Handler Registry 模式而非 try-except 大分支

| 方案 | 新增异常类型时 | 代码结构 | 开闭原则 |
|------|:---:|------|:---:|
| `try-except` 大分支 | 需修改分发函数体，追加 `except` 子句 | 一个函数内嵌大量分支，可读性随异常种类增多而恶化 | 违反（对修改开放） |
| Handler Registry | 只需在注册表中追加一行映射 | 异常类型与处理器分离，分发逻辑保持不变 | 遵循（对扩展开放，对修改关闭） |

Handler Registry 的核心思想是将"异常类型 -> 处理器"的映射集中在一处声明式注册表中，分发函数 `api_exception_handler` 保持简洁：遍历注册表、匹配类型、调用处理器。新增异常类型完全不需要触碰分发逻辑。

### 设计决策：为何处理器实例预创建而非每次 new

异常处理发生在每个请求的关键路径上。如果在每次异常发生时都 `new` 一个 Handler 实例，会产生额外的对象创建和 GC 开销。由于 Handler 本身是无状态的（只依赖传入的 `exc` 和 `context`），可以在模块加载时预创建 `handler_instance` 并安全复用。

### 设计决策：为何 DRF 内置异常也需要注册

DRF 框架在处理请求时，会在序列化器校验失败时自动抛出 `ValidationError`，在 JSON 解析失败时抛出 `ParseError`，在认证失败时抛出 `AuthenticationFailed`。这些异常并非 ZRAG 自定义的 `BaseZragException` 子类——如果不为它们注册独立的 Handler，DRF 的默认异常处理会将它们转换为格式不统一的响应（仅有 `detail` 字段），破坏 `Message + Data + RequestID + ErrorCode` 的统一响应约定。

### 设计决策：为何 BaseZragException 设计 http_status + error_code 双字段

```python
class BaseZragException(Exception):
    def __init__(self, message="", status_code=500, http_status=None, error_code=""):
        super().__init__(message)
        if http_status is not None:
            status_code = http_status
        self.status_code = status_code   # HTTP 层使用
        self.error_code = error_code     # 业务层使用
```

两者职责不同：`status_code`（`http_status`）给 HTTP 框架层使用，设置 Response 的 HTTP 状态码；`error_code` 给前端业务层使用，前端根据 ErrorCode 做用户提示映射和错误类型判断。例如 `LLM-CALL-ERROR` 和 `UNAUTHORIZED` 在 HTTP 层可能状态码不同，前端通过 `error_code` 即可精确区分。

### 注册表结构

```python
error_type = [
    {
        "exception_class": AuthenticationFailed,
        "handler_class": DRFAuthenticationFailedHandler,
        "handler_instance": DRFAuthenticationFailedHandler(),
    },
    {
        "exception_class": UnauthorizedException,
        "handler_class": UnauthorizedHandler,
        "handler_instance": UnauthorizedHandler(),
    },
    {
        "exception_class": ParseError,
        "handler_class": DRFParseErrorHandler,
        "handler_instance": DRFParseErrorHandler(),
    },
    {
        "exception_class": ValidationError,
        "handler_class": DRFValidationErrorHandler,
        "handler_instance": DRFValidationErrorHandler(),
    },
    {
        "exception_class": NotFoundException,
        "handler_class": NotFoundHandler,
        "handler_instance": NotFoundHandler(),
    },
    {
        "exception_class": RetrievalException,
        "handler_class": RetrievalHandler,
        "handler_instance": RetrievalHandler(),
    },
    {
        "exception_class": LLMCallException,
        "handler_class": LLMCallHandler,
        "handler_instance": LLMCallHandler(),
    },
    {
        "exception_class": IngestionException,
        "handler_class": IngestionHandler,
        "handler_instance": IngestionHandler(),
    },
    {
        "exception_class": APIException,
        "handler_class": DRFGenericAPIExceptionHandler,
        "handler_instance": DRFGenericAPIExceptionHandler(),
    },
]
```

> 注意：注册表中越具体的异常类型越靠前。DRF 内置异常（`AuthenticationFailed`、`ParseError`、`ValidationError`）优先于自定义异常，确保框架自动抛出的异常先被匹配。

### 分发函数

```python
def api_exception_handler(exc, context):
    """遍历注册表，找到匹配的 Handler 处理异常"""
    for entry in error_type:
        if isinstance(exc, entry["exception_class"]):
            return entry["handler_instance"].handle(exc, context)
    return DefaultErrorHandler().handle(exc, context)
```

### 自定义异常类继承体系

```python
BaseZragException(Exception)           # 基类: status_code + error_code 双字段
  ├─ UnauthorizedException             (401, "UNAUTHORIZED")
  ├─ NotFoundException                 (404, "NOT-FOUND")
  ├─ RetrievalException                (500, "RETRIEVAL-ERROR")
  ├─ LLMCallException                  (502, "LLM-CALL-ERROR")
  └─ IngestionException                (500, "INGESTION-ERROR")
```

每个子类仅指定 `http_status` 和 `error_code` 的默认值，构造时仍可覆盖：

```python
class LLMCallException(BaseZragException):
    def __init__(self, message, error_code="LLM-CALL-ERROR"):
        super().__init__(http_status=502, message=message, error_code=error_code)
```

## 8.4 API 端点设计

### 设计决策：为何选择 ViewSet + re_path 而非 DRF Router

| 方案 | URL 生成 | HTTP method 映射 | 自定义路径格式 |
|------|:---:|:---:|:---:|
| DRF Router | 自动（`basename-list`、`basename-detail` 等） | 隐式（按 ViewSet 的 `list`/`create`/`retrieve` 约定） | 困难，受 Router 命名规则约束 |
| ViewSet + re_path | 手动显式声明 | 显式（`{'get': 'list', 'post': 'create'}` 一目了然） | 自由，完全控制正则表达式 |

选择 `re_path` 的核心原因是**显式优于隐式**。URL 模式、HTTP method、对应的实例方法三者之间的关系直接可见，无需查阅 DRF Router 的命名约定。同时自定义路径格式（如 `/v1/conversations/{id}/messages` 而非 Router 默认的嵌套格式）更加灵活。

### 设计决策：为何列表和创建共用一个 URL

`GET /v1/conversations` 获取会话列表，`POST /v1/conversations` 创建新会话——两者共用同一个 URL，仅靠 HTTP method 区分。这是 RESTful API 设计的标准惯例：URL 标识资源集合，GET 读取集合，POST 在集合中创建新成员。避免引入 `/conversations/create` 或 `/conversations/list` 等非 RESTful 路径。

### 设计决策：为何 ViewSet 支持依赖注入

```python
class ConversationViewSet(viewsets.ViewSet):
    store = None         # 可注入 mock SQLiteStore
    retriever = None     # 可注入 mock Retriever
    llm_provider = None  # 可注入 mock LLMProvider
```

类属性级别的依赖注入设计使得单元测试无需 monkey-patch 全局单例——测试代码只需在 ViewSet 实例上设置类属性即可注入 mock 对象。懒加载方法 `_get_store()` / `_get_retriever()` / `_get_llm()` 优先使用注入的实例，未注入时回退到模块级单例，兼顾测试便利性和生产简洁性。

### 路由代码

```python
# zrag/api/urls.py

conversation_urls = [
    re_path(r'^v1/conversations$',
        ConversationViewSet.as_view({'get': 'list', 'post': 'create'})),
    re_path(r'^v1/conversations/(?P<conversation_id>[^/]+)/messages$',
        ConversationViewSet.as_view({'get': 'get_messages', 'post': 'add_message'})),
    re_path(r'^v1/conversations/(?P<conversation_id>[^/]+)$',
        ConversationViewSet.as_view({'delete': 'destroy'})),
]

document_urls = [
    re_path(r'^v1/documents/ingest$',
        DocumentViewSet.as_view({'post': 'ingest'})),
]

source_urls = [
    re_path(r'^v1/sources$',
        DocumentViewSet.as_view({'get': 'list_sources'})),
]

health_urls = [
    re_path(r'^v1/health/live$', HealthViewSet.as_view({'get': 'live'})),
    re_path(r'^v1/health/ready$', HealthViewSet.as_view({'get': 'ready'})),
]
```

端点一览：

| 方法 | 路径 | 说明 | 限流 |
|------|------|------|------|
| GET | `/v1/conversations` | 会话列表（按最近消息倒序） | chat 60/min |
| POST | `/v1/conversations` | 创建会话 + RAG 问答 | chat 60/min |
| DELETE | `/v1/conversations/{id}` | 删除会话及其消息（幂等） | chat 60/min |
| GET | `/v1/conversations/{id}/messages` | 获取会话消息列表 | chat 60/min |
| POST | `/v1/conversations/{id}/messages` | 在已有会话中追加消息 + RAG | chat 60/min |
| GET | `/v1/sources` | 按来源类型统计文档数量 | — |
| POST | `/v1/documents/ingest` | 触发文档摄入（异步，返回 202 + task_id） | ingest 3/min |
| GET | `/v1/ingest/{id}/status` | 查询摄入任务状态和进度 | — |
| POST | `/v1/ingest/{id}/cancel` | 取消摄入任务 | — |
| GET | `/v1/sources/available` | 返回已注册的数据源类型 | — |
| GET | `/v1/health/live` | Liveness 探针 | — |
| GET | `/v1/health/ready` | Readiness 探针 | — |
| GET | `/v1/docs/` | Swagger UI（仅 DEBUG 模式） | — |
| GET | `/v1/schema/` | OpenAPI Schema（仅 DEBUG 模式） | — |

### ViewSet 依赖注入示例

```python
class ConversationViewSet(viewsets.ViewSet):
    authentication_classes = [APIKeyAuthentication]
    throttle_classes = [ChatRateThrottle]

    store = None         # 可注入 mock SQLiteStore
    retriever = None     # 可注入 mock Retriever
    llm_provider = None  # 可注入 mock LLMProvider

    def _get_store(self):
        if hasattr(self, 'store') and self.store is not None:
            return self.store
        return get_sqlite_store()

    def _get_retriever(self):
        if hasattr(self, 'retriever') and self.retriever is not None:
            return self.retriever
        # 懒加载: 构建真实 Retriever 实例
        from zrag.retrieval.retriever import Retriever
        self.retriever = Retriever(
            sqlite_store=self._get_store(),
            chroma_store=get_chroma_store(),
            embedder=get_embedder(),
        )
        return self.retriever

    def _get_llm(self):
        if hasattr(self, 'llm_provider') and self.llm_provider is not None:
            return self.llm_provider
        from zrag.llm.gateway import LLMGatewayProvider
        self.llm_provider = LLMGatewayProvider()
        return self.llm_provider
```

## 8.5 Swagger 文档

### 设计决策：为何选择 drf-spectacular 而非 drf-yasg

| 维度 | drf-yasg | drf-spectacular |
|------|:---:|:---:|
| 维护状态 | 已停止维护 | 活跃维护中 |
| DRF 版本支持 | 仅 DRF 2.x/3.x 早期 | DRF 3.x 全系列 |
| OpenAPI 版本 | OpenAPI 2.0（Swagger） | OpenAPI 3.0 |

`drf-yasg` 已进入存档状态，不再接收新功能和安全修复。`drf-spectacular` 是社区推荐的继任方案，对 DRF 3.x 有完整的 OpenAPI 3.0 支持。

### 设计决策：为何通过 @extend_schema 而非自动推断

DRF ViewSet 的自动 schema 推断依赖 Serializer 定义和 Model 元数据。ZRAG 的 ViewSet 继承自 `viewsets.ViewSet`（非 `ModelViewSet`），没有绑定 Model——DRF 的自动推断对此类自定义 ViewSet 效果很差，生成的文档通常缺失请求体和响应格式。通过 `@extend_schema` 显式声明每个端点的 `summary`、`description`、`request` 和 `responses`，文档可以做到精确完整。

```python
@extend_schema(
    summary="创建会话并执行 RAG 问答",
    description="创建新会话并执行首轮 RAG 问答。流程：1.校验 query 2.写入 conversations 3.hybrid_search 4.build_rag_prompt 5.LLM 调用 6.写入消息 7.返回结果",
    request=ConversationQuerySerializer,
    responses={
        201: OpenApiResponse(response=ss.CreateConversationResponseSerializer,
                              description="创建成功"),
        400: OpenApiResponse(response=ss.ErrorResponseSerializer,
                              description="参数校验失败"),
        401: OpenApiResponse(response=ss.ErrorResponseSerializer,
                              description="认证失败"),
        429: OpenApiResponse(response=ss.ErrorResponseSerializer,
                              description="请求过于频繁"),
        502: OpenApiResponse(response=ss.ErrorResponseSerializer,
                              description="LLM 调用失败"),
    },
)
def create(self, request):
    ...
```

文档访问控制：
- `DEBUG=True` 时自动开启文档路由
- `DEBUG=False` 时自动关闭（生产安全）

---

# 9. 前端设计

前端是用户与 ZRAG 交互的主要入口，提供聊天问答和知识源管理两个核心页面。技术栈选用 Vue 3 + Vite + Tailwind CSS，遵循纯静态资源部署、无额外状态管理库依赖的原则，与后端通过 REST API 完全解耦。

本章从组件架构开始，逐层深入到数据流、状态管理和错误处理机制，说明每个设计决策所对应的具体问题和考量。

## 9.1 组件架构

前端采用 Vue 3 + Vite + Tailwind CSS 技术栈，组件树如下：

```
App.vue
├── ChatSidebar.vue          # 左侧会话列表导航
│   ├── 会话列表项 (按最近消息排序)
│   ├── 新建对话按钮
│   └── 删除会话操作
│
├── ChatView.vue             # 主聊天视图
│   ├── 空状态提示 ("向你的知识库提问")
│   ├── ChatMessage.vue      # 消息气泡 (多条)
│   │   ├── 用户消息: 右对齐, 蓝色背景
│   │   ├── AI 回复: 左对齐, Markdown 渲染, 来源标注
│   │   │   └── useMarkdown.js (marked.js + highlight.js)
│   │   └── 错误消息: 红色气泡 + ⚠️ 图标 + Trace ID
│   ├── 加载动画 (三个跳动圆点)
│   └── ChatInput.vue        # 底部输入区
│       ├── 自动扩展 textarea (最大 6 行)
│       ├── Enter 发送 / Shift+Enter 换行
│       └── 发送按钮
│
├── SourcesView.vue          # 知识源管理页 (/sources)
│   ├── 来源统计列表
│   ├── 增量导入 / 全量导入按钮
│   └── 进度指示条
│
└── router/index.js          # Vue Router (History 模式)
    ├── / → ChatView
    └── /sources → SourcesView
```

### 设计理念

**为何选择 Vue 3 Composition API + Composable 而非 Vuex/Pinia**。ZRAG 是一个个人使用规模的 RAG 知识库工具，前端状态管理的需求并不复杂——核心状态仅涉及会话列表（`conversations`）、当前会话的消息列表（`messages`）、发送中状态（`sending`）和加载状态（`conversationsLoading`、`messagesLoading`）四个维度的响应式数据。引入 Vuex 或 Pinia 这类集中式状态管理库，会增加额外的依赖体积（Pinia 约 10KB gzipped）、学习成本（Store 定义、Actions/Getters 模式、模块命名空间）以及项目启动时的样板代码量。Vue 3 内置的 `reactive` / `ref` + Composable 模式提供了同等的状态封装能力：通过一个 `useChat()` 函数将相关状态和操作封装为可复用的复合体，调用方只需解构获取所需属性和方法。这种模式更轻量——零额外依赖，代码即文档（一个文件包含该业务域的全部状态逻辑），且与 Vue 3 的 Composition API 天然契合。从个人项目的长期维护角度看，一个约 200 行的 `useChat.js` 文件比一个带有 Store 定义、Actions、Getters 的 Pinia 模块更容易理解和修改。

**为何前端与后端完全分离（独立 nginx 容器）**。在部署架构中，ZRAG 前端和后端各自独立构建、独立打包为容器镜像，通过独立的 nginx 容器（znginx）在外层做反向代理。前端容器内使用 `nginx:alpine` 镜像提供编译后的 Vue 静态资源（HTML + JS + CSS），并开启 gzip 压缩减少传输体积。后端容器内运行 uWSGI + Django，只处理 API 请求（`/zrag/*` 路径）。这种分离带来的关键收益是故障隔离和独立部署：前端容器的重启（如更新 UI 样式、修复前端 bug）不影响正在进行的后端 LLM 调用和数据库查询；同理，后端容器的重建（如更新检索逻辑、切换 Embedding 模型）不会导致前端静态资源的重新构建。前端 nginx 可以通过独立的健康检查和重启策略管理，不依赖后端服务的状态。此外，前端纯静态资源的特性意味着未来可以将前端部署到 CDN，而后端继续在本地运行——这在前后端耦合的部署方案中是难以实现的。

> 注意：当前阶段 znginx 已从 docker-compose 中移除，作为宿主机上的独立容器运行，同时代理多个项目的流量。ZRAG 的前端和后端容器仅 expose 内部端口，不对外映射。详见 [1.3 节](#13-系统架构全景) 中关于 znginx 独立部署的设计考量。

**为何 ChatMessage 用 computed 判断 role 而非不同组件**。在聊天界面中，消息有三种角色：`user`（用户输入）、`assistant`（AI 回复）和 `error`（错误信息）。三种角色的差异主要在于视觉样式（用户消息蓝色右对齐，AI 回复白色/深灰左对齐，错误消息红色左对齐）和部分交互行为（只有 assistant 消息显示来源标注，错误消息不显示复制按钮和时间戳）。它们在结构上共享相同的模板骨架——都是一个消息气泡容器，内部包含内容区和底部栏。如果为每种角色创建独立组件（`UserMessage.vue`、`AssistantMessage.vue`、`ErrorMessage.vue`），会导致三个组件中存在大量重复的模板结构、复制逻辑和时间戳格式化代码，修改一个通用行为需要同步修改三个文件，维护负担随组件数量线性增长。通过一个 `ChatMessage.vue` 组件，利用 `computed` 属性根据 `message.role` 动态返回对应的 CSS class（`bubbleClass`），可以在模板中统一处理通用结构（时间戳、复制按钮、Markdown 渲染），仅通过 `v-if="isUser"`、`v-if="isError"` 等条件渲染处理角色差异部分。这种设计将"同"与"异"的边界精确地画在了模板的条件判断上，而非组件文件的数量上。

聊天消息角色的 CSS class 映射实现：

```javascript
// ChatMessage.vue — computed 动态返回气泡样式
const isUser = computed(() => props.message.role === 'user')
const isError = computed(() => props.message.role === 'error')

const bubbleClass = computed(() => {
  if (isUser.value) {
    return 'bg-blue-600 text-white rounded-br-sm'
  }
  if (isError.value) {
    return 'bg-red-50 text-red-800 dark:bg-red-900/30 dark:text-red-300 border border-red-200 dark:border-red-800 rounded-bl-sm'
  }
  return 'bg-gray-100 text-gray-900 dark:bg-gray-800 dark:text-gray-100 rounded-bl-sm'
})
```

## 9.2 数据流与状态管理

前端通过 Composable 模式管理状态，不引入 Vuex/Pinia。

API 调用通过 `frontend/src/api/` 模块分层封装：

```
api/index.js              # 底层: fetch 封装 + 统一错误处理 + AbortController 超时
api/endpoints.js          # 中层: 按业务端点封装的具名函数
composables/useChat.js    # 上层: 业务逻辑 + 状态管理
```

`api/index.js` 提供 `apiGet` / `apiPost` / `apiDelete` 三个具名方法，内部统一注入 `Content-Type: application/json` 请求头和 Bearer 鉴权（`VITE_API_KEY` 环境变量构建时注入）。所有响应从约定的 `{ Data, Message, ErrorCode }` 包装中提取 `Data` 字段返回，非 2xx 响应统一抛出 `ApiError`。`api/endpoints.js` 在此之上封装了 `listConversations`、`createConversation`、`getMessages`、`addMessage`、`deleteConversation`、`getSources`、`triggerIngestion` 等业务端点函数。`useChat.js` 是最上层的业务逻辑 composable，组合了端点调用、乐观更新、错误回滚和状态同步。

### 设计理念

**为何 sendMessage 采用乐观更新（先追加临时消息）**。聊天应用的核心体验之一是"即时反馈"——用户按下发送键后，应立刻在聊天区看到自己的消息，而不需要等待后端处理完成。如果等整个 RAG 流程（检索 + LLM 调用，耗时通常在 2~20 秒，复杂 Query 可能超过 30 秒）全部完成后才在聊天区显示用户消息，用户在这段等待时间中会看到输入框下方的空白区域没有任何变化，产生"消息是否发送成功"的疑惑。乐观更新解决了这个问题：在 `sendMessage()` 方法中，先将一条带有临时 ID（`temp-user-{Date.now()}`）的用户消息追加到 `messages` 数组，渲染层立即显示这条消息气泡，用户获得即时的视觉确认。随后在后台发起 API 调用，成功后通过 `loadMessages()` 从后端拉取完整消息列表（包含带有真实 ID 和 assistant 回复的完整数据）替换本地消息列表，临时消息被后端返回的真实消息自然覆盖。如果调用失败，临时消息保留在聊天区（见下一个设计点），避免用户输入丢失。

这种模式在个人聊天应用中尤其关键——不同于后台管理系统的表单提交，聊天是高频、连续的操作流，任何感知到的"卡顿"都会破坏对话的流畅性。

**为何失败时保留用户消息 + 追加错误气泡，而非移除用户输入**。在 `sendMessage()` 的 `catch` 分支中，如果 API 调用失败，系统不会移除已经追加的临时用户消息，而是在消息列表末尾追加一条 `role: 'error'` 的红色错误气泡。这个设计基于两个考量。第一，用户已经输入了内容并期望它被发送成功——如果因为网络波动或后端暂时不可用就移除用户的消息，用户需要重新输入相同的文本，这在体验上是令人沮丧的（尤其是长文本输入场景）。第二，保留用户消息让用户在回溯聊天记录时能看到"我发了什么"——结合错误气泡中的 Trace ID，用户可以向开发者准确报告"我在某条消息后收到了这个错误"。相比之下，如果移除用户输入并仅弹出一个 Toast 通知，用户可能已经忘记了刚才输入的确切内容，无法提供完整的错误报告上下文。

```javascript
// useChat.js — 聊天业务逻辑的核心 composable
export function useChat() {
  const conversations = ref([])         // 会话列表
  const activeConversationId = ref(null) // 当前激活的会话 ID
  const messages = ref([])              // 当前会话的消息列表
  const sending = ref(false)            // 发送中状态

  async function sendMessage(query) {
    // 1. 乐观追加临时用户消息
    messages.value = [...messages.value, tempUserMsg]
    sending.value = true
    
    try {
      if (activeConversationId.value) {
        // 已有会话 → append
        await addMessage(activeConversationId.value, text)
      } else {
        // 新会话 → create
        const conv = await createConversation(text)
        activeConversationId.value = conv.conversation_id
      }
      await loadMessages(activeConversationId.value)
      await loadConversations()  // 刷新侧边栏排序
    } catch (e) {
      // 保留用户消息 + 追加错误气泡（不移除用户的输入）
      messages.value = [...messages.value, errorMsg]
    } finally {
      sending.value = false
    }
  }
}
```

## 9.3 错误处理双层反馈

前端对所有非正常 HTTP 响应提供两层反馈机制：

1. **Toast 通知**（右上角，5 秒消失）：简短错误描述，适用所有页面的 API 调用失败
2. **内联错误气泡**（聊天区，永久显示）：红色气泡 + ⚠️ 图标 + 详细错误 + Trace ID，仅在对话场景

### 设计理念

**为何需要两层反馈而非仅 Toast**。仅依赖 Toast 通知存在一个固有的体验缺陷：Toast 是短暂的——它会在几秒后自动消失。用户可能在 Toast 弹出时正好看向别处，或者离开页面后回来发现已经错过了 Toast 通知。如果没有其他形式的错误记录，用户回到聊天界面后会看到自己的消息已发送（乐观更新的临时消息），但看不到任何 AI 回复，也不清楚发生了什么——这种"半截对话"状态对用户来说是一种困惑。内联错误气泡作为聊天记录的一部分永久保留在消息列表中，用户可以在任何时候回溯查看：什么时候发的消息？因为什么原因失败了？错误 ID 是什么？即使关闭浏览器后重新打开，错误消息气泡仍然存在于聊天记录中（因为后端已持久化了 user message）。两种机制形成互补：Toast 提供即时的注意力吸引（"刚才的操作出错了"），内联气泡提供持久的错误记录（"这个错误的具体原因和 Trace ID"）。

**为何错误消息末尾追加 Trace ID**。错误消息映射（`getUserMessage()`）在返回用户可读的错误描述后，检查 `ApiError` 对象中是否携带 `requestId` 字段（来源于 HTTP 响应头 `X-Request-ID` 或响应体中的 `RequestID` 字段）。如果存在，在错误描述末尾追加 `(错误ID: a1b2c3d4)`。这个设计的出发点很朴素：用户向开发者报告 bug 时，需要一种简单高效的方式来定位后端日志。用户不需要理解 Trace ID 是什么——只需截图或复制错误气泡中的完整文本发给开发者，开发者用其中的 Trace ID 即可在 nginx access.log、Django info.log/error.log 中快速串联起该请求的完整调用链路（检索参数、LLM 请求和响应、异常堆栈）。相比让用户描述"我大概在 3 分钟前发了一条关于 Python 装饰器的问题然后报错了"然后开发者去日志中大海捞针，一个精确的 Trace ID 将问题定位时间从分钟级缩短到秒级。

> Tips: Trace ID 在整个请求链路中的传递机制详见 [第 10 章](#10-trace-id-全链路追踪)。

**为何用 AbortController 而非 axios timeout**。在实现 HTTP 请求超时控制时，有两种常见方案：引入 axios 库并使用其内置的 `timeout` 配置项，或使用浏览器原生 `fetch` + `AbortController`。ZRAG 选择后者，原因有两个层面。第一，减少依赖。引入 axios 会增加前端打包体积（axios 约 13KB gzipped），而 ZRAG 的 API 调用需求并不复杂——不需要 axios 的拦截器链、请求取消令牌、自动 JSON 解析等高级特性。`fetch` 是浏览器原生 API，零依赖，配合 `AbortController`（同样是浏览器标准 API）即可实现完整的超时控制。第二，`AbortController` 的能力范围更广。它不仅可以用于超时控制，还可以在组件卸载时取消进行中的请求（避免 `setState on unmounted component` 类问题）、在用户快速切换会话时取消前一个会话的消息加载请求、在用户输入新消息时取消仍在进行中的上一次请求。axios 的 CancelToken 虽然也能实现类似功能，但 API 设计较为复杂（需要创建 token source，手动调用 `cancel()`），而 `AbortController` 的 `signal.abort()` 调用方式更简洁直观。

错误消息映射（`getUserMessage()`）：

```javascript
const codeMap = {
  'UNAUTHORIZED':    '认证失败，请刷新页面重试',
  'NOT-FOUND':       '请求的资源不存在',
  'LLM-CALL-ERROR':  'AI 服务暂时不可用，请稍后重试',
  'RETRIEVAL-ERROR': '知识库检索异常，请稍后重试',
  'INGESTION-ERROR': '文档摄入失败，请稍后重试',
  'INTERNAL-ERROR':  '服务器内部错误，请稍后重试',
  'PARSE-ERROR':     '请求格式错误',
  'VALIDATION-ERROR':'请求参数有误',
  'API-ERROR':       '服务异常，请稍后重试',
  'TIMEOUT':         '请求超时，请稍后重试',
  'NETWORK-ERROR':   '网络连接失败，请检查网络',
}
// 错误消息末尾自动追加 Trace ID
// 示例: "AI 服务暂时不可用，请稍后重试 (错误ID: a1b2c3d4)"
```

60 秒超时机制通过 AbortController 实现：

```javascript
const controller = new AbortController()
const timeoutId = setTimeout(() => controller.abort(), 60000)
options.signal = controller.signal
```

---

# 10. Trace ID 全链路追踪

Trace ID 从请求入口到响应出口贯穿整个调用链，实现全链路日志关联。

### 为何由 znginx 生成 Trace ID 而非 Django

在全链路追踪的设计中，Trace ID 的生成位置决定了追踪覆盖的范围。如果 Trace ID 由 Django（RequestIDMiddleware）生成，追踪的起点是请求到达 Django 应用层的时刻——这意味着 nginx 层的反向代理耗时、TLS 握手耗时、请求排队等待 uWSGI worker 的时间都处于追踪范围之外。当排查一个"用户反映请求慢"的问题时，这些缺失的时间窗口恰恰可能是瓶颈所在：nginx 到 backend 的网络延迟、uWSGI worker 池耗尽导致的排队等待——这些信息只有在 Trace ID 覆盖 nginx 层的前提下才能串联起来。

znginx 作为整个项目的请求入口（Browser 直接连接 nginx），在 nginx 层使用 `$request_id` 变量生成 Trace ID 并将它通过 `X-Request-ID` 请求头透传给下游（Backend、Frontend），可以覆盖从请求进入 nginx 到响应离开 nginx 的完整生命周期。znginx 的 access.log 记录请求的完整耗时（`$request_time`），Django 的 info.log 记录业务逻辑各节点的耗时，两者通过同一个 Trace ID 关联后，可以精确区分"是 nginx 到 backend 的网络慢"还是"是 backend 内部 RAG 处理慢"。

> 注意：`$request_id` 是 nginx 1.11.0+ 内置变量，值为一个 16 字节的随机十六进制字符串（如 `a1b2c3d4e5f6a7b8a1b2c3d4e5f6a7b8`）。与 UUID 格式不同，但不影响追踪的唯一性——在个人项目的请求量级下，碰撞概率可以忽略不计。

### 为何 RequestIDMiddleware 既读取上游 X-Request-ID 又可自动生成

生产环境中，znginx 已在请求头中注入了 `X-Request-ID`，Django 侧的中间件只需读取并沿用即可——这是"透传"模式。但在开发环境中，用户可能通过 Django 的 `runserver` 直接访问后端（没有 nginx 前置），此时请求头中不存在 `X-Request-ID`——如果中间件不做兜底，Trace ID 就会缺失，导致开发阶段的日志无法关联。

因此 RequestIDMiddleware 采用"优先透传、兜底生成"的策略：先从 `request.META` 中读取 `HTTP_X_REQUEST_ID`（Django 将 HTTP 请求头的 `X-Request-ID` 规范化为该键名），若存在则沿用以保持与上游 nginx 的一致性；若不存在则使用 `uuid.uuid4()` 自动生成。这种设计使同一份中间件代码同时兼容生产环境（透传 nginx 生成的 Trace ID）和开发环境（自行生成 Trace ID），避免了为不同环境维护两套中间件逻辑。

### 为何两端都设置 request_id

中间件在 request.META 和 response header 两个位置都设置了 request_id，两者面向不同的消费者：

- **request.META** 中的 `X-Request-ID` 供 Django 内部代码读取。APIResponse 在构造响应体时从 `request.META["X-Request-ID"]` 中取值，写入 `RequestID` 字段；logger 在记录业务日志时从同一位置取值，拼接 `[req=xxx]` 前缀。request.META 是 Django 内部的标准数据通道，贯穿整个请求处理过程。

- **Response Header** 中的 `X-Request-ID` 供前端读取。当 API 调用失败时，前端可以从响应头中提取 Trace ID，在错误气泡中展示（如"请求失败，Trace ID: a1b2c3d4..."），用户可将这个 Trace ID 反馈给排查人员，快速在日志中定位对应请求的完整处理过程。响应头中的 Trace ID 是响应体 `RequestID` 字段的冗余备份——在某些错误场景中（如请求在到达 ViewSet 之前就被中间件拦截，响应体中没有 `RequestID` 字段），响应头仍然会携带 Trace ID，前端始终能拿到追踪标识。

```
znginx (生成 $request_id)
  │
  ├─→ X-Request-ID header
  │
  ▼
uWSGI → Django RequestIDMiddleware
  │
  ├─→ request.META["X-Request-ID"]  ← 内部代码读取 (APIResponse、logger)
  │
  ├─→ APIResponse 响应体 RequestID 字段  ← 前端展示
  ├─→ Response Header X-Request-ID     ← 前端提取 (错误处理)
  │
  └─→ Django logger: [req=xxx] 前缀
        例: [req=a1b2c3d4] 检索完成 results_count=5
```

各层日志中的 Trace ID 关联：

| 层级 | 日志位置 | Trace ID 字段 |
|------|----------|-------------|
| znginx | access.log | `$request_id` (日志行末尾) |
| uWSGI | uwsgi-req.log | 请求行 (含时间、状态) |
| Django | info.log / error.log | `[req=xxx]` 日志前缀 |
| API 响应 | Response Body | `RequestID` 字段 |
| API 响应 | Response Header | `X-Request-ID` |

RequestIDMiddleware 实现：

```python
class RequestIDMiddleware:
    """为每个请求自动生成/透传 X-Request-ID

    生产环境: 透传 znginx 注入的 X-Request-ID (HTTP_X_REQUEST_ID)
    开发环境: 自动生成 UUID 作为兜底

    两点注入:
    - request.META["X-Request-ID"]: 供 Django 内部代码读取 (APIResponse、logger)
    - response["X-Request-ID"]: 供前端提取 (错误处理时展示 Trace ID)
    """
    def __call__(self, request):
        request_id = request.META.get("HTTP_X_REQUEST_ID") or str(uuid.uuid4())
        request.META["X-Request-ID"] = request_id
        response = self.get_response(request)
        response["X-Request-ID"] = request_id
        return response
```

---

# 11. 配置管理

配置采用多文件 YAML + 环境变量覆盖的三阶段加载机制：

```
阶段 1: YAML 文件扫描合并
  config/*.yaml → 按 top-level key 深度合并
  (llm.yaml + embedding.yaml + ingest.yaml + api.yaml + storage.yaml + retrieval.yaml)

阶段 2: ${VAR:-default} 占位符替换
  递归替换配置值中的环境变量占位符
  例: ${LITELLM_MASTER_KEY} → 实际环境变量值

阶段 3: 同名 UPPER_SNAKE 环境变量覆盖
  环境变量优先级 > YAML 配置
  例: LLM_TIMEOUT=300 覆盖 llm.timeout
  扁平化规则: llm.gateway.base_url → LLM_GATEWAY_BASE_URL
```

### 为何多文件 YAML 而非单文件

在项目初期，将所有配置项集中在一个 YAML 文件中（如 `config.yaml`）看起来很直观——打开一个文件就能看到全部配置。但随着配置项数量增长，单一文件的维护成本会快速上升。ZRAG 的配置项分布在六个功能域中：LLM 相关配置（gateway 地址、模型名、API Key、超时）、Embedding 相关配置（模型名、缓存路径）、摄入相关配置（批次大小）、API 相关配置（API Key、限速阈值）、存储相关配置（数据库路径）、检索相关配置（top-k）。如果这些配置项全部拥挤在同一个文件中，修改 LLM 模型的超时时间时需要在文件中定位到 LLM 段——而映入眼帘的还有 embedding 模型路径、数据库文件路径等与当前操作无关的配置，增加了误修改的风险。

按模块拆分为独立文件后，每个文件的配置项数量控制在 3~5 个，修改 LLM 配置时只需编辑 `config/llm.yaml`，文件内容简洁，修改目标明确，误操作概率低。此外，多文件模式也为未来可能的配置版本控制带来了便利——如果需要在不同部署环境（本地开发、容器生产）中只覆盖部分配置模块，可以只替换对应的配置文件而不影响其他模块。

### 为何环境变量优先级高于 YAML

YAML 配置文件作为代码的一部分打包在容器镜像中（通过 `COPY config/ ./config/` 指令）。如果需要在容器化部署中修改某个配置项（如将 LLM 超时从 200 改为 300），修改 YAML 文件需要重新构建镜像并重启容器——这是一个"代码变更"级别的流程。环境变量通过 `docker-compose.yml` 的 `environment` 字段或 `.env` 文件注入，修改后只需执行 `docker compose restart` 即可生效——这是一个"配置调整"级别的操作，不需要重新构建镜像。

在这个设计框架下，YAML 配置文件承担"默认值"的角色——提供合理的出厂配置，使得项目在本地开发环境中可以直接运行，无需设置任何环境变量。环境变量承担"部署时覆盖"的角色——容器部署时，运维人员通过环境变量按需覆盖默认值，无需触碰镜像内部的文件。YAML 提供稳定性（默认值在版本控制中追踪，不会因人为遗忘环境变量设置而导致配置缺失），环境变量提供灵活性（切换模型、调整超时、修改 API Key 都不需要重新构建镜像）。

### 为何三阶段加载而非一次性

直觉上，配置加载可以设计为一步完成——读取 YAML 的同时解析 `${VAR}` 并检查环境变量覆盖。但这种一次性方案会将三个语义不同的操作混在一起，导致问题排查的难度增加。当配置值不符合预期时，需要同时排查三个可能的问题来源：YAML 文件本身写错了？`${VAR}` 替换时环境变量未设置或默认值不对？环境变量覆盖时键名拼写错误导致未覆盖？

三阶段加载将每个阶段的职责明确隔离：

- **阶段 1（YAML 合并）** 只负责从文件系统中读取结构化配置，不涉及环境变量。如果配置结构异常（YAML 解析失败），问题一定在配置文件中。
- **阶段 2（`${VAR:-default}` 替换）** 让 YAML 文件自身具备引用环境变量的能力。例如 `cache_dir: "${MODELS_DIR:-/app/models}"` 允许在不同部署环境中通过设置 `MODELS_DIR` 环境变量来改变模型缓存路径，同时保留了 `/app/models` 作为默认值——不需要在代码中硬编码 fallback 逻辑。
- **阶段 3（env override）** 让 docker-compose 可以覆盖配置树中的任意叶子节点。环境变量覆盖发生在 `${VAR:-default}` 替换之后，因此 env override 可以覆盖占位符解析后的结果。例如 YAML 中写 `${LLM_TIMEOUT:-200}`，阶段 2 解析为 `200`；阶段 3 中如果存在环境变量 `LLM_TIMEOUT=300`，则最终值为 `300`。

三个阶段流水线处理，每个阶段的输入和输出是明确的，排查配置问题时可以逐步缩小范围：先确认 YAML 合并结果是否符合预期（阶段 1），再确认 `${VAR}` 替换是否正确（阶段 2），最后确认 env override 是否按预期覆盖（阶段 3）。

配置模块划分：

| 配置文件 | 关键配置项 |
|----------|-----------|
| `llm.yaml` | gateway base_url, model, api_key; timeout |
| `embedding.yaml` | model_name, cache_dir |
| `ingest.yaml` | batch_size |
| `api.yaml` | key, throttle_rates (chat, ingest) |
| `storage.yaml` | sqlite_path, chroma_path |
| `retrieval.yaml` | top_k |

Django 配置加载：

```python
_config = load_config("config")
ZRAG_API_KEY = _config.get("api", {}).get("key", "")
ZRAG_LLM = _config.get("llm", {})
ZRAG_EMBEDDING = _config.get("embedding", {})
ZRAG_STORAGE = _config.get("storage", {})
ZRAG_INGEST = _config.get("ingest", {})
ZRAG_RETRIEVAL = _config.get("retrieval", {})
```

---

# 12. 日志体系

日志采用级别分流策略，使用自定义 `ExactLevelFilter` 将不同级别的日志写入独立文件。

### 为何级别分流（ExactLevelFilter）而非所有日志写一个文件

Python logging 模块的默认行为是：handler 设置的 `level` 是**包容性**的——`level=INFO` 的 handler 不仅接收 INFO 级别的日志，还会接收 WARNING、ERROR 和 CRITICAL 级别的日志。这意味着如果只使用一个 handler 将所有日志写入同一个文件，不同级别的日志会混杂在一起。

在实际排查问题时，查找路径是按级别展开的：排查一个已知的错误时，只需要看 `error.log`——这里面的每一条日志都是需要关注的异常；分析业务流程是否正常完成时，只需要看 `info.log`——这里面的业务节点日志清晰地展示了请求的处理步骤和耗时；需要查看某个模块的初始化细节时，才去看 `debug.log`——这里包含 SQL 查询、ChromaDB 内部状态等详细输出。如果所有级别混写在一个文件中，排查一个错误需要从大量 INFO 和 DEBUG 日志中过滤出 ERROR 记录，引入不必要的噪音。

级别分流的核心机制是自定义的 `ExactLevelFilter`——一个 `logging.Filter` 子类，在 `filter(record)` 方法中只放行 `record.levelno` 精确等于目标级别的记录。通过为每个 file handler 配置对应级别的 `ExactLevelFilter`，实现了"每个文件只存储单一级别的日志"。

### 为何用 TimedRotatingFileHandler 按天轮转

日志文件的大小随时间增长。如果不对日志文件做轮转，长时间运行后单个日志文件可能膨胀到数百 MB——在排查问题时，打开大文件本身就是负担。

日志轮转有两种主流策略：按文件大小轮转（`RotatingFileHandler`，超过 N MB 后切新文件）和按时间轮转（`TimedRotatingFileHandler`，每天/每小时切新文件）。按大小轮转的问题在于文件名与时间没有对应关系——"昨天的错误日志"可能已经因为文件大小超标而被切到了 `error.log.3` 中，而 `error.log.1` 和 `error.log.2` 的分界线对应哪段时间需要自行推断。按天轮转使文件名天然包含时间信息——`error.log` 是今天的，`error.log.2026-06-08` 是昨天的——排查"昨天的错误"时直接打开对应日期的文件即可。

对于个人项目（单用户、请求量低），按天轮转更合适：每天的日志量远低于按大小轮转的阈值（如 10MB），如果使用按大小轮转，可能需要几个月才触发一次切分，失去了轮转的意义。按天轮转保证了每天一个独立文件，配合 `backupCount=7` 自动清理 7 天前的日志——日志总量可控，历史定位方便。

### 为何记录完成时间而非开始时间

业务节点日志的设计遵循"只记录完成"的原则：在每个关键操作完成后记录一条 INFO 日志，包含操作名称、相关标识（如 `conversation_id`）和结果摘要（如 `results_count`、`reply_len`）。日志中不记录操作的开始时间和耗时。

这种设计的逻辑是：当前操作的完成时间戳就是下一个操作开始时间戳的近似值——两次相邻完成日志的时间差就是上一个操作的耗时。例如：

```
2026-06-09 10:30:01.234 [req=xxx] 检索完成 results_count=5
2026-06-09 10:30:04.567 [req=xxx] LLM 调用完成 reply_len=342
```

检索耗时 = 检索完成时间 - 请求到达时间（可从 uwsgi-req.log 获取），LLM 调用耗时 = LLM 调用完成时间 - 检索完成时间 = 10:30:04.567 - 10:30:01.234 = 3.333 秒。不需要额外的耗时日志来记录这 3.333 秒——两次完成日志的时间差已经精确提供了这个信息。

如果记录开始时间（如"LLM 调用开始"），日志量翻倍（每个操作需要"开始"和"完成"两条日志），但实际获得的信息增量很小——耗时仍然需要用"完成 - 开始"来计算。只记录完成时间使日志更加简洁，关键信息（哪个操作完成了、在什么时候完成的、结果如何）不丢失。

### 为何使用 [req=xxx] 前缀而非结构化 JSON 日志

全链路追踪要求各层日志能够通过 Trace ID 关联。实现这一关联有两种方式：在每条日志的文本中加入 `[req=xxx]` 前缀，或输出结构化 JSON 格式的日志（每行一个 JSON 对象，包含 `request_id` 字段）。

结构化 JSON 日志（如使用 `python-json-logger` 库输出 `{"timestamp": "...", "level": "INFO", "request_id": "xxx", "message": "..."}` ）的优点是机器可解析、便于接入 ELK（Elasticsearch + Logstash + Kibana）等日志收集分析系统。但 ZRAG 作为个人项目，没有 ELK 集群，也没有日志聚合和分析的需求。排查问题时唯一需要的操作是：根据 Trace ID 在日志文件中 grep 搜索，查看该请求的全部日志记录。

在这种场景下，`[req=xxx]` 前缀的文本格式日志更加直观——grep `req=a1b2c3d4` 即可在一个文件中找出该请求的所有记录，grep 结果直接可读，不需要额外的 JSON 解析步骤。同时，结构化 JSON 格式会显著增加日志文件的体积（每条日志携带重复的 `"timestamp"`、`"level"`、`"logger"` 等字段名），在个人场景下这种冗余是不必要的。因此 ZRAG 选择文本格式日志 + `[req=xxx]` 前缀，保持轻量和可读性。

```python
LOGGING = {
    'formatters': {
        'verbose': {
            'format': '%(asctime)s [%(levelname)s] %(thread)d '
                      '%(funcName)s:%(lineno)d %(message)s',
        },
    },
    'handlers': {
        'console': { ... },           # stdout/stderr (Docker 日志驱动)
        'file_debug': {               # debug.log, 按天轮转, 保留 7 天
            'class': 'TimedRotatingFileHandler',
            'filename': 'log/debug.log',
            'filters': ['level_debug'],
        },
        'file_info': { ... },         # info.log
        'file_warning': { ... },      # warning.log
        'file_error': { ... },        # error.log
    },
}
```

日志文件分布：

| 文件 | 级别 | 内容 |
|------|------|------|
| `debug.log` | DEBUG | SQL 查询、模块初始化详情 |
| `info.log` | INFO | 业务节点完成日志（含 `[req=xxx]` 前缀） |
| `warning.log` | WARNING | 可恢复异常 |
| `error.log` | ERROR | 需关注的错误（含异常栈） |
| `uwsgi.log` | — | uWSGI 进程日志 |
| `uwsgi-req.log` | — | uWSGI HTTP 请求日志 |

业务节点日志遵循"只记录完成时间"的原则，在每个关键操作节点完成时记录：

```python
logger.info("[req=%s] 检索完成 conversation_id=%s results_count=%d", ...)
logger.info("[req=%s] LLM 调用完成 conversation_id=%s reply_len=%d", ...)
logger.info("[req=%s] 消息已保存 conversation_id=%s", ...)
```

通过相邻日志的时间戳差值即可计算各节点的实际耗时，无需额外的耗时日志。

---

# 13. 扩展点

ZRAG 通过抽象基类（ABC）+ 注册表（Registry）模式，在核心模块预留了清晰的扩展点。

### ABC + Registry 扩展模式的通用设计原理

ABC（Abstract Base Class）定义接口契约——声明需要实现哪些方法以及这些方法的输入输出。Registry（注册表，一个 Python dict）建立类型标识符到具体实现类的映射。两者配合，使得新增一种实现只需两步：继承 ABC 并实现全部抽象方法，然后在注册表中添加一行映射。核心代码不需要任何修改——它只知道从注册表中按标识符查找类并实例化，不关心这个类是何时新增的、内部逻辑是什么。

这种模式来源于 zonebank 项目中的实践经验。在 zonebank 中，弹性伸缩的各类策略（扩容策略、缩容策略、定时触发策略）均通过 ABC + Registry 模式管理——新增一种扩缩容策略时，开发者不需要修改策略引擎的核心调度代码，只需新建一个策略类并注册。ZRAG 将这一经过验证的模式复用到了文档摄入、分块策略和 LLM 集成的设计中。

从 SOLID 原则的角度看，ABC + Registry 实现了"对扩展开放，对修改封闭"。当需要支持新的数据源时，开发者在 `zrag/ingest/sources/` 目录下新建一个文件，实现 `DocumentSource` ABC 的 `fetch_batch()` 和 `source_type`，然后 `SOURCE_REGISTRY["new_source"] = NewSource`。IngestionPipeline 的代码完全不受影响。如果扩展需要改动 Pipeline 的核心代码（例如需要新增一个特殊的处理阶段），那就说明 ABC 的接口设计不够通用——这是需要在设计层面修正的信号，而非扩展者的操作问题。

### 为何注册表用 Python dict 而不用配置文件反射

在某些框架中，扩展的注册方式是通过配置文件声明类名的字符串，然后由框架通过反射（如 Python 的 `importlib.import_module`）根据字符串加载类。这种方式的"便利"在于不需要写 Python 代码来注册——修改一个 YAML 或 JSON 配置文件即可。

但这种便利是有代价的。配置文件中书写的类名字符串是一个"不透明"的标识——IDE 无法追踪这个字符串到实际的类定义，无法提供自动补全和跳转支持；如果类名拼写错误（如 `"LocalFilesSource"` 多了一个 `s`），错误要到运行时通过反射才能发现——而反射失败的报错信息通常是 `ModuleNotFoundError` 或 `AttributeError`，排查时需要人工对比字符串拼写。更严重的是，反射能够加载任意模块中的任意类——配置文件被意外修改或恶意篡改时，可能加载预期之外的类，引入安全隐患。

使用 Python dict 作为注册表，注册的是 Python 类对象本身（而非类名的字符串），`import` 是注册的前提——类必须先被导入才能被注册。这意味着如果类名拼写错误或模块路径不对，错误会在代码的 import 阶段（通常是在应用启动时）立即暴露，而不是延迟到运行时。IDE 可以追踪 dict 中每个值的类引用，提供完整的代码导航。此外，dict 的键（如 `"mac_notes"`）虽然是字符串，但它只是一个查找键，不是类加载指令——即使键名写错，代码会抛出 `KeyError`（而非反射链中的 `ModuleNotFoundError`），错误信息直接指向缺失的注册表键，排查路径清晰。

> 注意：注册表 dict 中的键名应使用 snake_case，与 `source_type` 属性返回值保持一致。键名的唯一要求是在注册表范围内不重复——Python dict 天然保证了这一点。

## 13.1 新增数据源

新增数据源的步骤：

1. 实现 `DocumentSource` 抽象基类
2. 在 `SOURCE_REGISTRY` 中注册

```python
# zrag/ingest/sources/local_file.py

class LocalFileSource(DocumentSource):
    """本地文件数据源
    
    扫描指定目录下的 Markdown/PDF/DOCX 文件。
    """
    
    def fetch_batch(self, batch_size=10) -> Iterator[list[RawDocument]]:
        files = list(self._scan_files())
        for i in range(0, len(files), batch_size):
            batch = [self._file_to_doc(f) for f in files[i:i+batch_size]]
            yield batch
    
    @property
    def source_type(self):
        return "local_file"

# zrag/ingest/sources/__init__.py
SOURCE_REGISTRY = {
    "mac_notes": MacNotesSource,
    "local_file": LocalFileSource,  # 新注册
}
```

## 13.2 新增分块策略

新增分块策略的步骤：

1. 实现 `ChunkingStrategy` 抽象基类
2. 在分块注册表中注册

```python
# zrag/ingest/chunking/semantic_chunker.py

class SemanticChunker(ChunkingStrategy):
    """基于语义边界的文档分块器
    
    通过 Embedding 相似度检测文本中的语义断点，
    在语义转折处进行切分，保持每个 chunk 内语义连贯。
    """
    
    def chunk(self, document: RawDocument) -> list[Chunk]:
        sentences = self._split_sentences(document.content)
        # 基于相邻句子 Embedding 相似度检测断点
        breakpoints = self._find_breakpoints(sentences)
        return self._build_chunks(document, sentences, breakpoints)
```

`HeadingChunker` 是本项目已实现的一种 Markdown 标题感知分块策略，区别于上述基于语义相似度的方案，它利用 Markdown 文档的结构特征（`#`、`##`、`###` 标题标记）作为切分边界。

核心参数：

| 参数 | 值 | 说明 |
|------|-----|------|
| levels | [1, 2, 3] | H1-H3 作为切分边界 |
| max_size | 1024 | 单 chunk 字符上限 |
| min_size | 200 | 短 chunk 合并阈值 |
| overlap | 100 | 超长段二次切分时的重叠字符数 |

设计要点：
- 无标题文档回退到 `RecursiveCharacterChunker`
- 超长段（> max_size）由 RecursiveCharacterChunker 二次切分
- 子 chunk 继承父标题路径作为前缀，保留上下文
- 组合方式：`CompositeChunker(HeadingChunker, RecursiveCharacterChunker)`
- 当前仅应用于 `mac_notes` 来源

## 13.3 新增 LLM Provider

新增 LLM Provider 的步骤：

1. 实现 `LLMProvider` 抽象基类
2. 在 ViewSet 中注入使用

```python
# zrag/llm/ollama.py

class OllamaProvider(LLMProvider):
    """Ollama 本地模型实现
    
    通过 Ollama API 调用本地部署的开源模型。
    """
    
    def chat(self, messages, timeout=None):
        resp = requests.post(
            f"{self.base_url}/api/chat",
            json={"model": self.model, "messages": messages},
        )
        return resp.json()["message"]["content"]
```

使用方式：通过 ViewSet 的依赖注入机制替换 LLM Provider：

```python
viewset = ConversationViewSet()
viewset.llm_provider = OllamaProvider(model="qwen2.5:7b")
```
