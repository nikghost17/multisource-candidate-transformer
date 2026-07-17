"""
Simple JSON-file-based storage for candidate profiles.

Provides thread-safe read/write operations on a single JSON file.
Suitable for a portfolio project; can be swapped for SQLite/Postgres later.

File format: { "candidate_id": { ...candidate fields... }, ... }
"""

from __future__ import annotations

import json
import os
import threading
from typing import Dict, List, Optional, Any

from models.candidate import Candidate

_DEFAULT_STORE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "output", "candidates_store.json"
)


class CandidateStore:
    """
    Thread-safe persistent store for Candidate objects.

    Parameters
    ----------
    store_path : str, optional
        Path to the JSON file. Created automatically if it doesn't exist.
    """

    def __init__(self, store_path: Optional[str] = None):
        self._path = store_path or os.getenv("CANDIDATE_STORE_PATH", _DEFAULT_STORE_PATH)
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._lock = threading.Lock()
        self._data: Dict[str, Dict[str, Any]] = self._load()

    def _load(self) -> Dict[str, Dict[str, Any]]:
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save(self) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def upsert(self, candidate: Candidate) -> None:
        """Insert or replace a candidate record."""
        with self._lock:
            self._data[candidate.candidate_id] = candidate.model_dump()
            self._save()

    def upsert_many(self, candidates: List[Candidate]) -> None:
        """Bulk upsert."""
        with self._lock:
            for c in candidates:
                self._data[c.candidate_id] = c.model_dump()
            self._save()

    def get(self, candidate_id: str) -> Optional[Candidate]:
        """Fetch a single candidate by ID."""
        with self._lock:
            raw = self._data.get(candidate_id)
        if raw is None:
            return None
        return Candidate.model_validate(raw)

    def list_all(self, page: int = 1, page_size: int = 20) -> List[Candidate]:
        """Return a paginated list of all candidates, sorted by confidence desc."""
        with self._lock:
            all_raw = list(self._data.values())

        all_raw.sort(key=lambda r: r.get("overall_confidence", 0), reverse=True)
        start = (page - 1) * page_size
        end   = start + page_size
        return [Candidate.model_validate(r) for r in all_raw[start:end]]

    def count(self) -> int:
        with self._lock:
            return len(self._data)

    def delete(self, candidate_id: str) -> bool:
        """Delete a candidate. Returns True if it existed."""
        with self._lock:
            existed = candidate_id in self._data
            if existed:
                del self._data[candidate_id]
                self._save()
        return existed

    def update_fields(self, candidate_id: str, updates: Dict[str, Any]) -> Optional[Candidate]:
        """Partial update of specific fields on an existing candidate."""
        with self._lock:
            if candidate_id not in self._data:
                return None
            self._data[candidate_id].update(updates)
            self._save()
            return Candidate.model_validate(self._data[candidate_id])

    def search_by_name(self, query: str) -> List[Candidate]:
        """Simple case-insensitive name substring search."""
        q = query.lower().strip()
        with self._lock:
            matching = [
                r for r in self._data.values()
                if q in (r.get("full_name") or "").lower()
            ]
        return [Candidate.model_validate(r) for r in matching]

    def find_by_identity(
        self,
        emails: List[str] = None,
        phones: List[str] = None,
    ) -> Optional[Candidate]:
        """
        Find an existing candidate that shares any email or phone.
        Used for cross-upload deduplication — returns first match or None.
        """
        norm_emails = {e.lower().strip() for e in (emails or []) if e}
        norm_phones = {p.strip() for p in (phones or []) if p}
        if not norm_emails and not norm_phones:
            return None
        with self._lock:
            for raw in self._data.values():
                stored_emails = {e.lower().strip() for e in (raw.get("emails") or []) if e}
                stored_phones = {p.strip() for p in (raw.get("phones") or []) if p}
                if (norm_emails & stored_emails) or (norm_phones & stored_phones):
                    return Candidate.model_validate(raw)
        return None

    def clear(self) -> int:
        """Delete all candidates and wipe the store file. Returns count deleted."""
        with self._lock:
            count = len(self._data)
            self._data = {}
            self._save()
        return count
