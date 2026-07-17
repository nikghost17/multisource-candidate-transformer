"""
lc/loaders.py
--------------
Load documents (PDF, DOCX, TXT, CSV) using LangChain document loaders.

Every loader returns a list of LangChain `Document` objects:
    Document(
        page_content = "the extracted text",
        metadata     = {"source": "path/to/file", "page": 0, ...}
    )

This completely replaces parsers/resume_parser.py for text extraction.
The merger still handles identity resolution and field mapping.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Optional, Tuple

from langchain_core.documents import Document


# ---------------------------------------------------------------------------
# Resume loaders
# ---------------------------------------------------------------------------

def load_pdf(file_path: str) -> List[Document]:
    """Load a PDF resume. Returns one Document per page."""
    from langchain_community.document_loaders import PyPDFLoader
    loader = PyPDFLoader(file_path)
    docs = loader.load()
    print(f"[LC Loader] PDF: {len(docs)} pages from {Path(file_path).name}")
    return docs


def load_docx(file_path: str) -> List[Document]:
    """Load a DOCX resume. Returns a single Document."""
    from langchain_community.document_loaders import Docx2txtLoader
    loader = Docx2txtLoader(file_path)
    docs = loader.load()
    print(f"[LC Loader] DOCX: {len(docs)} doc(s) from {Path(file_path).name}")
    return docs


def load_txt(file_path: str) -> List[Document]:
    """Load a plain text resume."""
    from langchain_community.document_loaders import TextLoader
    loader = TextLoader(file_path, encoding="utf-8")
    docs = loader.load()
    print(f"[LC Loader] TXT: {len(docs)} doc(s) from {Path(file_path).name}")
    return docs


def load_resume(file_path: str) -> List[Document]:
    """
    Auto-detect format and load a resume file.
    Returns list of Documents (1 per page for PDF, 1 total for DOCX/TXT).
    """
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        return load_pdf(file_path)
    elif ext in (".docx", ".doc"):
        return load_docx(file_path)
    elif ext in (".txt", ".text", ".md"):
        return load_txt(file_path)
    else:
        raise ValueError(f"Unsupported file type: {ext}. Use PDF, DOCX, or TXT.")


def get_full_text(docs: List[Document]) -> str:
    """Merge all page_content from a list of Documents into one string."""
    return "\n\n".join(d.page_content for d in docs if d.page_content.strip())


# ---------------------------------------------------------------------------
# CSV loader (replaces parsers/recruiter_csv.py for raw text extraction)
# ---------------------------------------------------------------------------

def load_csv_as_records(file_path: str) -> List[dict]:
    """
    Load a CSV file using Python's csv module and return a list of row dicts.
    This keeps our existing RecruiterCSVParser logic intact —
    LangChain's CSVLoader is useful for RAG but we need the raw dicts
    for the merger pipeline.
    """
    import csv
    records = []
    with open(file_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Lowercase all column names for consistency
            clean_row = {k.strip().lower().replace(" ", "_"): v.strip()
                         for k, v in row.items() if k}
            records.append(clean_row)
    print(f"[LC Loader] CSV: {len(records)} rows from {Path(file_path).name}")
    return records


# ---------------------------------------------------------------------------
# Quick heuristic extractors (same as before, used for identity resolution)
# ---------------------------------------------------------------------------

_EMAIL_RE    = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", re.I)
_PHONE_RE    = re.compile(r"(?:\+?\d[\d\s\-().]{6,}\d)")
_LINKEDIN_RE = re.compile(r"linkedin\.com/in/[\w\-]+", re.I)
_GITHUB_RE   = re.compile(r"github\.com/[\w\-]+", re.I)


def extract_quick_fields(text: str) -> dict:
    """
    Fast regex extraction of key identity fields from raw resume text.
    Used for the merger's identity resolution step BEFORE the LLM runs.
    """
    email   = (m := _EMAIL_RE.search(text)) and m.group(0).lower()
    phone   = (m := _PHONE_RE.search(text)) and m.group(0).strip()
    linkedin = (m := _LINKEDIN_RE.search(text)) and f"https://{m.group(0)}"
    github   = (m := _GITHUB_RE.search(text))  and f"https://{m.group(0)}"

    # Name heuristic: first 2-4 capitalized words in first 5 lines
    name = None
    for line in text.splitlines()[:6]:
        line = line.strip()
        if not line or "@" in line or "http" in line.lower() or len(line) > 60:
            continue
        words = line.split()
        if 2 <= len(words) <= 5 and all(w[0].isupper() for w in words if w.isalpha()):
            name = line
            break

    return {
        k: v for k, v in {
            "name":       name    or None,
            "email":      email   or None,
            "phone":      phone   or None,
            "linkedin":   linkedin or None,
            "github_url": github  or None,
        }.items() if v
    }
