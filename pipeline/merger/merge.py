"""
Candidate Merger
----------------
Takes raw parsed records from *all* sources, deduplicates them into unique
candidate profiles, normalizes field values, and resolves conflicts using
the confidence scorer.

Key Design Decisions
--------------------
1. **Identity Resolution**: Primary match is by email. Fallback is by
   normalized E.164 phone number. This avoids the false-positive risk
   of name matching (two different people called "John Smith" should
   never be merged). Records with only a name are kept as standalone
   candidates — nothing is ever silently dropped.

2. **Conflict Resolution**: For scalar fields, the value with the highest
   confidence wins. For list fields (emails, phones, skills), we union the
   lists and deduplicate.

3. **Provenance**: Every field update is tracked — we record which source
   provided the winning value, what extraction method was used, and the
   confidence score.

4. **Normalization**: Phones are E.164-normalized, skills are canonicalized,
   dates are ISO-formatted. Normalization happens at merge time so the
   canonical record is always clean.
"""

from typing import List, Dict, Any, Optional
import uuid
import re

from models.candidate import (
    Candidate, ProvenanceRecord, Skill, Location, Links, Experience
)
from pipeline.normalizers.phone import normalize_phone, dial_code_for_country
from pipeline.normalizers.skills import canonicalize_skill
from pipeline.normalizers.dates import normalize_date
from pipeline.confidence.scorer import (
    get_confidence_score,
    get_source_tier,
    compute_multi_source_boost,
    compute_overall_confidence,
)
from pipeline.normalizers.dates import normalize_date_range


