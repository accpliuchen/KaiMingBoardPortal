"""Application configuration with Python 3.8+ compatible code.

The project keeps paths absolute so it runs reliably from PyCharm, Terminal,
or GitHub review machines as long as the command is run from the repo root.
"""

import os
from pathlib import Path

# Repo root: .../kai_ming_board_portal_modular
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


settings = Settings()
