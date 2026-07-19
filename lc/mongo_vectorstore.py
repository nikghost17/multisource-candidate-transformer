"""
lc/mongo_vectorstore.py
-----------------------
MongoDB-backed vector store for resume chunks.

Replaces lc/vectorstore.py (ChromaDB) with MongoDB.

Collection: candidate_platform.resume_chunks
Each document:
{
    "_id":          "<candidate_id>_<chunk_index>",
    "candidate_id": "...",
    "chunk_index":  0,
    "text":         "...",
    "embedding":    [0.1, 0.23, ...],   # list[float], stored directly
    "metadata":     {...}               # source, page, etc.
}

Semantic search = load embeddings from Mongo → cosine similarity in NumPy.
No Atlas Vector Search index required — works on M0 free tier.
"""

from __future__ import annotations

import os
import math
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
load_dotenv()


# ── Mongo connection ──────────────────────────────────────────────────────────

def _get_collection():
    import certifi
    from pymongo import MongoClient
    uri = os.getenv("MONGODB_URI", "")
    if not uri:
        raise RuntimeError("MONGODB_URI not set in .env")
    db_name = os.getenv("MONGODB_DB", "candidate_platform")
    client = MongoClient(uri, serverSelectionTimeoutMS=5000, tlsCAFile=certifi.where())
    return client[db_name]["resume_chunks"]


# ── Embedding helper ──────────────────────────────────────────────────────────

def _embed(texts: List[str]) -> List[List[float]]:
    """Embed a list of texts using the configured embedding model."""
    from lc.embeddings import get_embeddings
    emb = get_embeddings()
    return emb.embed_documents(texts)


def _embed_query(text: str) -> List[float]:
    from lc.embeddings import get_embeddings
    emb = get_embeddings()
    return emb.embed_query(text)


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two vectors — result in [-1, 1]."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ── Public API ────────────────────────────────────────────────────────────────

def index_resume(
    candidate_id: str,
    docs,           # list[langchain Document]
) -> int:
    """
    Embed and store resume chunks in MongoDB.
    Deletes existing chunks for this candidate first (re-index).

    Returns number of chunks indexed.
    """
    col = _get_collection()

    # Remove old chunks for this candidate
    col.delete_many({"candidate_id": candidate_id})

    if not docs:
        return 0

    texts    = [doc.page_content for doc in docs]
    embeddings = _embed(texts)

    to_insert = []
    for i, (doc, emb) in enumerate(zip(docs, embeddings)):
        to_insert.append({
            "_id":          f"{candidate_id}_{i}",
            "candidate_id": candidate_id,
            "chunk_index":  i,
            "text":         doc.page_content,
            "embedding":    emb,
            "metadata":     {k: str(v) for k, v in doc.metadata.items()},
        })

    col.insert_many(to_insert)
    print(f"[Mongo VectorStore] Indexed {len(to_insert)} chunks for {candidate_id[:8]}…")
    return len(to_insert)


def search(
    query: str,
    top_k: int = 10,
    candidate_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Semantic search over resume chunks.

    Fetches relevant documents from MongoDB, embeds the query,
    and ranks by cosine similarity.

    Parameters
    ----------
    query        : natural language query
    top_k        : number of results to return
    candidate_id : optional — restrict search to one candidate

    Returns
    -------
    list[dict] with keys: text, candidate_id, chunk_index, similarity
    """
    col = _get_collection()

    # Filter
    mongo_filter: Dict[str, Any] = {}
    if candidate_id:
        mongo_filter["candidate_id"] = candidate_id

    # Fetch documents (exclude raw embedding from projection for efficiency,
    # then include it — we need it for similarity)
    docs = list(col.find(mongo_filter, {"embedding": 1, "text": 1,
                                         "candidate_id": 1, "chunk_index": 1}))
    if not docs:
        return []

    # Embed query
    query_vec = _embed_query(query)

    # Cosine similarity for each doc
    scored = []
    for doc in docs:
        emb = doc.get("embedding")
        if not emb:
            continue
        sim = _cosine_similarity(query_vec, emb)
        # Normalise from [-1,1] → [0,1]
        sim_normalised = round((sim + 1) / 2, 4)
        scored.append((sim_normalised, doc))

    # Sort descending, take top_k
    scored.sort(key=lambda x: x[0], reverse=True)
    scored = scored[:top_k]

    return [
        {
            "text":         doc["text"],
            "candidate_id": doc["candidate_id"],
            "chunk_index":  doc["chunk_index"],
            "similarity":   score,
        }
        for score, doc in scored
    ]


def delete_candidate(candidate_id: str) -> int:
    """Delete all chunks for a candidate. Returns count deleted."""
    col = _get_collection()
    result = col.delete_many({"candidate_id": candidate_id})
    print(f"[Mongo VectorStore] Deleted {result.deleted_count} chunks for {candidate_id[:8]}…")
    return result.deleted_count


def get_candidate_context(
    candidate_id: str,
    question: str,
    top_k: int = 3,
) -> str:
    """
    Retrieve top-k relevant chunks for a candidate as a single context string.
    Used by the enrich endpoint to give Gemini grounding context.
    """
    hits = search(question, top_k=top_k, candidate_id=candidate_id)
    if not hits:
        return ""
    return "\n\n---\n\n".join(h["text"] for h in hits)


# ── LangChain Retriever Wrapper ────────────────────────────────────────────────
from langchain_core.retrievers import BaseRetriever
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document

class MongoCustomRetriever(BaseRetriever):
    """A custom LangChain retriever wrapping our manual MongoDB cosine search."""
    candidate_id: Optional[str] = None
    top_k: int = 4

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        hits = search(query, top_k=self.top_k, candidate_id=self.candidate_id)
        docs = []
        for h in hits:
            docs.append(Document(
                page_content=h["text"],
                metadata={"candidate_id": h["candidate_id"], "chunk_index": h["chunk_index"]}
            ))
        return docs

def get_retriever(candidate_id: Optional[str] = None, top_k: int = 4) -> BaseRetriever:
    """Returns a LangChain retriever interface for Q&A chains."""
    return MongoCustomRetriever(candidate_id=candidate_id, top_k=top_k)

