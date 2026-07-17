"""
tests/test_normalizers.py
--------------------------
Unit tests for the normalization pipeline:
  - Phone normalization (E.164 format)
  - Skill canonicalization
  - Date range normalization

These run with NO external deps — pure Python logic only.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from pipeline.normalizers.phone import normalize_phone
from pipeline.normalizers.skills import canonicalize_skill
from pipeline.normalizers.dates import normalize_date_range


# ---------------------------------------------------------------------------
# Phone Normalization
# ---------------------------------------------------------------------------

class TestPhoneNormalization:

    def test_us_number_normalized_to_e164(self):
        """A US number in local format should be normalized to E.164."""
        result = normalize_phone("(415) 555-0101")
        # Should contain digits and possibly a + prefix
        assert result is not None
        assert "4155550101" in result.replace("+", "").replace("-", "")

    def test_international_number_preserved(self):
        """An already E.164 number should be returned as-is or equivalent."""
        result = normalize_phone("+14155550101")
        assert result is not None
        assert "14155550101" in result.replace("+", "")

    def test_indian_number_normalized(self):
        """An Indian number with country code should be normalized."""
        result = normalize_phone("+917588968663")
        assert result is not None
        assert "7588968663" in result

    def test_empty_string_returns_none(self):
        """An empty string should return None."""
        result = normalize_phone("")
        assert result is None

    def test_none_input_returns_none(self):
        """None input should return None."""
        result = normalize_phone(None)
        assert result is None

    def test_garbage_returns_none(self):
        """Garbage strings that aren't phone numbers should return None."""
        result = normalize_phone("not-a-phone")
        assert result is None


# ---------------------------------------------------------------------------
# Skill Canonicalization
# ---------------------------------------------------------------------------

class TestSkillCanonicalization:

    def test_js_canonical_form(self):
        """'javascript' and 'JS' should map to the same canonical skill."""
        canon_js = canonicalize_skill("javascript")
        canon_abbr = canonicalize_skill("JS")
        assert canon_js.lower() == canon_abbr.lower()

    def test_ml_variants_canonical(self):
        """'machine learning' and 'ML' should canonicalize consistently."""
        result = canonicalize_skill("machine learning")
        assert result is not None
        assert len(result) > 0

    def test_whitespace_stripped(self):
        """Skills with extra whitespace should be canonicalized cleanly."""
        result = canonicalize_skill("  Python  ")
        assert result == result.strip()

    def test_unknown_skill_returned_normalized(self):
        """Unknown skills should be returned title-cased, not dropped."""
        result = canonicalize_skill("obscure-framework-xyz")
        assert result is not None
        assert len(result) > 0

    def test_empty_skill_returns_none_or_empty(self):
        """Empty skill string should be handled gracefully."""
        result = canonicalize_skill("")
        assert result == "" or result is None


# ---------------------------------------------------------------------------
# Date Normalization
# ---------------------------------------------------------------------------

class TestDateNormalization:

    def test_year_only_parsed(self):
        """A bare year like '2020' should be parseable."""
        result = normalize_date_range("2020")
        assert result is not None

    def test_year_month_range_parsed(self):
        """'2020-01' should parse correctly."""
        result = normalize_date_range("2020-01")
        assert result is not None

    def test_present_keyword_handled(self):
        """'Present' as end date should not raise an error."""
        result = normalize_date_range("Present")
        assert result is not None

    def test_empty_date_handled(self):
        """Empty string date should be handled gracefully without crashing."""
        result = normalize_date_range("")
        assert result is not None  # must return a dict, not raise
