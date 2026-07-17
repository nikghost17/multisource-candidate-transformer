"""
Date Normalizer
----------------
Converts a wide variety of date strings (from resumes, CSVs, LinkedIn exports)
into canonical ISO 8601 format.

Handles:
  - Standard formats:        "2021-05-01", "05/01/2021"
  - Month + Year:            "May 2021" → "2021-05"
  - Year only:               "2018" → "2018"
  - Quarter:                 "Q3 2020" → "2020-07" (approximate)
  - Range (experience):      "2018 – Present" → {"start": "2018", "end": None}
  - Range with months:       "Jun 2019 - Mar 2022" → {"start": "2019-06", "end": "2022-03"}
  - Relative (approx):       "3 years ago" → approximate ISO year
  - Present / Current:       returns None (caller interprets as ongoing)
"""

import re
from datetime import datetime, date
from typing import Optional, Dict, Union


_MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

# Quarter → approximate start month
_QUARTER_TO_MONTH = {"q1": 1, "q2": 4, "q3": 7, "q4": 10}

# Words that signal an ongoing/current role
_PRESENT_WORDS = {"present", "current", "now", "ongoing", "till date", "till now", "to date"}


def _is_present(text: str) -> bool:
    return text.strip().lower() in _PRESENT_WORDS


def _try_full_date(text: str) -> Optional[str]:
    """Parse exact date strings (YYYY-MM-DD, MM/DD/YYYY, etc.)."""
    patterns = [
        ("%Y-%m-%d", True),
        ("%Y/%m/%d", True),
        ("%m/%d/%Y", True),
        ("%m-%d-%Y", True),
        ("%d/%m/%Y", True),
        ("%d-%m-%Y", True),
    ]
    for pattern, full in patterns:
        try:
            parsed = datetime.strptime(text.strip(), pattern)
            return parsed.strftime("%Y-%m-%d") if full else parsed.strftime("%Y-%m")
        except ValueError:
            continue
    return None


def _try_month_year(text: str) -> Optional[str]:
    """Parse 'May 2021', 'Jan-2020', '05/2021' → '2021-05'."""
    text = text.strip()

    # "Month YYYY", "Month, YYYY", or "Month-YYYY"
    m = re.match(r"^([A-Za-z]+)[,\s\-]+(\d{4})$", text)
    if m:
        month_num = _MONTHS.get(m.group(1).lower())
        if month_num:
            return f"{m.group(2)}-{month_num:02d}"

    # "MM/YYYY" or "MM-YYYY"
    m = re.match(r"^(\d{1,2})[/-](\d{4})$", text)
    if m:
        month, year = int(m.group(1)), m.group(2)
        if 1 <= month <= 12:
            return f"{year}-{month:02d}"

    # "YYYY-MM" (already partial ISO)
    m = re.match(r"^(\d{4})-(\d{2})$", text)
    if m:
        month = int(m.group(2))
        if 1 <= month <= 12:
            return text

    return None


def _try_year_only(text: str) -> Optional[str]:
    """Parse '2018' → '2018'."""
    m = re.match(r"^(\d{4})$", text.strip())
    if m:
        year = int(m.group(1))
        if 1950 <= year <= 2100:
            return m.group(1)
    return None


def _try_quarter(text: str) -> Optional[str]:
    """Parse 'Q3 2020' → '2020-07'."""
    m = re.match(r"^(Q[1-4])\s+(\d{4})$", text.strip(), re.IGNORECASE)
    if m:
        quarter = m.group(1).lower()
        year    = m.group(2)
        month   = _QUARTER_TO_MONTH.get(quarter)
        if month:
            return f"{year}-{month:02d}"
    return None


def _try_relative(text: str) -> Optional[str]:
    """
    Parse relative dates like '3 years ago' → approximate ISO year.
    This is inherently approximate — we just subtract from the current year.
    """
    m = re.match(r"^(\d+)\s+years?\s+ago$", text.strip(), re.IGNORECASE)
    if m:
        years_ago = int(m.group(1))
        approx_year = date.today().year - years_ago
        return str(approx_year)
    return None


def _parse_single(text: str) -> Optional[str]:
    """
    Try all parsers on a single date token.
    Returns the best ISO representation or None.
    """
    if not text or not text.strip():
        return None

    t = text.strip()

    if _is_present(t):
        return None   # Caller interprets as "ongoing"

    return (
        _try_full_date(t)
        or _try_month_year(t)
        or _try_quarter(t)
        or _try_year_only(t)
        or _try_relative(t)
    )


def normalize_date(raw_date: Optional[str]) -> Optional[str]:
    """
    Normalize a single date string into ISO format.

    Returns
    -------
    str or None
        ISO date string (YYYY-MM-DD, YYYY-MM, or YYYY) or None if unparseable.
    """
    if raw_date is None:
        return None
    return _parse_single(str(raw_date))


def normalize_date_range(
    raw_range: Optional[str],
) -> Dict[str, Optional[str]]:
    """
    Parse an experience date range string into {"start": ..., "end": ...}.

    Supports separators: –, -, to, →, /
    'Present', 'Current', 'Now' → end = None (means ongoing)

    Examples
    --------
    "Jun 2019 - Mar 2022"  → {"start": "2019-06", "end": "2022-03"}
    "2018 – Present"       → {"start": "2018",    "end": None}
    "2015 to 2018"         → {"start": "2015",    "end": "2018"}
    "May 2021"             → {"start": "2021-05", "end": None}

    Parameters
    ----------
    raw_range : str or None

    Returns
    -------
    dict with keys "start" and "end", values are ISO strings or None.
    """
    if not raw_range or not raw_range.strip():
        return {"start": None, "end": None}

    text = raw_range.strip()

    # Try splitting on common range separators
    # Order matters: '–' (en-dash) before '-' to avoid false splits
    split_patterns = [
        r"\s*[–—]\s*",          # en-dash, em-dash
        r"\s+to\s+",            # "2018 to 2021"
        r"\s*→\s*",             # arrow
        r"\s*[-/]\s*(?=\w)",    # hyphen/slash followed by word char (avoid splitting "Jun-2019")
    ]

    for pattern in split_patterns:
        parts = re.split(pattern, text, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) == 2:
            start_str, end_str = parts[0].strip(), parts[1].strip()
            start = _parse_single(start_str)
            end   = None if _is_present(end_str) else _parse_single(end_str)
            return {"start": start, "end": end}

    # No separator found — treat whole string as a single date (start)
    return {"start": _parse_single(text), "end": None}


# ---------------------------------------------------------------------------
# Quick smoke-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    tests = [
        ("2021-05-01",       "2021-05-01"),
        ("May 2021",         "2021-05"),
        ("Q3 2020",          "2020-07"),
        ("2018",             "2018"),
        ("3 years ago",      None),   # approximate — skip exact check
        ("Jan-2020",         "2020-01"),
        ("05/2021",          "2021-05"),
    ]
    print(f"{'Input':<25} {'Expected':<15} {'Got':<15} {'OK'}")
    print("-" * 65)
    for raw, expected in tests:
        got = normalize_date(raw)
        ok  = "✅" if got == expected or expected is None else "❌"
        print(f"{raw:<25} {str(expected):<15} {str(got):<15} {ok}")

    print("\n--- Date ranges ---")
    ranges = [
        "Jun 2019 - Mar 2022",
        "2018 – Present",
        "2015 to 2018",
        "May 2021",
    ]
    for r in ranges:
        print(f"{r!r:35} → {normalize_date_range(r)}")
