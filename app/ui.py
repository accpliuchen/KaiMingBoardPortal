"""Small HTML rendering helpers used by the router modules.

The project avoids a template engine to keep the take-home easy to run in under
five minutes, while still separating routing logic from shared page layout.
"""

from html import escape

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .database import get_db


def current_user(request: Request):
    email = request.cookies.get("user_email")
    if not email:
        return None

    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE email=?",
            (email,),
        ).fetchone()


def require_user(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    return user


def require_admin(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    if user["role"] != "admin":
        return HTMLResponse(
            page("Forbidden", "<p>Admin access required.</p>", user),
            status_code=403,
        )

    return user


def page(title: str, body: str, user=None) -> str:
    nav = (
        '<a href="/meetings">Meetings</a>'
        '<a href="/motions">Motions</a>'
        '<a href="/motions/vote">Vote</a>'
        '<a href="/agent">AI Agent</a>'
    )

    auth = '<a href="/login">Login</a>'
    if user:
        auth = (
            f'<span>{escape(user["name"])} '
            f'({escape(user["role"])})</span> '
            f'<a href="/logout">Logout</a>'
        )

    return f"""
    <!doctype html>
    <html>
        <head>
            <meta charset="utf-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1" />
            <title>{escape(title)}</title>
            <link rel="stylesheet" href="/static/style.css" />
        </head>
        <body>
            <header>
                <div><b>Kai Ming Board Portal</b></div>
                <nav>{nav}</nav>
                <div>{auth}</div>
            </header>
            <main>{body}</main>
        </body>
    </html>
    """


def html(title: str, body: str, user=None) -> HTMLResponse:
    return HTMLResponse(page(title, body, user))


def e(value) -> str:
    return escape("" if value is None else str(value))