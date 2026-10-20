"""OfflineScholar settings. Change models with environment variables, no code edits needed."""
import os
from pathlib import Path

BASE = Path(__file__).parent
LIBRARY_DIR = BASE / "library"
SAVED_DIR = LIBRARY_DIR / "saved_pages"
DB_PATH = BASE / "scholar.db"


def _int_env(name, default, minimum=1):
    try:
        return max(minimum, int(os.environ[name]))
    except (KeyError, ValueError):
        return default


def _float_env(name, default, minimum=0.0, maximum=2.0):
    try:
        return min(maximum, max(minimum, float(os.environ[name])))
    except (KeyError, ValueError):
        return default


def _bool_env(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# Answer model (Gemma 4, runs locally through Ollama)
CHAT_MODEL = os.environ.get("OS_MODEL", "gemma4:e2b-it-qat")

# Search model (Snowflake Arctic Embed, open-weight, runs locally through Ollama)
EMBED_MODEL = os.environ.get("OS_EMBED", "snowflake-arctic-embed:33m")
USE_EMBEDDINGS = _bool_env("OS_EMBEDDINGS", True)
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

CHUNK_WORDS = _int_env("OS_CHUNK_WORDS", 250)
CHUNK_OVERLAP = _int_env("OS_CHUNK_OVERLAP", 40, minimum=0)
TOP_K = _int_env("OS_TOP_K", 4)
SUPPORTED = {".txt", ".md", ".pdf", ".docx"}

# Chat generation
NUM_CTX = _int_env("OS_NUM_CTX", 2048, minimum=512)
TEMPERATURE = _float_env("OS_TEMPERATURE", 0.5)
HISTORY_LIMIT = _int_env("OS_HISTORY", 8, minimum=0)
