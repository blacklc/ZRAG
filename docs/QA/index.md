# ZRAG 设计对话记录目录

> 原 `docs/QA.md` 按主题拆分为以下分类文件。

## 分类索引

| 文件 | 主题 | 说明 |
|------|------|------|
| [数据源与摄入](data-ingestion.md) | 数据源设计、macOS Notes 读取、分块策略、IngestionPipeline、异步导入方案 |
| [存储与 Embedding](storage-embedding.md) | Embedding 模型、ChromaDB、SQLite FTS5、数据一致性、数据模型汇总 |
| [检索与 LLM](retrieval-llm.md) | RRF 融合、Retriever、Prompt 构建、LLM Provider 实现 |
| [混合检索准确度优化](hybrid-search-accuracy.md) | 检索召回不足问题诊断、HTML→Markdown 转换增强、HeadingChunker、jieba 中文分词、同源合并方案 |
| [RAG 回答质量优化](rag-quality-optimization.md) | 导入管线数据质量优化、切分参数统一、查询改写、RRF 权重、候选池扩大、多轮对话优化（指代消解+上下文感知检索）、本地小模型部署、ConversationSummarizer、异步压缩、摘要 prompt 大小限制、接口净化 |
| [API 与会话管理](api-config.md) | API 设计、配置文件、会话存储、BGE 维度修正 |
| [日志 JSON 格式改造](log-json-format.md) | JsonFormatter 设计、全量 JSON 方案选型、extra 命名规范、改造范围清单 |
| [前端与部署运维](frontend-deploy.md) | Web UI 设计、容器化部署、跨平台构建、日志分级、Prompt 模板 |

## 查找方法

- **按功能查找**: 根据上表找到对应分类文件
- **按 Q 编号查找**: 在对应文件中搜索 `Q{编号}`
- **全文搜索**: `grep -rn "关键词" docs/QA/`

## 最近更新

- 2026-06-19: Q25-Q27 摘要 prompt 大小动态限制设计 — assistant_reply 截断优化、各部分大小限制、接口净化
- 2026-06-18: 日志格式改为 JSON 串 — JsonFormatter 设计、全量 JSON 方案选型、改造范围清单
- 2026-06-17: Q24 摘要注入 LLM 生成阶段 + 历史消息缩减（LIMIT 10→3）
- 2026-06-09: Q38 macOS Notes 异步导入完整方案
- 2026-06-08: Q37 Prompt 模板引擎 Jinja2
- 2026-06-05: Q36 容器跨平台构建
