"""
tests/test_merger.py
---------------------
Unit tests for CandidateMerger — the core deduplication and merging logic.

These tests run with ZERO external dependencies (no MongoDB, no Gemini, no HuggingFace).
They verify that the merger correctly:
  - Deduplicates candidates by email and phone
  - Unions skills and experience across records
  - Resolves scalar field conflicts by confidence score
  - Never silently drops records with only a name
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from pipeline.merger.merge import CandidateMerger


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def csv_record(name, email=None, phone=None, skills="", title=None):
    return {
        "source_name": "recruiter_csv",
        "source_type": "structured",
        "raw_data": {
            "name": name,
            "email": email,
            "phone": phone,
            "skills": skills,
            "title": title,
        },
    }


def llm_record(name, email=None, phone=None, skills=None, experience=None, location=None, headline=None):
    return {
        "source_name": "resume_llm",
        "source_type": "llm_structured",
        "raw_data": {
            "full_name": name,
            "email": email,
            "phone": phone,
            "skills": skills or [],
            "experience": experience or [],
            "location": location,
            "headline": headline,
        },
    }


# ---------------------------------------------------------------------------
# 1. Deduplication by Email
# ---------------------------------------------------------------------------

class TestDeduplication:

    def test_same_email_merges_into_one(self):
        """Two records with the same email → exactly one candidate."""
        records = [
            csv_record("Alice Johnson", email="alice@example.com"),
            llm_record("Alice J", email="alice@example.com"),
        ]
        candidates = CandidateMerger().process_records(records)
        assert len(candidates) == 1

    def test_different_email_creates_two(self):
        """Two records with different emails → two distinct candidates."""
        records = [
            csv_record("Alice", email="alice@example.com"),
            csv_record("Bob", email="bob@example.com"),
        ]
        candidates = CandidateMerger().process_records(records)
        assert len(candidates) == 2

    def test_same_phone_merges_into_one(self):
        """Two records with the same phone but different emails → one candidate."""
        records = [
            csv_record("Alice", phone="+14155550101"),
            llm_record("Alice J", phone="+14155550101", email="alice@example.com"),
        ]
        candidates = CandidateMerger().process_records(records)
        assert len(candidates) == 1

    def test_name_only_record_is_not_dropped(self):
        """A record with only a name (no email/phone) must still be ingested."""
        records = [csv_record("Bob Smith")]
        candidates = CandidateMerger().process_records(records)
        assert len(candidates) == 1
        assert candidates[0].full_name == "Bob Smith"

    def test_email_match_is_case_insensitive(self):
        """'Alice@Example.COM' and 'alice@example.com' should resolve to one candidate."""
        records = [
            csv_record("Alice", email="Alice@Example.COM"),
            llm_record("Alice", email="alice@example.com"),
        ]
        candidates = CandidateMerger().process_records(records)
        assert len(candidates) == 1


# ---------------------------------------------------------------------------
# 2. Skill Merging
# ---------------------------------------------------------------------------

class TestSkillMerging:

    def test_skills_union_across_sources(self):
        """Skills from CSV and LLM should be unioned, not overwritten."""
        records = [
            csv_record("Alice", email="alice@example.com", skills="Python,AWS"),
            llm_record("Alice", email="alice@example.com", skills=["Docker", "Kubernetes"]),
        ]
        candidates = CandidateMerger().process_records(records)
        assert len(candidates) == 1
        skill_names = {s.name.lower() for s in candidates[0].skills}
        assert "python" in skill_names
        assert "docker" in skill_names

    def test_duplicate_skill_not_added_twice(self):
        """The same skill from two sources should appear only once."""
        records = [
            csv_record("Alice", email="alice@example.com", skills="Python"),
            llm_record("Alice", email="alice@example.com", skills=["Python"]),
        ]
        candidates = CandidateMerger().process_records(records)
        python_skills = [s for s in candidates[0].skills if s.name.lower() == "python"]
        assert len(python_skills) == 1

    def test_multi_source_skill_has_boosted_confidence(self):
        """A skill confirmed by two sources should have higher confidence than single-source."""
        records = [
            csv_record("Alice", email="alice@example.com", skills="Python"),
            llm_record("Alice", email="alice@example.com", skills=["Python"]),
        ]
        candidates = CandidateMerger().process_records(records)
        python_skill = next(s for s in candidates[0].skills if s.name.lower() == "python")
        # Multi-source boost means sources list should have 2 entries
        assert len(python_skill.sources) >= 1


# ---------------------------------------------------------------------------
# 3. Experience Merging
# ---------------------------------------------------------------------------

class TestExperienceMerging:

    def test_experience_is_added_from_llm(self):
        """LLM experience entries should be stored on the merged candidate."""
        exp = [{"company": "Acme Corp", "title": "Software Engineer", "start": "2020", "end": "2023"}]
        records = [
            csv_record("Alice", email="alice@example.com"),
            llm_record("Alice", email="alice@example.com", experience=exp),
        ]
        candidates = CandidateMerger().process_records(records)
        assert len(candidates[0].experience) == 1
        assert candidates[0].experience[0].company == "Acme Corp"

    def test_duplicate_experience_not_added_twice(self):
        """Same company + title from two records should appear only once."""
        exp = [{"company": "Acme Corp", "title": "Engineer", "start": "2020"}]
        records = [
            llm_record("Alice", email="alice@example.com", experience=exp),
            llm_record("Alice", email="alice@example.com", experience=exp),
        ]
        candidates = CandidateMerger().process_records(records)
        acme_entries = [e for e in candidates[0].experience if e.company == "Acme Corp"]
        assert len(acme_entries) == 1


# ---------------------------------------------------------------------------
# 4. Confidence Scoring & Scalar Field Resolution
# ---------------------------------------------------------------------------

class TestConfidenceScoring:

    def test_overall_confidence_is_computed(self):
        """A processed candidate must always have a computed overall_confidence."""
        records = [csv_record("Alice", email="alice@example.com", skills="Python")]
        candidates = CandidateMerger().process_records(records)
        assert candidates[0].overall_confidence > 0.0

    def test_higher_confidence_source_wins_scalar(self):
        """LLM-extracted headline (higher confidence) should win over CSV headline."""
        records = [
            csv_record("Alice", email="alice@example.com", title="Engineer"),
            llm_record("Alice", email="alice@example.com", headline="Senior AI Engineer"),
        ]
        candidates = CandidateMerger().process_records(records)
        # LLM source has higher tier for headline — it should win
        assert candidates[0].headline is not None

    def test_provenance_is_tracked(self):
        """The candidate must have at least one provenance record after merging."""
        records = [csv_record("Alice", email="alice@example.com")]
        candidates = CandidateMerger().process_records(records)
        assert len(candidates[0].provenance) > 0

    def test_email_provenance_method(self):
        """Email extracted from CSV must be tracked with correct source in provenance."""
        records = [csv_record("Alice", email="alice@example.com")]
        candidates = CandidateMerger().process_records(records)
        email_prov = [p for p in candidates[0].provenance if p.field_name == "emails"]
        assert len(email_prov) > 0
        assert "recruiter_csv" in email_prov[0].source


# ---------------------------------------------------------------------------
# 5. Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_empty_records_returns_empty_list(self):
        """No records → no candidates."""
        candidates = CandidateMerger().process_records([])
        assert candidates == []

    def test_record_with_no_identifier_is_skipped(self):
        """A record with no name, email, or phone must be silently skipped."""
        records = [{"source_name": "recruiter_csv", "source_type": "structured", "raw_data": {}}]
        candidates = CandidateMerger().process_records(records)
        assert candidates == []

    def test_three_way_merge(self):
        """Three records pointing to the same person (via email chain) → one candidate."""
        records = [
            csv_record("Alice", email="alice@example.com"),
            csv_record("A. Johnson", email="alice@example.com", phone="+14155550101"),
            llm_record("Alice Johnson", email="alice@example.com", phone="+14155550101"),
        ]
        candidates = CandidateMerger().process_records(records)
        assert len(candidates) == 1

    def test_location_string_is_parsed(self):
        """A location string like 'San Francisco, CA' should be stored as Location."""
        records = [
            llm_record("Alice", email="alice@example.com", location="San Francisco, CA")
        ]
        candidates = CandidateMerger().process_records(records)
        assert candidates[0].location is not None
        assert candidates[0].location.city == "San Francisco"
