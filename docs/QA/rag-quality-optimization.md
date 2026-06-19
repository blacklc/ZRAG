# RAG 回答质量优化

> 从导入管线与混合检索两个方向系统性地提升 RAG 回答质量。

## Q1: 优化方向确定

**问题**：RAG 系统回答质量优化应从哪些方向开展？

**结论**：两个方向——（1）优化导入管线，提升入库数据质量；（2）优化混合检索，提升查询理解与召回精度。优先攻克方向 1。

**两个方向的关键发现**：

**方向 1（导入管线）**：
- `CompositeChunker` 的 `max_size=512` 覆盖了 `HeadingChunker` 的 `max_size=1024`，导致基于标题的切分总被二次切分
- `export_notes.py` 提取了标签但从未写入 JSON metadata
- HTML→Markdown 转换对嵌套标签处理不完善
- 若 ChromaDB 写入失败会导致 SQLite 与向量库数据不一致
- 缺乏 Unicode 规范化
- 段落切分器无 overlap、硬截断可能破坏单词边界
- 代码围栏中的 `#` 可能被误识别为标题
- 缺乏 content_hash 变更时的分块策略变更检测

**方向 2（检索）**：
- 完全没有查询理解层（无查询改写、扩展、同义词、HyDE）
- 两条路径都没有相关性阈值，永远返回 top-k
- FTS5 清洗函数阻断了所有高级查询语法
- RRF 融合时稠密/稀疏信号等权，无法按查询类型调整

## Q2: CompositeChunker 的 max_size 配置冲突

**问题**：`CompositeChunker` 默认 `max_size=512` 覆盖了 `HeadingChunker` 的 `max_size=1024`，导致标题切分几乎全部被废弃。

**结论**：重新协调所有切分参数，统一 chunk 目标大小。

## Q3: chunk 目标大小

**问题**：最终存入数据库的 chunk 目标大小设为多少？

**结论**：统一设为 **1000 字符**。依据：
- Embedding 模型 `BAAI/bge-small-zh-v1.5` 的 max sequence length = 512 tokens
- 中文 1 token ≈ 1.5-2 字符，512 tokens ≈ 800-1000 字符
- 参数调整：HeadingChunker、CompositeChunker、RecursiveCharacterChunker 的 max_size 全部统一为 1000

## Q4: 标签（tags）元数据

**问题**：`export_notes.py` 提取了标签但未写入 JSON metadata。

**结论**：需要补充。将 tags 存入 metadata，并在检索时使用（FTS5 索引 + 未来过滤检索）。

## Q5: SQLite 与 ChromaDB 数据一致性

**问题**：ChromaDB 写入失败后，SQLite 与 ChromaDB 可能不一致。

**结论**：`design.md` 第 3.3 节已有完整的设计方案，当前实现符合设计。核心设计：SQLite 是 Source of Truth，写入顺序"先 SQLite 后 ChromaDB"，若 ChromaDB 失败则 `processed_docs` 不更新，下次摄入自动补偿重写。不是 bug。

## Q6: 剩余管线质量问题

### ParagraphChunker
未被实际使用。仅在 `CompositeChunker.__init__` 回退逻辑中出现，但无代码路径触发此回退。有 3 个单元测试但无集成调用。可暂缓或后续清理。

### 代码围栏中 `#` 被误识别为标题
**需修复。** `HeadingChunker` 正则在 `re.MULTILINE` 模式下误匹配代码围栏内 `#` 注释行。方案：扫描标题前先识别并跳过代码围栏区域（```...```）。

### HTML→Markdown 嵌套标签
非贪婪 `.*?` 匹配导致嵌套结构（列表含代码块、嵌套列表、表格含段落、嵌套引用块）产生错误 Markdown。实际输入是 Apple Notes 专有富文本（非标准 HTML），实际测试中未见由此导致的严重问题。

