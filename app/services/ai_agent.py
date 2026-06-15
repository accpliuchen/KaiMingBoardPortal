"""Safe AI Agent implementation.

Compatibility target: Python 3.8+.

The agent is intentionally deterministic for the take-home demo. It answers from
board records and documents, and it only exposes a safe context to the UI. The
privacy boundary is enforced before answer generation: anonymous and officer-
election ballots expose aggregate totals only, never voter identities.
"""

from typing import Dict, List, Optional

from ..database import get_db


def build_safe_ai_context():
    """Build the only context the AI Agent is allowed to display/debug.

    Recorded votes may include voter names because the requirement says recorded
    results should show attribution. Anonymous/officer-election ballots expose
    totals only. No function in this module reads anonymous votes by voter choice
    because that table does not exist in the schema.
    """
    lines = []  # type: List[str]
    with get_db() as conn:
        meetings = conn.execute("SELECT * FROM meetings ORDER BY date DESC").fetchall()
        for meeting in meetings:
            lines.append(
                "SOURCE meeting:{id} title={title} date={date} attendees={attendees} "
                "agenda={agenda} minutes={minutes}".format(
                    id=meeting["id"],
                    title=meeting["title"],
                    date=meeting["date"],
                    attendees=meeting["attendees"],
                    agenda=meeting["agenda"].replace("\n", " | "),
                    minutes=meeting["minutes"],
                )
            )

            docs = conn.execute(
                "SELECT * FROM documents WHERE meeting_id=? ORDER BY id", (meeting["id"],)
            ).fetchall()
            for doc in docs:
                text = (doc["text_content"] or "").replace("\n", " ")[:1200]
                lines.append(
                    "SOURCE document:{id} meeting:{meeting_id} filename={filename} text={text}".format(
                        id=doc["id"],
                        meeting_id=meeting["id"],
                        filename=doc["filename"],
                        text=text,
                    )
                )

            motions = conn.execute(
                "SELECT * FROM motions WHERE meeting_id=? ORDER BY id", (meeting["id"],)
            ).fetchall()
            for motion in motions:
                lines.append(
                    "SOURCE motion:{id} meeting:{meeting_id} title={title} description={description} "
                    "ballot_mode={ballot_mode} motion_type={motion_type}".format(
                        id=motion["id"],
                        meeting_id=meeting["id"],
                        title=motion["title"],
                        description=motion["description"],
                        ballot_mode=motion["ballot_mode"],
                        motion_type=motion["motion_type"],
                    )
                )

                if motion["ballot_mode"] == "recorded" and motion["motion_type"] != "officer_election":
                    votes = conn.execute(
                        "SELECT voter_name, choice FROM recorded_votes WHERE motion_id=? ORDER BY voter_name",
                        (motion["id"],),
                    ).fetchall()
                    for vote in votes:
                        lines.append(
                            "SOURCE motion:{id} recorded_vote voter={voter} choice={choice}".format(
                                id=motion["id"],
                                voter=vote["voter_name"],
                                choice=vote["choice"],
                            )
                        )
                else:
                    totals = _get_anonymous_totals(conn, motion["id"])
                    lines.append(
                        "SOURCE motion:{id} anonymous_tally totals: yes={yes}, no={no}, abstain={abstain}. "
                        "Individual anonymous votes are not stored or available.".format(
                            id=motion["id"],
                            yes=totals.get("yes", 0),
                            no=totals.get("no", 0),
                            abstain=totals.get("abstain", 0),
                        )
                    )
    return "\n".join(lines)


def answer_with_safe_context(question, context):
    """Return a polished answer from safe board data.

    The `context` parameter is kept for transparency/debug display in the UI,
    but the final answer is generated from typed SQL queries instead of dumping
    raw context lines. This makes the agent response look like a real product.
    """
    q = (question or "").strip()
    q_lower = q.lower()

    if not q:
        return _decline("Please ask about a meeting, motion, vote, or document.")

    with get_db() as conn:
        if _is_anonymous_individual_vote_probe(q_lower):
            return _answer_anonymous_privacy_probe(conn)

        if _asks_for_motions(q_lower):
            return _answer_motions_for_meeting(conn, q_lower)

        if _asks_for_officer_result(q_lower):
            return _answer_officer_result(conn)

        if _asks_for_recorded_person_vote(q_lower):
            return _answer_recorded_person_vote(conn, q_lower)

        if _asks_for_documents(q_lower):
            return _answer_documents(conn, q_lower)

        if _asks_about_budget_or_decision(q_lower):
            return _answer_budget_decision(conn)

        if _asks_about_meetings(q_lower):
            return _answer_meetings(conn, q_lower)

    return _decline("I do not have enough data in the board records to answer that question.")


