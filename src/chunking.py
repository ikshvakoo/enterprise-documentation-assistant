"""Compatibility module for older imports of chunking helpers.

The active implementation now lives in processing.chunker, but this file keeps
older commands or notebooks from breaking if they still import chunking.py.
"""

from processing.chunker import chunk_document
from processing.chunker import chunk_documents

__all__ = ["chunk_document", "chunk_documents"]
