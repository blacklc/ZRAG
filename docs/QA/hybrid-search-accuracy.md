# 混合检索准确度优化

## 背景

用户提问"讲解一下在etcd的更新操作中, mvcc是如何进行工作的"，但发给 LLM 的 system prompt 中 `[来源: etcd mvcc]` 的内容非常少（几乎只有标题和一两句话），而其他来源有更多内容。

## 问题诊断

### 问题一：Chunk 碎片化严重

`[来源: etcd mvcc]` 原文 5368 字符被切成 **47 个 chunks**，平均每个只有 **114 字符**。55% 的 chunks 不足 100 字符，最小的一条只有 11 个字符（`# etcd mvcc`）。

原因：`mac_notes` 使用 `CompositeChunker(ParagraphChunker(max_size=512, min_size=50), RecursiveCharacterChunker(max_size=512, overlap=0))`。`ParagraphChunker` 按 `\n\n` 分割，Apple Notes 中的 Markdown 在标题、列表、代码块之间产生大量 `\n\n`，`min_size=50` 合并阈值太低。

### 问题二：FTS5 无法处理中文

FTS5 默认 `unicode61` tokenizer 不理解中文分词。用户查询中所有中文字词在 FTS5 中匹配为 0 条。混合检索实际退化为纯向量检索，`RRF_score = 1/(60+rank_v) + 0`。

**方案选择**：对比 N-gram 字级切分（零依赖、高召回低精度）和 jieba 分词（需第三方依赖、精准度高）后，选择 **jieba 分词**。

**实现要点**：
1. `sqlite_store.py` 新增 `_tokenize_text()` 方法，对中英混合文本做分词
2. 建 FTS5 表时对 content 列做 jieba 分词后再写入
3. `search_fts5()` 查询时同样对 query 做 jieba 分词再做 FTS5 MATCH
4. 对技术术语（treeIndex、keyIndex 等）可注册自定义词典

### 问题三：Apple Notes HTML 源缺乏语义标签

从实际笔记获取的 HTML body 中，`<pre>`、`<code>`、`<ul>`、`<ol>`、`<li>`、`<blockquote>`、`<table>` 等语义标签数量均为 0。仅 `<h1>`-`<h2>` 标题和 `<b>` 粗体标签存在。其余全为 `<div>` + `<span>` + `<br>` 表达。

## HTML→Markdown 转换增强

### 设计目标

`_html_to_markdown()` 应作为通用转换器，覆盖所有常见 HTML 标签。即使当前 Apple Notes 不输出某些标签，转换器也应具备处理能力，以便未来支持其他 HTML 来源。

### 新版转换代码（伪代码）