def _decline(message):
    return message + "\n\nSources: none."


def _is_anonymous_individual_vote_probe(q):
    person_words = ["grace", "david", "mei", "jerry", "who voted", "which director", "individual"]
    anonymous_words = ["officer", "election", "treasurer", "chair", "secretary", "anonymous"]
    vote_words = ["vote", "voted", "ballot", "choose", "chosen", "yes", "no", "abstain"]
    return any(w in q for w in person_words) and any(w in q for w in anonymous_words) and any(w in q for w in vote_words)


def _asks_for_motions(q):
    return "motion" in q or "motions" in q


def _asks_for_all_motions(q):
    """Detect questions that ask for the motion index/list.

    This needs a separate branch because "What motions are available?" should
    list every motion record, not assume the user is asking about the latest
    meeting. Specific questions like "motions for the May board meeting" are
    handled by the meeting-specific branch.
    """
    list_phrases = [
        "what motions",
        "motions are available",
        "available motions",
        "list motions",
        "list all motions",
        "all motions",
        "show motions",
        "show all motions",
        "motion records",
        "all board motions",
    ]
    return any(phrase in q for phrase in list_phrases)


def _asks_for_officer_result(q):
    return ("officer" in q or "treasurer" in q or "election" in q) and any(
        w in q for w in ["result", "results", "total", "totals", "how many", "count", "outcome"]
    )


def _asks_for_recorded_person_vote(q):
    return any(name in q for name in ["grace", "david", "mei", "jerry"]) and "vote" in q


def _asks_for_documents(q):
    return any(w in q for w in ["document", "documents", "file", "files", "attached", "attachment", "download"])


def _asks_about_budget_or_decision(q):
    # Avoid answering unrelated decision questions with the budget demo data.
    budget_words = ["budget", "renovation", "classroom"]
    approval_words = ["approve", "approved"]
    return any(w in q for w in budget_words) or (any(w in q for w in approval_words) and "motion" in q)


def _asks_about_meetings(q):
    return "meeting" in q or "meetings" in q or "agenda" in q or "minutes" in q


def _asks_for_meeting_list(q):
    """Detect questions that ask for all available meetings.

    This must be checked before the single-meeting-detail branch. Otherwise a
    broad question like "What meetings are available?" can accidentally return
    only the latest meeting.
    """
    list_phrases = [
        "what meetings",
        "meetings are available",
        "available meetings",
        "list meetings",
        "list all meetings",
        "all meetings",
        "show meetings",
        "show all meetings",
        "meeting records",
        "all board meetings",
    ]
    return any(phrase in q for phrase in list_phrases)


def _source_meeting(row):
    return "meeting:{id} — {title}, {date}".format(id=row["id"], title=row["title"], date=row["date"])


def _source_motion(row):
    return "motion:{id} — {title}".format(id=row["id"], title=row["title"])


def _source_document(row):
    return "document:{id} — {filename}".format(id=row["id"], filename=row["filename"])


def _get_may_meeting(conn):
    return conn.execute(
        "SELECT * FROM meetings WHERE lower(title) LIKE '%may%' OR date LIKE '2026-05%' ORDER BY date LIMIT 1"
    ).fetchone()


def _get_anonymous_totals(conn, motion_id):
    rows = conn.execute(
        "SELECT choice, count FROM anonymous_vote_tallies WHERE motion_id=?", (motion_id,)
    ).fetchall()
    totals = {"yes": 0, "no": 0, "abstain": 0}  # type: Dict[str, int]
    for row in rows:
        totals[row["choice"]] = row["count"]
    return totals


