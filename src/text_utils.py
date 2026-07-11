import re
import unicodedata
from collections.abc import Iterable


TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_+-]*|\d+(?:\.\d+)*")
WHITESPACE_RE = re.compile(r"\s+")
SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+|(?=\bIssue Key:|\bTest Summary:|\bStep:|\bExpected Result:)")


def clean_text(value: object) -> str:
    """Normalize text extracted from Jira, PDFs, DOCX files, and spreadsheets.

    Source files often contain smart quotes, non-breaking spaces, private-use
    glyphs, and inconsistent whitespace. This function makes the text safer for
    tokenization, display, and JSON persistence.
    """
    if value is None:
        return ""
    text = str(value)
    text = strip_unsupported_symbols(text)
    text = text.replace("\u00a0", " ")
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = WHITESPACE_RE.sub(" ", text)
    return text.strip()


def strip_unsupported_symbols(text: str) -> str:
    """Replace control/private-use characters that can break console output."""
    cleaned = []
    for character in text:
        category = unicodedata.category(character)
        if category in {"Co", "Cc", "Cf"} and character not in {"\n", "\t"}:
            cleaned.append(" ")
        else:
            cleaned.append(character)
    return "".join(cleaned)


def tokenize(text: str) -> list[str]:
    """Split text into lowercase tokens used by the BM25 index and matching logic."""
    return [match.group(0).lower() for match in TOKEN_RE.finditer(text)]


def split_sentences(text: str) -> list[str]:
    """Split text into sentence-like units while respecting Jira/test-case labels."""
    sentences = [clean_text(part) for part in SENTENCE_BOUNDARY_RE.split(clean_text(text))]
    return [sentence for sentence in sentences if sentence]


def keyword_excerpt(text: str, query: str, max_chars: int = 360) -> str:
    """Choose the sentence that best overlaps the query and return it as an excerpt."""
    query_terms = set(tokenize(query))
    sentences = split_sentences(text)
    if not sentences:
        return truncate(text, max_chars)

    scored: list[tuple[int, int, str]] = []
    for index, sentence in enumerate(sentences):
        terms = set(tokenize(sentence))
        # Basic relevance: count how many query terms appear in this sentence.
        score = len(query_terms & terms)
        lower = sentence.lower()
        # Prefer content-bearing lines over labels that merely identify a test or issue.
        if lower.startswith(("step ", "expected result:", "description:", "comments:")):
            score += 1
        if lower.startswith(("test summary:", "issue key:")):
            score -= 1
        if score:
            scored.append((score, -index, sentence))

    if not scored:
        return truncate(sentences[0], max_chars)

    scored.sort(reverse=True)
    best_sentence = scored[0][2]
    return truncate(best_sentence, max_chars)


def join_nonempty(parts: Iterable[object], separator: str = "\n") -> str:
    """Clean a sequence of values and join only the non-empty ones."""
    return separator.join(part for part in (clean_text(value) for value in parts) if part)


def truncate(text: str, max_chars: int = 500) -> str:
    """Shorten text for CLI display while keeping output readable."""
    text = clean_text(text)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."
