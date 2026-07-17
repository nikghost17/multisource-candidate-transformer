"""
lc/vectorstore.py
------------------
Persistent Chroma vector store managed via LangChain.

This replaces the entire rag/vector_store.py. With LangChain's Chroma
wrapper you get embedding + storage in one step — no manual ChromaDB API.

Usage:
    from lc.vectorstore import get_vectorstore, index_resume, search

    # Index a resume
    index_resume(candidate_id, chunks)

    # Semantic search
    results = search("Python ML engineer", top_k=5)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Dict, Any, Optional

from langchain_core.documents import Document

_DEFAULT_DB_PATH  = str(Path(__file__).parent.parent / "chromadb_store")
_COLLECTION_NAME  = "resume_chunks"

# Module-level cache so we only create one Chroma instance per process
_vectorstore = None


def get_vectorstore():
    """
    Get or create the persistent Chroma vectorstore.
    Uses the embedding model configured in lc/embeddings.py.
    """
    global _vectorstore
    if _vectorstore is None:
        from langchain_chroma import Chroma
        from lc.embeddings import get_embeddings

        db_path = os.getenv("CHROMA_DB_PATH", _DEFAULT_DB_PATH)
        os.makedirs(db_path, exist_ok=True)

        _vectorstore = Chroma(
            collection_name=_COLLECTION_NAME,
            embedding_function=get_embeddings(),
            persist_directory=db_path,
        )
        print(f"[LC VectorStore] Chroma loaded from: {db_path}")

    return _vectorstore


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def index_resume(
    candidate_id: str,
    chunks: List[Document],
) -> int:
    """
    Embed and store all chunks for a candidate.

    Deletes existing chunks for this candidate first to avoid stale data.
    Metadata on each chunk gets candidate_id added automatically.

    Parameters
    ----------
    candidate_id : str
    chunks : list[Document]  — from lc/splitter.py split_documents()

    Returns
    -------
    int — number of chunks stored
    """
    if not chunks:
        return 0

    vs = get_vectorstore()

    # Remove old chunks for this candidate
    delete_candidate(candidate_id)

    # Add candidate_id to each chunk's metadata
    ids = []
    for i, chunk in enumerate(chunks):
        chunk.metadata["candidate_id"] = candidate_id
        chunk.metadata["chunk_index"]  = i
        ids.append(f"{candidate_id}_{i}")

    # LangChain Chroma handles embedding + storage in one call
    vs.add_documents(chunks, ids=ids)

    print(f"[LC VectorStore] Indexed {len(chunks)} chunks for {candidate_id[:8]}…")
    return len(chunks)


def search(
    query: str,
    top_k: int = 5,
    candidate_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Semantic search across all indexed resumes (or one specific candidate).

    Parameters
    ----------
    query : str             — natural language query
    top_k : int             — number of results
    candidate_id : str, optional — filter to one candidate

    Returns
    -------
    list[dict]  with keys: text, candidate_id, chunk_index, score
    """
    vs = get_vectorstore()

    where_filter = {"candidate_id": candidate_id} if candidate_id else None

    kwargs: Dict[str, Any] = {"k": top_k}
    if where_filter:
        kwargs["filter"] = where_filter

    # Use plain similarity_search — avoids the "scores must be 0-1" warning
    # that occurs because Chroma stores cosine distances which can be negative.
    docs = vs.similarity_search(query, **kwargs)

    output = []
    for i, doc in enumerate(docs):
        # Assign a descending pseudo-score (1.0 → top result, lower for rest)
        score = round(1.0 - (i / max(len(docs), 1)) * 0.3, 4)
        output.append({
            "text":         doc.page_content,
            "candidate_id": doc.metadata.get("candidate_id"),
            "chunk_index":  doc.metadata.get("chunk_index"),
            "similarity":   score,
        })
    return output


def get_candidate_context(
    candidate_id: str,
    question: str,
    top_k: int = 3,
) -> str:
    """
    Retrieve the most relevant resume chunks for a specific candidate
    and question. Returns joined text for use in LLM prompts.
    """
    results = search(question, top_k=top_k, candidate_id=candidate_id)
    return "\n\n---\n\n".join(r["text"] for r in results)


def delete_candidate(candidate_id: str) -> None:
    """Remove all stored chunks for a candidate."""
    vs = get_vectorstore()
    try:
        # Get IDs to delete by filtering on metadata
        existing = vs._collection.get(
            where={"candidate_id": candidate_id},
        )
        ids = existing.get("ids", [])
        if ids:
            vs._collection.delete(ids=ids)
            print(f"[LC VectorStore] Deleted {len(ids)} chunks for {candidate_id[:8]}…")
    except Exception as e:
        print(f"[LC VectorStore] Warning deleting {candidate_id}: {e}")


def count() -> int:
    """Total chunks stored across all candidates."""
    return get_vectorstore()._collection.count()
