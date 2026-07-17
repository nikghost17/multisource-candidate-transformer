import re
from typing import Optional
from pipeline.normalizers.country import normalize_country

# ---------------------------------------------------------------------------
# ISO 3166-1 alpha-2 → E.164 country dial code
# Only the most common codes are listed; unknown codes fall back to +1.
# ---------------------------------------------------------------------------
_ISO_TO_DIAL: dict = {
    "US": "+1",   "CA": "+1",   "IN": "+91",  "GB": "+44",
    "AU": "+61",  "DE": "+49",  "FR": "+33",  "JP": "+81",
    "CN": "+86",  "BR": "+55",  "MX": "+52",  "SG": "+65",
    "AE": "+971", "SA": "+966", "NL": "+31",  "SE": "+46",
    "NO": "+47",  "DK": "+45",  "FI": "+358", "CH": "+41",
    "AT": "+43",  "BE": "+32",  "PT": "+351", "PL": "+48",
    "RU": "+7",   "UA": "+380", "KR": "+82",  "IL": "+972",
    "TR": "+90",  "AR": "+54",  "CO": "+57",  "NG": "+234",
    "ZA": "+27",  "EG": "+20",  "ID": "+62",  "PK": "+92",
    "BD": "+880", "MY": "+60",  "TH": "+66",  "VN": "+84",
    "PH": "+63",  "TW": "+886", "HK": "+852", "NZ": "+64",
    "IE": "+353", "CZ": "+420", "RO": "+40",  "HU": "+36",
    "GR": "+30",  "ES": "+34",  "IT": "+39",  "HR": "+385",
}


def dial_code_for_country(country_raw: Optional[str]) -> Optional[str]:
    """
    Return the E.164 dial code (e.g. '+91') for a country name or ISO code.

    Accepts both:
      - ISO 3166-1 alpha-2 codes: 'IN', 'GB', 'US'
      - Full country names:       'India', 'United Kingdom', 'United States'

    Internally normalizes the input to an ISO code via normalize_country()
    before the lookup, so bare location strings from the CSV work correctly.
    Returns None if the country is unrecognised.
    """
    if not country_raw:
        return None
    iso_code = normalize_country(country_raw)   # 'India' → 'IN', 'IN' → 'IN'
    if not iso_code:
        return None
    return _ISO_TO_DIAL.get(iso_code.upper())


def normalize_phone(
    raw_phone: Optional[str],
    default_country_code: str = "+1",
    country_hint: Optional[str] = None,
) -> Optional[str]:
    """
    Convert a phone number into E.164-like form.
    Strips extensions, handles international prefixes (00), trunk prefixes (0),
    and correctly routes length-based conditions.

    Parameters
    ----------
    raw_phone : str or None
        The raw phone string from the source data.
    default_country_code : str
        Fallback dial code (e.g. '+1') used when no country can be inferred.
    country_hint : str or None
        ISO 3166-1 alpha-2 country code (e.g. 'IN') parsed from the candidate's
        location field.  When provided and recognised, it overrides
        ``default_country_code`` so that bare local numbers get the correct
        international prefix instead of defaulting to +1 (US).
    """
    if raw_phone is None:
        return None

    text = str(raw_phone).strip()
    if not text:
        return None

    # Strip extensions before we pull out digits.
    text = re.sub(r"\s*(?:x|ext|extension)\s*\d+.*$", "", text, flags=re.IGNORECASE).strip()

    # Preserve explicit international formats — nothing to infer here.
    if text.startswith("+"):
        digits = re.sub(r"\D", "", text)
        return f"+{digits}" if digits else None

    cleaned = re.sub(r"\D", "", text)
    if not cleaned:
        return None

    # Handle the '00' international exit code (e.g. 0044... → +44...).
    # Require at least 7 digits after stripping the 00 prefix.
    if cleaned.startswith("00"):
        remainder = cleaned[2:]
        return f"+{remainder}" if len(remainder) >= 7 else None

    # If the caller supplied a country_hint, try to resolve it to a dial code.
    # This lets a bare "7588968663" become "+917588968663" when country="IN".
    resolved_code = dial_code_for_country(country_hint) if country_hint else None
    effective_code = resolved_code or default_country_code
    effective_digits = effective_code.replace("+", "")

    # Handle standard 10-digit domestic numbers.
    if len(cleaned) == 10:
        return f"{effective_code}{cleaned}"

    # Handle trunk prefixes (e.g. India or UK local dialing).
    if len(cleaned) == 11 and cleaned.startswith("0"):
        return f"+{effective_digits}{cleaned[1:]}"

    # Handle numbers that already include the effective country code.
    if len(cleaned) > 10 and cleaned.startswith(effective_digits):
        return f"+{cleaned}"

    # Fallback for any other digits — but only if it looks plausible.
    # E.164 requires at least 7 digits total (shortest real numbers: e.g. San Marino +378 xxx).
    if len(cleaned) < 7:
        return None
    return f"+{cleaned}"


# Minimum total digits for a plausible E.164 number (country code + subscriber).
_E164_MIN_DIGITS = 7
_E164_MAX_DIGITS = 15
_E164_RE = re.compile(r"^\+\d{" + str(_E164_MIN_DIGITS) + r"," + str(_E164_MAX_DIGITS) + r"}$")


def is_valid_e164(phone: Optional[str]) -> bool:
    """Return True if `phone` looks like a valid E.164 number (+digits, 7–15 digits)."""
    if not phone or not isinstance(phone, str):
        return False
    return bool(_E164_RE.match(phone))
