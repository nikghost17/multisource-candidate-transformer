"""
Multisource Candidate Matching Platform
FastAPI REST API
-----------------
All imports use the standalone package structure:
  models/      — Pydantic data models
  pipeline/    — merger, confidence, normalizers, parsers
  lc/          — LangChain AI layer
  api/         — storage + this file

Endpoints:
  POST   /candidates/from-csv       Upload recruiter CSV
  POST   /candidates/from-resume    Upload PDF / DOCX / TXT resume
  GET    /candidates                List all candidates (paginated)
  GET    /candidates/{id}           Get single candidate
  GET    /candidates/{id}/confidence  Per-field confidence breakdown
  POST   /candidates/{id}/enrich    Trigger Gemini LLM enrichment
  GET    /candidates/search?q=      Semantic search
  POST   /candidates/merge          Merge two candidates
  DELETE /candidates/{id}           Delete candidate + embeddings

Run:
  uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# ── Make project root importable ────────────────────────────────────────────
_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from dotenv import load_dotenv
load_dotenv(Path(_root) / ".env")

# ── Domain layer ─────────────────────────────────────────────────────────────
from models.candidate import Candidate
from pipeline.merger.merge import CandidateMerger
from pipeline.confidence.explainer import explain_candidate
from api.mongo_storage import MongoStorage          # ← MongoDB (was: api.storage)

# ── LangChain layer ───────────────────────────────────────────────────────────
from lc.loaders import load_resume, get_full_text, extract_quick_fields
from lc.splitter import split_documents
from lc import mongo_vectorstore as lc_vs          # ← MongoDB (was: lc.vectorstore)
from lc.extractor import extract_from_resume, extraction_to_raw_record
from lc.retriever import search_candidates, build_candidate_context

# ── App setup ─────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Multisource Candidate Matching Platform",
    description=(
        "End-to-end candidate intelligence: CSV + resume ingestion, "
        "Gemini LLM enrichment, RAG-powered semantic search, "
        "confidence scoring & provenance tracking."
    ),
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_ui_dir = Path(_root) / "ui"
if _ui_dir.exists():
    app.mount("/ui", StaticFiles(directory=str(_ui_dir), html=True), name="ui")

# ── Singletons ────────────────────────────────────────────────────────────────
_store: Optional[MongoStorage] = None

def get_store() -> MongoStorage:
    global _store
    if _store is None:
        _store = MongoStorage()
    return _store


# ── Helper ─────────────────────────────────────────────────────────────────────
def _c(candidate: Candidate, strip_raw: bool = True) -> Dict[str, Any]:
    data = candidate.model_dump()
    if strip_raw:
        data.pop("resume_raw_text", None)
        data.pop("rag_context", None)
    return data


def _dedup_against_store(candidates: List[Candidate], store: CandidateStore) -> List[Candidate]:
    """
    For each newly merged candidate, check if an existing candidate in the
    store shares any email or phone. If yes, merge the new data INTO the
    existing record (preserving its ID) instead of creating a duplicate.

    Returns the final list of candidates (deduplicated, ready to upsert).
    """
    result = []
    for new_c in candidates:
        existing = store.find_by_identity(
            emails=new_c.emails,
            phones=new_c.phones,
        )
        if existing:
            # Merge new data into existing — add any new emails, phones, skills
            for email in new_c.emails:
                if email not in existing.emails:
                    existing.emails.append(email)
            for phone in new_c.phones:
                if phone not in existing.phones:
                    existing.phones.append(phone)
            for skill in new_c.skills:
                if not any(s.name == skill.name for s in existing.skills):
                    existing.skills.append(skill)
            for exp in new_c.experience:
                if not any(e.company == exp.company and e.title == exp.title
                           for e in existing.experience):
                    existing.experience.append(exp)
            for edu in new_c.education:
                if not any(e.institution == edu.institution
                           for e in existing.education):
                    existing.education.append(edu)
            # Update scalar fields if new source has better confidence
            if new_c.overall_confidence > existing.overall_confidence:
                if new_c.full_name:    existing.full_name    = new_c.full_name
                if new_c.headline:     existing.headline     = new_c.headline
                if new_c.location:     existing.location     = new_c.location
                if new_c.llm_summary:  existing.llm_summary  = new_c.llm_summary
            # Always carry forward resume text + metadata from new source
            if new_c.resume_raw_text and not existing.resume_raw_text:
                existing.resume_raw_text = new_c.resume_raw_text
            if new_c.embedding_id and not existing.embedding_id:
                existing.embedding_id = new_c.embedding_id
            if new_c.years_experience and not existing.years_experience:
                existing.years_experience = new_c.years_experience
            # Keep the existing candidate's ID
            result.append(existing)
            print(f"[Dedup] Merged into existing {existing.candidate_id[:8]}… ({existing.full_name})")
        else:
            result.append(new_c)
    return result


# ── Health ─────────────────────────────────────────────────────────────────────
@app.get("/health", tags=["System"])
def health():
    return {"status": "ok", "version": "1.0.0"}


# ── POST /candidates/from-csv ──────────────────────────────────────────────────
@app.post("/candidates/from-csv", tags=["Ingestion"])
async def ingest_csv(
    file: UploadFile = File(...),
    enable_llm: bool = Form(False, description="LLM conflict resolution"),
):
    """Upload a recruiter CSV → merged candidate profiles."""
    if not file.filename.endswith(".csv"):
        raise HTTPException(400, "Only .csv files accepted.")

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        from pipeline.parsers.recruiter_csv import RecruiterCSVParser
        records    = RecruiterCSVParser(tmp_path).parse()
        merger     = CandidateMerger(enable_llm_conflict_resolution=enable_llm)
        candidates = merger.process_records(records)

        # Cross-upload deduplication — merge into existing if same email/phone
        store      = get_store()
        candidates = _dedup_against_store(candidates, store)

        store.upsert_many(candidates)
        return {
            "message":       f"Ingested {len(candidates)} candidates.",
            "candidate_ids": [c.candidate_id for c in candidates],
            "candidates":    [_c(c) for c in candidates],
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, str(e))
    finally:
        os.unlink(tmp_path)


# ── POST /candidates/from-resume ───────────────────────────────────────────────
@app.post("/candidates/from-resume", tags=["Ingestion"])
async def ingest_resume(
    file: UploadFile = File(...),
    enrich_with_llm: bool = Form(True, description="Extract structured data with Gemini"),
):
    """Upload a resume (PDF / DOCX / TXT) → enriched candidate profile."""
    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".pdf", ".docx", ".txt", ".text"):
        raise HTTPException(400, f"Unsupported type '{suffix}'. Use PDF, DOCX, or TXT.")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        # 1. Load + extract text via LangChain loader
        docs     = load_resume(tmp_path)
        raw_text = get_full_text(docs)
        if not raw_text.strip():
            raise HTTPException(422, "No text could be extracted from the file.")

        # 2. Quick heuristic fields (email, phone, name) for identity resolution
        quick = extract_quick_fields(raw_text)
        quick["raw_text"] = raw_text

        raw_records = [{"source_name": "resume_parsed", "source_type": "unstructured", "raw_data": quick}]

        # 3. Gemini structured extraction via with_structured_output
        if enrich_with_llm:
            try:
                extraction = extract_from_resume(raw_text)
                rec        = extraction_to_raw_record(extraction)
                rec["raw_data"]["raw_text"] = raw_text
                raw_records.append(rec)
            except Exception as e:
                print(f"[API] LLM enrichment skipped: {e}")

        # 4. Merge into canonical Candidate
        candidates = CandidateMerger().process_records(raw_records)
        if not candidates:
            raise HTTPException(422, "Could not create candidate profile.")

        candidate = candidates[0]

        # Cross-upload deduplication — merge into existing if same email/phone
        store     = get_store()
        [candidate] = _dedup_against_store([candidate], store)

        # 5. Chunk + index in ChromaDB via LangChain
        n_chunks = lc_vs.index_resume(candidate.candidate_id, split_documents(docs))
        candidate.embedding_id = candidate.candidate_id
        print(f"[API] Indexed {n_chunks} chunks for {candidate.candidate_id[:8]}")

        # 6. Persist
        store.upsert(candidate)

        return {
            "message":      "Resume ingested successfully.",
            "candidate_id": candidate.candidate_id,
            "candidate":    _c(candidate),
        }
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, str(e))
    finally:
        os.unlink(tmp_path)


# ── GET /candidates ─────────────────────────────────────────────────────────────
@app.get("/candidates", tags=["Candidates"])
def list_candidates(
    page:      int = Query(1,  ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List all candidates sorted by confidence descending."""
    store = get_store()
    return {
        "total":      store.count(),
        "page":       page,
        "page_size":  page_size,
        "candidates": [_c(c) for c in store.list_all(page, page_size)],
    }