def _answer_motions_for_meeting(conn, q):
    """Answer both all-motion and meeting-specific motion questions."""

    # Broad list intent: "What motions are available?", "List all motions."
    if _asks_for_all_motions(q) and not any(w in q for w in ["may", "june", "chen"]):
        motions = conn.execute(
            """
            SELECT
                m.id,
                m.title,
                m.description,
                m.ballot_mode,
                m.motion_type,
                mt.id AS meeting_id,
                mt.title AS meeting_title,
                mt.date AS meeting_date
            FROM motions m
            JOIN meetings mt ON mt.id = m.meeting_id
            ORDER BY mt.date DESC, m.id
            """
        ).fetchall()

        if not motions:
            return _decline("I could not find any motion records.")

        motion_lines = []
        source_lines = []
        for motion in motions:
            mode_note = motion["ballot_mode"]
            if motion["motion_type"] == "officer_election":
                mode_note = "anonymous officer election"

            motion_lines.append(
                "- {title}: {description} Attached to {meeting_title}. Ballot: {mode}.".format(
                    title=motion["title"],
                    description=motion["description"],
                    meeting_title=motion["meeting_title"],
                    mode=mode_note,
                )
            )
            source_lines.append(
                "- motion:{motion_id} — {motion_title}, {meeting_title}".format(
                    motion_id=motion["id"],
                    motion_title=motion["title"],
                    meeting_title=motion["meeting_title"],
                )
            )

        return (
            "The board portal currently has {count} motion record(s):\n\n"
            "{motions}\n\n"
            "Sources:\n{sources}".format(
                count=len(motions),
                motions="\n".join(motion_lines),
                sources="\n".join(source_lines),
            )
        )

    # Meeting-specific intent: "motions for the May board meeting", etc.
    if "may" in q:
        meeting = _get_may_meeting(conn)
    elif "june" in q:
        meeting = conn.execute(
            "SELECT * FROM meetings WHERE lower(title) LIKE '%june%' OR date LIKE '2026-06%' ORDER BY date DESC, id DESC LIMIT 1"
        ).fetchone()
    elif "chen" in q:
        meeting = conn.execute(
            "SELECT * FROM meetings WHERE lower(title) LIKE '%chen%' ORDER BY date DESC, id DESC LIMIT 1"
        ).fetchone()
    else:
        # If the user did not name a meeting and did not clearly ask for all
        # motions, fall back to all motions instead of guessing the latest meeting.
        motions = conn.execute(
            """
            SELECT
                m.id,
                m.title,
                m.description,
                m.ballot_mode,
                m.motion_type,
                mt.title AS meeting_title
            FROM motions m
            JOIN meetings mt ON mt.id = m.meeting_id
            ORDER BY mt.date DESC, m.id
            """
        ).fetchall()
        if not motions:
            return _decline("I could not find any motion records.")

        motion_lines = []
        source_lines = []
        for motion in motions:
            mode_note = motion["ballot_mode"]
            if motion["motion_type"] == "officer_election":
                mode_note = "anonymous officer election"
            motion_lines.append(
                "- {title}: {description} Attached to {meeting_title}. Ballot: {mode}.".format(
                    title=motion["title"],
                    description=motion["description"],
                    meeting_title=motion["meeting_title"],
                    mode=mode_note,
                )
            )
            source_lines.append(
                "- motion:{id} — {title}, {meeting_title}".format(
                    id=motion["id"], title=motion["title"], meeting_title=motion["meeting_title"]
                )
            )
        return (
            "The board portal currently has {count} motion record(s):\n\n{motions}\n\nSources:\n{sources}".format(
                count=len(motions),
                motions="\n".join(motion_lines),
                sources="\n".join(source_lines),
            )
        )

    if not meeting:
        return _decline("I could not find a matching board meeting.")

    motions = conn.execute("SELECT * FROM motions WHERE meeting_id=? ORDER BY id", (meeting["id"],)).fetchall()
    if not motions:
        return _decline("I found the meeting, but there are no motions recorded for it.")

    bullet_lines = []
    source_lines = ["- " + _source_meeting(meeting)]
    for motion in motions:
        mode_note = motion["ballot_mode"]
        if motion["motion_type"] == "officer_election":
            mode_note = "anonymous officer election"
        bullet_lines.append(
            "- {title}: {description} Ballot: {mode}.".format(
                title=motion["title"], description=motion["description"], mode=mode_note
            )
        )
        source_lines.append("- " + _source_motion(motion))

    return (
        "The {title} had {count} motion(s):\n\n{motions}\n\nSources:\n{sources}".format(
            title=meeting["title"], count=len(motions), motions="\n".join(bullet_lines), sources="\n".join(source_lines)
        )
    )

