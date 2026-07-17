"""
lc/retriever.py
----------------
RAG retrieval chain for semantic search and context building.

Uses LangChain's LCEL (pipe syntax) to compose:
  retriever → prompt → LLM → output parser

Two modes:
  1. search()           — find relevant candidates for a query
  2. answer_about()     — Q&A about a specific candidate's resume

Usage:
    from lc.retriever import search_candidates, build_candidate_context
"""

from __future__ import annotations

from typing import List, Dict, Any, Optional


def get_retriever(candidate_id: Optional[str] = None, top_k: int = 4):
    """
    Get a LangChain retriever from the Chroma vectorstore.

    Parameters
    ----------
    candidate_id : str, optional  — filter to one candidate's chunks
    top_k : int                   — number of chunks to retrieve
    """
    from lc.mongo_vectorstore import get_retriever as _get_retriever

    return _get_retriever(candidate_id=candidate_id, top_k=top_k)


def search_candidates(query: str, top_k: int = 10) -> List[Dict[str, Any]]:
    """
    Semantic search across ALL indexed resumes.

    Returns candidates ranked by relevance to the query.
    Deduplicates by candidate_id (one result per candidate).

    Parameters
    ----------
    query : str   — natural language query
    top_k : int   — max candidates to return

    Returns
    -------
    list[dict]  with keys: candidate_id, text, similarity
    """
    from lc.mongo_vectorstore import search

    hits = search(query, top_k=top_k * 2)  # over-fetch then deduplicate

    seen_ids: set = set()
    results: List[Dict[str, Any]] = []
    for hit in hits:
        cid = hit.get("candidate_id")
        if cid and cid not in seen_ids:
            seen_ids.add(cid)
            results.append(hit)
        if len(results) >= top_k:
            break

    return results


def build_candidate_context(candidate_id: str, top_k: int = 5) -> str:
    """
    Build a rich context string for LLM enrichment by asking several
    focused questions about the candidate and retrieving relevant chunks.

    This ensures the LLM gets relevant chunks from ALL sections of the
    resume (skills, experience, education, summary) — not just the top.

    Parameters
    ----------
    candidate_id : str
    top_k : int   — chunks to retrieve per question

    Returns
    -------
    str — deduplicated, concatenated resume context
    """
    from lc.mongo_vectorstore import search

    questions = [
        "technical skills programming languages frameworks tools",
        "work experience job titles companies responsibilities",
        "education degree university graduation",
        "projects achievements accomplishments",
        "professional summary objective profile",
    ]

    seen_chunks: set = set()
    context_parts: List[str] = []

    for question in questions:
        hits = search(question, top_k=2, candidate_id=candidate_id)
        for hit in hits:
            text = hit["text"]
            if text not in seen_chunks:
                seen_chunks.add(text)
                context_parts.append(text)

    return "\n\n---\n\n".join(context_parts)


def answer_about_candidate(candidate_id: str, question: str) -> str:
    """
    Answer a natural language question about a specific candidate
    using RAG + Gemini.

    This is a simple Q&A chain:
      retrieve relevant chunks → stuff into prompt → Gemini answers

    Parameters
    ----------
    candidate_id : str
    question : str   — e.g. "What databases has this candidate used?"

    Returns
    -------
    str — Gemini's answer based on the resume content
    """
    from langchain.chains.combine_documents import create_stuff_documents_chain
    from langchain.chains import create_retrieval_chain
    from langchain_core.prompts import ChatPromptTemplate
    from lc.llm import get_llm

    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are a helpful talent analyst. "
            "Answer the question about this candidate based ONLY on their resume below. "
            "If the information is not in the resume, say so clearly.\n\n"
            "Resume context:\n{context}"
        )),
        ("human", "{input}"),
    ])

    llm = get_llm()
    retriever = get_retriever(candidate_id=candidate_id, top_k=4)

    # LCEL chain: retriever → stuff documents → prompt → LLM
    document_chain = create_stuff_documents_chain(llm, prompt)
    rag_chain      = create_retrieval_chain(retriever, document_chain)

    result = rag_chain.invoke({"input": question})
    return result.get("answer", "Could not generate answer.")
