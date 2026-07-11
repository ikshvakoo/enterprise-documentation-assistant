"""Summarize the local anonymized project corpus.

This module intentionally reads the local data folder rather than relying only on
the retrieval index. The project report needs dataset-level facts such as file
counts, workbook counts, and release-note dates, which are easiest to calculate
from the source files.
"""

import json
import re
from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import openpyxl
from pypdf import PdfReader


DATE_PATTERNS = [
    re.compile(
        r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+\d{1,2},\s+\d{4}\b"
    ),
    re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b"),
]
RELEASE_VERSION_RE = re.compile(r"\b\d{2}\.\d(?:\.\d+)?(?:\s+Beta(?:\s+\d+)?)?\b", re.IGNORECASE)


@dataclass
class ReleaseNoteSummary:
    """Summary information for one release-note source file."""

    file_name: str
    file_type: str
    release_version: str
    detected_date: str


@dataclass
class TestCaseWorkbookSummary:
    """Summary information for one test-case workbook."""

    file_name: str
    worksheet_count: int
    detail_row_count: int


@dataclass
class CorpusSummary:
    """Aggregated dataset summary for the project corpus."""

    data_dir: str
    jira_ticket_count: int
    release_note_count: int
    release_note_pdf_count: int
    release_note_docx_count: int
    release_notes: list[ReleaseNoteSummary]
    release_date_start: str
    release_date_end: str
    release_version_start: str
    release_version_end: str
    test_case_workbook_count: int
    test_case_worksheet_count: int
    test_case_detail_row_count: int
    test_case_workbooks: list[TestCaseWorkbookSummary]

    def to_dict(self) -> dict[str, Any]:
        """Convert nested dataclasses into a JSON-serializable dictionary."""
        return asdict(self)


def build_corpus_summary(data_dir: Path) -> CorpusSummary:
    """Build a dataset summary from Jira JSON, release notes, and test workbooks."""
    release_notes = summarize_release_notes(data_dir / "release_notes")
    test_workbooks = summarize_test_case_workbooks(data_dir / "test_cases")

    detected_dates = [item.detected_date for item in release_notes if item.detected_date]
    sorted_dates = sorted(detected_dates, key=parse_date_for_sort)

    release_versions = [item.release_version for item in release_notes if item.release_version]
    dated_release_notes = sorted(
        [item for item in release_notes if item.detected_date],
        key=lambda item: parse_date_for_sort(item.detected_date),
    )
    release_version_start = (
        dated_release_notes[0].release_version
        if dated_release_notes and dated_release_notes[0].release_version
        else release_versions[0]
        if release_versions
        else ""
    )
    release_version_end = (
        dated_release_notes[-1].release_version
        if dated_release_notes and dated_release_notes[-1].release_version
        else release_versions[-1]
        if release_versions
        else ""
    )

    return CorpusSummary(
        data_dir=str(data_dir),
        jira_ticket_count=count_jira_tickets(data_dir / "jira_export.json"),
        release_note_count=len(release_notes),
        release_note_pdf_count=sum(1 for item in release_notes if item.file_type == "pdf"),
        release_note_docx_count=sum(1 for item in release_notes if item.file_type == "docx"),
        release_notes=release_notes,
        release_date_start=sorted_dates[0] if sorted_dates else "",
        release_date_end=sorted_dates[-1] if sorted_dates else "",
        release_version_start=release_version_start,
        release_version_end=release_version_end,
        test_case_workbook_count=len(test_workbooks),
        test_case_worksheet_count=sum(item.worksheet_count for item in test_workbooks),
        test_case_detail_row_count=sum(item.detail_row_count for item in test_workbooks),
        test_case_workbooks=test_workbooks,
    )


def count_jira_tickets(path: Path) -> int:
    """Count Jira issues in the anonymized JSON export."""
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return len(payload) if isinstance(payload, list) else 0


def summarize_release_notes(directory: Path) -> list[ReleaseNoteSummary]:
    """Collect release-note file counts, versions, and cover-page dates."""
    if not directory.exists():
        return []

    summaries = []
    for path in sorted(directory.iterdir()):
        if path.suffix.lower() not in {".pdf", ".docx"}:
            continue
        summaries.append(
            ReleaseNoteSummary(
                file_name=path.name,
                file_type=path.suffix.lower().lstrip("."),
                release_version=extract_release_version(path.stem),
                detected_date=extract_release_note_date(path),
            )
        )
    return summaries


def summarize_test_case_workbooks(directory: Path) -> list[TestCaseWorkbookSummary]:
    """Count worksheets and non-empty test detail rows in each workbook."""
    if not directory.exists():
        return []

    summaries = []
    for path in sorted(directory.glob("*.xlsx")):
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            worksheet_count = len(workbook.worksheets)
            detail_row_count = 0
            for worksheet in workbook.worksheets:
                rows = list(worksheet.iter_rows(values_only=True))
                # Skip the header row; count only rows containing actual details.
                detail_row_count += sum(1 for row in rows[1:] if any(cell not in (None, "") for cell in row))
        finally:
            workbook.close()

        summaries.append(
            TestCaseWorkbookSummary(
                file_name=path.name,
                worksheet_count=worksheet_count,
                detail_row_count=detail_row_count,
            )
        )
    return summaries


def extract_release_note_date(path: Path) -> str:
    """Extract the first recognizable date from the first two pages of a release note."""
    if path.suffix.lower() != ".pdf":
        return ""
    text = ""
    try:
        reader = PdfReader(str(path))
        for page in reader.pages[:2]:
            text += "\n" + (page.extract_text() or "")
    except Exception:
        return ""

    for pattern in DATE_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(0)
    return ""


def extract_release_version(name: str) -> str:
    """Extract a release-like version string from a file name."""
    match = RELEASE_VERSION_RE.search(name)
    return match.group(0) if match else ""


def parse_date_for_sort(value: str) -> datetime:
    """Parse supported date formats for sorting release-note dates."""
    for date_format in ("%B %d, %Y", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(value, date_format)
        except ValueError:
            continue
    return datetime.min


def format_corpus_summary(summary: CorpusSummary) -> str:
    """Format the corpus summary for readable command-line output."""
    lines = [
        "Corpus summary",
        f"Data directory: {summary.data_dir}",
        "",
        f"Jira tickets: {summary.jira_ticket_count}",
        f"Release notes: {summary.release_note_count} "
        f"({summary.release_note_pdf_count} PDF, {summary.release_note_docx_count} DOCX)",
        f"Release date span: {summary.release_date_start or 'unknown'} to {summary.release_date_end or 'unknown'}",
        f"Release version span: {summary.release_version_start or 'unknown'} to {summary.release_version_end or 'unknown'}",
        f"Test case workbooks: {summary.test_case_workbook_count}",
        f"Test case worksheets: {summary.test_case_worksheet_count}",
        f"Test case detail rows: {summary.test_case_detail_row_count}",
        "",
        "Release note files:",
    ]
    for item in summary.release_notes:
        date = f" | {item.detected_date}" if item.detected_date else ""
        version = f" | {item.release_version}" if item.release_version else ""
        lines.append(f"- {item.file_name}{version}{date}")

    lines.append("")
    lines.append("Test case workbooks:")
    for item in summary.test_case_workbooks:
        lines.append(f"- {item.file_name} | sheets={item.worksheet_count} | detail_rows={item.detail_row_count}")

    return "\n".join(lines)
