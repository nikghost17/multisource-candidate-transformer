"""
tests/test_api.py
------------------
Integration tests for the FastAPI HTTP endpoints.

MongoDB and LLM calls are fully mocked via the `client` fixture in conftest.py,
so these tests run offline and instantly.

Tests cover:
  - POST /candidates/from-csv
  - GET  /candidates
  - GET  /candidates/{id}
  - POST /candidates/{id}/enrich
  - DELETE /candidates/{id}
  - GET  /health
"""

from __future__ import annotations

import io
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------

class TestHealth:

    def test_health_returns_200(self, client):
        """GET /health must return HTTP 200 with status=ok."""
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# CSV Ingestion
# ---------------------------------------------------------------------------

class TestCSVIngestion:

    def test_upload_valid_csv_returns_200(self, client, sample_csv_bytes):
        """Uploading a well-formed CSV must return HTTP 200."""
        resp = client.post(
            "/candidates/from-csv",
            files={"file": ("candidates.csv", io.BytesIO(sample_csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200

    def test_upload_csv_creates_candidates(self, client, sample_csv_bytes, in_memory_store):
        """After CSV upload the store must contain the ingested candidates."""
        client.post(
            "/candidates/from-csv",
            files={"file": ("candidates.csv", io.BytesIO(sample_csv_bytes), "text/csv")},
        )
        assert in_memory_store.count() > 0

    def test_upload_csv_returns_candidate_count(self, client, sample_csv_bytes):
        """Response body must include how many candidates were ingested."""
        resp = client.post(
            "/candidates/from-csv",
            files={"file": ("candidates.csv", io.BytesIO(sample_csv_bytes), "text/csv")},
        )
        body = resp.json()
        assert "ingested" in body or "candidates" in body or "count" in str(body).lower()

    def test_upload_invalid_file_type_returns_400(self, client):
        """Uploading a .xlsx file must return HTTP 400."""
        resp = client.post(
            "/candidates/from-csv",
            files={"file": ("data.xlsx", io.BytesIO(b"fake"), "application/vnd.ms-excel")},
        )
        assert resp.status_code == 400

    def test_upload_empty_csv_returns_error(self, client):
        """Uploading a completely empty CSV must not crash the server."""
        empty_csv = b"name,email,phone\n"
        resp = client.post(
            "/candidates/from-csv",
            files={"file": ("empty.csv", io.BytesIO(empty_csv), "text/csv")},
        )
        # Should return a sensible error (4xx) or empty success, but never 500
        assert resp.status_code != 500


# ---------------------------------------------------------------------------
# Candidate Listing
# ---------------------------------------------------------------------------

class TestCandidateListing:

    def _seed(self, client, sample_csv_bytes):
        client.post(
            "/candidates/from-csv",
            files={"file": ("candidates.csv", io.BytesIO(sample_csv_bytes), "text/csv")},
        )

    def test_list_candidates_returns_200(self, client, sample_csv_bytes):
        """GET /candidates must return HTTP 200."""
        self._seed(client, sample_csv_bytes)
        resp = client.get("/candidates")
        assert resp.status_code == 200

    def test_list_candidates_is_list(self, client, sample_csv_bytes):
        """GET /candidates response body must contain a 'candidates' list."""
        self._seed(client, sample_csv_bytes)
        resp = client.get("/candidates")
        body = resp.json()
        assert "candidates" in body
        assert isinstance(body["candidates"], list)

    def test_list_candidates_reflects_uploaded(self, client, sample_csv_bytes):
        """Listed candidates must match what was uploaded."""
        self._seed(client, sample_csv_bytes)
        resp = client.get("/candidates")
        assert len(resp.json()["candidates"]) >= 2  # CSV has Alice and Bob

    def test_pagination_page_size(self, client, sample_csv_bytes):
        """page_size=1 must return at most 1 candidate."""
        self._seed(client, sample_csv_bytes)
        resp = client.get("/candidates?page=1&page_size=1")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["candidates"]) <= 1


# ---------------------------------------------------------------------------
# Single Candidate Retrieval
# ---------------------------------------------------------------------------

class TestCandidateRetrieval:

    def _upload_and_get_id(self, client, sample_csv_bytes):
        upload = client.post(
            "/candidates/from-csv",
            files={"file": ("candidates.csv", io.BytesIO(sample_csv_bytes), "text/csv")},
        )
        return client.get("/candidates").json()["candidates"][0]["candidate_id"]

    def test_get_existing_candidate_returns_200(self, client, sample_csv_bytes):
        """GET /candidates/{id} for an existing candidate must return 200."""
        cid = self._upload_and_get_id(client, sample_csv_bytes)
        resp = client.get(f"/candidates/{cid}")
        assert resp.status_code == 200

    def test_get_missing_candidate_returns_404(self, client):
        """GET /candidates/{id} for a non-existent ID must return 404."""
        resp = client.get("/candidates/does-not-exist-1234")
        assert resp.status_code == 404

    def test_candidate_has_required_fields(self, client, sample_csv_bytes):
        """A retrieved candidate must include candidate_id, full_name, and emails."""
        cid = self._upload_and_get_id(client, sample_csv_bytes)
        body = client.get(f"/candidates/{cid}").json()
        assert "candidate_id" in body
        assert "full_name" in body
        assert "emails" in body


# ---------------------------------------------------------------------------
# Resume Upload
# ---------------------------------------------------------------------------

class TestResumeIngestion:

    def test_upload_txt_resume_returns_200(self, client, sample_resume_txt):
        """Uploading a plain-text resume must return HTTP 200."""
        with patch("api.main.extract_from_resume") as mock_llm:
            mock_llm.side_effect = Exception("LLM disabled for test")
            resp = client.post(
                "/candidates/from-resume",
                data={"enrich_with_llm": "false"},
                files={"file": ("resume.txt", io.BytesIO(sample_resume_txt), "text/plain")},
            )
        assert resp.status_code == 200

    def test_upload_unsupported_resume_type_returns_400(self, client):
        """Uploading a .docx-like file with wrong mime must return HTTP 400."""
        resp = client.post(
            "/candidates/from-resume",
            data={"enrich_with_llm": "false"},
            files={"file": ("resume.zip", io.BytesIO(b"PK"), "application/zip")},
        )
        assert resp.status_code == 400

    def test_resume_stored_in_store(self, client, sample_resume_txt, in_memory_store):
        """After resume upload the candidate must be persisted in the store."""
        with patch("api.main.extract_from_resume") as mock_llm:
            mock_llm.side_effect = Exception("LLM disabled for test")
            client.post(
                "/candidates/from-resume",
                data={"enrich_with_llm": "false"},
                files={"file": ("resume.txt", io.BytesIO(sample_resume_txt), "text/plain")},
            )
        assert in_memory_store.count() == 1


# ---------------------------------------------------------------------------
# LLM Enrichment
# ---------------------------------------------------------------------------

class TestEnrichment:

    def _create_candidate_with_resume(self, client, in_memory_store, sample_resume_txt):
        """Helper: upload resume (no LLM) and return the candidate_id."""
        with patch("api.main.extract_from_resume") as mock_llm:
            mock_llm.side_effect = Exception("LLM disabled for setup")
            client.post(
                "/candidates/from-resume",
                data={"enrich_with_llm": "false"},
                files={"file": ("resume.txt", io.BytesIO(sample_resume_txt), "text/plain")},
            )
        return list(in_memory_store._data.values())[0].candidate_id

    def test_enrich_returns_200_on_success(self, client, in_memory_store, sample_resume_txt):
        """POST /candidates/{id}/enrich must return 200 when LLM succeeds."""
        from lc.extractor import CandidateExtraction
        cid = self._create_candidate_with_resume(client, in_memory_store, sample_resume_txt)

        mock_extraction = CandidateExtraction(
            full_name="John Doe",
            emails=["john.doe@example.com"],
            phones=["+14155550303"],
            skills=["Python", "Go", "Docker"],
            headline="Software Engineer",
        )

        with patch("api.main.extract_from_resume", return_value=mock_extraction):
            resp = client.post(f"/candidates/{cid}/enrich")

        assert resp.status_code == 200

    def test_enrich_nonexistent_candidate_returns_404(self, client):
        """POST /candidates/bad-id/enrich must return 404."""
        resp = client.post("/candidates/nonexistent-id-999/enrich")
        assert resp.status_code == 404

    def test_enrich_marks_llm_enriched_true(self, client, in_memory_store, sample_resume_txt):
        """After enrichment, the API response must confirm 'Enriched with Gemini'."""
        from lc.extractor import CandidateExtraction
        cid = self._create_candidate_with_resume(client, in_memory_store, sample_resume_txt)

        mock_extraction = CandidateExtraction(
            full_name="John Doe",
            emails=["john.doe@example.com"],
            skills=["Python"],
        )

        with patch("api.main.extract_from_resume", return_value=mock_extraction):
            resp = client.post(f"/candidates/{cid}/enrich")

        assert resp.status_code == 200
        assert "Enriched" in resp.json().get("message", "")

    def test_enrich_adds_skills_from_llm(self, client, in_memory_store, sample_resume_txt):
        """After enrichment, LLM-extracted skills must appear on the candidate."""
        from lc.extractor import CandidateExtraction
        cid = self._create_candidate_with_resume(client, in_memory_store, sample_resume_txt)

        mock_extraction = CandidateExtraction(
            full_name="John Doe",
            emails=["john.doe@example.com"],
            skills=["Python", "Go", "Docker", "Kubernetes", "PostgreSQL"],
        )

        with patch("api.main.extract_from_resume", return_value=mock_extraction):
            client.post(f"/candidates/{cid}/enrich")

        candidate = in_memory_store.get(cid)
        skill_names = {s.name.lower() for s in candidate.skills}
        assert "python" in skill_names


# ---------------------------------------------------------------------------
# Candidate Deletion
# ---------------------------------------------------------------------------

class TestDeletion:

    def _upload_and_get_id(self, client, sample_csv_bytes):
        client.post(
            "/candidates/from-csv",
            files={"file": ("candidates.csv", io.BytesIO(sample_csv_bytes), "text/csv")},
        )
        return client.get("/candidates").json()["candidates"][0]["candidate_id"]

    def test_delete_existing_returns_200(self, client, sample_csv_bytes):
        """DELETE /candidates/{id} for an existing candidate must return 200."""
        cid = self._upload_and_get_id(client, sample_csv_bytes)
        resp = client.delete(f"/candidates/{cid}")
        assert resp.status_code == 200

    def test_delete_removes_from_store(self, client, sample_csv_bytes, in_memory_store):
        """After deletion, the candidate must no longer exist in the store."""
        cid = self._upload_and_get_id(client, sample_csv_bytes)
        client.delete(f"/candidates/{cid}")
        assert in_memory_store.get(cid) is None

    def test_delete_nonexistent_returns_404(self, client):
        """DELETE /candidates/bad-id must return 404."""
        resp = client.delete("/candidates/totally-fake-id-abc")
        assert resp.status_code == 404
