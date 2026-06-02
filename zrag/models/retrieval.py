from dataclasses import dataclass


@dataclass
class SearchResult:
    chunk_id: str
    content: str
    doc_title: str
    source_id: str
    source_type: str
    score: float
