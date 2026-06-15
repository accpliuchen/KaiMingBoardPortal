"""Meeting routes.

Board members can browse meeting records. Admins can create meetings, edit meetings,
delete meetings, and attach documents.
"""

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from ..database import get_db
from ..ui import e, html, require_admin, require_user

router = APIRouter(prefix="/meetings")


def format_meeting_time(meeting) -> str:
    hour = meeting["meeting_hour"] or 9
    minute = meeting["meeting_minute"] or 0
    period = meeting["meeting_period"] or "AM"
    timezone = meeting["meeting_timezone"] or "America/Los_Angeles"
    return f"{hour}:{minute:02d} {period} {timezone}"


def selected(value, current) -> str:
    return " selected" if str(value) == str(current) else ""


def validate_meeting_time(meeting_hour, meeting_minute, meeting_period, meeting_timezone):
    if meeting_hour < 1 or meeting_hour > 12:
        return "Meeting hour must be between 1 and 12."
    if meeting_minute < 0 or meeting_minute > 59:
        return "Meeting minute must be between 0 and 59."
    if meeting_period not in ("AM", "PM"):
        return "Meeting period must be AM or PM."

    allowed_timezones = {
        "America/Los_Angeles",
        "America/Denver",
        "America/Chicago",
        "America/New_York",
    }

    if meeting_timezone not in allowed_timezones:
        return "Please select a supported timezone."

    return None


