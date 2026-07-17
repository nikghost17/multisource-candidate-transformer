"""
lc/splitter.py
---------------
Text splitting configuration for resume chunking.

Uses LangChain's RecursiveCharacterTextSplitter which is smarter than
a manual regex chunker — it tries to split on natural boundaries first:
  paragraphs → sentences → words → characters

Usage:
    from lc.splitter import get_splitter, split_documents
    chunks = split_documents(docs)
"""

from __future__ import annotations
from typing import List
from langchain_core.documents import Document


# Tuned for resumes:
# - 1000 chars ≈ 250 tokens, fits well inside embedding model limits
# - 150 char overlap preserves context at chunk boundaries
CHUNK_SIZE    = 1000
CHUNK_OVERLAP = 150


def get_splitter():
    """
    Returns a configured RecursiveCharacterTextSplitter.

    Split priority (tries each separator in order):
      1. Double newline   — paragraph break (most natural resume boundary)
      2. Single newline   — line break
      3. Period + space   — sentence end
      4. Space            — word boundary (last resort)
    """
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    return RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
        length_function=len,
        is_separator_regex=False,
    )


def split_documents(docs: List[Document]) -> List[Document]:
    """
    Split a list of Documents into smaller chunks.
    Metadata from parent docs (source, page) is inherited by each chunk.

    Parameters
    ----------
    docs : list[Document]  — e.g. output of load_resume()

    Returns
    -------
    list[Document]  — chunked Documents ready for embedding
    """
    splitter = get_splitter()
    chunks = splitter.split_documents(docs)
    print(f"[LC Splitter] {len(docs)} doc(s) → {len(chunks)} chunks")
    return chunks


def split_text(text: str) -> List[str]:
    """Split raw text string into chunk strings (no Document wrapper)."""
    splitter = get_splitter()
    return splitter.split_text(text)
