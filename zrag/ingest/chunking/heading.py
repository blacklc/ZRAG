"""zrag.ingest.chunking.heading — 按 Markdown 标题分块策略"""

import re

from zrag.ingest.chunking.base import ChunkingStrategy
from zrag.ingest.chunking.recursive import RecursiveCharacterChunker
from zrag.models.document import RawDocument, Chunk


class HeadingChunker(ChunkingStrategy):
    """按 Markdown 标题分块策略

    将文档按 H1/H2/H3 标题切分为多个 Chunk。
    若无标题则回退到 RecursiveCharacterChunker。
    超长段（> max_size）降级到 RecursiveCharacterChunker 二次切分，
    并继承标题前缀。过短段（< min_size）合并到相邻 chunk。

    @param levels: 作为切分边界的标题级别, defaults to [1, 2, 3]
    @type  levels: list[int], optional
    @param max_size: 单个 Chunk 最大字符数, defaults to 1024
    @type  max_size: int, optional
    @param min_size: 单个 Chunk 最小字符数, defaults to 200
    @type  min_size: int, optional
    @param overlap: 相邻 Chunk 之间的重叠字符数, defaults to 100
    @type  overlap: int, optional
    """

    HEADING_PATTERN = re.compile(r'^(#{1,3})\s+', re.MULTILINE)

    def __init__(self, levels: list[int] = None, max_size: int = 1024,
                 min_size: int = 200, overlap: int = 100):
        if levels is None:
            levels = [1, 2, 3]
        self.levels = sorted(levels)
        self.max_size = max_size
        self.min_size = min_size
        self.overlap = overlap

    def _resolve_title(self, document) -> str:
        """解析文档标题，保证非空

        优先级: metadata.title -> fallback(source_type_source_id)
        """
        title = (document.metadata.get("title") or "") if document.metadata else ""
        if not title:
            title = f"{document.source_type}_{document.source_id}"
        return title

    def chunk(self, document: RawDocument) -> list[Chunk]:
        """将原始文档按 Markdown 标题切分为多个 Chunk

        @param document: 待分块的原始文档
        @type  document: RawDocument

        @return: 分块后的 Chunk 列表
        @type:   list[Chunk]
        """
        if not document.content.strip():
            return []

        # 查找所有匹配指定级别的标题位置
        matches = list(self.HEADING_PATTERN.finditer(document.content))
        valid_matches = [
            m for m in matches
            if len(m.group(1)) in self.levels
        ]
        valid_matches.sort(key=lambda m: m.start())

        if not valid_matches:
            # 无标题，回退到 RecursiveCharacterChunker
            fallback = RecursiveCharacterChunker(
                max_size=self.max_size, overlap=self.overlap
            )
            return fallback.chunk(document)

        # 构建分片列表
        sections = []
        doc_title = self._resolve_title(document)
        heading_stack = []

        # 首个标题之前的内容作为独立分片
        first_heading_start = valid_matches[0].start()
        if first_heading_start > 0:
            pre_content = document.content[:first_heading_start].strip()
            if pre_content:
                sections.append({
                    'content': pre_content,
                    'heading_line': '',
                    'heading_path': doc_title,
                })

        # 按标题位置切分
        for i, match in enumerate(valid_matches):
            heading_start = match.start()

            # 当前标题段落的结束位置 = 下一个标题的起始位置（或文档末尾）
            if i + 1 < len(valid_matches):
                section_end = valid_matches[i + 1].start()
            else:
                section_end = len(document.content)

            section_content = document.content[heading_start:section_end].strip()
            if not section_content:
                continue

            # 提取标题行（分片内容的第一行）
            first_newline = section_content.find('\n')
            if first_newline == -1:
                heading_line = section_content.strip()
            else:
                heading_line = section_content[:first_newline].strip()

            # 更新标题层级路径
            heading_match = re.match(r'^(#{1,3})\s+(.*)', heading_line)
            if heading_match:
                level = len(heading_match.group(1))
                title_text = heading_match.group(2).strip()
                # 栈中移除同级及更深层级的标题，再推入当前标题
                heading_stack = [(lvl, txt) for lvl, txt in heading_stack if lvl < level]
                heading_stack.append((level, title_text))
                heading_path = doc_title + ' > ' + ' > '.join(t for _, t in heading_stack)
            else:
                heading_path = doc_title

            sections.append({
                'content': section_content,
                'heading_line': heading_line,
                'heading_path': heading_path,
            })

        # 将分片转换为 Chunk
        chunks = []
        idx = 0

        pending_prefix = ""

        for section in sections:
            content = section['content']
            heading_line = section['heading_line']
            heading_path = section['heading_path']

            if len(content) > self.max_size:
                if pending_prefix:
                    content = pending_prefix + '\n\n' + content
                    pending_prefix = ''
                # 超长分片：降级到 RecursiveCharacterChunker 二次切分
                sub_raw = RawDocument(
                    source_id=document.source_id,
                    source_type=document.source_type,
                    content=content,
                    content_hash='',
                    metadata=document.metadata,
                )
                sub_chunker = RecursiveCharacterChunker(
                    max_size=self.max_size, overlap=self.overlap
                )
                sub_chunks = sub_chunker.chunk(sub_raw)

                for j, sub in enumerate(sub_chunks):
                    if j > 0 and heading_path:
                        sub_content = f'{heading_path}\n\n{heading_line}\n\n{sub.content}'
                    else:
                        sub_content = sub.content

                    chunks.append(Chunk(
                        chunk_id=f'{document.source_id}_chunk_{idx}',
                        source_id=document.source_id,
                        source_type=document.source_type,
                        doc_title=doc_title,
                        content=sub_content,
                        chunk_index=idx,
                    ))
                    idx += 1

            elif len(content) < self.min_size:
                # 过短分片：仅当前一个 chunk 已达到 min_size 时才合并
                if (chunks
                        and len(chunks[-1].content) >= self.min_size):
                    prev = chunks[-1]
                    chunks[-1] = Chunk(
                        chunk_id=prev.chunk_id,
                        source_id=prev.source_id,
                        source_type=prev.source_type,
                        doc_title=prev.doc_title,
                        content=prev.content + '\n\n' + heading_path + '\n\n' + content,
                        chunk_index=prev.chunk_index,
                    )
                else:
                    pending_prefix = (pending_prefix + '\n\n' + heading_path + '\n\n' + content).strip()

            else:
                # 正常分片
                if pending_prefix:
                    content = pending_prefix + '\n\n' + content
                    pending_prefix = ''
                chunks.append(Chunk(
                    chunk_id=f'{document.source_id}_chunk_{idx}',
                    source_id=document.source_id,
                    source_type=document.source_type,
                    doc_title=doc_title,
                    content=f'{heading_path}\n\n{content}',
                    chunk_index=idx,
                ))
                idx += 1

        # 处理末尾残留的过短内容
        if pending_prefix:
            if chunks:
                prev = chunks[-1]
                chunks[-1] = Chunk(
                    chunk_id=prev.chunk_id,
                    source_id=prev.source_id,
                    source_type=prev.source_type,
                    doc_title=prev.doc_title,
                    content=prev.content + '\n\n' + pending_prefix,
                    chunk_index=prev.chunk_index,
                )
            else:
                chunks.append(Chunk(
                    chunk_id=f'{document.source_id}_chunk_{idx}',
                    source_id=document.source_id,
                    source_type=document.source_type,
                    doc_title=doc_title,
                    content=pending_prefix,
                    chunk_index=idx,
                ))

        return chunks