### embed_query 指令前缀
`BAAI/bge-small-zh-v1.5` 推荐中文查询添加前缀 `"为这个句子生成表示以用于检索相关文章："`。v1.5 对无指令容忍度较高（下降约 1-5%），但 s2p 场景仍建议添加。当前 `embed_query()` 与 `embed()` 完全一致，未添加任何前缀。参考：[BGE HuggingFace](https://huggingface.co/BAAI/bge-small-zh-v1.5)

## Q7: 方向 1 优化范围确认

**纳入本次优化**：
1. 切分参数统一（Q2/Q3）：max_size 全部统一为 1000
2. 标签元数据补充（Q4）：export_notes.py 写入 tags → 管线透传 → FTS5 索引
3. 代码围栏 `#` 误识别修复（Q6）：HeadingChunker 跳过代码围栏区域
4. embed_query 指令前缀（Q6）：`"为这个句子生成表示以用于检索相关文章："`
5. Unicode 规范化（NFC）

**暂缓**：
- ParagraphChunker（未被实际使用，不做处理）
- HTML→Markdown 嵌套标签（Apple Notes 富文本实际未产生该问题）
- 分块策略变更检测（现有 content_hash 机制已足够）

## Q8: 查询理解层方案

**问题**：当前用户查询原样传入 `hybrid_search()`，无预处理。

**结论**：采用查询改写（Query Rewriting），让 LLM 在检索前将口语化问题改写为更精准的搜索表达。

## Q9: 查询改写格式与触发策略

**改写目标格式**：同时产出关键词列表 + 精炼自然语言查询。关键词适合 FTS5 精确匹配，精炼查询适合向量语义搜索。

**触发策略**：全部改写（每条查询都执行）。

## Q10: 改写结果流入混合检索

**结论**：关键词列表直接拼接为 FTS5 MATCH 查询（不分词，LLM 已提炼）。精炼查询走 embed_query → 向量路径。两者也互为补充输入。

## Q11: 候选池扩大

**问题**：两条路径各用 k=10 拉取候选，导致 RRF 融合时可能遗漏"只有一条路径认可"的优质结果。

**结论**：各路径候选数扩大为 k×2（各取 20 个），RRF 融合后截取最终 top-10。

## Q12: 相关性阈值

**问题**：两条路径无条件返回 top-k，不判断候选是否真正相关。

**结论**：暂不引入阈值。依赖 RRF 融合自然压低低质量结果的排名。阈值调参环境依赖性强，且 k×2 候选池扩大后 RRF 已有足够材料进行有效排序。

## Q13: FTS5 异常静默处理

**问题**：`search_fts5()` 异常静默 catch 后返回空列表，检索退化为纯向量搜索。

**结论**：保持现状。引入查询改写后 LLM 产出关键词大概率是干净的中文词列表，触发 FTS5 语法错误的概率极低。静默降级简单可靠。

## Q14: RRF 权重配置

**问题**：RRF 融合时向量和关键词信号等权，无法按场景调整。

**结论**：引入可配置权重。在 `config/retrieval.yaml` 中增加 `rrf_weights: {vector: 1.0, keyword: 1.0}`，默认等权，需要时可调整。

**确认结论**：
1. 切分参数统一（max_size 全部 1000）
2. 标签元数据补充（export_notes.py → 管线透传 → FTS5 索引）
3. 代码围栏 `#` 误识别修复（HeadingChunker 跳过代码围栏区域）
4. embed_query 指令前缀（`"为这个句子生成表示以用于检索相关文章："`）
5. Unicode NFC 规范化

---

## Q15: 关键词同义词扩展

**问题**：用户的查询口语用词可能与文档中的术语表达不一致。例如用户说"实现原理"，但文档中更常用"工作原理"或"原理"。在 FTS5 隐式 AND 语义下，如果简单在 keywords 中追加同义词会收紧匹配约束（要求一个 chunk 同时包含所有 token），导致漏召。

**案例**：
- 用户查询：`"详细讲解Kubernetes默认调度器的实现原理"`
- 直接提取 keywords：`"Kubernetes 默认调度器 实现原理"`
- 同义词替换后 keywords：`"Kubernetes 默认调度器 工作原理"`
- 效果：文档中实际使用"工作原理"作为章节标题，替换后能正确召回。

**方案**：
- 在 query_rewrite.j2 模板中新增指令，要求 LLM 在提取关键词时将用户口语用词替换为技术文档中更常见的同义/近义表达。
- 策略是"替换"而非"追加"：将用户术语替换为文档侧更常见的同义表达，保持关键词总数在 5 个以内，不无意义扩充。
- 模板中给出具体示例进行 in-context learning。

**关键设计决策**：
1. **替换而非追加**：FTS5 隐式 AND 语义下追加同义词会要求 chunk 同时包含所有 token，反而缩小召回范围。替换策略用文档端更常见的表达替代用户口语用词，目标是在不增加关键词数量的前提下提升命中率。
2. **关键词总数上限 5 个**：限制 LLM 不要过度扩充关键词，避免 FTS5 因过多 token 导致过严格匹配。
3. **通过 in-context example 引导**：示例中 "实现原理" → "工作原理" 的替换模式让 LLM 隐式学习同义替换行为，不依赖外部同义词表或知识库。

**约束和未来扩展方向**：
- 当前完全依赖 LLM 的语义理解能力进行同义词替换，无外部同义词表作为兜底。如果 LLM 对特定领域术语不熟悉，替换可能不准确。
- 未来可考虑引入领域同义词表（如 YAML 配置），在 LLM 替换后做二次映射或兜底替换。
- 也可考虑将替换后的 keywords 通过 FTS5 同义词词典（synonym tokenizer）做二次扩展，实现"替换 + 可控扩展"的组合策略。

---

## Q16: 多轮对话处理现状分析

**问题**：当前 RAG 系统如何处理一个会话中的多轮问答？是否存在优化空间？

**现状**：对各阶段的上下文利用情况进行分析后，发现检索阶段完全忽视对话上下文：

| 阶段 | 是否使用对话历史 | 详情 |
|------|:--:|------|
| QueryRewriter | ❌ | 仅接收当前 query |
| hybrid_search 检索 | ❌ | 仅用当前改写后的 query |
| build_rag_prompt | ❌ | system prompt 仅含当前检索结果 |
| LLM 生成 | ✅ | 后端从 SQLite 加载最近 10 条历史 |

**后果**：追问 "那它的性能怎么样？" 时，"它" 无法解析为前一问的实体；"打分怎么做的"中的 "打分" 由上一轮 assistant 回复引入，QueryRewriter 完全无法关联。

**结论**：需要系统性地解决两个问题——指代消解（将 "它""这个" 解析为具体实体）和上下文感知检索（检索时利用对话历史调整检索方向）。方案是在检索前注入对话摘要，让 QueryRewriter 结合摘要进行改写。

**关键场景验证**：
- 只传 user 查询序列不能覆盖的场景：上一轮 assistant 回复中引入的术语（如 "打分"），这些词在用户查询序列中从未出现
- 结论：需传完整 user + assistant 消息，但通过增量压缩控制长度

---

## Q17: 上下文感知检索方案设计

**问题**：如何在检索阶段感知对话上下文？

**方案**：采用对话摘要注入方式。

**摘要生成策略**：
- 采用增量压缩：每轮在已有摘要 + 最新 Q&A 基础上生成更新后的摘要
- 摘要最大长度 200 字（通过配置项 `summary_max_chars` 控制）
- 摘要存入 conversations 表，与对话历史关联

**摘要注入时机**：
- 压缩在回答返回后异步执行（不阻塞用户请求）
- 下一轮追问时读取 summary 并传入 QueryRewriter
- 合并压缩与改写的方案被否决：两次独立调用可在 GPU 环境下（~1s/次）实现关注点分离，且压缩可异步化

**指代消解**：
- 在 query_rewrite.j2 中新增指令，引导 LLM 结合摘要解析指代词
- 摘要注入在 user message 中而非 system prompt 中，保持 system prompt 简洁

**设计决策**：
- 压缩与改写拆分：关注点分离、失败隔离、可独立扩展。GPU 充足时压缩异步化，用户零感知延迟
- 只传最新一轮 Q&A + 已有摘要（增量压缩），不传全量历史
- 摘要更新时机：在 LLM 生成回复并存入 DB 后立即异步压缩，下一次查询来时摘要已就绪

---

## Q18: 本地小模型选型与部署

**问题**：查询改写和对话压缩任务是否可以使用本地部署的小模型来节省 API 消费？

**结论**：可以。查询改写（指代消解 + 关键词提取 + 查询精炼）和对话压缩是高频、低语义难度的任务，7B-9B 级别的本地模型完全胜任。

**模型选型过程**：
1. Qwen2.5-7B-Instruct：中文指代消解 7B 级最佳，JSON 输出可靠，CPU Q4 约 4-7s，社区成熟
2. Qwen3-8B：性能略优但生态成熟度略逊
3. Qwen3.5 系列：无 7B-8B 版本。Qwen3.5-4B 偏小（5B），Qwen3.5-9B 偏大（10B，CPU Q4 约 7-11s）
4. Qwen3.5-9B-Base：纯基座模型，无指令微调，不能直接使用（IFEval 0 分，无法遵循指令输出 JSON）
5. 最终选择 Qwen3.5-9B：指令跟随 IFEval 91.5 分，完整 Chat API 支持，JSON 输出能力（BFCL-V4 66.1），可关闭思考模式加速

**部署方案**：
- 推理引擎：Ollama（独立 Docker 容器，`ollama/ollama:0.9.0`）
- 模型：Qwen3.5-9B Q4_K_M 量化，约 6GB 磁盘
- CPU 推理延迟：查询改写约 7-11s/次，压缩约 7-11s/次（异步执行不阻塞用户）
- 内存限制：`--memory="10g"`（模型 6GB + KV cache 等开销）
- `OLLAMA_KEEP_ALIVE=24h`：避免频繁冷启动（冷启动需重新加载 6GB 权重，耗时数十秒）

**统一路由**：所有 LLM 调用通过 LiteLLM Gateway 统一管理，本地模型作为 Gateway 的一个后端 provider。QueryRewriter 和 ConversationSummarizer 走 `ollama/qwen3.5:9b`，Chat 生成走 `smart-router`。统一监控、统一日志。

**参数相关基础概念解释**：
- 参数量：模型中可训练权重的个数（B = Billion，十亿）。决定模型的知识容量和推理天花板。对于 QueryRewriter 场景，7B-8B 已远超需求
- Q4 量化：将模型参数从 FP16（2 bytes/参数）压缩到 4-bit（0.5 byte/参数），7B 模型从 ~14GB 降至 ~4GB，精度损失仅 1-3%
- 指令跟随能力：衡量模型按照给定指令格式输出的可靠性。关键指标：IFEval 分数、JSON 输出合规率、是否添加废话前缀
- 推理引擎：将 GGUF 模型文件（被动数据）加载到内存、执行 Transformer 数学运算、生成输出文本的程序。Ollama 是 "推理引擎 + HTTP API" 的整合体

---

## Q19: ConversationSummarizer 增量压缩设计

**问题**：如何将多轮对话压缩为简洁摘要，既保留核心上下文，又不让 prompt 膨胀？

**方案**：ConversationSummarizer 类，独立于 QueryRewriter。

**核心设计**：
- 增量压缩：每次传入已有摘要 + 最新一轮 Q&A，生成更新后的摘要
- 助手回复截断到 500 字符（`_MAX_REPLY_CHARS`），避免长回复撑大 prompt
- 输出清理：`_clean_summary()` 移除常见废话前缀（"好的，"、"以下是"、"更新后的摘要："等），截断到 max_chars
- 首轮压缩时已有摘要为空，模板中以 "（首轮对话，无已有摘要）" 提示 LLM

**Prompt 设计**：
- System prompt（compress.j2）：任务说明 + 摘要要求 + 严格输出规则（禁止废话前缀）
- User message：`已有摘要：...\n\n最新一轮对话：\n用户提问：...\n助手回答：...`
- 严格输出规则中警告 LLM 违反将导致摘要无法被系统处理
- 代码层 `_clean_summary()` 作为第二道防线兜底清理

**与 QueryRewriter 的关系**：两者共享同一个本地 LLM 后端，但分属不同类。压缩是独立的职责，不应耦合到 QueryRewriter 中。

**设计约束**：
- 摘要最大长度 200 字（足够概括主题和实体）
- 增量压缩无需限制对话轮次——200 字的硬上限迫使 LLM 自行取舍，旧话题自然衰减
- 只传最新一轮 Q&A + 已有摘要，不会因对话变长而膨胀

---

## Q20: 异步压缩 CompressService 设计

**问题**：压缩在何时执行？如何避免阻塞用户请求？

**方案**：CompressService 封装异步调度逻辑。

**核心设计**：
- 复用 `settings.ZRAG_INGEST_EXECUTOR`（项目已有全局线程池，默认 2 workers），不新建线程池。与 TaskManager 注入方式一致
- CompressService 模块级单例（DoLC 懒加载），`get_compress_service()` 为唯一入口。不在 views.py 中重复维护单例逻辑
- 压缩任务创建独立 SqliteStore 实例获取独立 SQLite 连接（WAL 模式支持并发读写）。不在接口中传递 db_path，SqliteStore() 无参数构造从 Django settings 读取路径
- 静默失败：LLM 调用或 DB 写入失败仅写日志，不抛异常，不重试。下一轮降级使用旧摘要

**触发时机**：
- create() 返回前触发（首轮 Q1+A1 压缩）—— 此点为设计审查中发现的遗漏点，原方案仅 add_message 触发压缩会导致首轮摘要缺失
- add_message() 返回前触发（当前轮 Q+A 压缩）

**竞态处理**：用户极快连续发送消息时，两个压缩线程可能并发写同一 summary。最后写入者胜出，语义上正确（最新摘要来自最新 Q&A）。不需要加锁。

**与 GPU 生产环境的对比**：
- CPU：两次串行调用约 10-16s，异步压缩可消除改写后的等待
- GPU：两次调用各约 0.5-1.5s，大厂仍选两次独立调用——关注点分离、失败隔离、独立扩展
- 当前 CPU 场景下异步压缩最关键：用户只感知改写延迟（~7-11s），压缩在后台完成

---

## Q21: Ollama 部署决策

**问题**：Ollama 应作为项目 docker-compose 的一部分，还是独立部署？

**结论**：独立部署。Ollama 与 LiteLLM 属于同一级别的独立基础设施，可被多个项目复用。不入 ZRAG 的 docker-compose.yml。

**关键决策**：
- Docker 部署优于 brew install：跨电脑迁移时只需拷贝 volume 数据，一行 `docker run` 恢复。brew install 需新电脑重新配置
- LiteLLM Gateway 中注册 Ollama 后端：`api_base: http://host.docker.internal:11434`（不在同一 compose 网络，通过宿主机端口通信）
- LiteLLM Gateway 重启由用户手动操作，不自动执行
- BGE embedding 模型不受 Ollama 管理：BGE 是 encoder-only 架构，Ollama 只处理 decoder-only LLM。两类模型架构不同，推理引擎不同，没有统一管理的必要。BGE 继续通过 SentenceTransformer 进程内加载
- Ollama 本质是 "模型推理引擎 + HTTP API 服务" 的整合体。底层调用 llama.cpp 执行推理

---

## Q22: 同义词替换策略调整 — 核心词提取

**问题**：之前 Q15 的同义词替换方案（"实现原理"→"工作原理"）经过验证，LLM 未能遵循指令。

**根因**：LLM 无法从自身知识中预测文档侧实际使用的术语。"实现原理" 是有效的技术术语，LLM 没有理由替换它。这属于术语映射问题，不依赖模型大小，依赖对文档术语的感知。

**新方案**：改为核心词提取策略。
- "实现原理" 提取为 "原理"
- "事件推送" 提取为 "事件"+"推送"
- 对复合概念术语只保留最核心的名词，去掉修饰性前缀
- 降低对 LLM 领域知识的依赖——LLM 不需要知道文档用什么词，只需提取核心概念

**模板更新**：query_rewrite.j2 中指令改为：
```
4. 关键词提取时注意：对于复合概念术语，只保留最核心的名词，去掉修饰性前缀。
   例如 "实现原理" 提取为 "原理"。关键词总数保持在 5 个以内，不要无意义扩充。
```

---

## Q23: 降级策略 — Ollama 不可用时的处理

**问题**：本地模型可能因容器宕机、冷启动（首次加载 6GB 权重需数十秒）等原因暂时不可用。

**方案**：改写失败时降级使用原始 query。

**实现位置**：`retriever.py` 的 `hybrid_search()` 中。该处已有 "有 QueryRewriter 就走改写，没有就走原 query" 的分支逻辑，降级是此分支的自然扩展。

**设计选择**：
- 方案 A（不降级，直接报错）：容器重启后首请求必然失败，`OLLAMA_KEEP_ALIVE=24h` 可避免大部分冷启动但非绝对可靠
- 方案 B（降级为原始 query）：Ollama 不可用时检索质量下降但不中断服务。选择此方案
- 运维层面：依赖 LiteLLM Gateway 的监控告警发现异常；压缩任务失败独立静默，不影响改写链

---

## Q24: 摘要注入 LLM 生成阶段 + 历史消息数量缩减

**问题**：摘要目前仅用于查询改写阶段。LLM 生成阶段虽然有完整历史消息，但 SQL 查询 `LIMIT 10` 意味着超过 10 轮后早期对话被截断。摘要通过增量压缩保留了完整上下文，应考虑也将其注入生成阶段的 messages 中，并借此缩减历史消息数量。

**分析**：经过讨论，摘要与完整历史的关系如下：

| | 短对话（≤10 轮） | 长对话（>10 轮） |
|------|:--:|:--:|
| QueryRewriter 上下文 | ✅ 摘要（已实现） | ✅ 摘要（已实现） |
| LLM 生成上下文 | ✅ 完整历史 | ❌ 早期消息被 LIMIT 截断 |

摘要可以弥补生成阶段的历史截断问题。

**方案**：方案 B — 将摘要作为独立的 system 消息插入 `full_messages`。

**注入位置**：摘要作为第 2 条 system 消息，位于 rag system prompt（参考材料）之后、历史消息之前。理由：rag system prompt 定义了 LLM 的角色和回答规则，需放在最前面；摘要作为补充上下文紧跟其后，语义自然。

```
[0] system:  rag system prompt（参考材料 + 指令）
[1] system:  对话背景摘要（summary，仅多轮时存在）
[2] user:    历史消息 ...
[3] assistant: 历史消息 ...
[4] user:    当前 query
```

**历史消息缩减**：既然摘要提供了完整上下文，历史消息只需保留最近几轮语义连贯性即可。`LIMIT` 从 10 缩减为 3（约 1.5 轮 Q&A），减少 prompt token 消耗。

**改动范围**：仅 `views.py` 的 `add_message()` 方法，不改模板和 PromptBuilder。

**关键设计决策**：
1. 摘要不作为 user 消息（因为"对话背景摘要"不是用户说的，用 user 角色会造假）
2. 摘要不放在 rag system prompt 里（避免与参考材料混在一起，LLM 更难区分优先级）
3. `LIMIT 3` 而非更大的值——摘要已提供完整上下文，历史消息只需覆盖最近的口语连贯性
4. 摘要为空时跳过插入，不影响首轮对话

---

## Q25: 摘要压缩时 assistant_reply 被过度截断

**问题**：`ConversationSummarizer` 中使用 `_MAX_REPLY_CHARS = 500` 硬编码截断 `assistant_reply`。RAG 回答轻松超过 500 字符，导致压缩输入中最新一轮的回答信息严重丢失。

**分析**：
- 过小的截断阈值导致压缩器无法感知 assistant 回答的完整内容，压缩结果可能丢失关键信息。
- 硬编码值无法适配不同模型的上下文窗口差异——小模型窗口小，大模型窗口大，统一截断不合理。

**结论**：`assistant_reply` 的截断长度应基于模型 `context_window` 按比例动态计算，而非硬编码固定值。

**方案**：
1. 将 `_MAX_REPLY_CHARS` 改为从外部传入的配置参数，默认值基于 `context_window` 的 30%-50% 计算
2. 确保压缩器传入的 prompt 总长度（system_prompt + old_summary + user_query + assistant_reply）不超过 `context_window` 的 80%，为模型输出预留空间

## Q26: prompt 各部分大小限制设计

**问题**：会话压缩 prompt 由四部分组成（system_prompt、old_summary、user_query、assistant_reply），各部分应有合理的大小限制，以适配模型的 `context_window`。

**各部分限制分析**：

| 部分 | 大小 | 说明 |
|------|------|------|
| `system_prompt`（compress.j2） | ~200 字符 | 模板固定，几乎不变 |
| `old_summary` | ≤200 字符 | 上一轮已截断，传入时已在合理范围内 |
| `user_query` | 需加限制 | 之前无限制，多轮对话中单次 query 可能过长 |
| `assistant_reply` | 需重新设计 | 当前 500 字符硬编码，不合理 |

**结论**：
1. `context_window` 配置不放在 `config/retrieval.yaml`，应放在 `config/llm.yaml`，因为它是模型本身的属性
2. 配置项命名：`rewriter_model_context_window`
3. `user_query` 增加截断保护，上限设为 `context_window` 的 20%
4. `assistant_reply` 截断长度改为 `context_window` 的 30%，替代原来的 500 字符硬编码
5. 最终的 prompt 总长不应超过 `context_window` 的 80%

**设计决策**：
- 为什么 `context_window` 放在 `llm.yaml`：context_window 大小由模型决定（跟着模型走），而非检索业务决定。`retrieval.yaml` 存放检索策略参数，`llm.yaml` 存放模型能力参数。
- 为什么配置名用 `rewriter_model_context_window` 而非 `rewriter_context_window`：明确指出是哪个模型，为将来引入独立压缩/改写模型预留清晰命名空间。

## Q27: 接口净化 — 任务参数下移到方法形参

**问题**：`ConversationSummarizer.__init__` 接收了大量任务参数（`max_chars`、`context_window`、`template_dir`），其中 `template_dir` 在后续实现中始终指向固定路径（项目内），`max_chars` 和 `context_window` 仅在 `summarize()` 调用时使用。

**分析**：对象构造时应只接收与对象身份相关的依赖（如 `llm_provider`），而任务参数应绑定到方法调用层面。将任务参数放在构造函数中会导致：
- 每次调整参数都需要重新创建实例
- 难以适配同一实例对不同轮次使用不同压缩参数
- 构造函数签名膨胀，职责模糊

**方案**：
1. `template_dir` 从 `__init__` 参数中删除，改为在 `ConversationSummarizer` 内部硬编码为 `zrag/prompts/compress/`
2. `max_chars` 和 `context_window` 从 `__init__` 移至 `summarize()` 的方法形参，提供合理默认值
3. `ConversationSummarizer.__init__` 仅保留 `llm_provider` 一个参数

**改造前**：
```python
class ConversationSummarizer:
    def __init__(self, llm_provider, max_chars=200, context_window=8192, template_dir="..."):
```

**改造后**：
```python
class ConversationSummarizer:
    def __init__(self, llm_provider):
        ...

    async def summarize(
        self,
        old_summary: str,
        user_query: str,
        assistant_reply: str,
        max_chars: int = 200,
        context_window: int = 8192,
    ) -> str:
```

**How to apply**：
1. `llm_provider` 是对象的身份属性——注入后不再变更，放在 `__init__`
2. `max_chars`（本轮压缩目标长度）和 `context_window`（模型上下文窗口）是单次调用的参数——放在 `summarize()` 方法形参
3. `template_dir` 固定为项目内的 `zrag/prompts/compress/`，无需外部覆盖——直接硬编码
4. 这一净化原则适用于项目中其他类：区分"对象是什么"（构造函数）和"对象做什么"（方法参数）

---

## Q28: 摘要内容格式调整 — 从知识总结改为 Q&A 导向

**问题**：当前 `ConversationSummarizer` 生成的摘要是纯知识点总结。真实生产摘要（`system_prompt.md`）显示："Kubernetes中PV的创建分为静态模式和动态模式。静态模式由管理员手动创建PV对象..."。摘要丢失了用户问了什么、助手回答了什么，导致查询改写阶段 rewriter 无法感知用户关心的原始问题，指代消解能力受限；LLM 生成阶段注入 `"对话背景摘要：\n{summary}"` 后，模型无法还原对话进程。

**分析**：摘要同时服务于两个消费场景：
- 检索层（`QueryRewriter.rewrite(query, summary)`）— 帮助改写查询、消解指代
- 生成层（LLM messages 中 `"对话背景摘要：\n{summary}"` 作为 system 消息）— 让 LLM 感知对话背景

两个场景都要求摘要能够传达"之前聊了什么"，而非"之前的回答涉及哪些知识点"。

**新格式设计**：
- 核心原则：摘要应描述"用户问了什么 + 助手答了什么"，而非"回答中涉及哪些知识点"
- 示例格式："用户询问了 Kubernetes PV 的创建方式。助手介绍了静态模式（管理员手动创建并提交 YAML）和动态模式（External Provisioner 根据 PVC 自动触发），两种模式分别由管理员或组件驱动。"
- 多轮融合策略：按时间线串下来，优先保留最近轮次，早期轮次可适度归并

**实现方案**：
1. `zrag/prompts/compress.j2`：重写摘要要求，将模糊的"概括对话主题、核心概念"替换为明确的 Q&A 导向指令 + 示例引导。增加多轮融合规则。
2. `config/retrieval.yaml`：`summary_max_chars: 200` → `500`，以容纳更丰富的信息
3. `tests/test_conversation_summarizer.py`：更新测试断言为 Q&A 导向的形式特征断言

**不涉及的代码文件**：`conversation_summarizer.py`（`_render_messages()` 和 `_clean_summary()` 与新格式兼容）、`views.py`（摘要透传逻辑不变）

**关键设计决策**：
- 方案选型：明确指令 + 示例引导，而非固定格式模板。纯固定格式会导致摘要千篇一律，rewriter 和 LLM 难以提取有用信号
- 多轮融合：按时间线串下来（非话题归并）。查询改写需要时序信息来消解"这个""它"等指代词；话题归并会丢失追问链
- max_chars 提升到 500：单轮 Q&A 新格式约 80-120 字，3-5 轮累积约 200-350 字，500 字留有安全边际
- 测试策略：形式特征断言（如摘要包含"用户询问"等关键词），不依赖 LLM 实际输出质量