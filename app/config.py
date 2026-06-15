"""Application configuration with Python 3.8+ compatible code.

The AI Agent can use a free local model through Ollama. If Ollama is not
running, the app falls back to the existing deterministic safe agent.
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    # The app can still run with normal environment variables.
    pass


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(object):
    """Small settings object; avoids pydantic/version-specific config behavior."""

    def __init__(self):
        self.app_secret = os.getenv("APP_SECRET", "dev-secret-change-me")
        self.database_path = os.getenv(
            "DATABASE_PATH",
            str(BASE_DIR / "dbdata" / "board_portal.db"),
        )
        self.upload_dir = os.getenv("UPLOAD_DIR", str(BASE_DIR / "uploads"))
        self.static_dir = str(BASE_DIR / "app" / "static")

        # Free local AI Agent settings.
        self.use_llm_agent = os.getenv("USE_LLM_AGENT", "false").lower() == "true"
        self.llm_provider = os.getenv("LLM_PROVIDER", "ollama").lower()
        self.ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")


settings = Settings()