```python
import re
import textwrap
from html.parser import HTMLParser

class NotesExporter:
    """备忘录导出器"""

    _BASE64_PLACEHOLDER = ''

    def _html_to_markdown(self, html_content: str) -> str:
        """将 HTML 转换为 Markdown（五阶段流水线）

        阶段：
        1. 预处理  — 移除 base64 图片，统一换行
        2. 块级元素 — 标题、代码块、列表、表格、引用、分割线
        3. 内联元素 — 粗体、斜体、删除线、链接、图片、行内代码
        4. 清理     — 移除剩余标签，解码实体
        5. 整理     — 压缩空白，规范化段落间距
        """
        text = html_content

        # ================================================================
        # Phase 1: 预处理
        # ================================================================

        # 1a. 移除 base64 图片（src 为 data:image/...;base64,... 的 img 标签）
        text = re.sub(
            r'<img[^>]*src="data:image/[^"]*;base64,[^"]*"[^>]*>',
            self._BASE64_PLACEHOLDER,
            text
        )

        # 1b. 统一换行符
        text = text.replace('\r\n', '\n').replace('\r', '\n')

        # ================================================================
        # Phase 2: 块级元素转换（从上到下，避免嵌套干扰）
        # ================================================================

        # 2a. 代码块 <pre><code>...</code></pre> 或 <pre>...</pre>
        def _extract_codeblock(m: re.Match) -> str:
            inner = m.group(1)
            if inner.startswith('<code') and inner.endswith('</code>'):
                # 提取 <code> 内的内容
                inner = re.sub(r'^<code[^>]*>', '', inner)
                inner = re.sub(r'</code>$', '', inner)
            # 解码常见实体，保持代码原样
            inner = inner.replace('&lt;', '<').replace('&gt;', '>')
            inner = inner.replace('&amp;', '&').replace('&quot;', '"')
            inner = inner.replace('&#39;', "'").replace('&nbsp;', ' ')
            lang = m.group('lang') or ''
            return f'\n\n```{lang}\n{inner}\n```\n\n'
        text = re.sub(
            r'<pre(?P<lang>[^>]*)>(.*?)</pre>',
            _extract_codeblock,
            text,
            flags=re.DOTALL
        )

        # 2b. 标题 <h1> ~ <h6>
        for i in range(6, 0, -1):
            text = re.sub(
                rf'<h{i}[^>]*>(.*?)</h{i}>',
                rf'\n\n{"#" * i} \1\n\n',
                text,
                flags=re.DOTALL | re.IGNORECASE
            )

        # 2c. 无序列表：<ul> 内的每个 <li>
        def _convert_ul(m: re.Match) -> str:
            items = re.findall(r'<li[^>]*>(.*?)</li>', m.group(1), re.DOTALL)
            return '\n' + ''.join(f'- {it.strip()}\n' for it in items) + '\n'
        text = re.sub(r'<ul[^>]*>(.*?)</ul>', _convert_ul, text, flags=re.DOTALL | re.IGNORECASE)

        # 2d. 有序列表：<ol> 内的每个 <li>
        def _convert_ol(m: re.Match) -> str:
            items = re.findall(r'<li[^>]*>(.*?)</li>', m.group(1), re.DOTALL)
            return '\n' + ''.join(f'{i}. {it.strip()}\n' for i, it in enumerate(items, 1)) + '\n'
        text = re.sub(r'<ol[^>]*>(.*?)</ol>', _convert_ol, text, flags=re.DOTALL | re.IGNORECASE)

        # 2e. 独立的 <li>（不在 <ul>/<ol> 内）
        text = re.sub(
            r'<li[^>]*>(.*?)</li>',
            r'- \1\n',
            text,
            flags=re.DOTALL | re.IGNORECASE
        )

        # 2f. 引用块 <blockquote>
        def _convert_blockquote(m: re.Match) -> str:
            inner = m.group(1).strip()
            # 每行加 > 前缀
            lines = inner.split('\n')
            quoted = '\n'.join(f'> {ln}' if ln.strip() else '>' for ln in lines)
            return f'\n\n{quoted}\n\n'
        text = re.sub(
            r'<blockquote[^>]*>(.*?)</blockquote>',
            _convert_blockquote,
            text,
            flags=re.DOTALL | re.IGNORECASE
        )

        # 2g. 表格 <table>
        def _convert_table(m: re.Match) -> str:
            table_html = m.group(0)
            rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL | re.IGNORECASE)
            if not rows:
                return ''
            md_rows = []
            for ri, row in enumerate(rows):
                cells = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', row, re.DOTALL | re.IGNORECASE)
                md_rows.append('| ' + ' | '.join(c.strip() for c in cells) + ' |')
                if ri == 0:
                    # 分隔行
                    md_rows.append('| ' + ' | '.join('---' for _ in cells) + ' |')
            return '\n\n' + '\n'.join(md_rows) + '\n\n'
        text = re.sub(
            r'<table[^>]*>(.*?)</table>',
            _convert_table,
            text,
            flags=re.DOTALL | re.IGNORECASE
        )

        # 2h. 分割线 <hr>
        text = re.sub(r'<hr\s*/?>', '\n\n---\n\n', text, flags=re.IGNORECASE)

        # 2i. 段落 <p> 和换行 <br>
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<p[^>]*>(.*?)</p>', r'\n\n\1\n\n', text, flags=re.DOTALL | re.IGNORECASE)

        # 2j. <div> 块
        text = re.sub(r'<div[^>]*>(.*?)</div>', r'\n\1\n', text, flags=re.DOTALL | re.IGNORECASE)

        # ================================================================
        # Phase 3: 内联元素
        # ================================================================

        # 3a. 粗体 <b>, <strong>
        text = re.sub(r'<(?:b|strong)[^>]*>(.*?)</(?:b|strong)>', r'**\1**', text, flags=re.DOTALL | re.IGNORECASE)

        # 3b. 斜体 <i>, <em>
        text = re.sub(r'<(?:i|em)[^>]*>(.*?)</(?:i|em)>', r'*\1*', text, flags=re.DOTALL | re.IGNORECASE)

        # 3c. 删除线 <del>, <s>, <strike>
        text = re.sub(r'<(?:del|s|strike)[^>]*>(.*?)</(?:del|s|strike)>', r'~~\1~~', text, flags=re.DOTALL | re.IGNORECASE)

        # 3d. 行内代码 <code>（不在 <pre> 内的）
        text = re.sub(r'<code[^>]*>(.*?)</code>', r'`\1`', text, flags=re.DOTALL | re.IGNORECASE)

        # 3e. 链接 <a href="url">text</a>
        text = re.sub(
            r'<a\s+[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
            r'[\2](\1)',
            text,
            flags=re.DOTALL | re.IGNORECASE
        )

        # 3f. 图片 <img>（非 base64）
        text = re.sub(
            r'<img[^>]*src="([^"]*)"[^>]*alt="([^"]*)"[^>]*>',
            r'![\2](\1)',
            text,
            flags=re.IGNORECASE
        )
        # 无 alt 属性的 img
        text = re.sub(
            r'<img[^>]*src="([^"]*)"[^>]*>',
            r'![](\1)',
            text,
            flags=re.IGNORECASE
        )

        # ================================================================
        # Phase 4: 清理
        # ================================================================

        # 4a. 移除所有剩余 HTML 标签
        text = re.sub(r'<[^>]+>', '', text)

        # 4b. HTML 实体解码
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&amp;', '&')
        text = text.replace('&quot;', '"')
        text = text.replace('&#39;', "'")
        text = text.replace('&nbsp;', ' ')

        # ================================================================
        # Phase 5: 整理
        # ================================================================

        # 5a. Markdown 安全网 — 移除残留 base64 图片引用
        text = re.sub(
            r'!\[\s*\]\(data:image/[^);]*;base64,[^)]*\)',
            self._BASE64_PLACEHOLDER,
            text
        )

        # 5b. 压缩多余空白
        text = re.sub(r'[ \t]+', ' ', text)        # 水平空白折叠
        text = re.sub(r'\n{3,}', '\n\n', text)       # 至多一个空行
        text = text.strip()

        return text
```