@router.get("")
def list_meetings(request: Request):
    user = require_user(request)
    if not hasattr(user, "keys"):
        return user

    with get_db() as conn:
        meetings = conn.execute(
            "SELECT * FROM meetings ORDER BY date DESC, id DESC"
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
            <td>
                {f'''
                <a href="/meetings/{m["id"]}/edit">Edit</a>
                <span style="margin: 0 6px;">|</span>
                <form method="post" action="/meetings/{m["id"]}/delete" style="display:inline;">
                    <button
                        type="submit"
                        style="background:none;border:none;color:#b42318;padding:0;cursor:pointer;font:inherit;"
                        onclick="return confirm('Are you sure? This will delete this meeting and all related documents, motions, and votes.');"
                    >
                        Delete
                    </button>
                </form>
                ''' if user["role"] == "admin" else ''}
            </td>
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
            <th>Admin</th>
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

    error = validate_meeting_time(
        meeting_hour,
        meeting_minute,
        meeting_period,
        meeting_timezone,
    )

    if error:
        return html("Invalid time", f"<p>{e(error)}</p>", user)

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


@router.get("/{meeting_id}/edit")
def edit_meeting_form(request: Request, meeting_id: int):
    user = require_admin(request)
    if not hasattr(user, "keys"):
        return user

    with get_db() as conn:
        meeting = conn.execute(
            "SELECT * FROM meetings WHERE id=?",
            (meeting_id,),
        ).fetchone()

    if not meeting:
        return html("Not found", "<p>Meeting not found.</p>", user)

    hour_options = "".join(
        f'<option value="{hour}"{selected(hour, meeting["meeting_hour"])}>{hour}</option>'
        for hour in range(1, 13)
    )

    minute_options = "".join(
        f'<option value="{minute}"{selected(minute, meeting["meeting_minute"])}>{minute:02d}</option>'
        for minute in range(0, 60, 5)
    )

    timezone_options = "".join(
        f'<option value="{tz}"{selected(tz, meeting["meeting_timezone"])}>{label}</option>'
        for tz, label in [
            ("America/Los_Angeles", "Pacific Time"),
            ("America/Denver", "Mountain Time"),
            ("America/Chicago", "Central Time"),
            ("America/New_York", "Eastern Time"),
        ]
    )

    body = f"""
    <section class="card">
        <h1>Edit meeting</h1>

        <form method="post" action="/meetings/{meeting_id}/edit">
            <label>Date</label>
            <input name="date" type="date" value="{e(meeting['date'])}" required />

            <label>Meeting Time</label>
            <div style="display: flex; gap: 12px; align-items: center;">
                <select name="meeting_hour" required>
                    {hour_options}
                </select>

                <select name="meeting_minute" required>
                    {minute_options}
                </select>

                <select name="meeting_period" required>
                    <option value="AM"{selected("AM", meeting["meeting_period"])}>AM</option>
                    <option value="PM"{selected("PM", meeting["meeting_period"])}>PM</option>
                </select>

                <select name="meeting_timezone" required>
                    {timezone_options}
                </select>
            </div>

            <label>Title</label>
            <input name="title" value="{e(meeting['title'])}" required />

            <label>Attendees</label>
            <textarea name="attendees" required>{e(meeting['attendees'])}</textarea>

            <label>Agenda</label>
            <textarea name="agenda" required>{e(meeting['agenda'])}</textarea>

            <label>Meeting Minutes / Meeting Notes</label>
            <textarea name="minutes" required>{e(meeting['minutes'])}</textarea>

            <button type="submit">Save changes</button>
            <a class="button" href="/meetings/{meeting_id}">Cancel</a>
        </form>
    </section>
    """

    return html("Edit Meeting", body, user)


@router.post("/{meeting_id}/edit")
def update_meeting(
    request: Request,
    meeting_id: int,
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

    error = validate_meeting_time(
        meeting_hour,
        meeting_minute,
        meeting_period,
        meeting_timezone,
    )

    if error:
        return html("Invalid time", f"<p>{e(error)}</p>", user)

    with get_db() as conn:
        meeting = conn.execute(
            "SELECT id FROM meetings WHERE id=?",
            (meeting_id,),
        ).fetchone()

        if not meeting:
            return html("Not found", "<p>Meeting not found.</p>", user)

        conn.execute(
            """
            UPDATE meetings
            SET date=?,
                title=?,
                attendees=?,
                agenda=?,
                minutes=?,
                meeting_hour=?,
                meeting_minute=?,
                meeting_period=?,
                meeting_timezone=?
            WHERE id=?
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
                meeting_id,
            ),
        )

    return RedirectResponse(f"/meetings/{meeting_id}", status_code=303)


@router.post("/{meeting_id}/delete")
def delete_meeting(request: Request, meeting_id: int):
    user = require_admin(request)
    if not hasattr(user, "keys"):
        return user

    with get_db() as conn:
        meeting = conn.execute(
            "SELECT id FROM meetings WHERE id=?",
            (meeting_id,),
        ).fetchone()

        if not meeting:
            return html("Not found", "<p>Meeting not found.</p>", user)

        motion_rows = conn.execute(
            "SELECT id FROM motions WHERE meeting_id=?",
            (meeting_id,),
        ).fetchall()

        motion_ids = [row["id"] for row in motion_rows]

        for motion_id in motion_ids:
            conn.execute(
                "DELETE FROM recorded_votes WHERE motion_id=?",
                (motion_id,),
            )
            conn.execute(
                "DELETE FROM anonymous_vote_tallies WHERE motion_id=?",
                (motion_id,),
            )
            conn.execute(
                "DELETE FROM anonymous_vote_receipts WHERE motion_id=?",
                (motion_id,),
            )

        conn.execute(
            "DELETE FROM motions WHERE meeting_id=?",
            (meeting_id,),
        )

        conn.execute(
            "DELETE FROM documents WHERE meeting_id=?",
            (meeting_id,),
        )

        conn.execute(
            "DELETE FROM meetings WHERE id=?",
            (meeting_id,),
        )

    return RedirectResponse("/meetings", status_code=303)


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
            <td><a href="/motions/{m['id']}">Vote</a></td>
            <td><a href="/motions/{m['id']}/results">Results</a></td>
        </tr>
        """
        for m in motions
    )

    if not motion_rows:
        motion_rows = """
        <tr>
            <td colspan="5">No motions created yet.</td>
        </tr>
        """

    create_motion_link = (
        f'<p><a class="button" href="/motions/new?meeting_id={meeting_id}">Create motion</a></p>'
        if user["role"] == "admin"
        else ""
    )

    admin_controls = ""
    if user["role"] == "admin":
        admin_controls = f"""
        <section class="card">
            <a class="button" href="/meetings/{meeting_id}/edit">Edit meeting</a>

            <form
                method="post"
                action="/meetings/{meeting_id}/delete"
                style="display:inline; margin-left: 8px;"
            >
                <button
                    type="submit"
                    onclick="return confirm('Are you sure? This will delete this meeting and all related documents, motions, and votes.');"
                >
                    Delete meeting
                </button>
            </form>
        </section>
        """

    body = f"""
    <h1>{e(meeting['title'])}</h1>

    {admin_controls}

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
                <th>Vote</th>
                <th>Results</th>
            </tr>
            {motion_rows}
        </table>
    </section>
    """

    return html(meeting["title"], body, user)