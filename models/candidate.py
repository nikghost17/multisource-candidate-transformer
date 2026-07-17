from pydantic import BaseModel, Field
from typing import List, Optional


class ProvenanceRecord(BaseModel):
    """Tracks exactly where a specific field came from and how confident we are in it."""
    field_name: str
    source: str
    method: str
    confidence: float


class Skill(BaseModel):
    name: str
    confidence: float
    sources: List[str] = Field(default_factory=list)


class Location(BaseModel):
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None


class Links(BaseModel):
    linkedin: Optional[str] = None
    github: Optional[str] = None
    portfolio: Optional[str] = None
    other: List[str] = Field(default_factory=list)


class Experience(BaseModel):
    company: str
    title: str
    start: Optional[str] = None
    end: Optional[str] = None
    summary: Optional[str] = None


class Education(BaseModel):
    institution: str
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    end_year: Optional[str] = None


class Candidate(BaseModel):
    """The central, canonical representation of a candidate."""
    candidate_id: str
    full_name: Optional[str] = None
    emails: List[str] = Field(default_factory=list)
    phones: List[str] = Field(default_factory=list)
    location: Optional[Location] = None
    links: Optional[Links] = None
    headline: Optional[str] = None
    years_experience: Optional[float] = None
    skills: List[Skill] = Field(default_factory=list)
    experience: List[Experience] = Field(default_factory=list)
    education: List[Education] = Field(default_factory=list)

    # ── RAG / LLM enrichment fields ────────────────────────────────────────
    resume_raw_text: Optional[str] = None          # original extracted resume text
    llm_summary: Optional[str] = None              # 2-3 sentence LLM-generated profile
    rag_context: Optional[str] = None              # top chunks retrieved during enrichment
    llm_enriched: bool = False                      # True once LLM extraction has run
    embedding_id: Optional[str] = None             # reference key in ChromaDB
    potential_duplicate_of: Optional[str] = None   # candidate_id of soft-merge target

    provenance: List[ProvenanceRecord] = Field(default_factory=list)
    overall_confidence: float = 0.0