### 与原版对比

| 特性 | 原版 | 新版 |
|------|------|------|
| 标题 `<h1>`-`<h6>` | ✅ h1-h4 | ✅ h1-h6（含合并逻辑） |
| 粗体/斜体 | ✅ | ✅ |
| 链接 | ✅ | ✅ |
| 图片处理 | ✅ 非 base64 | ✅ 非 base64 + alt |
| 代码块 `<pre>` `<code>` | ❌ | ✅ 带语言标注 |
| 行内代码 `` `<code>` `` | ❌ | ✅ |
| 无序列表 `<ul><li>` | 仅独立 `<li>` | ✅ 嵌套处理 |
| 有序列表 `<ol><li>` | ❌ | ✅ 自动编号 |
| 引用 `<blockquote>` | ❌ | ✅ 每行 `>` 前缀 |
| 表格 `<table>` | ❌ | ✅ |
| 分割线 `<hr>` | ❌ | ✅ |
| 删除线 `<del>` `<s>` | ❌ | ✅ |
| base64 图片移除 | ✅ 单阶段 | ✅ 三阶段安全网 |
| HTML 实体解码 | ✅ | ✅ |
| 空白整理 | ✅ | ✅ |

### 实现说明

1. **无第三方依赖**：仅用 `re` 标准库，不引入 `html.parser` 或 `beautifulsoup4`
2. **分阶段流水线**：块级→内联→清理→整理，顺序保证嵌套正确性
3. **向后兼容**：所有原版支持的标签行为不变，仅扩展新标签支持
4. **通用性**：不依赖 Apple Notes 特定 HTML 结构，可处理任意来源的 HTML

## Chunking 改进方案：HeadingChunker

### 方案

新增 Markdown 标题感知 Chunker，按 `#`、`##`、`###` 作为语义切分边界。

