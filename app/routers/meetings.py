"""Meeting routes.

Board members can browse meeting records. Admins can create meetings and attach
documents, matching the required board portal workflow.
"""

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from ..database import get_db
from ..ui import e, html, require_admin, require_user

router = APIRouter(prefix="/meetings")


def format_meeting_time(meeting) -> str:
    """Format meeting time from stored hour/minute/AM-PM/timezone fields."""
    hour = meeting["meeting_hour"] or 9
    minute = meeting["meeting_minute"] or 0
    period = meeting["meeting_period"] or "AM"
    timezone = meeting["meeting_timezone"] or "America/Los_Angeles"
    return f"{hour}:{minute:02d} {period} {timezone}"


@router.get("")
def list_meetings(request: Request):
    user = require_user(request)
    if not hasattr(user, "keys"):
        return user

    with get_db() as conn:
        meetings = conn.execute(
            "SELECT * FROM meetings ORDER BY date DESC"
        ).fetchall()

    admin_action = (
        '<p><a class="button" href="/meetings/new">Create meeting</a></p>'
        if user["role"] == "admin"
        else ""
    )

    rows = "".join(
        f"""
        <tr>
            <td>{e(m['date'])}</td>
            <td>{e(format_meeting_time(m))}</td>
            <td><a href="/meetings/{m['id']}">{e(m['title'])}</a></td>
            <td>{e(m['attendees'])}</td>
        </tr>
        """
        for m in meetings
    )

    body = f"""
    <h1>Board meetings</h1>
    {admin_action}
    <table>
        <tr>
            <th>Date</th>
            <th>Time</th>
            <th>Title</th>
            <th>Attendees</th>
        </tr>
        {rows}
    </table>
    """

    return html("Meetings", body, user)


@router.get("/new")
def new_meeting(request: Request):
    user = require_admin(request)
    if not hasattr(user, "keys"):
        return user

    hour_options = "".join(
        f'<option value="{hour}">{hour}</option>'
        for hour in range(1, 13)
    )

    minute_options = "".join(
        f'<option value="{minute}">{minute:02d}</option>'
        for minute in range(0, 60, 5)
    )

    timezone_options = """
        <option value="America/Los_Angeles">Pacific Time</option>
        <option value="America/Denver">Mountain Time</option>
        <option value="America/Chicago">Central Time</option>
        <option value="America/New_York">Eastern Time</option>
    """

    body = f"""
    <section class="card">
        <h1>Create meeting</h1>

        <form method="post" action="/meetings/new">
            <label>Date</label>
            <input name="date" type="date" required />

            <label>Meeting Time</label>
            <div style="display: flex; gap: 12px; align-items: center;">
                <select name="meeting_hour" required>
                    {hour_options}
                </select>

                <select name="meeting_minute" required>
                    {minute_options}
                </select>

                <select name="meeting_period" required>
                    <option value="AM">AM</option>
                    <option value="PM">PM</option>
                </select>

                <select name="meeting_timezone" required>
                    {timezone_options}
                </select>
            </div>

            <label>Title</label>
            <input
                name="title"
                placeholder="Example: June Board Meeting"
                required
            />

            <label>Attendees</label>
            <textarea
                name="attendees"
                placeholder="Example: Grace Chen, David Lee, Mei Wong"
                required
            ></textarea>

            <label>Agenda</label>
            <textarea
                name="agenda"
                placeholder="Example:&#10;1. Review prior minutes&#10;2. Discuss budget update&#10;3. Vote on motions"
                required
            ></textarea>

            <label>Meeting Minutes / Meeting Notes</label>
            <textarea
                name="minutes"
                placeholder="Enter meeting notes, decisions, and discussion summary here."
                required
            ></textarea>

            <button type="submit">Create meeting</button>
        </form>
    </section>
    """

    return html("Create Meeting", body, user)


