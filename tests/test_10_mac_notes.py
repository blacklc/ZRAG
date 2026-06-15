"""切片 10 — MacNotesSource 单元测试（文件桥接模式）

旧版 MacNotesSource 通过 AppleScript 直接获取笔记数据；
新版改为轮询宿主机导出的 JSON 文件目录。

测试内容（文件桥接模式）:
  - export_dir 未设置 -> ValueError
  - result.json + note JSON 文件 -> 正确构造 RawDocument
  - manifest.json 和 result.json 被跳过
  - batch_size 参数分批次生效
  - result.json status != "ok" -> ValueError
  - source_type -> "mac_notes"
  - total_count -> result.json 的 "success" 值
"""

import hashlib
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from zrag.ingest.sources.mac_notes import MacNotesSource
from zrag.models.document import RawDocument


def _make_note_json(note_id: str, content: str, name: str = "") -> dict:
    """生成笔记的 JSON 字典（与导出脚本格式一致）

    @param note_id: 笔记 ID (如 NOTE:xxx)
    @type  note_id: str
    @param content: Markdown 内容
    @type  content: str
    @param name: 笔记名称 (写入 metadata)
    @type  name: str

    @return: 符合导出格式的 dict
    @rtype:  dict
    """
    return {
        "source_id": note_id,
        "source_type": "mac_notes",
        "content": content,
        "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "metadata": {"name": name} if name else {},
    }


class TestMacNotesSource:
    """MacNotesSource 测试 — 文件桥接模式"""

    # --------------------------------------------------
    # 1. source_type
    # --------------------------------------------------

    def test_source_type(self):
        """source_type 应返回 'mac_notes'"""
        source = MacNotesSource()
        assert source.source_type == "mac_notes"

    # --------------------------------------------------
    # 2. export_dir 未设置 -> ValueError
    # --------------------------------------------------

    def test_fetch_batch_raises_without_export_dir(self):
        """export_dir 未设置时 fetch_batch 抛出 ValueError"""
        source = MacNotesSource()
        with pytest.raises(ValueError, match="export_dir"):
            list(source.fetch_batch())

    # --------------------------------------------------
    # 3. result.json + note JSON -> RawDocument
    # --------------------------------------------------

    def test_fetch_batch_returns_raw_documents(self):
        """正确读取 result.json + note JSON，返回 RawDocument 列表"""
        with tempfile.TemporaryDirectory() as tmpdir:
            export_dir = Path(tmpdir)

            # 写入 result.json
            result_data = {
                "status": "ok",
                "task_id": "task-test",
                "expected": 2,
                "success": 2,
            }
            with open(export_dir / "result.json", "w", encoding="utf-8") as f:
                json.dump(result_data, f)

            # 写入笔记 JSON 文件
            note1 = _make_note_json("NOTE:111", "**会议记录内容**", "会议记录")
            note2 = _make_note_json("NOTE:222", "**日程安排内容**", "日程安排")
            with open(export_dir / "NOTE:111.json", "w", encoding="utf-8") as f:
                json.dump(note1, f)
            with open(export_dir / "NOTE:222.json", "w", encoding="utf-8") as f:
                json.dump(note2, f)

            source = MacNotesSource(export_dir=str(export_dir), poll_interval=0.1)
            batches = list(source.fetch_batch(batch_size=10))

            assert len(batches) == 1
            batch = batches[0]
            assert len(batch) == 2

            for doc in batch:
                assert isinstance(doc, RawDocument)
                assert doc.source_type == "mac_notes"

            assert batch[0].source_id == "NOTE:111"
            assert batch[0].content == "**会议记录内容**"
            assert batch[1].source_id == "NOTE:222"

    # --------------------------------------------------
    # 4. manifest.json 和 result.json 被跳过
    # --------------------------------------------------

    def test_skips_manifest_and_result_json(self):
        """manifest.json 和 result.json 不会被读取为笔记文档"""
        with tempfile.TemporaryDirectory() as tmpdir:
            export_dir = Path(tmpdir)

            # 写入 result.json (status ok)
            with open(export_dir / "result.json", "w", encoding="utf-8") as f:
                json.dump({"status": "ok", "success": 1}, f)

            # 写入 manifest.json (不应被读取为笔记)
            with open(export_dir / "manifest.json", "w", encoding="utf-8") as f:
                json.dump({"task_id": "t1"}, f)

            # 写入一个有效笔记
            note = _make_note_json("NOTE:001", "actual content")
            with open(export_dir / "NOTE:001.json", "w", encoding="utf-8") as f:
                json.dump(note, f)

            source = MacNotesSource(export_dir=str(export_dir), poll_interval=0.1)
            batches = list(source.fetch_batch(batch_size=10))

            assert len(batches) == 1
            assert len(batches[0]) == 1
            assert batches[0][0].source_id == "NOTE:001"

    # --------------------------------------------------
    # 5. batch_size 参数
    # --------------------------------------------------

    def test_batch_size_works(self):
        """batch_size 参数生效 — 5 篇文档, batch_size=2 -> 3 批次"""
        with tempfile.TemporaryDirectory() as tmpdir:
            export_dir = Path(tmpdir)

            with open(export_dir / "result.json", "w", encoding="utf-8") as f:
                json.dump({"status": "ok", "success": 5}, f)

            for i in range(1, 6):
                note = _make_note_json(f"NOTE:{i}", f"content_{i}")
                with open(export_dir / f"NOTE:{i}.json", "w", encoding="utf-8") as f:
                    json.dump(note, f)

            source = MacNotesSource(export_dir=str(export_dir), poll_interval=0.1)
            batches = list(source.fetch_batch(batch_size=2))

            assert len(batches) == 3
            assert len(batches[0]) == 2
            assert len(batches[1]) == 2
            assert len(batches[2]) == 1

    # --------------------------------------------------
    # 6. result.json status != "ok" -> ValueError
    # --------------------------------------------------

    def test_status_not_ok_raises_value_error(self):
        """result.json status != "ok" 时抛出 ValueError"""
        with tempfile.TemporaryDirectory() as tmpdir:
            export_dir = Path(tmpdir)

            with open(export_dir / "result.json", "w", encoding="utf-8") as f:
                json.dump({"status": "failed", "error": "export error"}, f)

            source = MacNotesSource(export_dir=str(export_dir), poll_interval=0.1)
            with pytest.raises(ValueError, match="status=failed"):
                list(source.fetch_batch())

    def test_status_missing_raises_value_error(self):
        """result.json 缺少 status 字段时抛出 ValueError"""
        with tempfile.TemporaryDirectory() as tmpdir:
            export_dir = Path(tmpdir)

            with open(export_dir / "result.json", "w", encoding="utf-8") as f:
                json.dump({"success": 0}, f)

            source = MacNotesSource(export_dir=str(export_dir), poll_interval=0.1)
            with pytest.raises(ValueError):
                list(source.fetch_batch())

    # --------------------------------------------------
    # 7. total_count
    # --------------------------------------------------

    def test_total_count_matches_success(self):
        """total_count 返回 result.json 中记录的 success 值"""
        with tempfile.TemporaryDirectory() as tmpdir:
            export_dir = Path(tmpdir)

            with open(export_dir / "result.json", "w", encoding="utf-8") as f:
                json.dump({"status": "ok", "success": 7}, f)

            source = MacNotesSource(export_dir=str(export_dir), poll_interval=0.1)
            list(source.fetch_batch(batch_size=10))

            assert source.total_count == 7

    def test_total_count_default_zero(self):
        """未调用 fetch_batch 时 total_count 为 0"""
        source = MacNotesSource()
        assert source.total_count == 0
