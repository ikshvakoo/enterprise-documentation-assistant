"""Structured release-note generation for selected Jira tickets.

The generator in this module is intentionally deterministic. It does not call
an external LLM, which keeps the academic prototype runnable offline and keeps
the anonymized company data local. The output is a baseline draft that can be
reviewed by a human or later replaced with an LLM-based generator.
"""

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import re

from models import Chunk
from models import SearchResult
from retrieval import SearchService
from text_utils import clean_text
from text_utils import keyword_excerpt
from text_utils import tokenize
from text_utils import truncate


REDACTION_PATTERNS = [
    (re.compile(r"working on [A-Z][A-Za-z0-9_-]+'?s?\s+Bank Configuration workbook", re.IGNORECASE), "working on Client Bank Configuration workbook"),
    (re.compile(r"Error processing [A-Z][A-Za-z0-9_-]+\s+events", re.IGNORECASE), "Error processing Banking Core events"),
    (re.compile(r"\b[A-Z][A-Za-z0-9_-]+\s+event preprocessing failed", re.IGNORECASE), "Banking Core event preprocessing failed"),
    (re.compile(r"\bGUID-[a-f0-9]+\b", re.IGNORECASE), "GUID-REDACTED"),
    (re.compile(r"\bID-[a-f0-9]+(?::\d{2}){0,3}(?:\.\d+)?(?:-\d{4})?\b", re.IGNORECASE), "ID-REDACTED"),
    (re.compile(r"\b[\w.+-]+@[\w.-]+\.\w+\b"), "[email]"),
    (re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE), "[url]"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[ip-address]"),
    (re.compile(r"tenant\s+'[^']+'", re.IGNORECASE), "tenant '[tenant]'"),
    (re.compile(r"\[[^\]]*(?:uat|dev|prod|qa|battle|adm)[^\]]*\]", re.IGNORECASE), "[environment]"),
]


@dataclass
class TicketEvidence:
    """A selected Jira ticket plus the chunks that support generated notes."""

    issue_key: str
    title: str
    issue_type: str
    status: str
    priority: str
    components: list[str]
    fix_versions: list[str]
    chunks: list[Chunk]


@dataclass
class ReleaseNotesDraft:
    """Generated release-note draft and the evidence used to produce it."""

    title: str
    markdown: str
    tickets: list[TicketEvidence]


def generate_release_notes_for_selection(
    service: SearchService,
    fix_version: str | None = None,
    issue_keys: list[str] | None = None,
    query: str | None = None,
    max_tickets: int = 40,
) -> ReleaseNotesDraft:
    """Generate release notes from selected Jira tickets and related evidence.

    The selection can be driven by a Jira fix version, a list of issue keys, a
    keyword query, or a combination of those inputs. The function first chooses
    Jira tickets, then converts each ticket into one readable release-note item.
    """
    selected = select_ticket_evidence(
        service=service,
        fix_version=fix_version,
        issue_keys=issue_keys or [],
        query=query,
        max_tickets=max_tickets,
    )
    title = build_release_title(fix_version=fix_version, query=query, issue_keys=issue_keys or [])
    markdown = format_release_notes_markdown(title=title, tickets=selected, query=query)
    return ReleaseNotesDraft(title=title, markdown=markdown, tickets=selected)


def select_ticket_evidence(
    service: SearchService,
    fix_version: str | None = None,
    issue_keys: list[str] | None = None,
    query: str | None = None,
    max_tickets: int = 40,
) -> list[TicketEvidence]:
    """Select unique Jira tickets from the index for document generation."""
    requested_keys = {clean_text(key).lower() for key in issue_keys if clean_text(key)}
    requested_version = clean_text(fix_version).lower()
    query_terms = set(tokenize(query or ""))
    tickets: dict[str, list[Chunk]] = {}

    for chunk in service.index.chunks:
        if chunk.source_type != "jira":
            continue

        issue_key = clean_text(chunk.metadata.get("issue_key"))
        if not issue_key:
            continue
        if requested_keys and issue_key.lower() not in requested_keys:
            continue
        if requested_version and not has_value(chunk.metadata.get("fix_versions", []), requested_version):
            continue
        if query_terms and not chunk_has_query_overlap(chunk, query_terms):
            continue

        tickets.setdefault(issue_key, []).append(chunk)

    # If a query was provided and the strict overlap removed too many tickets,
    # fall back to BM25 ranking so the user still gets a useful draft.
    if query_terms and not tickets:
        for result in service.search(query or "", top_k=max_tickets * 4):
            chunk = result.chunk
            if chunk.source_type != "jira":
                continue
            issue_key = clean_text(chunk.metadata.get("issue_key"))
            if not issue_key:
                continue
            if requested_version and not has_value(chunk.metadata.get("fix_versions", []), requested_version):
                continue
            if requested_keys and issue_key.lower() not in requested_keys:
                continue
            tickets.setdefault(issue_key, []).append(chunk)
            if len(tickets) >= max_tickets:
                break

    evidence = [ticket_from_chunks(issue_key, chunks) for issue_key, chunks in tickets.items()]
    evidence.sort(key=lambda ticket: ticket_sort_key(ticket, query_terms))
    return evidence[:max_tickets]


