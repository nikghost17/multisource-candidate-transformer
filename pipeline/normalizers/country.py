"""
Country Code Normalizer
-----------------------
Converts country name strings to ISO 3166-1 alpha-2 codes.

Handles:
  - Full names: "United States" -> "US"
  - Common variants: "USA", "U.S.A.", "America" -> "US"
  - Already correct codes: "US" -> "US"
  - Case-insensitive lookup
  - Unknown values returned as-is (no silent data loss)
"""

from typing import Optional

# ---------------------------------------------------------------------------
# Lookup table: normalized_name -> ISO 3166-1 alpha-2 code
# Covers the countries most likely to appear in recruiter / GitHub data.
# ---------------------------------------------------------------------------
_COUNTRY_LOOKUP: dict[str, str] = {
    # United States
    "united states":                   "US",
    "united states of america":        "US",
    "usa":                             "US",
    "u.s.a.":                          "US",
    "u.s.":                            "US",
    "us":                              "US",
    "america":                         "US",

    # Canada
    "canada":                          "CA",
    "ca":                              "CA",

    # United Kingdom
    "united kingdom":                  "GB",
    "uk":                              "GB",
    "great britain":                   "GB",
    "england":                         "GB",
    "britain":                         "GB",

    # India
    "india":                           "IN",
    "in":                              "IN",
    "bharat":                          "IN",

    # Germany
    "germany":                         "DE",
    "deutschland":                     "DE",
    "de":                              "DE",

    # France
    "france":                          "FR",
    "fr":                              "FR",

    # Australia
    "australia":                       "AU",
    "au":                              "AU",

    # China
    "china":                           "CN",
    "people's republic of china":      "CN",
    "cn":                              "CN",

    # Japan
    "japan":                           "JP",
    "jp":                              "JP",

    # Brazil
    "brazil":                          "BR",
    "brasil":                          "BR",
    "br":                              "BR",

    # Mexico
    "mexico":                          "MX",
    "méxico":                          "MX",
    "mx":                              "MX",

    # Netherlands
    "netherlands":                     "NL",
    "the netherlands":                 "NL",
    "holland":                         "NL",
    "nl":                              "NL",

    # Spain
    "spain":                           "ES",
    "españa":                          "ES",
    "es":                              "ES",

    # Italy
    "italy":                           "IT",
    "italia":                          "IT",
    "it":                              "IT",

    # Sweden
    "sweden":                          "SE",
    "sverige":                         "SE",
    "se":                              "SE",

    # Norway
    "norway":                          "NO",
    "norge":                           "NO",
    "no":                              "NO",

    # Denmark
    "denmark":                         "DK",
    "danmark":                         "DK",
    "dk":                              "DK",

    # Finland
    "finland":                         "FI",
    "suomi":                           "FI",
    "fi":                              "FI",

    # Switzerland
    "switzerland":                     "CH",
    "schweiz":                         "CH",
    "ch":                              "CH",

    # Austria
    "austria":                         "AT",
    "österreich":                      "AT",
    "at":                              "AT",

    # Belgium
    "belgium":                         "BE",
    "belgique":                        "BE",
    "be":                              "BE",

    # Portugal
    "portugal":                        "PT",
    "pt":                              "PT",

    # Poland
    "poland":                          "PL",
    "polska":                          "PL",
    "pl":                              "PL",

    # Russia
    "russia":                          "RU",
    "russian federation":              "RU",
    "ru":                              "RU",

    # Ukraine
    "ukraine":                         "UA",
    "ua":                              "UA",

    # South Korea
    "south korea":                     "KR",
    "korea":                           "KR",
    "republic of korea":               "KR",
    "kr":                              "KR",

    # Singapore
    "singapore":                       "SG",
    "sg":                              "SG",

    # Israel
    "israel":                          "IL",
    "il":                              "IL",

    # Turkey
    "turkey":                          "TR",
    "türkiye":                         "TR",
    "tr":                              "TR",

    # Argentina
    "argentina":                       "AR",
    "ar":                              "AR",

    # Colombia
    "colombia":                        "CO",
    "co":                              "CO",

    # Nigeria
    "nigeria":                         "NG",
    "ng":                              "NG",

    # South Africa
    "south africa":                    "ZA",
    "za":                              "ZA",

    # Egypt
    "egypt":                           "EG",
    "eg":                              "EG",

    # Indonesia
    "indonesia":                       "ID",
    "id":                              "ID",

    # Pakistan
    "pakistan":                        "PK",
    "pk":                              "PK",

    # Bangladesh
    "bangladesh":                      "BD",
    "bd":                              "BD",

    # New Zealand
    "new zealand":                     "NZ",
    "nz":                              "NZ",

    # Ireland
    "ireland":                         "IE",
    "éire":                            "IE",
    "ie":                              "IE",

    # Czech Republic
    "czech republic":                  "CZ",
    "czechia":                         "CZ",
    "cz":                              "CZ",

    # Romania
    "romania":                         "RO",
    "ro":                              "RO",

    # Hungary
    "hungary":                         "HU",
    "hu":                              "HU",

    # Greece
    "greece":                          "GR",
    "gr":                              "GR",

    # United Arab Emirates
    "united arab emirates":            "AE",
    "uae":                             "AE",
    "ae":                              "AE",

    # Saudi Arabia
    "saudi arabia":                    "SA",
    "sa":                              "SA",

    # Malaysia
    "malaysia":                        "MY",
    "my":                              "MY",

    # Thailand
    "thailand":                        "TH",
    "th":                              "TH",

    # Vietnam
    "vietnam":                         "VN",
    "viet nam":                        "VN",
    "vn":                              "VN",

    # Philippines
    "philippines":                     "PH",
    "ph":                              "PH",

    # Taiwan
    "taiwan":                          "TW",
    "tw":                              "TW",

    # Hong kong
    "hong kong":                       "HK",
    "hk":                              "HK",
}