### 核心逻辑

1. 按标题层级切分文档为语义段
2. 每个段内容 ≤ max_size 时作为一个完整 chunk
3. 超过 max_size 时降级使用 RecursiveCharacterChunker 二次切分
4. 子 chunk 继承父标题前缀，保留上下文

### 参数

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| levels | [1, 2, 3] | H1-H3 作为切分边界 |
| max_size | 1024 字符 | 单 chunk 上限 |
| overlap | 100 字符 | 超长段二次切分时的重叠 |
| min_size | 200 字符 | 过短的相邻 chunk 合并 |

---

## System prompt 同源 chunks 合并

### 方案选择

在 `build_rag_prompt()` 中按 `doc_title` 分组，同源 chunk 内容按 chunk_index 排序后拼接，输出单个 `[来源: X]` 块。

### 实现要点

```python
# build_rag_prompt() 中新增合并逻辑
merged = {}
for r in sorted(results, key=lambda x: getattr(x, 'chunk_index', 0)):
    merged.setdefault(r.doc_title, []).append(r.content)
materials = [{"doc_title": k, "content": "\n\n".join(v)} for k, v in merged.items()]
```

---

## 已完成讨论

| 议题 | 决策 |
|------|------|
| HTML→Markdown 转换增强 | 五阶段流水线，覆盖 12 种标签 |
| Chunking 改进 | 新增 HeadingChunker，按 H1-H3 边界切分 |
| FTS5 中文分词 | jieba 分词 |
| 同源 chunks 合并 | build_rag_prompt() 中按 doc_title 合并 |

## 相关文件

- `zrag/ingest/chunking/paragraph.py` — ParagraphChunker 实现
- `zrag/ingest/chunking/registry.py` — chunker 注册与组合
- `zrag/store/sqlite_store.py` — FTS5 建表和查询
- `zrag/retrieval/retriever.py` — 混合检索与 RRF
- `zrag/prompts/chat_system.j2` — system prompt 模板
- `export_notes.py` — NotesExporter._html_to_markdown()

---

## 实施计划

### 实现顺序

| 序号 | 文件 | 改动内容 |
|------|------|----------|
| 1 | `export_notes.py` | `_html_to_markdown()` 五阶段增强 |
| 2 | `zrag/ingest/chunking/heading.py`（新增） | `HeadingChunker` 实现 |
| 3 | `zrag/ingest/chunking/registry.py` | mac_notes 配置改为 `CompositeChunker(HeadingChunker, RecursiveCharacterChunker)` |
| 4 | `zrag/store/sqlite_store.py` | jieba `_tokenize_text()` + FTS5 写入/查询 |
| 5 | `zrag/models/retrieval.py` | `SearchResult.chunk_index` 字段 |
| 6 | `zrag/retrieval/retriever.py` | `_build_results()` 传递 `chunk_index` |
| 7 | `zrag/retrieval/prompt_builder.py` | 同源 chunks 合并 |
| 8 | `requirements.txt` | 新增 jieba |
| 9 | 测试 | 各模块单元测试更新/新增 |

### 验证步骤

1. 清空 zrag.db（chunks、processed_docs、ingest_tasks）和 ChromaDB
2. 重新运行导出 → 重写后的 Markdown 格式质量检查
3. 全量摄入，验证 chunks 数量减少且平均大小提升（114→300+字符）
4. ChromaDB embeddings 数量与 chunks 一致
5. 用中文查询测试检索效果

---

## 验证结果

优化后 system prompt 分析：

**改进确认**：同源合并生效（`[来源: etcd mvcc]` 从 4 块合并为 1 块）、chunk 平均大小显著提升、中文检索召回完整。

**遗留问题**：
1. `[来源: ]` 空块 — 存在 doc_title 为空的 chunk
2. `[来源: etcd设计思想]` 仅有标题 — 该来源只召回了 header chunk
3. 中文空格（暂不解决）

---

## 日志验证新发现

### 问题 4：Path A（FTS5 关键词检索）始终为 0

三次查询日志显示 `path_a=0`，FTS5 BM25 检索无任何结果。

**根因**：jieba 分词后的索引中中文以独立令牌存储（如"设计"+"思想"），但 `search_fts5()` 中查询未经过 jieba 分词，`unicode61` tokenizer 将查询中文视为一个整体令牌，无法匹配。

