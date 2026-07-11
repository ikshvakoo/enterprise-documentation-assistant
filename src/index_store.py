"""Compatibility module for older imports of index storage helpers.

The active BM25 implementation now lives under retrieval/. Keeping these
aliases avoids breaking older scripts while Phase 1 is being refactored.
"""

from retrieval.bm25 import BM25Index
from retrieval.index_io import load_index
from retrieval.index_io import save_index

__all__ = ["BM25Index", "load_index", "save_index"]
