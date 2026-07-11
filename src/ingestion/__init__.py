from pathlib import Path

from models import SourceDocument

from .jira_loader import load_jira_export
from .release_notes_loader import load_release_notes
from .test_case_loader import load_test_case_workbook


def load_all_documents(data_dir: Path) -> list[SourceDocument]:
    """Load every supported source file under the project data directory.

    This is the main ingestion entry point. It knows the folder layout and
    delegates source-specific parsing to the Jira, release-note, and test-case
    loader modules.
    """
    documents: list[SourceDocument] = []

    # Jira data is one JSON export containing many issues.
    jira_path = data_dir / "jira_export.json"
    if jira_path.exists():
        documents.extend(load_jira_export(jira_path))

    # Release notes can come from PDF files and, after cleanup, DOCX files.
    release_notes_dir = data_dir / "release_notes"
    if release_notes_dir.exists():
        documents.extend(load_release_notes(release_notes_dir))

    # Test cases are stored as one or more Excel workbooks.
    test_cases_dir = data_dir / "test_cases"
    if test_cases_dir.exists():
        for path in sorted(test_cases_dir.glob("*.xlsx")):
            documents.extend(load_test_case_workbook(path))

    return documents
