"""OfflineScholar launcher: starts the custom FastAPI web app.

The original Gradio interface is still available in gradio_app.py.
"""
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))


def main():
    import uvicorn

    import server

    uvicorn.run(
        server.app,
        host=os.environ.get("OS_HOST", "127.0.0.1"),
        port=int(os.environ.get("OS_PORT", "7860")),
        log_level="info",
    )


if __name__ == "__main__":
    main()
