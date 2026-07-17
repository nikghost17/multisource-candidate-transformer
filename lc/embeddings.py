"""
lc/embeddings.py
-----------------
Single place to create the embedding model used by the vector store.

Default: Google text-embedding-004 (via Gemini API key you already have)
Fallback: HuggingFace all-MiniLM-L6-v2 (free, local, no API key needed)

Usage:
    from lc.embeddings import get_embeddings
    emb = get_embeddings()
"""

import os
from functools import lru_cache
from dotenv import load_dotenv

load_dotenv()


@lru_cache(maxsize=2)
def get_embeddings(provider: str = None):
    """
    Returns a cached LangChain embeddings instance.

    provider options:
      "gemini"              — Google text-embedding-004  (needs GEMINI_API_KEY)
      "huggingface"         — all-MiniLM-L6-v2           (free, local)

    Reads EMBEDDING_PROVIDER env var if provider not specified.
    Defaults to "huggingface" so it works without any extra keys.
    """
    provider = provider or os.getenv("EMBEDDING_PROVIDER", "huggingface")

    if provider == "gemini":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set — needed for Gemini embeddings.")
        return GoogleGenerativeAIEmbeddings(
            model="models/text-embedding-004",
            google_api_key=api_key,
            task_type="retrieval_document",
        )

    # Default: HuggingFace (free, no API key, works offline)
    # Uses langchain_community which is already installed
    from langchain_community.embeddings import HuggingFaceEmbeddings
    model_name = os.getenv("ST_MODEL", "all-MiniLM-L6-v2")
    return HuggingFaceEmbeddings(
        model_name=model_name,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )
