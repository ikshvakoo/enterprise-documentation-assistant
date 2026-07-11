from dataclasses import asdict
from dataclasses import dataclass
from typing import Any


@dataclass
class SourceDocument:
    """A normalized source document before it is split into search chunks.

    One SourceDocument represents one logical source unit, such as a Jira issue,
    a release-note page/document, or a test-case worksheet.
    """

    doc_id: str
    source_type: str
    title: str
    body: str
    source_path: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Convert the dataclass into a JSON-serializable dictionary."""
        return asdict(self)


@dataclass
class Chunk:
    """A smaller searchable piece of a SourceDocument.

    Retrieval happens at chunk level so search can return the exact passage that
    supports an answer instead of returning an entire long document.
    """

    chunk_id: str
    doc_id: str
    source_type: str
    title: str
    text: str
    source_path: str
    metadata: dict[str, Any]
    token_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert the chunk into a JSON-serializable dictionary for index storage."""
        return asdict(self)


@dataclass
class SearchResult:
    """A ranked retrieval result containing the matched chunk and its score."""

    score: float
    chunk: Chunk
    rank: int = 0


@dataclass
class SearchFilters:
    """Optional metadata filters applied before ranking chunks."""

    source_type: str | None = None
    issue_type: str | None = None
    status: str | None = None
    priority: str | None = None
    component: str | None = None
    fix_version: str | None = None
    issue_key: str | None = None

    def has_filters(self) -> bool:
        """Return True when at least one user-facing filter has been supplied."""
        return any(
            [
                self.source_type,
                self.issue_type,
                self.status,
                self.priority,
                self.component,
                self.fix_version,
                self.issue_key,
            ]
        )
