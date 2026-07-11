from pathlib import Path

from models import SourceDocument
from ingestion import load_all_documents as _load_all_documents
from ingestion.jira_loader import extract_adf_text
from ingestion.jira_loader import load_jira_export
from ingestion.jira_loader import nested_name
from ingestion.release_notes_loader import load_pdf
from ingestion.test_case_loader import load_test_case_workbook


def load_all_documents(data_dir: Path) -> list[SourceDocument]:
    """Compatibility wrapper for older code that imported from loaders.py."""
    return _load_all_documents(data_dir)


__all__ = [
    "extract_adf_text",
    "load_all_documents",
    "load_jira_export",
    "load_pdf",
    "load_test_case_workbook",
    "nested_name",
]
