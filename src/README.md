# AI-Powered Enterprise Documentation Assistant

This Phase 1 baseline ingests anonymized Jira tickets, release-note PDFs/DOCX files, and test-case workbooks, then builds a local BM25 searchable knowledge index.

The current implementation supports:

- normalized ingestion across Jira, release notes, and test cases
- sentence-aware chunking
- custom BM25 retrieval
- metadata-filtered search
- grounded extractive answers with citations
- release/fix-version ticket listing for later document generation

## Quick Start

From the project root:

```powershell
& 'C:\Users\vsharma\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' src\main.py build-index
& 'C:\Users\vsharma\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' src\main.py search "payment transfer release notes"
& 'C:\Users\vsharma\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' src\main.py answer "What changed for account opening?"
& 'C:\Users\vsharma\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' src\main.py release-tickets "26.2.0" --limit 10
```

Generated artifacts are written to `src/artifacts/`.

## Useful Commands

```powershell
# Show corpus/index counts
& 'C:\Users\vsharma\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' src\main.py stats

# Search only one corpus type
& 'C:\Users\vsharma\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' src\main.py search "exception processing" --source-type jira --top-k 5

# Filter by fix version
& 'C:\Users\vsharma\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' src\main.py search "exception routing" --fix-version "26.2.0" --top-k 5

# Draft simple release-note bullets from retrieved evidence
& 'C:\Users\vsharma\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' src\main.py release-notes "exception routing 26.2.0" --fix-version "26.2.0"

# Evaluate retrieval quality with Recall@K and MRR
& 'C:\Users\vsharma\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' src\main.py eval-retrieval src\evaluation\test_questions.example.json --top-k 10
```

## Phase 1 Module Layout

```text
src/
  ingestion/     # Jira, release note, and test case loaders
  processing/    # chunking and normalization-facing utilities
  retrieval/     # BM25 index, index IO, and search service
  generation/    # placeholder for Phase 2 structured generation
  export/        # placeholder for generated DOCX/PDF/XLSX outputs
  evaluation/    # placeholder for retrieval/generation evaluation
```
