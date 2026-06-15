"""Motion and voting routes.

Admins create motions, directors cast votes, and results are rendered differently
for recorded versus anonymous ballots.
"""

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import RedirectResponse

from ..database import get_db
from ..services.voting import cast_vote, create_motion, enforce_ballot_mode
from ..ui import e, html, require_admin, require_user

router = APIRouter(prefix="/motions")


def format_officer_role(officer_role):
    """Format officer role for display."""
    if not officer_role:
        return "Not applicable"
    return officer_role.replace("_", " ").title()


def format_candidate(candidate):
    """Format officer candidate for display."""
    return candidate if candidate else "Not applicable"


def officer_info_html(motion):
    """Render officer role and candidate details when this is an officer election."""
    if motion["motion_type"] != "officer_election":
        return ""

    return f"""
    <p><b>Officer role:</b> {e(format_officer_role(motion['officer_role']))}</p>
    <p><b>Candidate:</b> {e(format_candidate(motion['officer_candidate']))}</p>
    """


@router.get("")
def list_motions(request: Request):
    user = require_user(request)
    if not hasattr(user, "keys"):
        return user

    with get_db() as conn:
        motions = conn.execute(
            """
            SELECT motions.*, meetings.title AS meeting_title
            FROM motions
            JOIN meetings ON meetings.id = motions.meeting_id
            ORDER BY motions.id
            """
        ).fetchall()

        meetings = conn.execute(
            "SELECT id, title, date FROM meetings ORDER BY date DESC, id DESC"
        ).fetchall()

    create_motion_form = ""
    if user["role"] == "admin":
        meeting_options = "".join(
            f'<option value="{m["id"]}">{e(m["date"])} - {e(m["title"])}</option>'
            for m in meetings
        )

        if meeting_options:
            create_motion_form = f"""
            <section class="card">
                <h2>Create a motion / Start a vote</h2>
                <p class="hint">
                    Admin users can create a motion attached to a specific meeting.
                    Directors can then vote on that motion.
                </p>
                <form method="get" action="/motions/new">
                    <label>Select meeting</label>
                    <select name="meeting_id" required>
                        {meeting_options}
                    </select>
                    <button type="submit">Create motion</button>
                </form>
            </section>
            """
        else:
            create_motion_form = """
            <section class="card">
                <h2>Create a motion / Start a vote</h2>
                <p>No meetings exist yet. Create a meeting before creating a motion.</p>
                <p><a class="button" href="/meetings/new">Create meeting</a></p>
            </section>
            """

    rows = "".join(
        f"""
        <tr>
            <td><a href="/motions/{m['id']}">{e(m['title'])}</a></td>
            <td>{e(m['meeting_title'])}</td>
            <td>{e(m['ballot_mode'])}</td>
            <td>{e(m['motion_type'])}</td>
            <td>{e(format_officer_role(m['officer_role']))}</td>
            <td>{e(format_candidate(m['officer_candidate']))}</td>
            <td><a class="button" href="/motions/{m['id']}">Vote</a></td>
            <td><a href="/motions/{m['id']}/results">Results</a></td>
        </tr>
        """
        for m in motions
    )

    if not rows:
        rows = """
        <tr>
            <td colspan="8">No motions have been created yet.</td>
        </tr>
        """

    body = f"""
    <h1>Motions</h1>

    {create_motion_form}

    <table>
        <tr>
            <th>Title</th>
            <th>Meeting</th>
            <th>Ballot</th>
            <th>Type</th>
            <th>Officer Role</th>
            <th>Candidate</th>
            <th>Vote</th>
            <th>Results</th>
        </tr>
        {rows}
    </table>
    """

    return html("Motions", body, user)