def normalize_country(raw: Optional[str]) -> Optional[str]:
    """
    Convert a country name/variant to its ISO 3166-1 alpha-2 code.

    Parameters
    ----------
    raw : str or None
        Raw country string (e.g. "United States", "USA", "India", "IN").

    Returns
    -------
    str or None
        ISO 3166-1 alpha-2 code (e.g. "US", "IN") if recognized,
        or the original cleaned string if not in the lookup table.
        Returns None if input is None or empty.
    """
    if not raw or not isinstance(raw, str):
        return None

    cleaned = raw.strip().lower()
    # Strip trailing punctuation
    cleaned = cleaned.rstrip(".")

    if not cleaned:
        return None

    # Primary lookup
    code = _COUNTRY_LOOKUP.get(cleaned)
    if code:
        return code

    # Secondary: strip all dots (handles "U.S.A." → "usa")
    no_dots = cleaned.replace(".", "").strip()
    code = _COUNTRY_LOOKUP.get(no_dots)
    if code:
        return code

    # Already looks like a valid 2-letter code not in our map → return uppercased
    if len(cleaned) == 2 and cleaned.isalpha():
        return cleaned.upper()

    # Unknown — return original (don't silently drop)
    return raw.strip()


# --- Quick smoke test ---
if __name__ == "__main__":
    tests = [
        ("United States",  "US"),
        ("USA",            "US"),
        ("u.s.a.",         "US"),
        ("India",          "IN"),
        ("india",          "IN"),
        ("IN",             "IN"),
        ("Germany",        "DE"),
        ("Deutschland",    "DE"),
        ("United Kingdom", "GB"),
        ("UK",             "GB"),
        ("Australia",      "AU"),
        ("Mexico",         "MX"),
        ("México",         "MX"),
        ("South Korea",    "KR"),
        ("Hong Kong",      "HK"),
        ("Narnia",         "Narnia"),   # Unknown — kept as-is
    ]
    print(f"{'Input':<25} {'Expected':<6} {'Got':<6} OK")
    print("-" * 50)
    for raw, expected in tests:
        got = normalize_country(raw)
        ok = "✅" if got == expected else "❌"
        print(f"{raw:<25} {expected:<6} {str(got):<6} {ok}")
