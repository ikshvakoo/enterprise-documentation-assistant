import json
from pathlib import Path

from .bm25 import BM25Index


def save_index(index: BM25Index, path: Path) -> None:
    """Persist the BM25 index to disk as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(index.to_dict(), handle, ensure_ascii=False)


def load_index(path: Path) -> BM25Index:
    """Load a previously persisted BM25 index from disk."""
    with path.open("r", encoding="utf-8") as handle:
        return BM25Index.from_dict(json.load(handle))
