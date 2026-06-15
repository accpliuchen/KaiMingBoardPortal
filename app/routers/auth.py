"""Authentication routes.

Implements the fake magic-link login requested in the PDF: the link is displayed
on the page instead of being sent via SMTP.
"""

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from ..database import get_db
from ..security import make_login_token, verify_login_token
from ..ui import current_user, e, html

router = APIRouter()

@router.get("/")
def root():
    return RedirectResponse("/meetings", status_code=303)

@router.get("/login")
def login_page(request: Request):
    user = current_user(request)
    body = '''<section class="card"><h1>Magic-link login</h1><p>Enter a demo email. The sign-in link is shown directly on the page for this take-home exercise.</p><form method="post" action="/login"><label>Email</label><input name="email" value="admin@kaiming.org"/><button type="submit">Create magic link</button></form><p class="hint">Try admin@kaiming.org, grace@kaiming.org, david@kaiming.org, or mei@kaiming.org.</p></section>'''
    return html("Login", body, user)

@router.post("/login")
def create_magic_link(email: str = Form(...)):
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if not user:
        return html("Login", f"<section class='card'><p>Unknown demo user: {e(email)}</p><a href='/login'>Back</a></section>")
    link = f"/magic-login?token={make_login_token(email)}"
    body = f'''<section class="card"><h1>Magic link created</h1><p>In production this would be emailed. For the demo, click below:</p><p><a class="button" href="{link}">Sign in as {e(email)}</a></p></section>'''
    return html("Magic Link", body)

@router.get("/magic-login")
def magic_login(token: str):
    email = verify_login_token(token)
    if not email:
        return html("Invalid link", "<section class='card'><p>Invalid or expired link.</p></section>")
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if not user:
        return html("Invalid user", "<section class='card'><p>User not found.</p></section>")
    response = RedirectResponse("/meetings", status_code=303)
    response.set_cookie("user_email", email, httponly=True, samesite="lax")
    return response

@router.get("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("user_email")
    return response
