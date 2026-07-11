from models import Chunk
from models import SourceDocument
from text_utils import split_sentences
from text_utils import tokenize


def chunk_documents(
    documents: list[SourceDocument],
    chunk_words: int,
    overlap_words: int,
) -> list[Chunk]:
    """Split all normalized source documents into searchable chunks."""
    chunks: list[Chunk] = []
    for document in documents:
        chunks.extend(chunk_document(document, chunk_words, overlap_words))
    return chunks


def chunk_document(
    document: SourceDocument,
    chunk_words: int,
    overlap_words: int,
) -> list[Chunk]:
    """Split one source document into sentence-aware overlapping chunks.

    The goal is to keep enough surrounding context for citations while avoiding
    huge chunks that make retrieval noisy.
    """
    sentences = split_sentences(document.body)
    if not sentences:
        return []

    chunks: list[Chunk] = []
    chunk_index = 0
    start = 0
    while start < len(sentences):
        # Build a chunk by adding whole sentences until the target word budget
        # would be exceeded. Keeping sentence boundaries avoids mid-sentence
        # evidence in answers.
        window: list[str] = []
        word_count = 0
        index = start
        while index < len(sentences):
            sentence_words = sentences[index].split()
            if window and word_count + len(sentence_words) > chunk_words:
                break
            window.append(sentences[index])
            word_count += len(sentence_words)
            index += 1

        text = " ".join(window)
        token_count = len(tokenize(text))
        # Very tiny chunks usually contain only labels or noise, so skip them.
        if token_count < 4:
            start += 1
            continue

        chunks.append(
            Chunk(
                chunk_id=f"{document.doc_id}:chunk:{chunk_index}",
                doc_id=document.doc_id,
                source_type=document.source_type,
                title=document.title,
                text=text,
                source_path=document.source_path,
                metadata={**document.metadata, "chunk_index": chunk_index},
                token_count=token_count,
            )
        )
        chunk_index += 1
        if index >= len(sentences):
            break

        # Move the next window backward by overlap_words so adjacent chunks
        # share context around boundaries.
        overlap_count = 0
        next_start = index
        while next_start > start + 1 and overlap_count < overlap_words:
            next_start -= 1
            overlap_count += len(sentences[next_start].split())
        start = next_start

    return chunks
