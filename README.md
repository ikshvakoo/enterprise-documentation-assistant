# AI574 Enterprise Documentation Assistant

This project is an NLP/RAG prototype for searching and generating documentation from anonymized enterprise delivery artifacts.

The system currently supports a Phase 1 local baseline:

- load anonymized Jira exports, release notes, and QA test case workbooks
- normalize source documents into a shared schema
- split long text into sentence-aware chunks
- build a custom BM25 retrieval index
- run metadata-filtered search
- produce grounded extractive answers with citations
- list Jira tickets by release/fix version for later document generation

## Repository Safety

Company data is intentionally excluded from this repository. The following folders are ignored:

- `src/data/`
- `src/artifacts/`
- `data_ori/`
- generated PDFs, Word documents, rendered review files, and extracted text artifacts

To run the project, place the anonymized data locally under:

```text
src/data/
  jira_export.json
  release_notes/
  test_cases/
```

## Quick Start

```powershell
python -m pip install -r requirements.txt
python src/main.py build-index
python src/main.py stats
python src/main.py search "exception processing" --source-type jira --top-k 5
python src/main.py answer "What changed for exception processing?" --top-k 3
python src/main.py release-tickets "26.2.0" --limit 10
python src/main.py eval-retrieval src/evaluation/test_questions.example.json --top-k 10
```

## Project Structure

```text
src/
  ingestion/     # Jira, release-note, and test-case loaders
  processing/    # text chunking and preprocessing
  retrieval/     # BM25 index, index persistence, search service
  generation/    # placeholder for Phase 2 document generation
  export/        # placeholder for DOCX/PDF/XLSX export
  evaluation/    # placeholder for retrieval/generation evaluation
```

## Current Status

Phase 1 is implemented. The next project step is to build the document generation workflow on top of the existing retrieval service.
