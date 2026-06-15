#!/usr/bin/env python3
"""macOS 备忘录导出脚本

在宿主机（macOS）上执行，通过 AppleScript 调用 Notes.app
将笔记导出为 JSON 文件，供容器内的 MacNotesSource 读取。

用法:
    python3 export_notes.py <task_id>
    python3 export_notes.py <task_id> --tag "技术笔记"

依赖:
    - macOS（需已登录 iCloud 并启用 Notes.app）
    - Python 3.10+
"""

import argparse
import hashlib
import json
import logging
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---- 日志配置（与项目统一格式） ----
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(thread)d %(funcName)s:%(lineno)d %(message)s"
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(logging.Formatter(LOG_FORMAT))
logger = logging.getLogger("zrag.export_notes")
logger.addHandler(_handler)
logger.setLevel(logging.INFO)


class NotesExporter:
    """备忘录导出器

    负责从 MAC OS 备忘录应用获取文章内容并导出为 Markdown 格式。
    使用 AppleScript 与备忘录应用交互，支持导出多篇文章。
    支持按文章名称或标签筛选。
    自动移除 HTML 中的 base64 图片数据。
    """

    _BASE64_PLACEHOLDER = ''

    def _html_to_markdown(self, html_content: str) -> str:
        """将 HTML 内容转换为 Markdown，同时移除 base64 图片

        五阶段流水线处理：
        阶段 A: HTML 预处理 — 移除 base64 <img> 标签
        阶段 B: 块级元素转换 — <pre><code>, <ol>/<ul>, <blockquote>, <table>, <hr>
        阶段 C: 内联元素转换 — <b>/<strong>, <i>/<em>, <del>, <code>, <img>, <a>
        阶段 D: 标题与结构 — <h1>-<h6>, <p>, <br>, <div>, <li>
        阶段 E: 实体解码与清理 — 实体解码，剩余标签移除，空白规整
        阶段 F: Markdown 安全网 — 移除残留 base64 引用

        @param html_content: HTML 格式内容
        @type  html_content: str
        @return: 已移除 base64 图片的 Markdown 格式内容
        @rtype:  str
        """
        placeholder = self._BASE64_PLACEHOLDER

        # === Phase A: HTML 预处理 — 移除 base64 <img> 标签 ===
        md = re.sub(
            r'<img[^>]*src="data:image/[^"]*;base64,[^"]*"[^>]*>',
            placeholder,
            html_content
        )

        # === Phase B: 块级元素转换 ===

        # B1: <pre><code> → 代码围栏
        md = re.sub(
            r'<pre><code>(.*?)</code></pre>',
            r'```\n\1\n```',
            md,
            flags=re.DOTALL
        )

        # B2: <ol> → 有序列表
        def _replace_ol(match):
            items = re.findall(r'<li>(.*?)</li>', match.group(0), re.DOTALL)
            return '\n'.join(f'{i+1}. {item}' for i, item in enumerate(items))

        md = re.sub(r'<ol>(.*?)</ol>', _replace_ol, md, flags=re.DOTALL)

        # B3: <ul> → 无序列表
        def _replace_ul(match):
            items = re.findall(r'<li>(.*?)</li>', match.group(0), re.DOTALL)
            return '\n'.join(f'- {item}' for item in items)

        md = re.sub(r'<ul>(.*?)</ul>', _replace_ul, md, flags=re.DOTALL)

        # B4: <blockquote> → 引用
        md = re.sub(
            r'<blockquote>(.*?)</blockquote>',
            r'> \1',
            md,
            flags=re.DOTALL
        )

        # B5: <table> → Markdown 表格
        def _replace_table(match):
            rows = re.findall(r'<tr>(.*?)</tr>', match.group(0), re.DOTALL)
            md_rows = []
            for i, row in enumerate(rows):
                cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.DOTALL)
                md_row = '| ' + ' | '.join(cells) + ' |'
                md_rows.append(md_row)
                if i == 0:
                    md_rows.append('| ' + ' | '.join(['---'] * len(cells)) + ' |')
            return '\n'.join(md_rows)

        md = re.sub(r'<table>(.*?)</table>', _replace_table, md, flags=re.DOTALL)

        # B6: <hr> → 水平分割线
        md = re.sub(r'<hr\s*/?>', '\n---\n', md)

        # === Phase C: 内联元素转换 ===

        # C1: <b>/<strong> → **粗体**
        md = re.sub(r'<(b|strong)>(.*?)</\1>', r'**\2**', md)
        # C2: <i>/<em> → *斜体*
        md = re.sub(r'<(i|em)>(.*?)</\1>', r'*\2*', md)
        # C3: <del> → ~~删除内容~~
        md = re.sub(r'<del>(.*?)</del>', r'~~\1~~', md)
        # C4: <code>（内联，在 <pre><code> 之后处理）
        md = re.sub(r'<code>(.*?)</code>', r'`\1`', md)
        # C5: <img>（含 alt 属性提取）
        def _img_sub(m):
            src = m.group(1)
            alt_m = re.search(r'alt="([^"]*)"', m.group(0))
            alt = alt_m.group(1) if alt_m else ''
            return f'![{alt}]({src})'
        md = re.sub(r'<img[^>]*src="([^"]*)"[^>]*>', _img_sub, md)
        # C6: <a> → [text](url)
        md = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', r'[\2](\1)', md)

        # === Phase D: 标题与结构 ===

        def merge_h_tags(match):
            h_tags = re.findall(r'<h([1-6])>(.*?)</h\1>', match.group(0))
            if h_tags:
                level = h_tags[0][0]
                content_parts = []
                for _, tag_content in h_tags:
                    clean_content = re.sub(r'<br\s*/?>', '', tag_content).strip()
                    if clean_content:
                        content_parts.append(clean_content)
                if content_parts:
                    content = ' '.join(content_parts)
                    return f'{"#" * int(level)} {content}'
            return match.group(0)

        md = re.sub(r'<div>((?:<h[1-6]>.*?</h[1-6]>)+)</div>', merge_h_tags, md)

        md = re.sub(r'<br\s*/?>', '\n', md)
        md = re.sub(r'<p>(.*?)</p>', r'\1\n\n', md)
        # <h1>-<h6>（含可选属性）
        md = re.sub(r'<h1[^>]*>(.*?)</h1>', r'# \1\n', md)
        md = re.sub(r'<h2[^>]*>(.*?)</h2>', r'## \1\n', md)
        md = re.sub(r'<h3[^>]*>(.*?)</h3>', r'### \1\n', md)
        md = re.sub(r'<h4[^>]*>(.*?)</h4>', r'#### \1\n', md)
        md = re.sub(r'<h5[^>]*>(.*?)</h5>', r'##### \1\n', md)
        md = re.sub(r'<h6[^>]*>(.*?)</h6>', r'###### \1\n', md)
        md = re.sub(r'<div>(.*?)</div>', r'\1\n', md)

        # 残留 <li>（<ol>/<ul> 已处理，此处捕获游离项）
        md = re.sub(r'<li>(.*?)</li>', r'- \1\n', md)

        # === Phase E: 实体解码与清理 ===

        md = re.sub(r'<[^>]+>', '', md)
        md = re.sub(r'&\n', '', md)
        md = re.sub(r'&lt;', '<', md)
        md = re.sub(r'&gt;', '>', md)
        md = re.sub(r'&amp;', '&', md)
        md = re.sub(r'&nbsp;', ' ', md)
        md = re.sub(r'\n{3,}', '\n\n', md)
        md = md.strip()

        # === Phase F: Markdown 安全网 — 移除残留 base64 引用 ===
        md = re.sub(
            r'!\[\s*\]\(data:image/[^);]*;base64,[^)]*\)',
            placeholder,
            md
        )

        return md

    def _sanitize_note_name(self, note_name: str) -> str:
        """清理文章名称中的多余空白和特殊字符

        用于解决备忘录中文章名称与搜索时输入的名称格式不完全匹配的问题。
        例如：多余的空格、特殊空白字符等。

        @param note_name: 原始文章名称
        @type  note_name: str
        @return: 清理后的文章名称
        @rtype:  str
        """
        # 移除多余空白字符（保留单个空格）
        note_name = re.sub(r'\s+', ' ', note_name)
        # 移除首尾空白
        note_name = note_name.strip()
        return note_name

    def _normalize_for_matching(self, note_name: str) -> str:
        """标准化文章名称用于匹配搜索

        移除所有空白字符并转为小写，用于模糊匹配。

        @param note_name: 原始文章名称
        @type  note_name: str
        @return: 标准化后的名称
        @rtype:  str
        """
        # 移除所有空白字符并转为小写
        return re.sub(r'\s+', '', note_name).lower()

    def _find_note_by_fuzzy_match(self, note_name: str) -> Optional[str]:
        """通过模糊匹配查找备忘录文章

        当精确匹配失败时，使用标准化后的名称进行模糊匹配。

        @param note_name: 文章名称
        @type  note_name: str
        @return: 匹配到的实际文章名称，匹配失败时返回 None
        @rtype:  Optional[str]
        """
        script = '''
        tell application "Notes"
            set allNotes to every note
            return name of allNotes
        end tell
        '''

        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=60
            )
            all_names = result.stdout.strip()
            if not all_names or all_names == "{}":
                return None

            target_normalized = self._normalize_for_matching(note_name)

            # 遍历所有文章名称进行模糊匹配
            for name in all_names.split(","):
                name = name.strip()
                if self._normalize_for_matching(name) == target_normalized:
                    return name

            return None
        except Exception:
            logger.exception("模糊匹配失败: note_name=%s", note_name)
            return None

    def _get_note_content(self, note_name: str) -> Optional[str]:
        """通过 AppleScript 获取备忘录文章内容

        @param note_name: 文章名称
        @type  note_name: str
        @return: 文章内容，文章不存在时返回 None
        @rtype:  Optional[str]
        """
        # 先尝试清理后的精确名称
        sanitized_name = self._sanitize_note_name(note_name)

        script = f'''
        tell application "Notes"
            set theNote to first note whose name is "{sanitized_name}"
            if exists theNote then
                return body of theNote
            else
                return "NOTE_NOT_FOUND"
            end if
        end tell
        '''

        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=30
            )
            content = result.stdout.strip()

            if content == "NOTE_NOT_FOUND":
                # 尝试模糊匹配
                matched_name = self._find_note_by_fuzzy_match(note_name)
                if matched_name:
                    return self._get_note_content(matched_name)
                return None
            return content
        except Exception:
            logger.exception("获取笔记内容失败(将尝试模糊匹配): note_name=%s", note_name)
            # 尝试模糊匹配作为最后的备选方案
            matched_name = self._find_note_by_fuzzy_match(note_name)
            if matched_name:
                return self._get_note_content(matched_name)
            return None

    def get_notes_by_tag_or_folder(self, tag_or_folder: str) -> list[str]:
        """通过 AppleScript 获取指定标签或文件夹下的所有文章名称

        @param tag_or_folder: 标签或文件夹名称
        @type  tag_or_folder: str
        @return: 文章名称列表
        @rtype:  list[str]
        """
        script = f'''
        tell application "Notes"
            try
                set targetFolder to folder "{tag_or_folder}"
                return name of every note of targetFolder
            on error
                set noteList to every note
                set matchingNotes to {{}}
                repeat with eachNote in noteList
                    try
                        set noteTags to tags of eachNote
                        if noteTags contains "{tag_or_folder}" then
                            set end of matchingNotes to name of eachNote
                        end if
                    end try
                end repeat
                return matchingNotes as string
            end try
        end tell
        '''

        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=60
            )
            output = result.stdout.strip()

            if not output or output == "{}":
                return []
            return [name.strip() for name in output.split(",")]
        except Exception:
            logger.exception("按标签/文件夹获取笔记列表失败: tag_or_folder=%s", tag_or_folder)
            return []

    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名中的非法字符

        @param filename: 原始文件名
        @type  filename: str
        @return: 清理后的文件名
        @rtype:  str
        """
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, "_")
        return filename.strip()

    def _get_all_notes_names(self) -> list[str]:
        """获取所有笔记名称"""
        script = '''
        tell application "Notes"
            set allNoteNames to {}
            repeat with f in folders
                repeat with n in notes of f
                    try
                        set end of allNoteNames to name of n
                    end try
                end repeat
            end repeat
            return allNoteNames as string
        end tell
        '''
        try:
            result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=60)
            output = result.stdout.strip()
            if not output or output == "{}":
                return []
            return [name.strip() for name in output.split(",")]
        except Exception:
            logger.exception("获取所有笔记名称失败")
            return []

    def _get_note_metadata(self, note_name: str) -> dict:
        """获取单条笔记的 id、folder、tags"""
        sanitized_name = self._sanitize_note_name(note_name)
        script = f'''
        tell application "Notes"
            try
                set theNote to first note whose name is "{sanitized_name}"
                set noteId to id of theNote
                set noteFolderName to ""
                try
                    set noteFolderName to name of container of theNote
                end try
                set noteTags to ""
                try
                    set noteTags to tags of theNote as string
                end try
                return noteId & "§§§" & noteFolderName & "§§§" & noteTags
            on error
                return "NOTE_NOT_FOUND"
            end try
        end tell
        '''
        try:
            result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=30)
            output = result.stdout.strip()
            if output == "NOTE_NOT_FOUND" or not output:
                return {"id": "", "folder": "", "tags": ""}
            parts = output.split("§§§", 2)
            return {"id": parts[0] if len(parts) > 0 else "", "folder": parts[1] if len(parts) > 1 else "", "tags": parts[2] if len(parts) > 2 else ""}
        except Exception:
            logger.exception("获取笔记元数据失败: note_name=%s", note_name)
            return {"id": "", "folder": "", "tags": ""}


# ---- 纯函数（不记录日志，只捕获异常并向上抛出） ----

def load_manifest(export_dir: Path) -> dict:
    """读取 manifest.json

    @param export_dir: 任务导出目录
    @type  export_dir: Path

    @return: manifest 字典
    @rtype:  dict

    @raises FileNotFoundError: manifest.json 不存在时抛出
    @raises json.JSONDecodeError: manifest.json 格式非法时抛出
    """
    manifest_path = export_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.json 不存在: {manifest_path}")
    try:
        with open(manifest_path, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        raise
    except OSError as e:
        raise RuntimeError(f"读取 manifest.json 失败: {manifest_path}") from e


def compute_hash(content: str) -> str:
    """计算 SHA256 哈希值

    @param content: 内容文本
    @type  content: str

    @return: SHA256 十六进制哈希字符串
    @rtype:  str
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# ---- 导出流程 ----

