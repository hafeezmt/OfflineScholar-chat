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


def _available_memory_gb():
    try:
        with open("/proc/meminfo", encoding="ascii") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / 1024 / 1024
    except (OSError, ValueError):
        pass
    return None


AVAILABLE_MEMORY_GB = _available_memory_gb()
LOW_MEMORY = _bool_env("OS_LOW_MEMORY", AVAILABLE_MEMORY_GB is not None and AVAILABLE_MEMORY_GB < 5.5)

# Answer model (Gemma 4, runs locally through Ollama)
CHAT_MODEL_EXPLICIT = "OS_MODEL" in os.environ
CHAT_MODEL = os.environ.get("OS_MODEL", "gemma4:e2b-it-qat")

# Search model (Snowflake Arctic Embed, open-weight, runs locally through Ollama)
EMBED_MODEL = os.environ.get("OS_EMBED", "snowflake-arctic-embed:33m")
USE_EMBEDDINGS = _bool_env("OS_EMBEDDINGS", True)
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

CHUNK_WORDS = _int_env("OS_CHUNK_WORDS", 160)
CHUNK_OVERLAP = _int_env("OS_CHUNK_OVERLAP", 30, minimum=0)
TOP_K = _int_env("OS_TOP_K", 4)
SUPPORTED = {".txt", ".md", ".pdf", ".docx"}

# Retrieval quality. Semantic-only matches below this cosine score are treated as
# unrelated (the small embedding model gives unrelated text around 0.45-0.55).
RAG_MIN_SCORE = _float_env("OS_RAG_MIN_SCORE", 0.75, 0.0, 1.0)
RAG_MIN_MARGIN = _float_env("OS_RAG_MIN_MARGIN", 0.06, 0.0, 1.0)
RAG_MAX_PASSAGES = _int_env("OS_RAG_MAX_PASSAGES", 1, minimum=1)
RAG_PASSAGE_WORDS = _int_env("OS_RAG_PASSAGE_WORDS", 90, minimum=20)
EXTRACTIVE_RAG = _bool_env("OS_EXTRACTIVE_RAG", True)
WEB_MAX_RESULTS = _int_env("OS_WEB_MAX_RESULTS", 5)
EXTRACTIVE_WEB = _bool_env("OS_EXTRACTIVE_WEB", True)
LIVE_LOOKUP_ENABLED = False

# Chat generation. Low-RAM machines use a smaller context, shorter history and
# shorter answers so the first token appears sooner and swap is avoided.
CPU_COUNT = os.cpu_count() or 2
FAST_THREADS = CPU_COUNT if CPU_COUNT <= 2 else min(4, CPU_COUNT - 1)
NUM_CTX = _int_env("OS_NUM_CTX", 1024 if LOW_MEMORY else 2048, minimum=512)
TEMPERATURE = _float_env("OS_TEMPERATURE", 0.2)
TOP_P = _float_env("OS_TOP_P", 0.9, 0.0, 1.0)
REPEAT_PENALTY = _float_env("OS_REPEAT_PENALTY", 1.05, 1.0, 2.0)
HISTORY_LIMIT = _int_env("OS_HISTORY", 4 if LOW_MEMORY else 8, minimum=0)
MAX_MESSAGE_CHARS = _int_env("OS_MAX_MESSAGE_CHARS", 20_000, minimum=200)

# Keeps CPU and memory use in check on small laptops (the UI stays responsive).
NUM_PREDICT = _int_env("OS_NUM_PREDICT", 256 if LOW_MEMORY else 512, minimum=32)
NUM_THREAD = _int_env("OS_NUM_THREAD", FAST_THREADS if LOW_MEMORY else max(1, CPU_COUNT // 2), minimum=1)
NUM_BATCH = _int_env("OS_NUM_BATCH", 64 if LOW_MEMORY else 128, minimum=16)
KEEP_ALIVE = os.environ.get("OS_KEEP_ALIVE", "30m")

# Keep chats fast: index new notes and preload the chat model in the background.
AUTO_INDEX = _bool_env("OS_AUTO_INDEX", True)
WARMUP = _bool_env("OS_WARMUP", True)
