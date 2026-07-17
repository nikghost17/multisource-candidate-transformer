"""
Skills Normalizer
-----------------
Canonicalizes raw skill strings (from CSV or GitHub) into a standard form.

Strategy
--------
1. Clean the input (lowercase, normalize separators).
2. Check the alias map — fast, exact lookups for common shorthands.
3. Fall back to RapidFuzz token_set_ratio against the canonical vocab.
4. If no vocab match above threshold, return the cleaned string as-is
   (unknown skills shouldn't be silently dropped).
"""

import re
from typing import Optional, List
from rapidfuzz import process, fuzz

# ---------------------------------------------------------------------------
# Canonical vocabulary — the "source of truth" for skill names.
# These are the exact strings that will appear in the output.
# ---------------------------------------------------------------------------
CANONICAL_TECH_VOCAB = [
    # Languages
    "python", "javascript", "typescript", "java", "c", "c++", "c#",
    "go", "rust", "ruby", "php", "swift", "kotlin", "scala", "r",
    "matlab", "perl", "haskell", "elixir", "dart", "lua",
    "assembly", "bash", "powershell",

    # Web / Frontend
    "react.js", "vue.js", "angular", "next.js", "svelte",
    "html", "css", "sass", "webpack", "vite",

    # Backend / Frameworks
    "node.js", "express.js", "django", "flask", "fastapi",
    "spring boot", "rails", "laravel", "asp.net", "graphql", "rest api",

    # Databases
    "sql", "postgresql", "mysql", "sqlite", "mongodb", "redis",
    "elasticsearch", "cassandra", "dynamodb", "firebase", "neo4j",

    # Data / ML / AI
    "machine learning", "deep learning", "natural language processing",
    "computer vision", "data science", "data engineering",
    "pytorch", "tensorflow", "scikit-learn", "keras", "pandas",
    "numpy", "spark", "hadoop", "kafka", "airflow", "dbt",
    "tableau", "power bi", "jupyter",

    # Cloud / DevOps
    "amazon web services", "google cloud platform", "microsoft azure",
    "docker", "kubernetes", "terraform", "ansible", "jenkins",
    "github actions", "gitlab ci", "ci cd", "linux", "nginx",
    "prometheus", "grafana",

    # Mobile
    "ios", "android", "react native", "flutter", "xamarin",

    # Other tools / concepts
    "git", "agile", "scrum", "microservices", "system design",
    "distributed systems", "nosql", "oauth", "websockets",

    # Modern AI / LLM / RAG
    "large language models", "retrieval augmented generation",
    "vector database", "embeddings", "semantic search",
    "langchain", "llama index", "hugging face", "transformers",
    "fine tuning", "prompt engineering", "rag pipeline",
    "openai api", "gemini", "gpt", "claude", "mistral",
    "langsmith", "llamacpp", "ollama", "qdrant", "pinecone", "weaviate",
    "stable diffusion", "diffusion models", "reinforcement learning from human feedback",
    "data annotation", "model evaluation", "mlops", "kubeflow", "mlflow",
]

