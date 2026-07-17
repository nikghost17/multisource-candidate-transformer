"""
lc/extractor.py
----------------
Structured resume extraction using LangChain's with_structured_output().

This is the KEY advantage of LangChain over doing it from scratch:

  structured_llm = llm.with_structured_output(CandidateExtraction)
  result = structured_llm.invoke(prompt)
  # result is a typed Pydantic object — no JSON parsing, no sanitisation needed

Gemini will ALWAYS return data matching the schema. If it can't, it returns
the field as None rather than hallucinating or throwing errors.

Usage:
    from lc.extractor import extract_from_resume
    data = extract_from_resume(resume_text)
    # data.full_name, data.skills, data.experience — all typed
"""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Output schema — Pydantic models define exactly what Gemini must return
# ---------------------------------------------------------------------------

class ExperienceItem(BaseModel):
    company: str                   = Field(description="Company or organisation name")
    title:   str                   = Field(description="Job title or role")
    start:   Optional[str]         = Field(None, description="Start date (YYYY-MM or YYYY)")
    end:     Optional[str]         = Field(None, description="End date or 'Present'")
    summary: Optional[str]         = Field(None, description="1-2 sentence role summary")


class EducationItem(BaseModel):
    institution:    str            = Field(description="University or college name")
    degree:         Optional[str]  = Field(None, description="Degree type e.g. B.Tech, M.S.")
    field_of_study: Optional[str]  = Field(None, description="Major or specialisation")
    end_year:       Optional[str]  = Field(None, description="Graduation year")


class LinksData(BaseModel):
    linkedin:  Optional[str] = Field(None, description="LinkedIn profile URL")
    github:    Optional[str] = Field(None, description="GitHub profile URL")
    portfolio: Optional[str] = Field(None, description="Portfolio or personal website URL")


class CandidateExtraction(BaseModel):
    """
    Complete structured extraction from a resume.
    Every field is Optional so partial resumes still work.
    """
    full_name:        Optional[str]          = Field(None,  description="Candidate's full name")
    emails:           List[str]              = Field([],    description="All email addresses found")
    phones:           List[str]              = Field([],    description="All phone numbers found")
    headline:         Optional[str]          = Field(None,  description="Job title or professional headline")
    years_experience: Optional[float]        = Field(None,  description="Total years of professional experience (compute from dates if not stated)")
    location:         Optional[str]          = Field(None,  description="City, region, country as free text")
    skills:           List[str]              = Field([],    description="Technical skills, tools, frameworks, languages")
    experience:       List[ExperienceItem]   = Field([],    description="Work experience entries, newest first")
    education:        List[EducationItem]    = Field([],    description="Education entries")
    links:            LinksData              = Field(default_factory=LinksData)
    llm_summary:      Optional[str]          = Field(None,  description="2-3 sentence professional summary of this candidate, written in third person")


# ---------------------------------------------------------------------------
# Extraction prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an expert resume parser for a talent intelligence platform.
Extract ALL information present in the resume text below.

Rules:
- Only extract information explicitly stated — do NOT invent or infer data.
- For years_experience: compute it by summing all experience durations if not stated.
- For skills: return canonical strings like "Python", "AWS", "Machine Learning".
- For dates: use YYYY-MM if month is known, or YYYY if only year is known.
- For llm_summary: write 2-3 sentences in third person highlighting the candidate's unique strengths.
- If a field has no information, leave it as null/empty — never guess.
"""

_HUMAN_TEMPLATE = """\
Parse the following resume and extract all candidate information:

{resume_text}
"""


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_from_resume(
    resume_text: str,
    rag_context: Optional[str] = None,
) -> CandidateExtraction:
    """
    Use Gemini to extract structured candidate data from resume text.

    Parameters
    ----------
    resume_text : str
        Full raw text of the resume (from lc/loaders.py).
    rag_context : str, optional
        Additional context retrieved from the vector store for this candidate.
        Appended to the prompt to help with poorly-formatted PDFs.

    Returns
    -------
    CandidateExtraction
        Fully typed Pydantic object — access fields directly as attributes.
    """
    from langchain_core.prompts import ChatPromptTemplate
    from lc.llm import get_llm

    if not resume_text or not resume_text.strip():
        return CandidateExtraction()

    # Truncate very long resumes to stay within token limits
    MAX_CHARS = 12_000
    text = resume_text[:MAX_CHARS]
    if len(resume_text) > MAX_CHARS:
        print(f"[LC Extractor] Truncated resume to {MAX_CHARS} chars")

    # Optionally prepend RAG context
    context_block = ""
    if rag_context and rag_context.strip():
        context_block = f"\n\nADDITIONAL CONTEXT (from semantic retrieval):\n{rag_context}\n"

    prompt = ChatPromptTemplate.from_messages([
        ("system", _SYSTEM_PROMPT),
        ("human",  _HUMAN_TEMPLATE),
    ])

    llm = get_llm(temperature=0.0)   # deterministic for extraction

    # THE KEY LANGCHAIN FEATURE:
    # with_structured_output() forces Gemini to return data matching CandidateExtraction
    # No JSON parsing, no sanitisation — it just works
    structured_llm = llm.with_structured_output(CandidateExtraction)

    chain = prompt | structured_llm

    print(f"[LC Extractor] Calling Gemini ({llm.model})…", flush=True)

    result: CandidateExtraction = chain.invoke({
        "resume_text": text + context_block
    })

    if result is None:
        result = CandidateExtraction()

    skill_count = len(result.skills or [])
    exp_count   = len(result.experience or [])
    print(
        f"[LC Extractor] Done: name={result.full_name!r} | "
        f"skills={skill_count} | exp={exp_count}",
        flush=True,
    )
    return result


def extraction_to_raw_record(extraction: CandidateExtraction) -> dict:
    """
    Convert a CandidateExtraction into the raw_record format
    expected by CandidateMerger.process_records().

    Converts the Pydantic model to a plain dict and wraps it.
    """
    data = extraction.model_dump()

    # Flatten links into top-level keys the merger expects
    links = data.pop("links", {}) or {}
    if links.get("linkedin"):
        data["linkedin"] = links["linkedin"]
    if links.get("github"):
        data["github_url"] = links["github"]
    if links.get("portfolio"):
        data["portfolio"] = links["portfolio"]

    return {
        "source_name": "resume_llm",
        "source_type": "llm_structured",
        "raw_data":    data,
    }
