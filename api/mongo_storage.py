"""
api/mongo_storage.py
---------------------
MongoDB-backed CandidateStore.

Replaces api/storage.py (JSON file) with a proper MongoDB collection.
Collection: candidate_platform.candidates

Each document = one Candidate (stored as raw dict, keyed by candidate_id).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
load_dotenv()

from models.candidate import Candidate


def _get_collection():
    """Lazy-connect and return the `candidates` collection."""
    from pymongo import MongoClient
    uri = os.getenv("MONGODB_URI", "")
    if not uri:
        raise RuntimeError("MONGODB_URI not set in .env")
    db_name = os.getenv("MONGODB_DB", "candidate_platform")
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    return client[db_name]["candidates"]


class MongoStorage:
    """
    Thread-safe MongoDB store for Candidate objects.

    API is identical to the old CandidateStore so api/main.py
    only needs the import swapped — nothing else changes.
    """

    def __init__(self):
        self._col = _get_collection()
        # Ensure unique index on candidate_id
        self._col.create_index("candidate_id", unique=True, background=True)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def upsert(self, candidate: Candidate) -> None:
        """Insert or replace a candidate record."""
        doc = candidate.model_dump()
        doc["_id"] = candidate.candidate_id   # use candidate_id as Mongo _id
        self._col.replace_one(
            {"candidate_id": candidate.candidate_id},
            doc,
            upsert=True,
        )

    def upsert_many(self, candidates: List[Candidate]) -> None:
        """Bulk upsert."""
        for c in candidates:
            self.upsert(c)

    def get(self, candidate_id: str) -> Optional[Candidate]:
        """Fetch a single candidate by ID."""
        doc = self._col.find_one({"candidate_id": candidate_id})
        if doc is None:
            return None
        doc.pop("_id", None)
        return Candidate.model_validate(doc)

    def list_all(self, page: int = 1, page_size: int = 20) -> List[Candidate]:
        """Return paginated candidates sorted by confidence desc."""
        skip = (page - 1) * page_size
        cursor = (
            self._col
            .find({}, {"_id": 0})
            .sort("overall_confidence", -1)
            .skip(skip)
            .limit(page_size)
        )
        return [Candidate.model_validate(doc) for doc in cursor]

    def count(self) -> int:
        return self._col.count_documents({})

    def delete(self, candidate_id: str) -> bool:
        """Delete a candidate. Returns True if it existed."""
        result = self._col.delete_one({"candidate_id": candidate_id})
        return result.deleted_count > 0

    def update_fields(self, candidate_id: str, updates: Dict[str, Any]) -> Optional[Candidate]:
        """Partial update of specific fields."""
        result = self._col.find_one_and_update(
            {"candidate_id": candidate_id},
            {"$set": updates},
            return_document=True,
        )
        if result is None:
            return None
        result.pop("_id", None)
        return Candidate.model_validate(result)

    def search_by_name(self, query: str) -> List[Candidate]:
        """Simple case-insensitive name substring search."""
        import re
        cursor = self._col.find(
            {"full_name": {"$regex": re.escape(query), "$options": "i"}},
            {"_id": 0},
        )
        return [Candidate.model_validate(doc) for doc in cursor]

    def find_by_identity(
        self,
        emails: List[str] = None,
        phones: List[str] = None,
    ) -> Optional[Candidate]:
        """
        Find an existing candidate sharing any email or phone.
        Used for cross-upload deduplication.
        """
        norm_emails = [e.lower().strip() for e in (emails or []) if e]
        norm_phones = [p.strip() for p in (phones or []) if p]
        if not norm_emails and not norm_phones:
            return None

        # Build $or query across emails and phones arrays
        conditions = []
        if norm_emails:
            conditions.append({"emails": {"$in": norm_emails}})
        if norm_phones:
            conditions.append({"phones": {"$in": norm_phones}})

        doc = self._col.find_one({"$or": conditions}, {"_id": 0})
        if doc is None:
            return None
        return Candidate.model_validate(doc)

    def clear(self) -> int:
        """Delete all candidates. Returns count deleted."""
        count = self._col.count_documents({})
        self._col.delete_many({})
        return count
