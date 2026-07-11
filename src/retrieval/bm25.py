import math
from collections import Counter
from collections import defaultdict
from typing import Any

from models import Chunk
from models import SearchFilters
from models import SearchResult
from text_utils import clean_text
from text_utils import tokenize


class BM25Index:
    """A small custom BM25 index used as the Phase 1 retrieval baseline."""

    def __init__(
        self,
        chunks: list[Chunk],
        term_freqs: list[dict[str, int]],
        doc_freqs: dict[str, int],
        avg_doc_len: float,
    ) -> None:
        """Store precomputed BM25 statistics and the indexed chunks."""
        self.chunks = chunks
        self.term_freqs = term_freqs
        self.doc_freqs = doc_freqs
        self.avg_doc_len = avg_doc_len or 1.0

    @classmethod
    def build(cls, chunks: list[Chunk]) -> "BM25Index":
        """Create BM25 statistics from a list of chunks."""
        term_freqs: list[dict[str, int]] = []
        doc_freqs: dict[str, int] = defaultdict(int)
        lengths = []

        for chunk in chunks:
            # Term frequency is per chunk; document frequency counts whether a
            # term appears in each chunk at least once.
            counts = Counter(tokenize(chunk.text))
            term_freqs.append(dict(counts))
            lengths.append(sum(counts.values()))
            for term in counts:
                doc_freqs[term] += 1

        avg_doc_len = sum(lengths) / len(lengths) if lengths else 1.0
        return cls(chunks, term_freqs, dict(doc_freqs), avg_doc_len)

    def search(
        self,
        query: str,
        top_k: int = 6,
        filters: SearchFilters | None = None,
        diversify: bool = True,
    ) -> list[SearchResult]:
        """Rank chunks for a query using BM25 with optional metadata filtering."""
        query_terms = tokenize(query)
        if not query_terms:
            return []

        scores: list[tuple[float, int]] = []
        for index, chunk in enumerate(self.chunks):
            # Filtering happens before scoring so irrelevant source types or
            # release versions do not compete in the ranking.
            if filters and not chunk_matches_filters(chunk, filters):
                continue
            score = self._score(query_terms, index)
            if score > 0:
                scores.append((score, index))

        scores.sort(reverse=True, key=lambda item: item[0])
        selected = self._diversify(scores, top_k) if diversify else scores[:top_k]
        # Store the display rank on the result so downstream UI/CLI code does
        # not have to recompute it.
        return [
            SearchResult(score=score, chunk=self.chunks[index], rank=rank)
            for rank, (score, index) in enumerate(selected, start=1)
        ]

    def _diversify(self, scores: list[tuple[float, int]], top_k: int) -> list[tuple[float, int]]:
        """Prefer results from different documents before repeating one source."""
        selected: list[tuple[float, int]] = []
        seen_docs = set()
        deferred: list[tuple[float, int]] = []

        for score, index in scores:
            doc_id = self.chunks[index].doc_id
            if doc_id in seen_docs:
                deferred.append((score, index))
                continue
            selected.append((score, index))
            seen_docs.add(doc_id)
            if len(selected) >= top_k:
                return selected

        selected.extend(deferred[: top_k - len(selected)])
        return selected

    def _score(self, query_terms: list[str], index: int) -> float:
        """Calculate the BM25 relevance score for one chunk."""
        k1 = 1.5
        b = 0.75
        counts = self.term_freqs[index]
        doc_len = sum(counts.values()) or 1
        score = 0.0
        total_docs = len(self.chunks)

        for term in query_terms:
            tf = counts.get(term, 0)
            if not tf:
                continue
            df = self.doc_freqs.get(term, 0)
            # IDF rewards terms that appear in fewer chunks. The length
            # normalization below prevents long chunks from winning only because
            # they contain more words.
            idf = math.log(1 + (total_docs - df + 0.5) / (df + 0.5))
            denominator = tf + k1 * (1 - b + b * doc_len / self.avg_doc_len)
            score += idf * (tf * (k1 + 1)) / denominator
        return score

    def to_dict(self) -> dict[str, Any]:
        """Serialize the index so it can be saved as JSON."""
        return {
            "chunks": [chunk.to_dict() for chunk in self.chunks],
            "term_freqs": self.term_freqs,
            "doc_freqs": self.doc_freqs,
            "avg_doc_len": self.avg_doc_len,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BM25Index":
        """Rehydrate a BM25 index from the saved JSON structure."""
        chunks = [Chunk(**with_chunk_defaults(item)) for item in data["chunks"]]
        return cls(
            chunks=chunks,
            term_freqs=data["term_freqs"],
            doc_freqs=data["doc_freqs"],
            avg_doc_len=float(data["avg_doc_len"]),
        )


def with_chunk_defaults(item: dict[str, Any]) -> dict[str, Any]:
    """Add fields missing from older saved chunk records."""
    if "token_count" not in item:
        item = {**item, "token_count": len(tokenize(item.get("text", "")))}
    return item


def chunk_matches_filters(chunk: Chunk, filters: SearchFilters) -> bool:
    """Return True when a chunk satisfies all supplied metadata filters."""
    metadata = chunk.metadata
    if filters.source_type and chunk.source_type != filters.source_type:
        return False
    if filters.issue_key and clean_text(metadata.get("issue_key")).lower() != filters.issue_key.lower():
        return False
    if filters.issue_type and clean_text(metadata.get("issue_type")).lower() != filters.issue_type.lower():
        return False
    if filters.status and clean_text(metadata.get("status")).lower() != filters.status.lower():
        return False
    if filters.priority and clean_text(metadata.get("priority")).lower() != filters.priority.lower():
        return False
    if filters.component and not contains_casefold(metadata.get("components", []), filters.component):
        return False
    if filters.fix_version and not contains_casefold(metadata.get("fix_versions", []), filters.fix_version):
        return False
    return True


def contains_casefold(values: object, target: str) -> bool:
    """Case-insensitive membership check for list-like metadata fields."""
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return False
    target_folded = target.lower()
    return any(clean_text(value).lower() == target_folded for value in values)
