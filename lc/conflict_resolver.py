"""
lc/conflict_resolver.py
------------------------
LangChain LCEL chain for resolving field-level data conflicts.

When two sources disagree on a value (e.g., one CSV says "Software Engineer"
and a resume says "Senior SWE"), we call Gemini to pick the better one.

Uses the LCEL pipe syntax:
    chain = prompt | llm | parser

This is clean, testable, and easy to swap the LLM or parser later.

Usage:
    from lc.conflict_resolver import should_resolve, resolve_conflict
"""

from __future__ import annotations

from typing import Any, Tuple


# Only invoke LLM when BOTH sources have high confidence
# (no point asking Gemini if one source is clearly weak)
CONFIDENCE_THRESHOLD = 0.75


def should_resolve(confidence_a: float, confidence_b: float) -> bool:
    """
    Return True if both sources are confident enough to warrant LLM resolution.
    If one source is clearly weaker, we just pick the higher-confidence one.
    """
    return (
        confidence_a >= CONFIDENCE_THRESHOLD
        and confidence_b >= CONFIDENCE_THRESHOLD
        and abs(confidence_a - confidence_b) < 0.15  # close enough to be ambiguous
    )


def resolve_conflict(
    field_name: str,
    value_a: Any,
    source_a: str,
    confidence_a: float,
    value_b: Any,
    source_b: str,
    confidence_b: float,
    candidate_context: str = "",
) -> Tuple[Any, float, str, str]:
    """
    Use Gemini to pick the better value when two sources conflict.

    Returns
    -------
    tuple: (chosen_value, final_confidence, winning_source, reason)
    """
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import JsonOutputParser
    from lc.llm import get_llm

    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are a data quality expert for a talent intelligence platform. "
            "Two data sources disagree on the value of a candidate field. "
            "Choose the more accurate and reliable value.\n\n"
            "Return ONLY valid JSON with this exact structure:\n"
            '{{"winner": "A" or "B", "confidence": 0.0-1.0, "reason": "brief explanation"}}'
        )),
        ("human", (
            "Field: {field_name}\n\n"
            "Option A (from {source_a}, confidence {confidence_a:.0%}):\n  {value_a}\n\n"
            "Option B (from {source_b}, confidence {confidence_b:.0%}):\n  {value_b}\n\n"
            "Candidate context: {context}\n\n"
            "Which value is more accurate? Reply with JSON only."
        )),
    ])

    parser = JsonOutputParser()
    llm    = get_llm(temperature=0.0)

    # LCEL chain: prompt → LLM → JSON parser
    chain = prompt | llm | parser

    try:
        result = chain.invoke({
            "field_name":   field_name,
            "source_a":     source_a,
            "confidence_a": confidence_a,
            "value_a":      str(value_a),
            "source_b":     source_b,
            "confidence_b": confidence_b,
            "value_b":      str(value_b),
            "context":      candidate_context or "Not provided",
        })

        winner   = result.get("winner", "A")
        conf     = float(result.get("confidence", 0.8))
        reason   = result.get("reason", "LLM resolved")

        if winner.upper() == "B":
            return value_b, conf, source_b, reason
        else:
            return value_a, conf, source_a, reason

    except Exception as e:
        # If LLM resolution fails, fall back to the higher-confidence source
        print(f"[LC ConflictResolver] Fallback for {field_name}: {e}")
        if confidence_b > confidence_a:
            return value_b, confidence_b, source_b, "fallback_higher_confidence"
        return value_a, confidence_a, source_a, "fallback_higher_confidence"