@router.get("/new")
def new_motion(request: Request, meeting_id: int = Query(...)):
    user = require_admin(request)
    if not hasattr(user, "keys"):
        return user

    with get_db() as conn:
        meeting = conn.execute(
            "SELECT id, title, date FROM meetings WHERE id=?",
            (meeting_id,),
        ).fetchone()

    if not meeting:
        return html("Meeting not found", "<p>Please select an existing meeting.</p>", user)

    body = f"""
    <section class="card">
        <h1>Create motion / Start vote</h1>
        <p>
            <b>Attached meeting:</b>
            {e(meeting['date'])} - {e(meeting['title'])}
        </p>

        <form method="post" action="/motions/new">
            <input type="hidden" name="meeting_id" value="{meeting_id}" />

            <label>Motion title</label>
            <input
                name="title"
                placeholder="Example: Elect Board Treasurer"
                required
            />

            <label>Description</label>
            <textarea
                name="description"
                placeholder="Describe the motion, the reason for the vote, and any important context."
                required
            ></textarea>

            <label>Ballot mode</label>
            <select name="ballot_mode" required>
                <option value="recorded">Recorded</option>
                <option value="anonymous">Anonymous</option>
            </select>

            <label>Motion type</label>
            <select name="motion_type" required>
                <option value="general">General</option>
                <option value="officer_election">Officer election: force anonymous</option>
            </select>

            <label>Officer role</label>
            <select name="officer_role">
                <option value="">Not an officer election</option>
                <option value="chair">Chair</option>
                <option value="treasurer">Treasurer</option>
                <option value="secretary">Secretary</option>
            </select>

            <label>Officer candidate name</label>
            <input
                name="officer_candidate"
                placeholder="Example: Grace Chen"
            />

            <button type="submit">Start vote</button>
        </form>

        <p class="hint">
            Recorded mode stores each director's identity and vote choice.
            Anonymous mode stores aggregate totals only. Chair, treasurer, and
            secretary elections are forced to anonymous on the server side even
            if the form submits recorded.
        </p>
    </section>
    """

    return html("Create Motion", body, user)


@router.post("/new")
def post_new_motion(
    request: Request,
    meeting_id: int = Form(...),
    title: str = Form(...),
    description: str = Form(...),
    ballot_mode: str = Form(...),
    motion_type: str = Form(...),
    officer_role: str = Form(""),
    officer_candidate: str = Form(""),
):
    user = require_admin(request)
    if not hasattr(user, "keys"):
        return user

    motion_id = create_motion(
        meeting_id,
        title,
        description,
        ballot_mode,
        motion_type,
        user["email"],
        officer_role,
        officer_candidate,
    )

    return RedirectResponse(f"/motions/{motion_id}", status_code=303)


@router.get("/vote")
def vote_list(request: Request):
    user = require_user(request)
    if not hasattr(user, "keys"):
        return user

    with get_db() as conn:
        meetings = conn.execute(
            "SELECT id, title, date FROM meetings ORDER BY date DESC, id DESC"
        ).fetchall()

        motions = conn.execute(
            """
            SELECT motions.*, meetings.title AS meeting_title, meetings.date AS meeting_date
            FROM motions
            JOIN meetings ON meetings.id = motions.meeting_id
            ORDER BY meetings.date DESC, motions.id DESC
            """
        ).fetchall()

    meeting_options = "".join(
        f'<option value="{m["id"]}">{e(m["date"])} - {e(m["title"])}</option>'
        for m in meetings
    )

    motion_options = "".join(
        f"""
        <option value="{m['id']}">
            {e(m['meeting_date'])} - {e(m['meeting_title'])} / {e(m['title'])}
            ({e(m['ballot_mode'])}, {e(m['motion_type'])},
            {e(format_officer_role(m['officer_role']))},
            Candidate: {e(format_candidate(m['officer_candidate']))})
        </option>
        """
        for m in motions
    )

    if motion_options:
        select_vote_form = f"""
        <section class="card">
            <h2>Select meeting and motion to vote</h2>
            <p class="hint">
                Choose a meeting and the motion you want to vote on, then continue to the voting page.
            </p>

            <form method="post" action="/motions/vote/select">
                <label>Meeting</label>
                <select name="meeting_id" required>
                    {meeting_options}
                </select>

                <label>Motion</label>
                <select name="motion_id" required>
                    {motion_options}
                </select>

                <button type="submit">Continue to vote</button>
            </form>
        </section>
        """
    else:
        select_vote_form = """
        <section class="card">
            <h2>Select meeting and motion to vote</h2>
            <p>No motions are available yet. An admin must create a motion first.</p>
        </section>
        """

    rows = "".join(
        f"""
        <tr>
            <td>{e(m['meeting_title'])}</td>
            <td><a href="/motions/{m['id']}">{e(m['title'])}</a></td>
            <td>{e(m['ballot_mode'])}</td>
            <td>{e(m['motion_type'])}</td>
            <td>{e(format_officer_role(m['officer_role']))}</td>
            <td>{e(format_candidate(m['officer_candidate']))}</td>
            <td><a class="button" href="/motions/{m['id']}">Vote</a></td>
            <td><a href="/motions/{m['id']}/results">Results</a></td>
        </tr>
        """
        for m in motions
    )

    if not rows:
        rows = """
        <tr>
            <td colspan="8">No motions are available for voting yet.</td>
        </tr>
        """

    body = f"""
    <h1>Vote on motions</h1>

    <section class="card">
        <h2>Online voting rules</h2>
        <p>
            <b>Recorded mode:</b> every director's vote is stored with their identity.
            The results page shows who voted which way, by name.
        </p>
        <p>
            <b>Anonymous mode:</b> individual votes are not linked to voters at the
            data layer. The results page shows totals only.
        </p>
        <p>
            <b>Officer elections:</b> Chair, treasurer, and secretary elections are
            always anonymous. The server enforces this even if the form submits recorded.
        </p>
    </section>

    {select_vote_form}

    <table>
        <tr>
            <th>Meeting</th>
            <th>Motion</th>
            <th>Ballot</th>
            <th>Type</th>
            <th>Officer Role</th>
            <th>Candidate</th>
            <th>Vote</th>
            <th>Results</th>
        </tr>
        {rows}
    </table>
    """

    return html("Vote", body, user)