class CandidateMerger:
    """
    Merges raw parsed records from multiple sources into deduplicated
    canonical Candidate profiles.
    """

    def __init__(self, enable_llm_conflict_resolution: bool = False):
        """
        Parameters
        ----------
        enable_llm_conflict_resolution : bool
            If True, the merger will call Gemini to resolve field conflicts
            when two high-confidence sources disagree. Requires GEMINI_API_KEY.
            Defaults to False to avoid unintended API calls.
        """
        # Maps candidate_id -> Candidate object
        self.candidates: Dict[str, Candidate] = {}
        # Maps candidate_id -> { field_name: best_confidence_so_far }
        self.confidence_tracker: Dict[str, Dict[str, float]] = {}
        # Maps candidate_id -> { field_name: best_source_so_far }
        self.field_source_tracker: Dict[str, Dict[str, str]] = {}
        # Lookup indices for deduplication
        self._email_to_id: Dict[str, str] = {}
        self._phone_to_id: Dict[str, str] = {}  # normalized E.164 → candidate_id

        # Optional LLM conflict resolver
        self._conflict_resolver = None
        if enable_llm_conflict_resolution:
            try:
                from llm.conflict_resolver import ConflictResolver
                self._conflict_resolver = ConflictResolver()
                print("[CandidateMerger] LLM conflict resolution enabled", flush=True)
            except Exception as e:
                print(f"[CandidateMerger] Warning: Could not init ConflictResolver: {e}", flush=True)

    # ------------------------------------------------------------------
    # Identity Resolution
    # ------------------------------------------------------------------

    def _normalize_name_key(self, name: Optional[str]) -> Optional[str]:
        """Lowercase, strip, collapse whitespace for name-based matching."""
        if not name:
            return None
        return re.sub(r"\s+", " ", name.strip().lower())

    def _get_or_create_candidate(
        self,
        email: Optional[str],
        phone: Optional[str],
        name: Optional[str],
    ) -> str:
        """
        Find an existing candidate by email or phone, or create a new one.

        Identity resolution priority:
          1. Email match   — most reliable unique identifier
          2. Phone match   — normalized E.164 comparison, avoids format drift
          3. No match      — create a fresh candidate (nothing is dropped)

        Name is deliberately NOT used as a match key because two different
        people can share the same name (e.g. "John Smith"), which would
        cause incorrect merges.

        Returns the candidate_id.
        """
        # Priority 1: Match by email
        if email:
            norm_email = email.strip().lower()
            if norm_email in self._email_to_id:
                return self._email_to_id[norm_email]

        # Priority 2: Match by normalized phone
        if phone:
            norm_phone = normalize_phone(phone)
            if norm_phone and norm_phone in self._phone_to_id:
                cid = self._phone_to_id[norm_phone]
                # Also register the email so future records can match by email
                if email:
                    self._email_to_id[email.strip().lower()] = cid
                return cid

        # No match — create a new candidate
        cid = str(uuid.uuid4())
        self.candidates[cid] = Candidate(candidate_id=cid)
        self.confidence_tracker[cid] = {}
        self.field_source_tracker[cid] = {}

        if email:
            self._email_to_id[email.strip().lower()] = cid
        if phone:
            norm_phone = normalize_phone(phone)
            if norm_phone:
                self._phone_to_id[norm_phone] = cid

        return cid

    # ------------------------------------------------------------------
    # Field Update Helpers
    # ------------------------------------------------------------------

    def _update_scalar_field(
        self,
        cid: str,
        field_name: str,
        value: Any,
        source: str,
        confidence: float,
        method: str = "extracted",
    ):
        """
        Update a scalar field on a candidate only if the new value has
        higher confidence than the existing one. Tracks provenance.

        If LLM conflict resolution is enabled and both sources have high
        confidence, invokes the ConflictResolver to pick the better value.
        """
        if value is None:
            return

        current_best = self.confidence_tracker[cid].get(field_name, -1.0)
        current_source = self.field_source_tracker[cid].get(field_name)
        current_source_tier = get_source_tier(current_source) if current_source else -1.0
        incoming_source_tier = get_source_tier(source)

        # Check if LLM conflict resolution should be applied
        if (
            self._conflict_resolver is not None
            and current_best >= 0
            and current_source is not None
        ):
            current_value = getattr(self.candidates[cid], field_name, None)
            should_llm_resolve = self._conflict_resolver.should_resolve(
                confidence_a=current_best,
                confidence_b=confidence,
            )
            if should_llm_resolve and current_value is not None and str(current_value) != str(value):
                cand = self.candidates[cid]
                context = f"Candidate: {cand.full_name}, Headline: {cand.headline}"
                chosen_value, final_conf, winning_source, reason = self._conflict_resolver.resolve(
                    field_name=field_name,
                    value_a=current_value,
                    source_a=current_source,
                    confidence_a=current_best,
                    value_b=value,
                    source_b=source,
                    confidence_b=confidence,
                    candidate_context=context,
                )
                setattr(self.candidates[cid], field_name, chosen_value)
                self.confidence_tracker[cid][field_name] = final_conf
                self.field_source_tracker[cid][field_name] = winning_source
                cand.provenance = [p for p in cand.provenance if p.field_name != field_name]
                cand.provenance.append(ProvenanceRecord(
                    field_name=field_name,
                    source=winning_source,
                    method="llm_resolved",
                    confidence=final_conf,
                ))
                return

        should_replace = False
        if confidence > current_best:
            should_replace = True
        elif confidence == current_best and incoming_source_tier > current_source_tier:
            should_replace = True

        if should_replace:
            setattr(self.candidates[cid], field_name, value)
            self.confidence_tracker[cid][field_name] = confidence
            self.field_source_tracker[cid][field_name] = source

            # Replace old provenance for this field
            cand = self.candidates[cid]
            cand.provenance = [
                p for p in cand.provenance if p.field_name != field_name
            ]
            cand.provenance.append(ProvenanceRecord(
                field_name=field_name,
                source=source,
                method=method,
                confidence=confidence,
            ))

    def _append_to_list_field(
        self,
        cid: str,
        field_name: str,
        value: Any,
        source: str,
        confidence: float,
        method: str = "extracted",
    ):
        """
        Append a value to a list field (emails, phones) if not already present.

        Provenance is deduplicated: only one entry per (field_name, source, method)
        triple is kept. Confidence is updated if a higher value comes in later.
        """
        if value is None:
            return

        current_list = getattr(self.candidates[cid], field_name, [])
        if value not in current_list:
            current_list.append(value)
            setattr(self.candidates[cid], field_name, current_list)

            # Only add a provenance record if we don't already have one for
            # this (field_name, source, method) combination.
            cand = self.candidates[cid]
            existing_prov = next(
                (p for p in cand.provenance
                 if p.field_name == field_name
                 and p.source == source
                 and p.method == method),
                None,
            )
            if existing_prov is None:
                cand.provenance.append(ProvenanceRecord(
                    field_name=field_name,
                    source=source,
                    method=method,
                    confidence=confidence,
                ))
            else:
                # Update confidence to the highest seen from this source
                if confidence > existing_prov.confidence:
                    existing_prov.confidence = confidence

            # Track the best confidence we've seen for this list field
            existing_conf = self.confidence_tracker[cid].get(field_name, 0.0)
            self.confidence_tracker[cid][field_name] = max(existing_conf, confidence)

    # ------------------------------------------------------------------
    # Source-Specific Mapping
    # ------------------------------------------------------------------

    def _merge_csv_record(self, cid: str, data: Dict[str, Any], source: str):
        """
        Map recruiter CSV fields to the canonical Candidate model.

        Handles all common recruiter CSV columns:
          name, email, phone, current_company, title, location,
          skills, linkedin, years_experience, education, degree, field_of_study
        Extra/unknown columns are silently ignored (no crash).
        """
        cand = self.candidates[cid]

        # Full Name
        self._update_scalar_field(
            cid, "full_name", data.get("name"),
            source, get_confidence_score(source, "name"),
        )

        # Email (list)
        email = data.get("email")
        if email:
            self._append_to_list_field(
                cid, "emails", email.strip().lower(),
                source, get_confidence_score(source, "email"),
            )

        # Location (free-text like "San Francisco, CA") — parsed BEFORE phone
        # so we can use the country as a dial-code hint.
        raw_location = data.get("location")
        location_obj = None
        if raw_location:
            location_obj = self._parse_location_string(raw_location)
            if location_obj:
                self._update_scalar_field(
                    cid, "location", location_obj,
                    source, get_confidence_score(source, "location"),
                    method="parsed_location_string",
                )

        # Phone (normalize + list)
        # Pass the parsed country as a hint so bare local numbers (e.g. Indian
        # 10-digit numbers) get the correct dial code instead of defaulting to +1.
        raw_phone = data.get("phone")
        if raw_phone:
            country_hint = location_obj.country if location_obj else None
            norm_phone = normalize_phone(raw_phone, country_hint=country_hint)
            if norm_phone:
                self._append_to_list_field(
                    cid, "phones", norm_phone,
                    source, get_confidence_score(source, "phone"),
                    method="normalized_e164",
                )

        # Headline from title
        self._update_scalar_field(
            cid, "headline", data.get("title"),
            source, get_confidence_score(source, "title"),
        )

        # Skills (comma-separated string like "Python, Java, ML")
        raw_skills = data.get("skills")
        if raw_skills:
            skill_items = [s.strip() for s in raw_skills.split(",") if s.strip()]
            for raw_skill in skill_items:
                canonical_name = canonicalize_skill(raw_skill)
                if canonical_name:
                    existing_skill = next(
                        (s for s in cand.skills if s.name == canonical_name), None
                    )
                    if existing_skill:
                        if source not in existing_skill.sources:
                            existing_skill.sources.append(source)
                            existing_skill.confidence = compute_multi_source_boost(
                                existing_skill.confidence, len(existing_skill.sources)
                            )
                    else:
                        cand.skills.append(Skill(
                            name=canonical_name,
                            confidence=get_confidence_score(source, "skills"),
                            sources=[source],
                        ))
            if cand.skills:
                best_skill_conf = max(s.confidence for s in cand.skills)
                self.confidence_tracker[cid]["skills"] = best_skill_conf

        # LinkedIn URL → links.linkedin
        linkedin_url = data.get("linkedin")
        if linkedin_url:
            current_links = cand.links or Links()
            current_links.linkedin = linkedin_url.strip()
            cand.links = current_links
            cand.provenance.append(ProvenanceRecord(
                field_name="links",
                source=source,
                method="extracted",
                confidence=get_confidence_score(source, "linkedin") if "linkedin" in data else 0.8,
            ))
            existing_conf = self.confidence_tracker[cid].get("links", 0.0)
            self.confidence_tracker[cid]["links"] = max(existing_conf, 0.8)

        # Years of Experience (numeric)
        raw_yoe = data.get("years_experience") or data.get("yoe") or data.get("experience_years")
        if raw_yoe:
            try:
                yoe = float(raw_yoe)
                self._update_scalar_field(
                    cid, "years_experience", yoe,
                    source, get_confidence_score(source, "years_experience") if "years_experience" in data else 0.75,
                    method="parsed_numeric",
                )
            except (ValueError, TypeError):
                pass  # Not a valid number — skip silently

        # Education: derive from education/degree/field_of_study columns
        institution = data.get("education") or data.get("institution") or data.get("university")
        degree = data.get("degree")
        field_of_study = data.get("field_of_study") or data.get("major")
        end_year = data.get("graduation_year") or data.get("end_year")
        if institution:
            from models.candidate import Education
            edu = Education(
                institution=institution,
                degree=degree,
                field_of_study=field_of_study,
                end_year=end_year,
            )
            # Dedup: don't add if same institution + degree already exists
            is_dup = any(
                e.institution.lower() == edu.institution.lower() and
                (e.degree or "").lower() == (edu.degree or "").lower()
                for e in cand.education
            )
            if not is_dup:
                cand.education.append(edu)
                cand.provenance.append(ProvenanceRecord(
                    field_name="education",
                    source=source,
                    method="extracted",
                    confidence=0.8,
                ))
                existing_conf = self.confidence_tracker[cid].get("education", 0.0)
                self.confidence_tracker[cid]["education"] = max(existing_conf, 0.8)

        # Experience: derive from current_company + title
        company = data.get("current_company")
        title = data.get("title")
        if company:
            exp = Experience(
                company=company,
                title=title or "Unknown",
            )
            # Only add if no duplicate (same company + title)
            existing_exps = cand.experience
            is_dup = any(
                e.company.lower() == exp.company.lower() and
                e.title.lower() == exp.title.lower()
                for e in existing_exps
            )
            if not is_dup:
                cand.experience.append(exp)
                cand.provenance.append(ProvenanceRecord(
                    field_name="experience",
                    source=source,
                    method="derived_from_company_title",
                    confidence=get_confidence_score(source, "current_company"),
                ))
                existing_conf = self.confidence_tracker[cid].get("experience", 0.0)
                self.confidence_tracker[cid]["experience"] = max(
                    existing_conf, get_confidence_score(source, "current_company")
                )

    def _merge_github_record(self, cid: str, data: Dict[str, Any], source: str):
        """Map GitHub API fields to the canonical Candidate model."""
        cand = self.candidates[cid]

        # Full Name (lower confidence than CSV)
        self._update_scalar_field(
            cid, "full_name", data.get("name"),
            source, get_confidence_score(source, "name"),
        )

        # Email (list)
        email = data.get("email")
        if email:
            self._append_to_list_field(
                cid, "emails", email.strip().lower(),
                source, get_confidence_score(source, "email"),
            )

        # Headline from bio
        self._update_scalar_field(
            cid, "headline", data.get("bio"),
            source, get_confidence_score(source, "bio"),
        )

        # Location: parse the free-text location string
        raw_location = data.get("location")
        if raw_location:
            location_obj = self._parse_location_string(raw_location)
            if location_obj:
                self._update_scalar_field(
                    cid, "location", location_obj,
                    source, get_confidence_score(source, "location"),
                    method="parsed_location_string",
                )

        # Links: github_url → links.github, blog → links.portfolio
        github_url = data.get("github_url")
        blog_url = data.get("blog")
        current_links = cand.links or Links()

        if github_url:
            current_links.github = github_url
        if blog_url:
            current_links.portfolio = blog_url

        cand.links = current_links
        # Log provenance for links
        if github_url or blog_url:
            cand.provenance.append(ProvenanceRecord(
                field_name="links",
                source=source,
                method="extracted",
                confidence=get_confidence_score(source, "github_url"),
            ))
            existing_conf = self.confidence_tracker[cid].get("links", 0.0)
            self.confidence_tracker[cid]["links"] = max(
                existing_conf, get_confidence_score(source, "github_url")
            )

        # Skills: repo languages → canonicalized skills
        languages = data.get("languages", [])
        for lang in languages:
            canonical_name = canonicalize_skill(lang)
            if canonical_name:
                existing_skill = next(
                    (s for s in cand.skills if s.name == canonical_name), None
                )
                if existing_skill:
                    # Skill already exists — add this source if not tracked
                    if source not in existing_skill.sources:
                        existing_skill.sources.append(source)
                        # Boost confidence when multiple sources agree
                        existing_skill.confidence = compute_multi_source_boost(
                            existing_skill.confidence, len(existing_skill.sources)
                        )
                else:
                    cand.skills.append(Skill(
                        name=canonical_name,
                        confidence=get_confidence_score(source, "languages"),
                        sources=[source],
                    ))

            # Track skills confidence
            if cand.skills:
                best_skill_conf = max(s.confidence for s in cand.skills)
                self.confidence_tracker[cid]["skills"] = best_skill_conf

    # ------------------------------------------------------------------
    # Utility: Location Parsing
    # ------------------------------------------------------------------

    def _parse_location_string(self, raw: str) -> Optional[Location]:
        """
        Parse a free-text location string into a Location model.

        Heuristic: split by comma, try to identify city/region/country.
        Examples:
          "Portland, OR"          → city=Portland, region=OR
          "San Francisco, CA, US" → city=San Francisco, region=CA, country=US
          "India"                 → country=India
          "London"                → city=London
        """
        if not raw or not raw.strip():
            return None

        parts = [p.strip() for p in raw.split(",") if p.strip()]

        if len(parts) == 0:
            return None
        elif len(parts) == 1:
            token = parts[0]
            # If it's 2-3 chars, treat as country code; otherwise city
            if len(token) <= 3 and token.isalpha():
                return Location(country=token.upper())
            else:
                return Location(city=token)
        elif len(parts) == 2:
            return Location(city=parts[0], region=parts[1])
        else:
            return Location(city=parts[0], region=parts[1], country=parts[2])

    # ------------------------------------------------------------------
    # Main Entry Point
    # ------------------------------------------------------------------

    def process_records(self, raw_records: List[Dict[str, Any]]) -> List[Candidate]:
        """
        Process all raw records from every source, merge into canonical
        Candidate objects, and compute overall confidence.

        Parameters
        ----------
        raw_records : list
            Each record is a dict with keys:
            - "source_name": str  (e.g. "recruiter_csv", "github_api")
            - "source_type": str  (e.g. "structured", "unstructured")
            - "raw_data": dict    (the extracted key-value pairs)

        Returns
        -------
        list[Candidate]
            Deduplicated, normalized, confidence-scored candidate profiles.
        """
        for record in raw_records:
            source = record.get("source_name", "unknown")
            data = record.get("raw_data", {})

            if not data:
                continue

            # Identify or create the candidate
            email = data.get("email")
            name = data.get("name") or data.get("full_name")
            phone = data.get("phone")

            # Skip only if the record has NO identifier at all — not even a name.
            if not email and not phone and not name:
                print(f"[CSV Parser] Warning: Row lacks name, email, and phone. Skipping.",
                      flush=True)
                continue

            cid = self._get_or_create_candidate(email, phone, name)

            # Dispatch to source-specific merge logic
            if source == "recruiter_csv":
                self._merge_csv_record(cid, data, source)
            elif source == "github_api":
                self._merge_github_record(cid, data, source)
            elif source == "resume_llm":
                self._merge_resume_llm_record(cid, data, source)
            elif source == "resume_parsed":
                self._merge_resume_parsed_record(cid, data, source)
            else:
                # Generic fallback for unknown sources
                self._merge_generic_record(cid, data, source)

        # ----------------------------------------------------------
        # Post-processing: compute overall confidence for each candidate
        # ----------------------------------------------------------
        for cid, cand in self.candidates.items():
            field_confs = self.confidence_tracker.get(cid, {})
            cand.overall_confidence = compute_overall_confidence(field_confs)

        return list(self.candidates.values())

    def _merge_generic_record(self, cid: str, data: Dict[str, Any], source: str):
        """Fallback merge for any unknown source — maps common field names."""
        for raw_key, value in data.items():
            if not value:
                continue
            simple_map = {
                "name": "full_name",
                "title": "headline",
            }
            if raw_key in simple_map:
                self._update_scalar_field(
                    cid, simple_map[raw_key], value,
                    source, get_confidence_score(source, raw_key),
                )
            elif raw_key == "email":
                self._append_to_list_field(
                    cid, "emails", value.strip().lower(),
                    source, get_confidence_score(source, raw_key),
                )
            elif raw_key == "phone":
                norm = normalize_phone(value)
                if norm:
                    self._append_to_list_field(
                        cid, "phones", norm,
                        source, get_confidence_score(source, raw_key),
                        method="normalized_e164",
                    )

    # ------------------------------------------------------------------
    # Resume LLM source handler
    # ------------------------------------------------------------------

    def _merge_resume_llm_record(self, cid: str, data: Dict[str, Any], source: str):
        """
        Map LLM-extracted resume fields to the canonical Candidate model.

        This handles the rich structured output from llm/extractor.py:
        skills list, experience list, education list, links dict, llm_summary.
        """
        from models.candidate import Education, Experience as ExpModel
        cand = self.candidates[cid]

        # Full name
        self._update_scalar_field(
            cid, "full_name", data.get("full_name"),
            source, get_confidence_score(source, "full_name"),
        )

        # Emails
        for email in data.get("emails", []):
            if email:
                self._append_to_list_field(
                    cid, "emails", email.strip().lower(),
                    source, get_confidence_score(source, "email"),
                )

        # Phones
        for phone in data.get("phones", []):
            if phone:
                norm = normalize_phone(phone)
                if norm:
                    self._append_to_list_field(
                        cid, "phones", norm,
                        source, get_confidence_score(source, "phone"),
                        method="normalized_e164",
                    )

        # Headline
        self._update_scalar_field(
            cid, "headline", data.get("headline"),
            source, get_confidence_score(source, "headline"),
        )

        # Years of experience
        yoe = data.get("years_experience")
        if yoe is not None:
            try:
                self._update_scalar_field(
                    cid, "years_experience", float(yoe),
                    source, get_confidence_score(source, "years_experience"),
                    method="llm_computed",
                )
            except (TypeError, ValueError):
                pass

        # Location (free text from LLM)
        raw_loc = data.get("location")
        if raw_loc:
            loc_obj = self._parse_location_string(raw_loc)
            if loc_obj:
                self._update_scalar_field(
                    cid, "location", loc_obj,
                    source, get_confidence_score(source, "location"),
                    method="llm_parsed_location",
                )

        # Skills
        for raw_skill in data.get("skills", []):
            canonical_name = canonicalize_skill(raw_skill)
            if canonical_name:
                existing = next((s for s in cand.skills if s.name == canonical_name), None)
                if existing:
                    if source not in existing.sources:
                        existing.sources.append(source)
                        existing.confidence = compute_multi_source_boost(
                            existing.confidence, len(existing.sources)
                        )
                else:
                    cand.skills.append(Skill(
                        name=canonical_name,
                        confidence=get_confidence_score(source, "skills"),
                        sources=[source],
                    ))
        if cand.skills:
            best_conf = max(s.confidence for s in cand.skills)
            self.confidence_tracker[cid]["skills"] = best_conf

        # Experience
        for exp_data in data.get("experience", []):
            if not isinstance(exp_data, dict):
                continue
            company = exp_data.get("company", "Unknown")
            title   = exp_data.get("title",   "Unknown")
            # Normalize date range
            start = normalize_date_range(exp_data.get("start") or "").get("start")
            end   = normalize_date_range(exp_data.get("end") or "").get("start") if exp_data.get("end") else None

            is_dup = any(
                e.company.lower() == company.lower() and e.title.lower() == title.lower()
                for e in cand.experience
            )
            if not is_dup:
                cand.experience.append(ExpModel(
                    company=company,
                    title=title,
                    start=start or exp_data.get("start"),
                    end=end or exp_data.get("end"),
                    summary=exp_data.get("summary"),
                ))
        if cand.experience:
            self.confidence_tracker[cid]["experience"] = get_confidence_score(source, "experience")
            cand.provenance.append(ProvenanceRecord(
                field_name="experience",
                source=source,
                method="llm_extracted",
                confidence=get_confidence_score(source, "experience"),
            ))

        # Education
        for edu_data in data.get("education", []):
            if not isinstance(edu_data, dict):
                continue
            institution = edu_data.get("institution", "")
            degree      = edu_data.get("degree")
            is_dup = any(
                e.institution.lower() == institution.lower()
                for e in cand.education
            )
            if not is_dup:
                cand.education.append(Education(
                    institution=institution,
                    degree=degree,
                    field_of_study=edu_data.get("field_of_study"),
                    end_year=edu_data.get("end_year"),
                ))
        if cand.education:
            self.confidence_tracker[cid]["education"] = get_confidence_score(source, "education")
            cand.provenance.append(ProvenanceRecord(
                field_name="education",
                source=source,
                method="llm_extracted",
                confidence=get_confidence_score(source, "education"),
            ))

        # Links
        links_data = data.get("links") or {}
        current_links = cand.links or Links()
        if links_data.get("linkedin"):
            current_links.linkedin = links_data["linkedin"]
        if links_data.get("github"):
            current_links.github = links_data["github"]
        if links_data.get("portfolio"):
            current_links.portfolio = links_data["portfolio"]
        cand.links = current_links

        # LLM summary
        llm_summary = data.get("llm_summary")
        if llm_summary:
            cand.llm_summary = llm_summary
            cand.llm_enriched = True
            cand.provenance.append(ProvenanceRecord(
                field_name="llm_summary",
                source=source,
                method="llm_generated",
                confidence=get_confidence_score(source, "llm_summary"),
            ))
            self.confidence_tracker[cid]["llm_summary"] = get_confidence_score(source, "llm_summary")

        # Store raw text on the candidate if present
        raw_text = data.get("raw_text")
        if raw_text and not cand.resume_raw_text:
            cand.resume_raw_text = raw_text

    def _merge_resume_parsed_record(self, cid: str, data: Dict[str, Any], source: str):
        """
        Map heuristically-parsed resume fields (from parsers/resume_parser.py)
        into the candidate model. Only basic fields are available at this stage
        — the rich extraction happens in _merge_resume_llm_record.
        """
        cand = self.candidates[cid]

        self._update_scalar_field(
            cid, "full_name", data.get("name"),
            source, get_confidence_score(source, "name"),
        )
        email = data.get("email")
        if email:
            self._append_to_list_field(
                cid, "emails", email.strip().lower(),
                source, get_confidence_score(source, "email"),
            )
        phone = data.get("phone")
        if phone:
            norm = normalize_phone(phone)
            if norm:
                self._append_to_list_field(
                    cid, "phones", norm,
                    source, get_confidence_score(source, "phone"),
                    method="normalized_e164",
                )

        # Links
        current_links = cand.links or Links()
        if data.get("linkedin"):
            current_links.linkedin = data["linkedin"]
        if data.get("github_url"):
            current_links.github = data["github_url"]
        cand.links = current_links

        # Store raw text for RAG indexing
        raw_text = data.get("raw_text")
        if raw_text and not cand.resume_raw_text:
            cand.resume_raw_text = raw_text
