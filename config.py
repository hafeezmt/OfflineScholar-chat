# config.py
import os

# Model configuration
OS_MODEL = os.getenv("OS_MODEL", "gemma4:e2b-it-qat")

# Embedding model (optional)
USE_EMBEDDINGS = os.getenv("USE_EMBEDDINGS", "false").lower() == "true"
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")

# Library path
LIBRARY_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "library"))

# Database file
DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "library.db"))
