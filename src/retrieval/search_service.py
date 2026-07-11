from collections import Counter
from pathlib import Path

from config import DEFAULT_CHUNK_OVERLAP
from config import DEFAULT_CHUNK_WORDS
from config import INDEX_PATH
from ingestion import load_all_documents
from models import SearchFilters
from models import SearchResult
from processing import chunk_documents
from text_utils import clean_text

from .bm25 import BM25Index
from .index_io import load_index
from .index_io import save_index


class SearchService:
    """Application-facing wrapper around indexing and retrieval operations."""

    def __init__(self, index: BM25Index, index_path: Path = INDEX_PATH) -> None:
        """Hold the active index and remember where it is stored on disk."""
        self.index = index
        self.index_path = index_path

    @classmethod
    def build(
        cls,
        data_dir: Path,
        index_path: Path = INDEX_PATH,
        chunk_words: int = DEFAULT_CHUNK_WORDS,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    ) -> "SearchService":
        """Ingest source data, create chunks, build BM25, and save the index."""
        # This method is the Phase 1 pipeline in miniature:
        # files -> normalized documents -> chunks -> BM25 index -> artifact JSON.
        documents = load_all_documents(data_dir)
        chunks = chunk_documents(documents, chunk_words=chunk_words, overlap_words=chunk_overlap)
        index = BM25Index.build(chunks)
        save_index(index, index_path)
        service = cls(index=index, index_path=index_path)
        service.last_build_counts = {"documents": len(documents), "chunks": len(chunks)}
        return service

    @classmethod
    def load_or_build(cls, data_dir: Path, index_path: Path = INDEX_PATH) -> "SearchService":
        """Load the saved index, or build it if the artifact does not exist."""
        if not index_path.exists():
            return cls.build(data_dir=data_dir, index_path=index_path)
        return cls(index=load_index(index_path), index_path=index_path)

    def search(
        self,
        query: str,
        top_k: int,
        filters: SearchFilters | None = None,
        diversify: bool = True,
    ) -> list[SearchResult]:
        """Search the active index and return ranked chunks."""
        return self.index.search(query=query, top_k=top_k, filters=filters, diversify=diversify)

    def source_counts(self) -> Counter:
        """Count indexed chunks by source type for the stats command."""
        return Counter(chunk.source_type for chunk in self.index.chunks)

    def jira_issues_for_fix_version(self, fix_version: str) -> list[dict[str, object]]:
        """Return unique Jira issues assigned to a specific fix version."""
        seen: dict[str, dict[str, object]] = {}
        requested = clean_text(fix_version).lower()
        for chunk in self.index.chunks:
            if chunk.source_type != "jira":
                continue
            # Each Jira issue may produce multiple chunks. The seen dictionary
            # collapses those chunks back to one issue record.
            versions = chunk.metadata.get("fix_versions", [])
            if not isinstance(versions, list):
                continue
            if not any(clean_text(version).lower() == requested for version in versions):
                continue
            issue_key = str(chunk.metadata.get("issue_key") or chunk.doc_id)
            seen[issue_key] = {
                "issue_key": issue_key,
                "title": chunk.title,
                "issue_type": chunk.metadata.get("issue_type", ""),
                "status": chunk.metadata.get("status", ""),
                "priority": chunk.metadata.get("priority", ""),
                "components": chunk.metadata.get("components", []),
                "fix_versions": versions,
            }
        return sorted(seen.values(), key=lambda item: str(item["issue_key"]))
