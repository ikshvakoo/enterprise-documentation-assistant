from pathlib import Path


# Project paths are resolved relative to this file so commands work from the
# project root, src folder, or another working directory.
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
ARTIFACT_DIR = PROJECT_ROOT / "artifacts"
INDEX_PATH = ARTIFACT_DIR / "knowledge_index.json"

JIRA_EXPORT = DATA_DIR / "jira_export.json"
RELEASE_NOTES_DIR = DATA_DIR / "release_notes"
TEST_CASES_DIR = DATA_DIR / "test_cases"

# Retrieval defaults for the Phase 1 BM25 baseline.
DEFAULT_CHUNK_WORDS = 220
DEFAULT_CHUNK_OVERLAP = 45
DEFAULT_TOP_K = 6