@router.post("/new")
def create_meeting(
    request: Request,
    date: str = Form(...),
    title: str = Form(...),
    attendees: str = Form(...),
    agenda: str = Form(...),
    minutes: str = Form(...),
    meeting_hour: int = Form(...),
    meeting_minute: int = Form(...),
    meeting_period: str = Form(...),
    meeting_timezone: str = Form(...),
):
    user = require_admin(request)
    if not hasattr(user, "keys"):
        return user

    if meeting_hour < 1 or meeting_hour > 12:
        return html("Invalid time", "<p>Meeting hour must be between 1 and 12.</p>", user)
    if meeting_minute < 0 or meeting_minute > 59:
        return html("Invalid time", "<p>Meeting minute must be between 0 and 59.</p>", user)
    if meeting_period not in ("AM", "PM"):
        return html("Invalid time", "<p>Meeting period must be AM or PM.</p>", user)

    allowed_timezones = {
        "America/Los_Angeles",
        "America/Denver",
        "America/Chicago",
        "America/New_York",
    }
    if meeting_timezone not in allowed_timezones:
        return html("Invalid timezone", "<p>Please select a supported timezone.</p>", user)

    with get_db() as conn:
        cur = conn.execute(
            """
            INSERT INTO meetings(
                date,
                title,
                attendees,
                agenda,
                minutes,
                meeting_hour,
                meeting_minute,
                meeting_period,
                meeting_timezone
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                date,
                title,
                attendees,
                agenda,
                minutes,
                meeting_hour,
                meeting_minute,
                meeting_period,
                meeting_timezone,
            ),
        )

    return RedirectResponse(f"/meetings/{cur.lastrowid}", status_code=303)


@router.get("/{meeting_id}")
def meeting_detail(request: Request, meeting_id: int):
    user = require_user(request)
    if not hasattr(user, "keys"):
        return user

    with get_db() as conn:
        meeting = conn.execute(
            "SELECT * FROM meetings WHERE id=?",
            (meeting_id,),
        ).fetchone()

        docs = conn.execute(
            "SELECT * FROM documents WHERE meeting_id=? ORDER BY id",
            (meeting_id,),
        ).fetchall()

        motions = conn.execute(
            "SELECT * FROM motions WHERE meeting_id=? ORDER BY id",
            (meeting_id,),
        ).fetchall()

    if not meeting:
        return html("Not found", "<p>Meeting not found.</p>", user)

    docs_html = (
        "".join(
            f"""
            <li>
                <a href="/documents/{d['id']}/download">{e(d['filename'])}</a>
                <span class="muted">uploaded by {e(d['uploaded_by'])}</span>
            </li>
            """
            for d in docs
        )
        or "<li>No documents yet.</li>"
    )

    upload_form = (
        f"""
        <section class="card">
            <h2>Attach document</h2>
            <form
                method="post"
                action="/meetings/{meeting_id}/documents"
                enctype="multipart/form-data"
            >
                <input type="file" name="file" accept=".pdf,.docx,.txt" />
                <button type="submit">Upload</button>
            </form>
        </section>
        """
        if user["role"] == "admin"
        else ""
    )

    motion_rows = "".join(
        f"""
        <tr>
            <td><a href="/motions/{m['id']}">{e(m['title'])}</a></td>
            <td>{e(m['ballot_mode'])}</td>
            <td>{e(m['motion_type'])}</td>
            <td><a href="/motions/{m['id']}/results">Results</a></td>
        </tr>
        """
        for m in motions
    )

    create_motion_link = (
        f'<p><a class="button" href="/motions/new?meeting_id={meeting_id}">Create motion</a></p>'
        if user["role"] == "admin"
        else ""
    )

    body = f"""
    <h1>{e(meeting['title'])}</h1>

    <section class="card">
        <p><b>Date:</b> {e(meeting['date'])}</p>
        <p><b>Time:</b> {e(format_meeting_time(meeting))}</p>
        <p><b>Attendees:</b> {e(meeting['attendees'])}</p>

        <h3>Agenda</h3>
        <pre>{e(meeting['agenda'])}</pre>

        <h3>Meeting Minutes / Meeting Notes</h3>
        <pre>{e(meeting['minutes'])}</pre>
    </section>

    <section class="card">
        <h2>Documents</h2>
        <ul>{docs_html}</ul>
    </section>

    {upload_form}

    <section class="card">
        <h2>Motions</h2>
        {create_motion_link}
        <table>
            <tr>
                <th>Motion</th>
                <th>Ballot</th>
                <th>Type</th>
                <th>Results</th>
            </tr>
            {motion_rows}
        </table>
    </section>
    """

    return html(meeting["title"], body, user)