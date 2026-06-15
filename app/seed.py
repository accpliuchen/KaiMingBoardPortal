"""Seed demo data for reviewers.

The seeded records include one recorded motion and one anonymous officer election
so the screen recording can demonstrate the required privacy probe immediately.
"""

from pathlib import Path

from .config import settings
from .database import get_db


def seed_demo_data():
    """Insert deterministic demo data once.

    The demo document is also written to disk so download works on a fresh clone.
    """
    with get_db() as conn:
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            return

        conn.executemany(
            "INSERT INTO users(email, name, role) VALUES (?, ?, ?)",
            [
                ("admin@kaiming.org", "Jerry Admin", "admin"),
                ("grace@kaiming.org", "Grace Chen", "director"),
                ("david@kaiming.org", "David Lee", "director"),
                ("mei@kaiming.org", "Mei Wong", "director"),
            ],
        )

        conn.execute(
            """
            INSERT INTO meetings(
                date,
                title,
                attendees,
                agenda,
                minutes
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "2026-05-15",
                "May Board Meeting",
                "Grace Chen, David Lee, Mei Wong, Jerry Admin",
                "1. Approve prior minutes\n"
                "2. Review classroom renovation budget\n"
                "3. Elect interim treasurer",
                "The board approved the April minutes. The classroom renovation budget was discussed "
                "and a recorded motion was opened. An officer-election motion for interim treasurer "
                "was opened as anonymous.",
            ),
        )

        meeting_id = conn.execute(
            "SELECT id FROM meetings LIMIT 1"
        ).fetchone()[0]

        upload_dir = Path(settings.upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)

        seeded_doc_path = upload_dir / "may_budget_notes.txt"
        seeded_doc_text = (
            "Classroom renovation budget is capped at $35,000. "
            "Priority is safety repairs and accessibility improvements."
        )
        seeded_doc_path.write_text(seeded_doc_text, encoding="utf-8")

        conn.execute(
            """
            INSERT INTO documents(
                meeting_id,
                filename,
                stored_path,
                text_content,
                uploaded_by
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                meeting_id,
                "may_budget_notes.txt",
                str(seeded_doc_path),
                seeded_doc_text,
                "admin@kaiming.org",
            ),
        )

        conn.execute(
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
                "Approve classroom renovation budget",
                "Approve a renovation budget up to $35,000.",
                "recorded",
                "general",
                "",
                "",
                "admin@kaiming.org",
            ),
        )

        recorded_motion_id = conn.execute(
            "SELECT id FROM motions WHERE title='Approve classroom renovation budget'"
        ).fetchone()[0]

        conn.executemany(
            """
            INSERT INTO recorded_votes(
                motion_id,
                voter_email,
                voter_name,
                choice
            )
            VALUES (?, ?, ?, ?)
            """,
            [
                (recorded_motion_id, "grace@kaiming.org", "Grace Chen", "yes"),
                (recorded_motion_id, "david@kaiming.org", "David Lee", "no"),
            ],
        )

        conn.execute(
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
                "Elect interim treasurer",
                "Officer election for interim treasurer candidate Mei Wong.",
                "anonymous",
                "officer_election",
                "treasurer",
                "Mei Wong",
                "admin@kaiming.org",
            ),
        )

        officer_motion_id = conn.execute(
            "SELECT id FROM motions WHERE title='Elect interim treasurer'"
        ).fetchone()[0]

        conn.executemany(
            """
            INSERT INTO anonymous_vote_tallies(
                motion_id,
                choice,
                count
            )
            VALUES (?, ?, ?)
            """,
            [
                (officer_motion_id, "yes", 2),
                (officer_motion_id, "no", 0),
                (officer_motion_id, "abstain", 1),
            ],
        )