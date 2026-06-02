from dataclasses import dataclass


@dataclass
class RawDocument:
    source_id: str
    source_type: str
    content: str
    content_hash: str
    metadata: dict | None = None


@dataclass
class Chunk:
    chunk_id: str
    source_id: str
    source_type: str
    doc_title: str
    content: str
    chunk_index: int