@router.post("/vote/select")
def select_motion_to_vote(
    request: Request,
    meeting_id: int = Form(...),
    motion_id: int = Form(...),
):
    user = require_user(request)
    if not hasattr(user, "keys"):
        return user

    with get_db() as conn:
        motion = conn.execute(
            """
            SELECT id
            FROM motions
            WHERE id=? AND meeting_id=?
            """,
            (motion_id, meeting_id),
        ).fetchone()

    if not motion:
        return html(
            "Invalid selection",
            """
            <section class="card">
                <p>The selected motion does not belong to the selected meeting.</p>
                <p><a href="/motions/vote">Back to Vote page</a></p>
            </section>
            """,
            user,
        )

    return RedirectResponse(f"/motions/{motion_id}", status_code=303)


@router.get("/{motion_id}")
def motion_detail(request: Request, motion_id: int):
    user = require_user(request)
    if not hasattr(user, "keys"):
        return user

    with get_db() as conn:
        motion = conn.execute(
            """
            SELECT motions.*, meetings.title AS meeting_title
            FROM motions
            JOIN meetings ON meetings.id = motions.meeting_id
            WHERE motions.id=?
            """,
            (motion_id,),
        ).fetchone()

    if not motion:
        return html("Not found", "<p>Motion not found.</p>", user)

    mode = enforce_ballot_mode(
        motion["motion_type"],
        motion["ballot_mode"],
        motion["officer_role"],
    )

    if mode == "recorded":
        mode_note = """
        <p class="hint">
            Recorded ballot: your name and vote choice will be stored and shown
            on the results page.
        </p>
        """
    else:
        mode_note = """
        <p class="privacy-note">
            Anonymous ballot: your identity will not be stored with your vote choice.
            Results will show totals only.
        </p>
        """

    body = f"""
    <section class="card">
        <h1>{e(motion['title'])}</h1>
        <p><b>Meeting:</b> {e(motion['meeting_title'])}</p>
        <p><b>Description:</b> {e(motion['description'])}</p>
        <p><b>Ballot mode:</b> {e(mode)}</p>
        <p><b>Motion type:</b> {e(motion['motion_type'])}</p>
        {officer_info_html(motion)}
        {mode_note}
    </section>

    <section class="card">
        <h2>Cast your vote</h2>
        <form method="post" action="/motions/{motion_id}/vote">
            <label>Choice</label>
            <select name="choice" required>
                <option value="yes">Yes</option>
                <option value="no">No</option>
                <option value="abstain">Abstain</option>
            </select>
            <button type="submit">Submit vote</button>
        </form>
        <p><a href="/motions/{motion_id}/results">View results</a></p>
        <p><a href="/motions/vote">Back to Vote page</a></p>
    </section>
    """

    return html(motion["title"], body, user)


