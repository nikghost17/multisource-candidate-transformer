"""
lc/llm.py
----------
Single place to create the Gemini LLM instance used everywhere.

Usage:
    from lc.llm import get_llm
    llm = get_llm()                        # gemini-2.0-flash (fast, default)
    llm = get_llm(model="gemini-1.5-pro")  # higher quality
"""

import os
from functools import lru_cache
from dotenv import load_dotenv

load_dotenv()


@lru_cache(maxsize=4)
def get_llm(
    model: str = None,
    temperature: float = 0.1,
):
    """
    Returns a cached ChatGoogleGenerativeAI instance.

    lru_cache means the same model+temperature combo is only
    instantiated once — no repeated API handshakes.
    """
    from langchain_google_genai import ChatGoogleGenerativeAI

    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY not set. Add it to your .env file."
        )

    model_name = model or os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    return ChatGoogleGenerativeAI(
        model=model_name,
        temperature=temperature,
        google_api_key=api_key,
        convert_system_message_to_human=True,  # Gemini quirk
    )
