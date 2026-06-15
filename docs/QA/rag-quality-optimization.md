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