def ticket_from_chunks(issue_key: str, chunks: list[Chunk]) -> TicketEvidence:
    """Create a ticket-level evidence record from one or more indexed chunks."""
    first = chunks[0]
    metadata = first.metadata
    return TicketEvidence(
        issue_key=issue_key,
        title=first.title,
        issue_type=clean_text(metadata.get("issue_type")),
        status=clean_text(metadata.get("status")),
        priority=clean_text(metadata.get("priority")),
        components=as_clean_list(metadata.get("components", [])),
        fix_versions=as_clean_list(metadata.get("fix_versions", [])),
        chunks=chunks,
    )


def format_release_notes_markdown(title: str, tickets: list[TicketEvidence], query: str | None = None) -> str:
    """Format selected ticket evidence as a Markdown release-note draft."""
    lines = [
        f"# {title}",
        "",
        "## Overview",
        overview_sentence(tickets),
        "",
        "## Highlights",
    ]

    grouped = group_tickets_for_release_notes(tickets)
    for section, section_tickets in grouped.items():
        if not section_tickets:
            continue
        lines.extend(["", f"### {section}"])
        for ticket in section_tickets:
            lines.append(f"- {release_note_bullet(ticket, query=query)}")

    lines.extend(["", "## Traceability"])
    if tickets:
        lines.append("| Issue Key | Type | Status | Priority | Components |")
        lines.append("| --- | --- | --- | --- | --- |")
        for ticket in tickets:
            lines.append(
                "| "
                + " | ".join(
                    [
                        ticket.issue_key,
                        ticket.issue_type or "Unknown",
                        ticket.status or "Unknown",
                        ticket.priority or "Unknown",
                        ", ".join(ticket.components) or "None",
                    ]
                )
                + " |"
            )
    else:
        lines.append("No matching Jira tickets were found for this selection.")

    lines.extend(["", "## Source Evidence"])
    for number, ticket in enumerate(tickets, start=1):
        excerpt = ticket_excerpt(ticket, query=query, max_chars=300)
        lines.append(f"{number}. {ticket.issue_key}: {excerpt}")

    return "\n".join(lines).strip() + "\n"


def group_tickets_for_release_notes(tickets: list[TicketEvidence]) -> dict[str, list[TicketEvidence]]:
    """Group tickets into simple release-note sections based on issue type."""
    groups = {
        "New Features and Enhancements": [],
        "Bug Fixes": [],
        "Quality and Validation Notes": [],
        "Other Changes": [],
    }
    for ticket in tickets:
        label = classify_ticket(ticket)
        groups[label].append(ticket)
    return groups


def classify_ticket(ticket: TicketEvidence) -> str:
    """Classify a Jira ticket into a release-note section."""
    issue_type = ticket.issue_type.lower()
    title = ticket.title.lower()
    text = " ".join(chunk.text.lower() for chunk in ticket.chunks)

    if "bug" in issue_type or "defect" in issue_type or "fix" in title:
        return "Bug Fixes"
    if "test" in issue_type or "qa" in text or "validation" in text:
        return "Quality and Validation Notes"
    if any(term in issue_type for term in ["story", "enhancement", "feature", "task"]):
        return "New Features and Enhancements"
    return "Other Changes"


