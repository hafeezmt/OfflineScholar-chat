"""OfflineScholar settings. Change models with environment variables, no code edits needed."""
import os
from pathlib import Path

BASE = Path(__file__).parent
LIBRARY_DIR = BASE / "library"
SAVED_DIR = LIBRARY_DIR / "saved_pages"
DB_PATH = BASE / "scholar.db"

# Answer model (Gemma 4, runs locally through Ollama)
CHAT_MODEL = os.environ.get("OS_MODEL", "gemma4:e2b-it-qat")

# Search model (Snowflake Arctic Embed, open-weight, runs locally through Ollama)
EMBED_MODEL = os.environ.get("OS_EMBED", "snowflake-arctic-embed:33m")
USE_EMBEDDINGS = os.environ.get("OS_EMBEDDINGS", "1") == "1"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

CHUNK_WORDS = 250
CHUNK_OVERLAP = 40
TOP_K = 4
SUPPORTED = {".txt", ".md", ".pdf", ".docx"}
