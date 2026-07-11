"""Evaluate retrieval quality for the Phase 1 search baseline.

The evaluator uses a small JSON question set. Each question lists one or more
expected relevant sources, such as issue keys, source types, file names, or title
substrings. The command reports Recall@K and MRR so the project can compare BM25
against later semantic or hybrid retrieval stages.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from models import SearchFilters
from models import SearchResult
from retrieval import SearchService
from text_utils import clean_text


@dataclass
class EvaluationQuestion:
    """One retrieval test question and its expected relevant evidence."""

    question: str
    relevant_issue_keys: list[str]
    relevant_source_types: list[str]
    relevant_file_names: list[str]
    relevant_title_contains: list[str]


@dataclass
class RetrievalEvaluationResult:
    """Aggregated retrieval metric results for a question set."""

    question_count: int
    evaluated_count: int
    recall_at_k: float
    mrr: float
    details: list[dict[str, Any]]


def load_questions(path: Path) -> list[EvaluationQuestion]:
    """Load retrieval evaluation questions from a JSON file."""
    with path.open("r", encoding="utf-8") as handle:
        raw_questions = json.load(handle)

    questions = []
    for item in raw_questions:
        questions.append(
            EvaluationQuestion(
                question=clean_text(item.get("question")),
                relevant_issue_keys=listify(item.get("relevant_issue_keys")),
                relevant_source_types=listify(item.get("relevant_source_types")),
                relevant_file_names=listify(item.get("relevant_file_names")),
                relevant_title_contains=listify(item.get("relevant_title_contains")),
            )
        )
    return questions


def evaluate_retrieval(
    service: SearchService,
    questions: list[EvaluationQuestion],
    top_k: int,
    filters: SearchFilters | None = None,
) -> RetrievalEvaluationResult:
    """Run retrieval for each question and calculate Recall@K and MRR."""
    details: list[dict[str, Any]] = []
    hits = 0
    reciprocal_ranks = []
    evaluated_count = 0

    for question in questions:
        if not question.question:
            continue
        evaluated_count += 1
        results = service.search(question.question, top_k=top_k, filters=filters)
        first_relevant_rank = first_relevant_result_rank(question, results)
        is_hit = first_relevant_rank is not None
        if is_hit:
            hits += 1
            reciprocal_ranks.append(1 / first_relevant_rank)
        else:
            reciprocal_ranks.append(0.0)

        details.append(
            {
                "question": question.question,
                "hit": is_hit,
                "first_relevant_rank": first_relevant_rank,
                "top_results": [
                    {
                        "rank": result.rank,
                        "score": round(result.score, 4),
                        "title": result.chunk.title,
                        "source_type": result.chunk.source_type,
                        "issue_key": result.chunk.metadata.get("issue_key"),
                        "file_name": result.chunk.metadata.get("file_name"),
                    }
                    for result in results
                ],
            }
        )

    recall_at_k = hits / evaluated_count if evaluated_count else 0.0
    mrr = sum(reciprocal_ranks) / evaluated_count if evaluated_count else 0.0
    return RetrievalEvaluationResult(
        question_count=len(questions),
        evaluated_count=evaluated_count,
        recall_at_k=recall_at_k,
        mrr=mrr,
        details=details,
    )


def first_relevant_result_rank(question: EvaluationQuestion, results: list[SearchResult]) -> int | None:
    """Return the rank of the first relevant result, or None when no result matches."""
    for result in results:
        if result_is_relevant(question, result):
            return result.rank
    return None


def result_is_relevant(question: EvaluationQuestion, result: SearchResult) -> bool:
    """Check whether one retrieved result matches any expected relevance signal."""
    chunk = result.chunk
    metadata = chunk.metadata

    issue_key = clean_text(metadata.get("issue_key")).lower()
    if issue_key and issue_key in {value.lower() for value in question.relevant_issue_keys}:
        return True

    if chunk.source_type in question.relevant_source_types:
        return True

    file_name = clean_text(metadata.get("file_name")).lower()
    if file_name and file_name in {value.lower() for value in question.relevant_file_names}:
        return True

    title = clean_text(chunk.title).lower()
    return any(value.lower() in title for value in question.relevant_title_contains)


def listify(value: Any) -> list[str]:
    """Normalize a JSON value into a clean list of strings."""
    if value is None:
        return []
    if isinstance(value, str):
        return [clean_text(value)]
    if isinstance(value, list):
        return [clean_text(item) for item in value if clean_text(item)]
    return [clean_text(value)]


def result_to_text(result: RetrievalEvaluationResult) -> str:
    """Format evaluation results for command-line display."""
    lines = [
        "Retrieval evaluation",
        f"Questions loaded: {result.question_count}",
        f"Questions evaluated: {result.evaluated_count}",
        f"Recall@K: {result.recall_at_k:.3f}",
        f"MRR: {result.mrr:.3f}",
        "",
        "Question details:",
    ]
    for item in result.details:
        status = "HIT" if item["hit"] else "MISS"
        rank = item["first_relevant_rank"] if item["first_relevant_rank"] is not None else "-"
        lines.append(f"- {status} rank={rank}: {item['question']}")
    return "\n".join(lines)