# ── GET /candidates/search ─────────────────────────────────────────────────────
@app.get("/candidates/search", tags=["Search"])
def semantic_search(
    q:     str = Query(..., min_length=2),
    top_k: int = Query(10,  ge=1, le=50),
):
    """Semantic search across all indexed resumes using natural language."""
    hits  = search_candidates(q, top_k=top_k)
    store = get_store()
    results = []
    for hit in hits:
        cid = hit.get("candidate_id")
        if cid:
            c = store.get(cid)
            if c:
                results.append({
                    "candidate":       _c(c),
                    "relevance_score": hit.get("similarity", 0.0),
                    "matched_chunk":   hit.get("text", "")[:300],
                })
    return {"query": q, "results": results}


# ── GET /candidates/{id} ────────────────────────────────────────────────────────
@app.get("/candidates/{candidate_id}", tags=["Candidates"])
def get_candidate(candidate_id: str):
    c = get_store().get(candidate_id)
    if not c:
        raise HTTPException(404, f"Candidate {candidate_id!r} not found.")
    return _c(c)


# ── GET /candidates/{id}/confidence ────────────────────────────────────────────
@app.get("/candidates/{candidate_id}/confidence", tags=["Candidates"])
def get_confidence(candidate_id: str):
    """Per-field confidence breakdown with source and method."""
    c = get_store().get(candidate_id)
    if not c:
        raise HTTPException(404, f"Candidate {candidate_id!r} not found.")
    return explain_candidate(c)