@router.post("/{motion_id}/vote")
def vote(request: Request, motion_id: int, choice: str = Form(...)):
    user = require_user(request)
    if not hasattr(user, "keys"):
        return user

    ok, message = cast_vote(motion_id, user["email"], user["name"], choice)
    klass = "success" if ok else "error"

    body = f"""
    <section class="card {klass}">
        <p>{e(message)}</p>
        <p><a href="/motions/{motion_id}/results">View results</a></p>
        <p><a href="/motions/{motion_id}">Back to motion</a></p>
        <p><a href="/motions/vote">Back to Vote page</a></p>
    </section>
    """

    return html("Vote", body, user)


@router.get("/{motion_id}/results")
def results(request: Request, motion_id: int):
    user = require_user(request)
    if not hasattr(user, "keys"):
        return user

    with get_db() as conn:
        motion = conn.execute(
            """
            SELECT motions.*, meetings.title AS meeting_title
            FROM motions
            JOIN meetings ON meetings.id = motions.meeting_id
            WHERE motions.id=?
            """,
            (motion_id,),
        ).fetchone()

        if not motion:
            return html("Not found", "<p>Motion not found.</p>", user)

        mode = enforce_ballot_mode(
            motion["motion_type"],
            motion["ballot_mode"],
            motion["officer_role"],
        )

        if mode == "recorded":
            votes = conn.execute(
                """
                SELECT voter_name, choice
                FROM recorded_votes
                WHERE motion_id=?
                ORDER BY voter_name
                """,
                (motion_id,),
            ).fetchall()

            rows = "".join(
                f"""
                <tr>
                    <td>{e(v['voter_name'])}</td>
                    <td>{e(v['choice'])}</td>
                </tr>
                """
                for v in votes
            )

            if not rows:
                rows = """
                <tr>
                    <td colspan="2">No votes have been submitted yet.</td>
                </tr>
                """

            result_explanation = """
            <p>
                <b>Recorded mode:</b> each director's vote is stored with their
                identity. The results below show who voted which way, by name.
            </p>
            """

            result_html = f"""
            {result_explanation}
            <table>
                <tr>
                    <th>Director</th>
                    <th>Choice</th>
                </tr>
                {rows}
            </table>
            """

        else:
            tallies = conn.execute(
                """
                SELECT choice, count
                FROM anonymous_vote_tallies
                WHERE motion_id=?
                ORDER BY
                    CASE choice
                        WHEN 'yes' THEN 1
                        WHEN 'no' THEN 2
                        WHEN 'abstain' THEN 3
                        ELSE 4
                    END
                """,
                (motion_id,),
            ).fetchall()

            rows = "".join(
                f"""
                <tr>
                    <td>{e(t['choice'])}</td>
                    <td>{e(t['count'])}</td>
                </tr>
                """
                for t in tallies
            )

            if not rows:
                rows = """
                <tr><td>yes</td><td>0</td></tr>
                <tr><td>no</td><td>0</td></tr>
                <tr><td>abstain</td><td>0</td></tr>
                """

            result_explanation = """
            <p class="privacy-note">
                <b>Anonymous mode:</b> individual votes are not linked to voters
                at the data layer. The results below show aggregate totals only.
            </p>
            """

            result_html = f"""
            {result_explanation}
            <table>
                <tr>
                    <th>Choice</th>
                    <th>Total</th>
                </tr>
                {rows}
            </table>
            """

    body = f"""
    <section class="card">
        <h1>Results: {e(motion['title'])}</h1>
        <p><b>Meeting:</b> {e(motion['meeting_title'])}</p>
        <p><b>Ballot mode:</b> {e(mode)}</p>
        <p><b>Motion type:</b> {e(motion['motion_type'])}</p>
        {officer_info_html(motion)}
        {result_html}
    </section>
    """

    return html("Results", body, user)