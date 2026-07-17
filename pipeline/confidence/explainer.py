"""
Confidence Explainer
---------------------
Generates a human-readable, structured breakdown of a candidate's
confidence scores per field, including the winning source and method.

Used by:
  - The FastAPI /candidates/{id}/confidence endpoint
  - The Web UI confidence visualization panel
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from models.candidate import Candidate
from pipeline.confidence.scorer import FIELD_IMPORTANCE, compute_overall_confidence


# Labels for displaying confidence levels in the UI
_LEVEL_LABELS = [
    (0.90, "Very High", "#22c55e"),   # green
    (0.75, "High",      "#86efac"),   # light green
    (0.60, "Medium",    "#facc15"),   # yellow
    (0.45, "Low",       "#f97316"),   # orange
    (0.00, "Very Low",  "#ef4444"),   # red
]


def _confidence_level(score: float) -> Dict[str, str]:
    for threshold, label, color in _LEVEL_LABELS:
        if score >= threshold:
            return {"label": label, "color": color}
    return {"label": "Very Low", "color": "#ef4444"}


def explain_candidate(candidate: Candidate) -> Dict[str, Any]:
    """
    Build a rich confidence explanation for a single candidate.

    Parameters
    ----------
    candidate : Candidate
        The fully merged candidate object.

    Returns
    -------
    dict
        A structured breakdown suitable for JSON serialisation and UI display.

    Example output
    --------------
    {
      "candidate_id": "...",
      "overall_confidence": 0.87,
      "overall_level": {"label": "Very High", "color": "#22c55e"},
      "llm_enriched": true,
      "source_summary": ["recruiter_csv", "github_api", "resume_llm"],
      "fields": [
        {
          "field": "full_name",
          "confidence": 0.90,
          "level": {"label": "Very High", "color": "#22c55e"},
          "source": "recruiter_csv",
          "method": "extracted",
          "importance": 2.0,
          "present": true
        },
        ...
      ]
    }
    """
    # Build provenance index: field_name -> best ProvenanceRecord
    prov_by_field: Dict[str, Any] = {}
    for prov in candidate.provenance:
        existing = prov_by_field.get(prov.field_name)
        if existing is None or prov.confidence > existing.confidence:
            prov_by_field[prov.field_name] = prov

    # Collect field-level data
    field_breakdown: List[Dict[str, Any]] = []
    field_confidences: Dict[str, float] = {}

    # Determine which fields are present on the candidate
    presence_checks = {
        "full_name":    lambda c: bool(c.full_name),
        "emails":       lambda c: bool(c.emails),
        "phones":       lambda c: bool(c.phones),
        "headline":     lambda c: bool(c.headline),
        "skills":       lambda c: bool(c.skills),
        "location":     lambda c: c.location is not None,
        "links":        lambda c: c.links is not None,
        "experience":   lambda c: bool(c.experience),
        "education":    lambda c: bool(c.education),
        "years_experience": lambda c: c.years_experience is not None,
        "llm_summary":  lambda c: bool(c.llm_summary),
    }

    for field_name, is_present in presence_checks.items():
        present = is_present(candidate)
        prov = prov_by_field.get(field_name)
        confidence = prov.confidence if prov else (0.0 if not present else 0.5)
        source     = prov.source     if prov else "unknown"
        method     = prov.method     if prov else "unknown"

        if present:
            field_confidences[field_name] = confidence

        field_breakdown.append({
            "field":      field_name,
            "confidence": round(confidence, 3),
            "level":      _confidence_level(confidence) if present else {"label": "Missing", "color": "#6b7280"},
            "source":     source,
            "method":     method,
            "importance": FIELD_IMPORTANCE.get(field_name, 1.0),
            "present":    present,
        })

    # Sort by importance descending, then by field name
    field_breakdown.sort(key=lambda x: (-x["importance"], x["field"]))

    # Unique sources used
    source_summary = sorted({
        prov.source for prov in candidate.provenance
        if prov.source not in ("unknown",)
    })

    overall = candidate.overall_confidence or compute_overall_confidence(field_confidences)

    return {
        "candidate_id":      candidate.candidate_id,
        "full_name":         candidate.full_name,
        "overall_confidence": overall,
        "overall_level":     _confidence_level(overall),
        "llm_enriched":      candidate.llm_enriched,
        "source_summary":    source_summary,
        "fields":            field_breakdown,
    }


def explain_batch(candidates: List[Candidate]) -> List[Dict[str, Any]]:
    """
    Run explain_candidate for a list of candidates.
    Returns a list of explanations sorted by overall_confidence descending.
    """
    explanations = [explain_candidate(c) for c in candidates]
    explanations.sort(key=lambda x: x["overall_confidence"], reverse=True)
    return explanations
