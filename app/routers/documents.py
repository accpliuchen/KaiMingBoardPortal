"""Document upload and download routes.

Admins can attach PDF/DOCX/TXT files to meetings; logged-in users can download
those documents from the meeting page.
"""

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from ..database import get_db
from ..services.documents import save_upload
from ..ui import html, require_admin, require_user

router = APIRouter()

@router.post("/meetings/{meeting_id}/documents")
async def upload_document(request: Request, meeting_id: int, file: UploadFile = File(...)):
    user = require_admin(request)
    if not hasattr(user, "keys"):
        return user
    try:
        filename, stored_path, text = await save_upload(file)
    except ValueError as exc:
        return html("Upload error", f"<section class='card'><p>{exc}</p><a href='/meetings/{meeting_id}'>Back</a></section>", user)
    with get_db() as conn:
        conn.execute("INSERT INTO documents(meeting_id,filename,stored_path,text_content,uploaded_by) VALUES (?,?,?,?,?)", (meeting_id, filename, stored_path, text, user["email"]))
    return RedirectResponse(f"/meetings/{meeting_id}", status_code=303)

@router.get("/documents/{document_id}/download")
def download_document(request: Request, document_id: int):
    user = require_user(request)
    if not hasattr(user, "keys"):
        return user
    with get_db() as conn:
        doc = conn.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
    if not doc:
        return html("Not found", "<p>Document not found.</p>", user)
    return FileResponse(doc["stored_path"], filename=doc["filename"])