def release_note_bullet(ticket: TicketEvidence, query: str | None = None) -> str:
    """Create one customer-readable release-note bullet for a ticket."""
    component_text = f" ({', '.join(ticket.components)})" if ticket.components else ""
    excerpt = ticket_excerpt(ticket, query=query, max_chars=220)
    summary = scrub_output_text(truncate(ticket.title, 140))
    if excerpt and excerpt.lower() != summary.lower():
        return f"{summary}{component_text}: {excerpt} [{ticket.issue_key}]"
    return f"{summary}{component_text}. [{ticket.issue_key}]"


def ticket_excerpt(ticket: TicketEvidence, query: str | None = None, max_chars: int = 260) -> str:
    """Select the most useful text excerpt from a ticket's chunks."""
    query_text = query or ticket.title
    best = ""
    best_score = -1
    query_terms = set(tokenize(query_text))
    for chunk in ticket.chunks:
        excerpt = keyword_excerpt(chunk.text, query_text, max_chars=max_chars)
        score = len(query_terms & set(tokenize(excerpt)))
        if score > best_score:
            best = excerpt
            best_score = score
    return scrub_output_text(truncate(best, max_chars))


def overview_sentence(tickets: list[TicketEvidence]) -> str:
    """Create a short summary sentence for the generated release notes."""
    if not tickets:
        return "No Jira tickets matched the selected release criteria."
    type_counts = Counter(ticket.issue_type or "Unknown" for ticket in tickets)
    common_types = ", ".join(f"{count} {issue_type}" for issue_type, count in type_counts.most_common(3))
    return f"This draft summarizes {len(tickets)} selected Jira tickets, including {common_types}."


def build_release_title(fix_version: str | None, query: str | None, issue_keys: list[str]) -> str:
    """Build a readable title for the generated release-note draft."""
    if fix_version:
        return f"Release Notes Draft - {fix_version}"
    if issue_keys:
        return "Release Notes Draft - Selected Jira Issues"
    if query:
        return f"Release Notes Draft - {truncate(query, 60)}"
    return "Release Notes Draft"


def parse_issue_keys(values: list[str] | None, issue_keys_file: Path | None = None) -> list[str]:
    """Parse issue keys supplied directly or through a text file."""
    keys: list[str] = []
    for value in values or []:
        keys.extend(part.strip() for part in value.replace("\n", ",").split(",") if part.strip())
    if issue_keys_file and issue_keys_file.exists():
        keys.extend(part.strip() for part in issue_keys_file.read_text(encoding="utf-8").splitlines() if part.strip())
    return dedupe_preserve_order(keys)


def dedupe_preserve_order(values: list[str]) -> list[str]:
    """Remove duplicate values without changing their first-seen order."""
    seen = set()
    unique = []
    for value in values:
        folded = value.lower()
        if folded in seen:
            continue
        unique.append(value)
        seen.add(folded)
    return unique


def has_value(values: object, target_lower: str) -> bool:
    """Return True when a metadata list contains a value case-insensitively."""
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return False
    return any(clean_text(value).lower() == target_lower for value in values)


def chunk_has_query_overlap(chunk: Chunk, query_terms: set[str]) -> bool:
    """Check whether a chunk contains at least one query term."""
    if not query_terms:
        return True
    chunk_terms = set(tokenize(chunk.title + " " + chunk.text))
    return bool(query_terms & chunk_terms)


def ticket_sort_key(ticket: TicketEvidence, query_terms: set[str]) -> tuple[int, str]:
    """Sort tickets by query overlap first, then issue key."""
    text = ticket.title + " " + " ".join(chunk.text for chunk in ticket.chunks)
    overlap = len(query_terms & set(tokenize(text)))
    return (-overlap, ticket.issue_key)


def as_clean_list(values: object) -> list[str]:
    """Normalize a metadata value into a cleaned string list."""
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    return [clean_text(value) for value in values if clean_text(value)]


def scrub_output_text(text: str) -> str:
    """Remove sensitive or noisy identifiers from generated documentation text."""
    cleaned = clean_text(text)
    for pattern, replacement in REDACTION_PATTERNS:
        cleaned = pattern.sub(replacement, cleaned)
    cleaned = re.sub(r"\bSELECT\s+\*\s+FROM\s+\S+", "A system log entry", cleaned, flags=re.IGNORECASE)
    return truncate(cleaned, len(cleaned))