**修复**：确保 `search_fts5()` 中对 query 调用 `_tokenize_text()`。

### 问题 5：Path C 空 metadata + 空 doc_title

日志中出现 `Path C fallback: metadata_keys=[]` 和 `Empty doc_title` 警告。

**三个子根因**：

| 子问题 | 根因 | 修复 |
|--------|------|------|
| Chunker `doc_title=None` | `dict.get("title", "")` 对 null 值返回 None 而非 "" | 改为 `(data.get("title") or "")` |
| Path C 空壳 SearchResult | `content=''` + 空 metadata 被传入 prompt | Path C 改为 `continue`（跳过） |
| `vector_store.py` 掩盖 None | `metadatas[i] or {}` 静默替换 | 移除 `or {}`，记录 WARNING |

### 问题 6：HeadingChunker 首段孤立短 chunk

`etcd设计思想` 首段仅 13 字符（`# etc d 设计 思想`），chunks 为空时无法合并，直接创建为独立 chunk。

**根因**：`min_size` 合并逻辑在 `chunks` 为空（第一个 section）时无前段可合并。

**修复**：首段 < min_size 时，缓存为前缀，合并到下一段。

---

## 摄入任务后端进度问题

来源：原 `docs/ingest-backend-issues.md`（该文件已归档移除）

### 问题 A：任务状态切换过早

点击摄入后，用户尚未执行导出脚本，API 已返回 `processing`（`total=0, processed=0`）。

**根因**：`TaskManager._run()` 在 `pipeline.run()` 开始时立即将状态设为 `PROCESSING`，但 pipeline 第一步就是阻塞等待 `result.json`。

### 问题 B：task.total 始终为 0

`result.json` 就绪、开始逐篇处理后，`task.total` 仍为 0，前端无法展示百分比进度。

**根因**：`pipeline.run()` 中 `report.total = len(all_docs)` 仅记录在内部报告上，从未回写到 `IngestTask.total`。

### 修复决策

仅实施改动 1（`on_total_known` 回调）：在 `pipeline.run()` 新增可选回调参数，`fetch_batch()` 完成后通知 `TaskManager` 更新 `task.total`。改动 2（延迟状态切换）后续再议。

---

## Chunk content 标题层级路径

### 问题

每个 chunk 的 `content` 仅包含段落正文，FTS5 索引无法覆盖标题中的关键词。例如搜索"mvcc"时，正文中无此词但在标题中有的 chunk 无法被 FTS5 召回。

### 设计

HeadingChunker 遍历 section 时维护 `heading_stack`（按标题层级更新）。生成 chunk 时将当前 stack 拼接为前缀：

```
改前: "type keyIndex struct { ... }"
改后: "etcd mvcc > 整体架构 > treeIndex\n\ntype keyIndex struct { ... }"
```

### 实现

- `heading_stack` 数组存储 `(level, title_text)` 元组
- 遇到新标题时清空 >= 当前层级的所有条目，push 新标题
- 构建 `heading_path = doc_title + " > " + " > ".join(各层级标题)`
- 子 chunk（超长段降级）在原有 `# heading_line` 基础上再叠加 heading_path

---

## FTS5 查询 token 过滤

### 问题

jieba 分词后 token 数量过多（15 个），FTS5 隐式 AND 要求全部匹配。其中"我""想""在""时"等单字词在目标文档中不存在，导致零匹配。

### 设计

分词后过滤短 token：非 ASCII 且长度 < 2 的丢弃。保留英文 token（如 etcd、mvcc）和长度 >= 2 的中文词（如 更新、操作）。

```
改前: 我 想 知道 etcd 在 执行 更新 操作 时 mvcc 是 如何 进行 工作 的  (15 tokens)
改后: 知道 etcd 执行 更新 操作 mvcc 如何 进行 工作  (9 tokens)
```

## 遗留问题

| 问题 | 状态 |
|------|:--:|
| Path A 仍为 0 | token 过滤后 AND 匹配仍太严格，需进一步降低门槛 |
| 标题路径冗余 | doc_title = H1 时出现 `etcd mvcc > etcd mvcc` 重复 |
