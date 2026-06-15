"""SQLite database connection and schema setup.

The schema is intentionally explicit because the interview emphasizes data modeling
for meetings, motions, documents, recorded votes, and anonymous votes.
"""

import sqlite3
from pathlib import Path

from .config import settings


def get_db() -> sqlite3.Connection:
    """Open a SQLite connection and enable foreign-key enforcement."""
    Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.database_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    """Return True if a SQLite table already has the requested column."""
    columns = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(column["name"] == column_name for column in columns)


def init_db() -> None:
    """Create all tables required by the take-home project if missing."""
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                email TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'director'))
            );

            CREATE TABLE IF NOT EXISTS meetings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                title TEXT NOT NULL,
                attendees TEXT NOT NULL,
                agenda TEXT NOT NULL,
                minutes TEXT NOT NULL,
                meeting_hour INTEGER NOT NULL DEFAULT 9,
                meeting_minute INTEGER NOT NULL DEFAULT 0,
                meeting_period TEXT NOT NULL DEFAULT 'AM',
                meeting_timezone TEXT NOT NULL DEFAULT 'America/Los_Angeles'
            );

            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                meeting_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                text_content TEXT NOT NULL DEFAULT '',
                uploaded_by TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(meeting_id) REFERENCES meetings(id) ON DELETE CASCADE,
                FOREIGN KEY(uploaded_by) REFERENCES users(email)
            );

            CREATE TABLE IF NOT EXISTS motions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                meeting_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                ballot_mode TEXT NOT NULL CHECK(ballot_mode IN ('recorded', 'anonymous')),
                motion_type TEXT NOT NULL DEFAULT 'general',
                officer_role TEXT NOT NULL DEFAULT '',
                officer_candidate TEXT NOT NULL DEFAULT '',
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(meeting_id) REFERENCES meetings(id) ON DELETE CASCADE,
                FOREIGN KEY(created_by) REFERENCES users(email)
            );

            -- Recorded ballots store voter identity because board minutes need attribution.
            CREATE TABLE IF NOT EXISTS recorded_votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                motion_id INTEGER NOT NULL,
                voter_email TEXT NOT NULL,
                voter_name TEXT NOT NULL,
                choice TEXT NOT NULL CHECK(choice IN ('yes', 'no', 'abstain')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(motion_id, voter_email),
                FOREIGN KEY(motion_id) REFERENCES motions(id) ON DELETE CASCADE,
                FOREIGN KEY(voter_email) REFERENCES users(email)
            );

            -- Anonymous ballots store aggregate counts only. There is no voter_email column here,
            -- so the AI Agent cannot receive individual anonymous vote choices.
            CREATE TABLE IF NOT EXISTS anonymous_vote_tallies (
                motion_id INTEGER NOT NULL,
                choice TEXT NOT NULL CHECK(choice IN ('yes', 'no', 'abstain')),
                count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(motion_id, choice),
                FOREIGN KEY(motion_id) REFERENCES motions(id) ON DELETE CASCADE
            );

            -- Receipts prevent duplicate anonymous voting without linking a voter to a choice.
            CREATE TABLE IF NOT EXISTS anonymous_vote_receipts (
                motion_id INTEGER NOT NULL,
                voter_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(motion_id, voter_hash),
                FOREIGN KEY(motion_id) REFERENCES motions(id) ON DELETE CASCADE
            );
            """
        )

        # Migrations for existing local demo databases.
        if not _column_exists(conn, "meetings", "meeting_hour"):
            conn.execute(
                "ALTER TABLE meetings ADD COLUMN meeting_hour INTEGER NOT NULL DEFAULT 9"
            )

        if not _column_exists(conn, "meetings", "meeting_minute"):
            conn.execute(
                "ALTER TABLE meetings ADD COLUMN meeting_minute INTEGER NOT NULL DEFAULT 0"
            )

        if not _column_exists(conn, "meetings", "meeting_period"):
            conn.execute(
                "ALTER TABLE meetings ADD COLUMN meeting_period TEXT NOT NULL DEFAULT 'AM'"
            )

        if not _column_exists(conn, "meetings", "meeting_timezone"):
            conn.execute(
                "ALTER TABLE meetings ADD COLUMN meeting_timezone TEXT NOT NULL DEFAULT 'America/Los_Angeles'"
            )

        if not _column_exists(conn, "motions", "officer_role"):
            conn.execute(
                "ALTER TABLE motions ADD COLUMN officer_role TEXT NOT NULL DEFAULT ''"
            )

        if not _column_exists(conn, "motions", "officer_candidate"):
            conn.execute(
                "ALTER TABLE motions ADD COLUMN officer_candidate TEXT NOT NULL DEFAULT ''"
            )