# ── POST /candidates/{id}/enrich ───────────────────────────────────────────────
@app.post("/candidates/{candidate_id}/enrich", tags=["Enrichment"])
def enrich_candidate(candidate_id: str):
    """Re-run Gemini LLM extraction on a candidate's stored resume text."""
    store = get_store()
    c     = store.get(candidate_id)
    if not c:
        raise HTTPException(404, f"Candidate {candidate_id!r} not found.")
    if not c.resume_raw_text:
        raise HTTPException(422, "No resume text stored. Upload the resume first.")
    if c.llm_enriched:
        return {"message": "Already enriched.", "candidate": _c(c)}

    try:
        rag_ctx    = build_candidate_context(candidate_id)
        extraction = extract_from_resume(c.resume_raw_text, rag_context=rag_ctx or None)
        rec = extraction_to_raw_record(extraction)
        rec["raw_data"]["raw_text"] = c.resume_raw_text
        
        # Inject existing identifiers so the merger can link them if needed
        if c.emails: rec["raw_data"]["email"] = c.emails[0]
        if c.phones: rec["raw_data"]["phone"] = c.phones[0]

        temp_cands = CandidateMerger().process_records([rec])
        if not temp_cands:
            raise HTTPException(500, "Enrichment produced no candidate.")
        
        extracted_cand = temp_cands[0]
        extracted_cand.llm_enriched = True
        
        # Merge the newly extracted data into the existing candidate in the store
        [enriched] = _dedup_against_store([extracted_cand], store)
        
        return {"message": "Enriched with Gemini.", "candidate": _c(enriched)}

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, str(e))


# ── POST /candidates/merge ─────────────────────────────────────────────────────
@app.post("/candidates/merge", tags=["Candidates"])
def merge_candidates(body: Dict[str, str]):
    """Merge secondary candidate into primary, then delete secondary."""
    pid = body.get("primary_id")
    sid = body.get("secondary_id")
    if not pid or not sid:
        raise HTTPException(400, "Both 'primary_id' and 'secondary_id' required.")
    if pid == sid:
        raise HTTPException(400, "Cannot merge a candidate with itself.")

    store = get_store()
    p = store.get(pid)
    s = store.get(sid)
    if not p: raise HTTPException(404, f"Primary {pid!r} not found.")
    if not s: raise HTTPException(404, f"Secondary {sid!r} not found.")

    # Merge collections
    for email in s.emails:
        if email not in p.emails: p.emails.append(email)
    for phone in s.phones:
        if phone not in p.phones: p.phones.append(phone)
    for skill in s.skills:
        if not any(sk.name == skill.name for sk in p.skills): p.skills.append(skill)
    for exp in s.experience:
        if not any(e.company == exp.company and e.title == exp.title for e in p.experience):
            p.experience.append(exp)
    for edu in s.education:
        if not any(e.institution == edu.institution for e in p.education):
            p.education.append(edu)

    store.upsert(p)
    store.delete(sid)
    lc_vs.delete_candidate(sid)

    return {"message": f"Merged into {pid[:8]}…", "merged_candidate": _c(p)}


# ── DELETE /candidates/{id} ────────────────────────────────────────────────────
@app.delete("/candidates/{candidate_id}", tags=["Candidates"])
def delete_candidate(candidate_id: str):
    """Delete candidate and their vector store embeddings."""
    if not get_store().delete(candidate_id):
        raise HTTPException(404, f"Candidate {candidate_id!r} not found.")
    lc_vs.delete_candidate(candidate_id)
    return {"message": f"Candidate {candidate_id} deleted."}


# ── DELETE /candidates ─────────────────────────────────────────────────────────
@app.delete("/candidates", tags=["System"])
def clear_all_candidates():
    """
    Delete ALL candidates and wipe the vector store.
    Useful for resetting the platform during development/demo.
    """
    count = get_store().clear()
    # Clear chroma collection too
    try:
        vs = lc_vs.get_vectorstore()
        vs._collection.delete(where={"chunk_index": {"$gte": 0}})
    except Exception:
        pass  # best effort
    return {"message": f"Cleared {count} candidates.", "deleted": count}
