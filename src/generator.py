from collections import defaultdict

from models import SearchResult
from text_utils import keyword_excerpt
from text_utils import truncate
from text_utils import tokenize


def format_citation(result: SearchResult, number: int) -> str:
    """Format one search result as a human-readable numbered citation."""
    chunk = result.chunk
    details = []
    if chunk.source_type == "release_note":
        details.append(f"page {chunk.metadata.get('page')}")
    if chunk.source_type == "test_case":
        details.append(f"sheet {chunk.metadata.get('sheet')}")
    if chunk.source_type == "jira":
        details.append(f"issue {chunk.metadata.get('issue_key')}")
    suffix = f" ({', '.join(str(item) for item in details if item)})" if details else ""
    return f"[{number}] {chunk.title}{suffix}"


def generate_answer(query: str, results: list[SearchResult]) -> str:
    """Create an extractive grounded answer from retrieved search results.

    This Phase 1 answer is not an LLM response. It selects useful snippets from
    retrieved chunks and presents them with citations.
    """
    evidence = select_evidence(query, results)
    if not evidence:
        return "I could not find enough relevant source material to answer that question."

    lines = [f"Question: {query}", "", "Grounded answer:"]
    lines.append("Based on the retrieved sources, the relevant changes/validation points are:")
    for index, result in enumerate(evidence, start=1):
        snippet = keyword_excerpt(result.chunk.text, query, max_chars=360)
        label = source_label(result)
        lines.append(f"- {label}: {snippet} [{index}]")

    lines.extend(["", "Sources:"])
    for index, result in enumerate(evidence, start=1):
        lines.append(f"- {format_citation(result, index)}")
    return "\n".join(lines)


def generate_release_notes(results: list[SearchResult]) -> str:
    """Create a simple release-note draft from retrieved evidence.

    This is the local baseline for Phase 1. Phase 2 will replace or extend this
    with structured document-generation logic.
    """
    if not results:
        return "No matching items were found for the requested release-note draft."

    grouped: dict[str, list[SearchResult]] = defaultdict(list)
    for result in results:
        # Group by corpus type so QA/test evidence can be shown separately from
        # Jira and historical release-note evidence.
        grouped[result.chunk.source_type].append(result)

    lines = ["Release Notes Draft", "", "Updates and Enhancements"]
    for result in grouped.get("jira", []) + grouped.get("release_note", []):
        lines.append(f"- {truncate(result.chunk.title, 120)}: {truncate(result.chunk.text, 260)}")

    test_cases = grouped.get("test_case", [])
    if test_cases:
        lines.extend(["", "QA / Validation Notes"])
        for result in test_cases:
            lines.append(f"- {truncate(result.chunk.title, 120)}: {truncate(result.chunk.text, 240)}")

    lines.extend(["", "Sources"])
    for index, result in enumerate(results, start=1):
        lines.append(f"- {format_citation(result, index)}")
    return "\n".join(lines)


def select_evidence(query: str, results: list[SearchResult], max_items: int = 5) -> list[SearchResult]:
    """Choose a small, diverse set of evidence snippets for answer generation."""
    selected: list[SearchResult] = []
    seen_titles = set()
    seen_snippets = set()

    for result in results:
        title_key = normalize_key(result.chunk.title)
        snippet = keyword_excerpt(result.chunk.text, query, max_chars=260)
        snippet_key = normalize_key(snippet)
        # Skip empty or repetitive evidence so the grounded answer does not show
        # the same fact multiple times.
        if not snippet_key:
            continue
        if title_key in seen_titles:
            continue
        if is_near_duplicate(snippet_key, seen_snippets):
            continue
        selected.append(result)
        seen_titles.add(title_key)
        seen_snippets.add(snippet_key)
        if len(selected) >= max_items:
            break

    return selected


def normalize_key(text: str) -> str:
    """Create a rough comparable key for duplicate detection."""
    terms = tokenize(text)
    return " ".join(terms[:35])


def is_near_duplicate(candidate: str, existing: set[str]) -> bool:
    """Detect whether a candidate evidence snippet is too similar to prior ones."""
    candidate_terms = set(candidate.split())
    if not candidate_terms:
        return True
    for item in existing:
        item_terms = set(item.split())
        # Compare overlap against the shorter snippet so small duplicated
        # excerpts are still caught.
        overlap = len(candidate_terms & item_terms) / max(1, min(len(candidate_terms), len(item_terms)))
        if overlap >= 0.78:
            return True
    return False


def source_label(result: SearchResult) -> str:
    """Create a short source label for answer bullets."""
    chunk = result.chunk
    if chunk.source_type == "jira":
        return f"Jira {chunk.metadata.get('issue_key') or chunk.title}"
    if chunk.source_type == "test_case":
        return f"Test case {chunk.metadata.get('issue_key') or chunk.metadata.get('sheet')}"
    if chunk.source_type == "release_note":
        return f"Release note page {chunk.metadata.get('page')}"
    return chunk.title