# ---------------------------------------------------------------------------
# Alias map — fast exact-match lookups for shorthands and common variants.
# Always preferred over fuzzy matching.
# ---------------------------------------------------------------------------
_ALIAS_MAP = {
    # Language shorthands
    "py":           "python",
    "js":           "javascript",
    "ts":           "typescript",
    "rb":           "ruby",
    "cs":           "c#",
    "cpp":          "c++",
    "golang":       "go",

    # ML / AI / LLM
    "ml":           "machine learning",
    "dl":           "deep learning",
    "nlp":          "natural language processing",
    "ai":           "machine learning",
    "cv":           "computer vision",
    "llm":          "large language models",
    "llms":         "large language models",
    "rag":          "retrieval augmented generation",
    "vector db":    "vector database",
    "vectordb":     "vector database",
    "langchain":    "langchain",
    "llamaindex":   "llama index",
    "llama-index":  "llama index",
    "huggingface":  "hugging face",
    "hf":           "hugging face",
    "fine-tuning":  "fine tuning",
    "finetuning":   "fine tuning",
    "rlhf":         "reinforcement learning from human feedback",
    "openai":       "openai api",

    # Cloud
    "aws":          "amazon web services",
    "gcp":          "google cloud platform",
    "azure":        "microsoft azure",
    "s3":           "amazon web services",
    "ec2":          "amazon web services",

    # Frameworks
    "react":        "react.js",
    "reactjs":      "react.js",
    "vue":          "vue.js",
    "vuejs":        "vue.js",
    "nextjs":       "next.js",
    "next":         "next.js",
    "node":         "node.js",
    "node js":      "node.js",
    "nodejs":       "node.js",
    "express":      "express.js",
    "fastapi":      "fastapi",
    "flask":        "flask",
    "django":       "django",
    "rails":        "rails",
    "springboot":   "spring boot",
    "spring":       "spring boot",

    # Databases
    "postgres":     "postgresql",
    "pg":           "postgresql",
    "mongo":        "mongodb",
    "elastic":      "elasticsearch",
    "dynamo":       "dynamodb",
    "dynamo db":    "dynamodb",

    # DevOps / CI
    "k8s":          "kubernetes",
    "kube":         "kubernetes",
    "tf":           "terraform",
    "gh actions":   "github actions",
    "ci/cd":        "ci cd",
    "cicd":         "ci cd",

    # Data
    "sklearn":      "scikit-learn",
    "scikit":       "scikit-learn",
    "sk learn":     "scikit-learn",
    "tf keras":     "keras",
    "pyspark":      "spark",
    "hive":         "hadoop",

    # Mobile
    "rn":           "react native",
}


def canonicalize_skill(
    raw_skill: Optional[str],
    vocab: List[str] = CANONICAL_TECH_VOCAB,
) -> Optional[str]:
    """
    Standardize an unpredictable skill label into its canonical form.

    Flow:
    1. Clean (lowercase, normalize separators/whitespace).
    2. Check the alias map for exact shorthand matches.
    3. Fuzzy-match against the canonical vocab (token_set_ratio ≥ 85).
    4. Return the cleaned string as-is if no match (don't drop unknown skills).
    """
    if not raw_skill or not isinstance(raw_skill, str):
        return None

    # Step 1: Clean
    cleaned = raw_skill.strip().lower()
    cleaned = re.sub(r"[/\\]+", " ", cleaned)     # slashes → space
    cleaned = re.sub(r"[\s\-_]+", " ", cleaned)   # hyphens/underscores → space
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if not cleaned:
        return None

    # Strip common trailing noise words so "node js framework" → "node js"
    _NOISE_SUFFIX = re.compile(
        r"\s+(framework|library|lib|sdk|api|engine|platform|runtime|lang|language)s?$"
    )
    cleaned_no_noise = _NOISE_SUFFIX.sub("", cleaned).strip()

    # Step 2: Alias map (fast path)
    for candidate_str in (cleaned, cleaned_no_noise, cleaned.replace(".", ""), cleaned_no_noise.replace(".", "")):
        if candidate_str in _ALIAS_MAP:
            return _ALIAS_MAP[candidate_str]

    # Step 3: Fuzzy match against canonical vocab
    match = process.extractOne(
        cleaned,
        vocab,
        scorer=fuzz.token_set_ratio,
        score_cutoff=85.0,
    )
    if match:
        return match[0]

    # Step 4: Return as-is (unknown but valid skill)
    return cleaned


# --- Quick smoke test ---
if __name__ == "__main__":
    tests = [
        ("Pythn",               "python"),        # Typo
        ("ReactJS",             "react.js"),      # Common variant
        ("Node JS Framework",   "node.js"),       # Extra fluff
        ("K8s",                 "kubernetes"),    # Alias
        ("ML",                  "machine learning"),
        ("NLP",                 "natural language processing"),
        ("AWS",                 "amazon web services"),
        ("GCP",                 "google cloud platform"),
        ("Golang",              "go"),
        ("sklearn",             "scikit-learn"),
        ("CI/CD",               "ci cd"),
        ("Postgres",            "postgresql"),
        ("Mongo",               "mongodb"),
        ("Rust",                "rust"),
        ("BizarreSkillXYZ",     "bizarreskillxyz"),  # Unknown — kept as-is
    ]
    print(f"{'Raw':<25} {'Expected':<25} {'Got':<25} {'OK'}")
    print("-" * 85)
    for raw, expected in tests:
        got = canonicalize_skill(raw)
        ok = "✅" if got == expected else "❌"
        print(f"{raw:<25} {expected:<25} {str(got):<25} {ok}")