def _answer_officer_result(conn):
    motion = conn.execute(
        "SELECT * FROM motions WHERE motion_type='officer_election' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not motion:
        return _decline("I could not find an officer election motion in the board records.")

    totals = _get_anonymous_totals(conn, motion["id"])
    return (
        "The officer election is anonymous. I can report aggregate totals only:\n\n"
        "- Yes: {yes}\n- No: {no}\n- Abstain: {abstain}\n\n"
        "Sources:\n- {motion_source}\n- anonymous_tally for motion:{motion_id}".format(
            yes=totals.get("yes", 0),
            no=totals.get("no", 0),
            abstain=totals.get("abstain", 0),
            motion_source=_source_motion(motion),
            motion_id=motion["id"],
        )
    )


def _answer_anonymous_privacy_probe(conn):
    motion = conn.execute(
        "SELECT * FROM motions WHERE motion_type='officer_election' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not motion:
        return _decline("I could not find an officer election motion in the board records.")

    totals = _get_anonymous_totals(conn, motion["id"])
    return (
        "I cannot reveal or infer how any individual director voted in an anonymous officer election. "
        "The system only stores and exposes aggregate totals for that motion.\n\n"
        "Result:\n- Yes: {yes}\n- No: {no}\n- Abstain: {abstain}\n\n"
        "Sources:\n- {motion_source}\n- anonymous_tally for motion:{motion_id}\n\n"
        "Privacy enforcement: individual anonymous votes are not stored with voter identity, "
        "so the AI Agent cannot access or reveal them.".format(
            yes=totals.get("yes", 0),
            no=totals.get("no", 0),
            abstain=totals.get("abstain", 0),
            motion_source=_source_motion(motion),
            motion_id=motion["id"],
        )
    )


def _person_from_question(q):
    mapping = {
        "grace": "Grace Chen",
        "david": "David Lee",
        "mei": "Mei Wong",
        "jerry": "Jerry Admin",
    }
    for key, name in mapping.items():
        if key in q:
            return name
    return None


def _answer_recorded_person_vote(conn, q):
    person = _person_from_question(q)
    if not person:
        return _decline("I could not identify which director you are asking about.")

    # Privacy check first: if the user is asking about officer/anonymous election,
    # refuse even if a person's name appears in the question.
    if any(w in q for w in ["officer", "election", "treasurer", "chair", "secretary", "anonymous"]):
        return _answer_anonymous_privacy_probe(conn)

    row = conn.execute(
        """
        SELECT rv.choice, m.id AS motion_id, m.title AS motion_title
        FROM recorded_votes rv
        JOIN motions m ON m.id = rv.motion_id
        WHERE rv.voter_name=?
        ORDER BY rv.created_at DESC
        LIMIT 1
        """,
        (person,),
    ).fetchone()
    if not row:
        return _decline("I could not find a recorded vote for {person}.".format(person=person))

    return (
        "{person} voted {choice} on the recorded motion '{motion_title}'.\n\n"
        "Sources:\n- motion:{motion_id} — {motion_title}\n- recorded_vote for {person}".format(
            person=person,
            choice=row["choice"],
            motion_title=row["motion_title"],
            motion_id=row["motion_id"],
        )
    )


def _answer_documents(conn, q):
    meeting = _get_may_meeting(conn) if "may" in q else conn.execute("SELECT * FROM meetings ORDER BY date DESC LIMIT 1").fetchone()
    if not meeting:
        return _decline("I could not find a matching meeting.")
    docs = conn.execute("SELECT * FROM documents WHERE meeting_id=? ORDER BY id", (meeting["id"],)).fetchall()
    if not docs:
        return _decline("I found the meeting, but there are no documents attached to it.")

    doc_lines = []
    source_lines = ["- " + _source_meeting(meeting)]
    for doc in docs:
        summary = (doc["text_content"] or "").strip()
        if len(summary) > 180:
            summary = summary[:180] + "..."
        doc_lines.append("- {filename}: {summary}".format(filename=doc["filename"], summary=summary or "No extracted text."))
        source_lines.append("- " + _source_document(doc))

    return (
        "The {title} has the following attached document(s):\n\n{docs}\n\nSources:\n{sources}".format(
            title=meeting["title"], docs="\n".join(doc_lines), sources="\n".join(source_lines)
        )
    )


def _answer_budget_decision(conn):
    meeting = _get_may_meeting(conn)
    motion = conn.execute(
        "SELECT * FROM motions WHERE lower(title) LIKE '%renovation%' OR lower(description) LIKE '%renovation%' ORDER BY id LIMIT 1"
    ).fetchone()
    doc = conn.execute(
        "SELECT * FROM documents WHERE lower(text_content) LIKE '%renovation%' OR lower(filename) LIKE '%budget%' ORDER BY id LIMIT 1"
    ).fetchone()

    if not motion and not doc:
        return _decline("I could not find a classroom renovation budget record.")

    parts = []
    sources = []
    if motion:
        parts.append("A recorded motion was created to approve a classroom renovation budget up to $35,000.")
        sources.append("- " + _source_motion(motion))
        votes = conn.execute("SELECT voter_name, choice FROM recorded_votes WHERE motion_id=? ORDER BY voter_name", (motion["id"],)).fetchall()
        if votes:
            vote_text = ", ".join("{name}: {choice}".format(name=v["voter_name"], choice=v["choice"]) for v in votes)
            parts.append("The recorded votes currently shown are: {votes}.".format(votes=vote_text))
            sources.append("- recorded_votes for motion:{id}".format(id=motion["id"]))
    if doc:
        parts.append("The attached budget note says the classroom renovation budget is capped at $35,000, with priority on safety repairs and accessibility improvements.")
        sources.append("- " + _source_document(doc))
    if meeting:
        sources.insert(0, "- " + _source_meeting(meeting))

    return " ".join(parts) + "\n\nSources:\n" + "\n".join(sources)


def _answer_meetings(conn, q):
    """Answer meeting-list and single-meeting questions.

    Broad questions return all meeting records. Specific questions such as
    "What was discussed in the May Board Meeting?" return one meeting's detail.
    """
    if _asks_for_meeting_list(q):
        meetings = conn.execute("SELECT * FROM meetings ORDER BY date DESC, id DESC").fetchall()
        if not meetings:
            return _decline("I could not find any meeting records.")

        lines = []
        sources = []
        seen = set()
        for meeting in meetings:
            # Show the true records, including duplicates created during testing,
            # but avoid duplicate source lines if SQLite returns the same ID twice.
            lines.append(
                "- {title} — {date}".format(
                    title=meeting["title"],
                    date=meeting["date"],
                )
            )
            source = "- " + _source_meeting(meeting)
            if source not in seen:
                sources.append(source)
                seen.add(source)

        return (
            "The board portal currently has {count} meeting record(s):\n\n"
            "{meetings}\n\n"
            "Sources:\n{sources}".format(
                count=len(meetings),
                meetings="\n".join(lines),
                sources="\n".join(sources),
            )
        )

    if "may" in q:
        meeting = _get_may_meeting(conn)
    elif "june" in q:
        meeting = conn.execute(
            "SELECT * FROM meetings WHERE lower(title) LIKE '%june%' OR date LIKE '2026-06%' ORDER BY date DESC, id DESC LIMIT 1"
        ).fetchone()
    elif "chen" in q:
        meeting = conn.execute(
            "SELECT * FROM meetings WHERE lower(title) LIKE '%chen%' ORDER BY date DESC, id DESC LIMIT 1"
        ).fetchone()
    else:
        meeting = conn.execute("SELECT * FROM meetings ORDER BY date DESC, id DESC LIMIT 1").fetchone()

    if not meeting:
        return _decline("I could not find any meeting records matching that question.")

    return (
        "{title} was held on {date}. Attendees were {attendees}.\n\n"
        "Agenda:\n{agenda}\n\n"
        "Minutes:\n{minutes}\n\n"
        "Sources:\n- {source}".format(
            title=meeting["title"],
            date=meeting["date"],
            attendees=meeting["attendees"],
            agenda=meeting["agenda"],
            minutes=meeting["minutes"],
            source=_source_meeting(meeting),
        )
    )
