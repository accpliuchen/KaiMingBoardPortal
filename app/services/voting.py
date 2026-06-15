"""Voting service functions.

Compatibility target: Python 3.8+.

This module contains the core privacy rule from the prompt:
- Recorded ballots store voter identity with the vote choice.
- Anonymous ballots do not link individual voters to choices at the data layer.
- Chair, treasurer, and secretary elections are forced to anonymous on the server side.
"""

from sqlite3 import IntegrityError

from ..database import get_db
from ..security import voter_hash

VALID_CHOICES = {"yes", "no", "abstain"}
VALID_OFFICER_ROLES = {"chair", "treasurer", "secretary"}


def normalize_officer_role(officer_role):
    """Keep only supported officer-election roles."""
    officer_role = (officer_role or "").strip().lower()
    return officer_role if officer_role in VALID_OFFICER_ROLES else ""


def normalize_officer_candidate(officer_candidate):
    """Normalize the candidate name text."""
    return (officer_candidate or "").strip()


def normalize_motion_type(motion_type, officer_role=""):
    """Chair, treasurer, and secretary votes are always officer elections."""
    officer_role = normalize_officer_role(officer_role)

    if motion_type == "officer_election" or officer_role in VALID_OFFICER_ROLES:
        return "officer_election"

    return "general"


def enforce_ballot_mode(motion_type, submitted_mode, officer_role=""):
    """Server-side source of truth for ballot mode.

    Even if a browser submits `recorded`, chair / treasurer / secretary elections
    are forced to `anonymous` here on the server.
    """
    officer_role = normalize_officer_role(officer_role)

    if motion_type == "officer_election" or officer_role in VALID_OFFICER_ROLES:
        return "anonymous"

    return "anonymous" if submitted_mode == "anonymous" else "recorded"


def _ensure_anonymous_tally_rows(conn, motion_id):
    """Create zero-count tally rows for anonymous results."""
    for choice in ("yes", "no", "abstain"):
        conn.execute(
            """
            INSERT OR IGNORE INTO anonymous_vote_tallies(
                motion_id,
                choice,
                count
            )
            VALUES (?, ?, 0)
            """,
            (motion_id, choice),
        )


def create_motion(
    meeting_id,
    title,
    description,
    submitted_mode,
    motion_type,
    created_by,
    officer_role="",
    officer_candidate="",
):
    """Create a motion attached to a meeting.

    A motion is also the voting item.

    Officer-election roles are enforced here:
    chair, treasurer, and secretary always become anonymous votes, even if the
    form submits recorded mode.
    """
    officer_role = normalize_officer_role(officer_role)
    officer_candidate = normalize_officer_candidate(officer_candidate)

    motion_type = normalize_motion_type(motion_type, officer_role)
    ballot_mode = enforce_ballot_mode(motion_type, submitted_mode, officer_role)

    if motion_type != "officer_election":
        officer_role = ""
        officer_candidate = ""

    with get_db() as conn:
        cur = conn.execute(
            """
            INSERT INTO motions(
                meeting_id,
                title,
                description,
                ballot_mode,
                motion_type,
                officer_role,
                officer_candidate,
                created_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                meeting_id,
                title,
                description,
                ballot_mode,
                motion_type,
                officer_role,
                officer_candidate,
                created_by,
            ),
        )

        motion_id = int(cur.lastrowid)

        if ballot_mode == "anonymous":
            _ensure_anonymous_tally_rows(conn, motion_id)

        return motion_id


def _increment_anonymous_tally(conn, motion_id, choice):
    """Increment aggregate anonymous tally only.

    No voter name, email, or identity is stored with this choice.
    """
    row = conn.execute(
        """
        SELECT count
        FROM anonymous_vote_tallies
        WHERE motion_id=? AND choice=?
        """,
        (motion_id, choice),
    ).fetchone()

    if row:
        conn.execute(
            """
            UPDATE anonymous_vote_tallies
            SET count = count + 1
            WHERE motion_id=? AND choice=?
            """,
            (motion_id, choice),
        )
    else:
        conn.execute(
            """
            INSERT INTO anonymous_vote_tallies(
                motion_id,
                choice,
                count
            )
            VALUES (?, ?, 1)
            """,
            (motion_id, choice),
        )


def cast_vote(motion_id, voter_email, voter_name, choice):
    """Cast one vote and return (success, message).

    Recorded ballots:
        Store voter identity + vote choice.

    Anonymous ballots:
        Store only aggregate counts plus a separate receipt hash.
        The receipt is never stored together with yes/no/abstain.
    """
    if choice not in VALID_CHOICES:
        return False, "Invalid vote choice."

    with get_db() as conn:
        motion = conn.execute(
            """
            SELECT *
            FROM motions
            WHERE id=?
            """,
            (motion_id,),
        ).fetchone()

        if not motion:
            return False, "Motion not found."

        ballot_mode = enforce_ballot_mode(
            motion["motion_type"],
            motion["ballot_mode"],
            motion["officer_role"],
        )

        if ballot_mode == "recorded":
            try:
                conn.execute(
                    """
                    INSERT INTO recorded_votes(
                        motion_id,
                        voter_email,
                        voter_name,
                        choice
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (motion_id, voter_email, voter_name, choice),
                )
            except IntegrityError:
                return False, "You already voted on this recorded motion."

            return True, "Recorded vote saved. Your name and choice will appear in the results."

        receipt = voter_hash(voter_email, motion_id)

        try:
            conn.execute(
                """
                INSERT INTO anonymous_vote_receipts(
                    motion_id,
                    voter_hash
                )
                VALUES (?, ?)
                """,
                (motion_id, receipt),
            )
        except IntegrityError:
            return False, "You already voted on this anonymous motion."

        _ensure_anonymous_tally_rows(conn, motion_id)
        _increment_anonymous_tally(conn, motion_id, choice)

        return True, "Anonymous vote saved. Your identity is not linked to your choice."