"""Document service functions.

Handles safe file naming, storage, extension validation, and lightweight text
extraction for agent context.
"""

from pathlib import Path
from typing import Tuple
from uuid import uuid4
from fastapi import UploadFile
from ..config import settings

ALLOWED_SUFFIXES = {".pdf", ".docx", ".txt"}


def extract_text(path: Path, suffix: str) -> str:
    """Best-effort text extraction for TXT, DOCX, and PDF uploads."""
    try:
        if suffix == ".txt":
            return path.read_text(encoding="utf-8", errors="ignore")
        if suffix == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages).strip()
        if suffix == ".docx":
            from docx import Document
            doc = Document(str(path))
            return "\n".join(p.text for p in doc.paragraphs).strip()
    except Exception as exc:
        return f"[Text extraction failed for {path.name}: {exc}]"
    return ""


async def save_upload(file: UploadFile) -> Tuple[str, str, str]:
    """Validate, store, and extract text from an uploaded board document."""
    original = Path(file.filename or "uploaded_document").name
    suffix = Path(original).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError("Only PDF, DOCX, and TXT files are supported.")
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored_path = upload_dir / f"{uuid4().hex}{suffix}"
    stored_path.write_bytes(await file.read())
    return original, str(stored_path), extract_text(stored_path, suffix)
