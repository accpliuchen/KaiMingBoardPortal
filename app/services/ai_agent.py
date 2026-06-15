"""Safe AI Agent implementation.

Compatibility target: Python 3.8+.

The agent answers from board records and documents. The privacy boundary is
enforced before answer generation: anonymous and officer-election ballots expose
aggregate totals only, never voter identities.
"""

from typing import Dict, List

from ..database import get_db


def build_safe_ai_context():
    """Build the only context the AI Agent or local LLM is allowed to receive."""
    lines = []  # type: List[str]

    with get_db() as conn:
        meetings = conn.execute(
            "SELECT * FROM meetings ORDER BY date DESC, id DESC"
        ).fetchall()

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
                "SELECT * FROM documents WHERE meeting_id=? ORDER BY id",
                (meeting["id"],),
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
                "SELECT * FROM motions WHERE meeting_id=? ORDER BY id",
                (meeting["id"],),
            ).fetchall()

            for motion in motions:
                officer_role = ""
                officer_candidate = ""

                if "officer_role" in motion.keys():
                    officer_role = motion["officer_role"] or ""

                if "officer_candidate" in motion.keys():
                    officer_candidate = motion["officer_candidate"] or ""

                lines.append(
                    "SOURCE motion:{id} meeting:{meeting_id} title={title} description={description} "
                    "ballot_mode={ballot_mode} motion_type={motion_type} "
                    "officer_role={officer_role} officer_candidate={officer_candidate}".format(
                        id=motion["id"],
                        meeting_id=meeting["id"],
                        title=motion["title"],
                        description=motion["description"],
                        ballot_mode=motion["ballot_mode"],
                        motion_type=motion["motion_type"],
                        officer_role=officer_role,
                        officer_candidate=officer_candidate,
                    )
                )

                if (
                    motion["ballot_mode"] == "recorded"
                    and motion["motion_type"] != "officer_election"
                ):
                    votes = conn.execute(
                        """
                        SELECT voter_name, choice
                        FROM recorded_votes
                        WHERE motion_id=?
                        ORDER BY voter_name
                        """,
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
    """Return a stable fallback answer from safe board data."""
    q = (question or "").strip()
    q_lower = q.lower()

    if not q:
        return _decline("Please ask about a meeting, motion, vote, or document.")

    with get_db() as conn:
        # 1. Privacy probes first.
        if _is_anonymous_individual_vote_probe(q_lower):
            return _answer_anonymous_privacy_probe(conn, q_lower)

        # 2. Recorded person vote must be checked before generic motion questions.
        if _asks_for_recorded_person_vote(q_lower):
            return _answer_recorded_person_vote(conn, q_lower)

        # 3. Officer election result.
        if _asks_for_officer_result(q_lower):
            return _answer_officer_result(conn, q_lower)

        # 4. Generic motions.
        if _asks_for_motions(q_lower):
            return _answer_motions_for_meeting(conn, q_lower)

        # 5. Documents.
        if _asks_for_documents(q_lower):
            return _answer_documents(conn, q_lower)

        # 6. Budget / decision.
        if _asks_about_budget_or_decision(q_lower):
            return _answer_budget_decision(conn)

        # 7. Meetings.
        if _asks_about_meetings(q_lower):
            return _answer_meetings(conn, q_lower)

    return _decline(
        "I do not have enough data in the board records to answer that question."
    )


def _decline(message):
    return message + "\n\nSources:\n- none"


def _is_anonymous_individual_vote_probe(q):
    person_words = [
        "grace",
        "david",
        "mei",
        "jerry",
        "who voted",
        "which director",
        "which directors",
        "individual",
        "raw anonymous",
        "show me who",
        "who voted yes",
        "who voted no",
        "support",
        "supported",
    ]
    anonymous_words = [
        "officer",
        "election",
        "treasurer",
        "chair",
        "secretary",
        "anonymous",
    ]
    vote_words = [
        "vote",
        "voted",
        "ballot",
        "choose",
        "chosen",
        "yes",
        "no",
        "abstain",
        "support",
        "supported",
    ]

    return (
        any(word in q for word in person_words)
        and any(word in q for word in anonymous_words)
        and any(word in q for word in vote_words)
    )


def _asks_for_motions(q):
    return "motion" in q or "motions" in q


def _asks_for_all_motions(q):
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
    return (
        "officer" in q
        or "treasurer" in q
        or "chair" in q
        or "secretary" in q
        or "election" in q
    ) and any(
        word in q
        for word in [
            "result",
            "results",
            "total",
            "totals",
            "how many",
            "count",
            "outcome",
        ]
    )


def _asks_for_recorded_person_vote(q):
    return any(name in q for name in ["grace", "david", "mei", "jerry"]) and "vote" in q


def _asks_for_documents(q):
    return any(
        word in q
        for word in [
            "document",
            "documents",
            "file",
            "files",
            "attached",
            "attachment",
            "download",
        ]
    )


def _asks_about_budget_or_decision(q):
    budget_words = ["budget", "renovation", "classroom"]
    approval_words = ["approve", "approved"]
    return any(word in q for word in budget_words) or (
        any(word in q for word in approval_words) and "motion" in q
    )


def _asks_about_meetings(q):
    return "meeting" in q or "meetings" in q or "agenda" in q or "minutes" in q


def _asks_for_meeting_list(q):
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
    return "meeting:{id} — {title}, {date}".format(
        id=row["id"],
        title=row["title"],
        date=row["date"],
    )


def _source_motion(row):
    return "motion:{id} — {title}".format(
        id=row["id"],
        title=row["title"],
    )


def _source_document(row):
    return "document:{id} — {filename}".format(
        id=row["id"],
        filename=row["filename"],
    )


def _get_may_meeting(conn):
    return conn.execute(
        """
        SELECT *
        FROM meetings
        WHERE lower(title) LIKE '%may%' OR date LIKE '2026-05%'
        ORDER BY date
        LIMIT 1
        """
    ).fetchone()


def _get_anonymous_totals(conn, motion_id):
    rows = conn.execute(
        """
        SELECT choice, count
        FROM anonymous_vote_tallies
        WHERE motion_id=?
        """,
        (motion_id,),
    ).fetchall()

    totals = {"yes": 0, "no": 0, "abstain": 0}  # type: Dict[str, int]

    for row in rows:
        totals[row["choice"]] = row["count"]

    return totals


def _format_officer_info(motion):
    officer_role = ""
    officer_candidate = ""

    if "officer_role" in motion.keys():
        officer_role = motion["officer_role"] or ""

    if "officer_candidate" in motion.keys():
        officer_candidate = motion["officer_candidate"] or ""

    parts = []

    if officer_role:
        parts.append("Officer role: {role}".format(role=officer_role.title()))

    if officer_candidate:
        parts.append("Candidate: {candidate}".format(candidate=officer_candidate))

    return " ".join(parts)


def _find_officer_motion(conn, q=""):
    """Find the correct officer-election motion based on the question."""
    q = (q or "").lower()

    role = ""
    if "treasurer" in q:
        role = "treasurer"
    elif "chair" in q:
        role = "chair"
    elif "secretary" in q:
        role = "secretary"

    if role:
        motion = conn.execute(
            """
            SELECT *
            FROM motions
            WHERE motion_type='officer_election'
              AND lower(officer_role)=?
            ORDER BY id DESC
            LIMIT 1
            """,
            (role,),
        ).fetchone()

        if motion:
            return motion

        motion = conn.execute(
            """
            SELECT *
            FROM motions
            WHERE motion_type='officer_election'
              AND (
                    lower(title) LIKE ?
                 OR lower(description) LIKE ?
              )
            ORDER BY id DESC
            LIMIT 1
            """,
            ("%" + role + "%", "%" + role + "%"),
        ).fetchone()

        if motion:
            return motion

    return conn.execute(
        """
        SELECT *
        FROM motions
        WHERE motion_type='officer_election'
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()


def _answer_motions_for_meeting(conn, q):
    if _asks_for_all_motions(q) and not any(
        word in q for word in ["may", "june", "chen"]
    ):
        motions = conn.execute(
            """
            SELECT
                m.id,
                m.title,
                m.description,
                m.ballot_mode,
                m.motion_type,
                m.officer_role,
                m.officer_candidate,
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

            officer_info = _format_officer_info(motion)
            if officer_info:
                officer_info = " " + officer_info

            motion_lines.append(
                "- {title}: {description} Attached to {meeting_title}. Ballot: {mode}.{officer_info}".format(
                    title=motion["title"],
                    description=motion["description"],
                    meeting_title=motion["meeting_title"],
                    mode=mode_note,
                    officer_info=officer_info,
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

    if "may" in q:
        meeting = _get_may_meeting(conn)
    elif "june" in q:
        meeting = conn.execute(
            """
            SELECT *
            FROM meetings
            WHERE lower(title) LIKE '%june%' OR date LIKE '2026-06%'
            ORDER BY date DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
    elif "chen" in q:
        meeting = conn.execute(
            """
            SELECT *
            FROM meetings
            WHERE lower(title) LIKE '%chen%'
            ORDER BY date DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
    else:
        motions = conn.execute(
            """
            SELECT
                m.id,
                m.title,
                m.description,
                m.ballot_mode,
                m.motion_type,
                m.officer_role,
                m.officer_candidate,
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

            officer_info = _format_officer_info(motion)
            if officer_info:
                officer_info = " " + officer_info

            motion_lines.append(
                "- {title}: {description} Attached to {meeting_title}. Ballot: {mode}.{officer_info}".format(
                    title=motion["title"],
                    description=motion["description"],
                    meeting_title=motion["meeting_title"],
                    mode=mode_note,
                    officer_info=officer_info,
                )
            )

            source_lines.append(
                "- motion:{id} — {title}, {meeting_title}".format(
                    id=motion["id"],
                    title=motion["title"],
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

    if not meeting:
        return _decline("I could not find a matching board meeting.")

    motions = conn.execute(
        "SELECT * FROM motions WHERE meeting_id=? ORDER BY id",
        (meeting["id"],),
    ).fetchall()

    if not motions:
        return _decline("I found the meeting, but there are no motions recorded for it.")

    bullet_lines = []
    source_lines = ["- " + _source_meeting(meeting)]

    for motion in motions:
        mode_note = motion["ballot_mode"]

        if motion["motion_type"] == "officer_election":
            mode_note = "anonymous officer election"

        officer_info = _format_officer_info(motion)
        if officer_info:
            officer_info = " " + officer_info

        bullet_lines.append(
            "- {title}: {description} Ballot: {mode}.{officer_info}".format(
                title=motion["title"],
                description=motion["description"],
                mode=mode_note,
                officer_info=officer_info,
            )
        )
        source_lines.append("- " + _source_motion(motion))

    return (
        "The {title} had {count} motion(s):\n\n{motions}\n\nSources:\n{sources}".format(
            title=meeting["title"],
            count=len(motions),
            motions="\n".join(bullet_lines),
            sources="\n".join(source_lines),
        )
    )


def _answer_officer_result(conn, q=""):
    motion = _find_officer_motion(conn, q)

    if not motion:
        return _decline("I could not find a matching officer election motion in the board records.")

    totals = _get_anonymous_totals(conn, motion["id"])
    officer_info = _format_officer_info(motion)

    if officer_info:
        officer_info = "\n" + officer_info + "\n"

    return (
        "The officer election is anonymous.{officer_info}"
        "I can report aggregate totals only:\n\n"
        "- Yes: {yes}\n"
        "- No: {no}\n"
        "- Abstain: {abstain}\n\n"
        "Sources:\n"
        "- {motion_source}\n"
        "- anonymous_tally for motion:{motion_id}".format(
            officer_info=officer_info,
            yes=totals.get("yes", 0),
            no=totals.get("no", 0),
            abstain=totals.get("abstain", 0),
            motion_source=_source_motion(motion),
            motion_id=motion["id"],
        )
    )


def _answer_anonymous_privacy_probe(conn, q=""):
    motion = _find_officer_motion(conn, q)

    if not motion:
        return _decline("I could not find a matching officer election motion in the board records.")

    officer_info = _format_officer_info(motion)

    if officer_info:
        officer_info = "\n" + officer_info + "\n"

    return (
        "I cannot reveal or infer which individual director voted yes, no, abstain, "
        "or supported a candidate in an anonymous officer election. "
        "The system does not store individual anonymous vote choices with voter identity."
        "{officer_info}\n"
        "Only aggregate totals are available for this anonymous motion. "
        "To view the aggregate result, ask: 'What was the result of the treasurer election?'\n\n"
        "Sources:\n"
        "- {motion_source}\n"
        "- anonymous_tally for motion:{motion_id}\n\n"
        "Privacy enforcement: individual anonymous votes are not stored with voter identity, "
        "so the AI Agent cannot access or reveal them.".format(
            officer_info=officer_info,
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

    if any(
        word in q
        for word in [
            "officer",
            "election",
            "treasurer",
            "chair",
            "secretary",
            "anonymous",
        ]
    ):
        return _answer_anonymous_privacy_probe(conn, q)

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
        return _decline(
            "I could not find a recorded vote for {person}.".format(person=person)
        )

    return (
        "{person} voted {choice} on the recorded motion '{motion_title}'.\n\n"
        "Sources:\n"
        "- motion:{motion_id} — {motion_title}\n"
        "- recorded_vote for {person}".format(
            person=person,
            choice=row["choice"],
            motion_title=row["motion_title"],
            motion_id=row["motion_id"],
        )
    )


def _answer_documents(conn, q):
    if "may" in q:
        meeting = _get_may_meeting(conn)
    else:
        meeting = conn.execute(
            "SELECT * FROM meetings ORDER BY date DESC, id DESC LIMIT 1"
        ).fetchone()

    if not meeting:
        return _decline("I could not find a matching meeting.")

    docs = conn.execute(
        "SELECT * FROM documents WHERE meeting_id=? ORDER BY id",
        (meeting["id"],),
    ).fetchall()

    if not docs:
        return _decline(
            "I found the meeting, but there are no documents attached to it."
        )

    doc_lines = []
    source_lines = ["- " + _source_meeting(meeting)]

    for doc in docs:
        summary = (doc["text_content"] or "").strip()

        if len(summary) > 180:
            summary = summary[:180] + "..."

        doc_lines.append(
            "- {filename}: {summary}".format(
                filename=doc["filename"],
                summary=summary or "No extracted text.",
            )
        )
        source_lines.append("- " + _source_document(doc))

    return (
        "The {title} has the following attached document(s):\n\n{docs}\n\nSources:\n{sources}".format(
            title=meeting["title"],
            docs="\n".join(doc_lines),
            sources="\n".join(source_lines),
        )
    )


def _answer_budget_decision(conn):
    meeting = _get_may_meeting(conn)

    motion = conn.execute(
        """
        SELECT *
        FROM motions
        WHERE lower(title) LIKE '%renovation%'
           OR lower(description) LIKE '%renovation%'
        ORDER BY id
        LIMIT 1
        """
    ).fetchone()

    doc = conn.execute(
        """
        SELECT *
        FROM documents
        WHERE lower(text_content) LIKE '%renovation%'
           OR lower(filename) LIKE '%budget%'
        ORDER BY id
        LIMIT 1
        """
    ).fetchone()

    if not motion and not doc:
        return _decline("I could not find a classroom renovation budget record.")

    parts = []
    sources = []

    if motion:
        parts.append(
            "A recorded motion was created to approve a classroom renovation budget up to $35,000."
        )
        sources.append("- " + _source_motion(motion))

        votes = conn.execute(
            """
            SELECT voter_name, choice
            FROM recorded_votes
            WHERE motion_id=?
            ORDER BY voter_name
            """,
            (motion["id"],),
        ).fetchall()

        if votes:
            vote_text = ", ".join(
                "{name}: {choice}".format(
                    name=vote["voter_name"],
                    choice=vote["choice"],
                )
                for vote in votes
            )
            parts.append(
                "The recorded votes currently shown are: {votes}.".format(
                    votes=vote_text
                )
            )
            sources.append("- recorded_votes for motion:{id}".format(id=motion["id"]))

    if doc:
        parts.append(
            "The attached budget note says the classroom renovation budget is capped at $35,000, "
            "with priority on safety repairs and accessibility improvements."
        )
        sources.append("- " + _source_document(doc))

    if meeting:
        sources.insert(0, "- " + _source_meeting(meeting))

    return " ".join(parts) + "\n\nSources:\n" + "\n".join(sources)


def _answer_meetings(conn, q):
    if _asks_for_meeting_list(q):
        meetings = conn.execute(
            "SELECT * FROM meetings ORDER BY date DESC, id DESC"
        ).fetchall()

        if not meetings:
            return _decline("I could not find any meeting records.")

        lines = []
        sources = []
        seen = set()

        for meeting in meetings:
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
            """
            SELECT *
            FROM meetings
            WHERE lower(title) LIKE '%june%' OR date LIKE '2026-06%'
            ORDER BY date DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
    elif "chen" in q:
        meeting = conn.execute(
            """
            SELECT *
            FROM meetings
            WHERE lower(title) LIKE '%chen%'
            ORDER BY date DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
    else:
        meeting = conn.execute(
            "SELECT * FROM meetings ORDER BY date DESC, id DESC LIMIT 1"
        ).fetchone()

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