def _write_note_json(
    note_id: str,
    note_data: dict,
    export_dir: Path,
) -> bool:
    """将单条笔记写入 JSON 文件

    @param note_id: 笔记标识
    @type  note_id: str
    @param note_data: 笔记数据
    @type  note_data: dict
    @param export_dir: 导出目录
    @type  export_dir: Path

    @return: True 表示写入成功
    @rtype:  bool

    @raises: 不抛出 — 写入失败返回 False
    """
    # note_id 可能含非法文件名字符（如 x-coredata://...），用哈希生成安全文件名
    safe_id = compute_hash(note_id)
    note_file = export_dir / f"{safe_id}.json"
    try:
        with open(note_file, "w", encoding="utf-8") as f:
            json.dump(note_data, f, ensure_ascii=False, indent=2)
        return True
    except OSError:
        logger.exception("写入笔记文件失败: note_id=%s, file_path=%s", note_id, note_file)
        return False


def _write_result_json(
    export_dir: Path,
    task_id: str,
    expected: int,
    success: int,
) -> None:
    """写入 result.json

    @param export_dir: 导出目录
    @type  export_dir: Path
    @param task_id: 任务 ID
    @type  task_id: str
    @param expected: 计划导出数
    @type  expected: int
    @param success: 成功导出数
    @type  success: int

    @raises OSError: 文件写入失败时抛出
    """
    result = {
        "status": "ok",
        "task_id": task_id,
        "expected": expected,
        "success": success,
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }
    result_path = export_dir / "result.json"
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


def main():
    """入口函数

    所有关键节点均有日志记录，最外层有兜底异常捕获。
    """
    parser = argparse.ArgumentParser(
        description="导出 macOS Notes 备忘录为 JSON 文件"
    )
    parser.add_argument("task_id", help="摄入任务 ID（对应 manifest.json 所在目录）")
    parser.add_argument("--tag", help="按标签过滤，只导出包含指定标签的笔记")
    args = parser.parse_args()

    try:
        _do_export(args)
    except SystemExit:
        raise
    except Exception:
        logger.exception("导出过程发生未预期异常")
        sys.exit(1)


def _do_export(args):
    """执行导出流程

    @param args: argparse 解析后的参数对象
    @type  args: argparse.Namespace

    @raises SystemExit: 预期内的错误场景（目录不存在、manifest 缺失等）直接退出
    """
    logger.info("===== 导出开始 =====")
    logger.info("task_id=%s tag=%s", args.task_id, args.tag or "(无)")

    base_dir = Path(__file__).resolve().parent
    export_dir = base_dir / "data" / "pro" / "export" / args.task_id
    logger.info("导出目录: %s", export_dir)

    if not export_dir.exists():
        logger.error("导出目录不存在: %s", export_dir)
        sys.exit(1)

    # ---- 加载 manifest ----
    logger.info("加载 manifest.json...")
    try:
        manifest = load_manifest(export_dir)
        logger.info("manifest.json 加载成功 (processed_docs=%d)",
                    len(manifest.get("processed_docs", [])))
    except FileNotFoundError as e:
        logger.error("%s", e)
        sys.exit(1)
    except (json.JSONDecodeError, RuntimeError) as e:
        logger.error("manifest.json 解析失败: %s", e)
        sys.exit(1)

    processed = {
        d["source_id"]: d["content_hash"]
        for d in manifest.get("processed_docs", [])
    }

    # ---- 获取笔记名称列表（使用 NotesExporter） ----
    exporter = NotesExporter()
    logger.info("正在从 Notes.app 获取笔记 (tag=%s)...", args.tag or "(无)")

    if args.tag:
        note_names = exporter.get_notes_by_tag_or_folder(args.tag)
    else:
        note_names = exporter._get_all_notes_names()

    logger.info("获取笔记名称 (总数=%d, tag=%s)", len(note_names), args.tag or "(无)")

    if not note_names:
        logger.warning("没有获取到任何笔记，导出结束")
        _write_result_json(export_dir, args.task_id, 0, 0)
        return

    # ---- 逐篇导出 ----
    total_notes = len(note_names)
    expected = 0
    success = 0
    skipped = 0

    for idx, note_name in enumerate(note_names, 1):
        html_content = exporter._get_note_content(note_name)
        if html_content is None:
            logger.warning("[%d/%d] 笔记内容获取失败: %s (tag=%s)", idx, total_notes, note_name, args.tag or "(无)")
            continue

        meta = exporter._get_note_metadata(note_name)
        note_id = meta.get("id", "")
        note_folder = meta.get("folder", "")

        markdown = exporter._html_to_markdown(html_content)
        note_hash = compute_hash(markdown)

        if note_id and note_id in processed and processed[note_id] == note_hash:
            skipped += 1
            logger.debug("[%d/%d] 跳过未变更: %s", idx, total_notes, note_name)
            continue

        expected += 1
        logger.info("[%d/%d] 导出: %s (folder=%s)",
                    idx, total_notes, note_name, note_folder)

        note_data = {
            "source_id": note_id,
            "source_type": "mac_notes",
            "content": markdown,
            "content_hash": note_hash,
            "metadata": {
                "title": note_name,
                "folder": note_folder,
            },
        }

        if _write_note_json(note_id, note_data, export_dir):
            success += 1
        else:
            logger.warning("[%d/%d] 笔记写入失败: %s (tag=%s, folder=%s)", idx, total_notes, note_name, args.tag or "(无)", note_folder)

    # ---- 写入 result.json ----
    logger.info("写入 result.json...")
    try:
        _write_result_json(export_dir, args.task_id, expected, success)
        logger.info("result.json 写入成功")
    except OSError as e:
        logger.exception("写入 result.json 失败: %s", e)
        sys.exit(1)

    logger.info("===== 导出完成 =====")
    logger.info("统计: 总数=%d 跳过=%d 计划=%d 成功=%d 失败=%d",
                total_notes, skipped, expected, success, expected - success)


if __name__ == "__main__":
    main()
