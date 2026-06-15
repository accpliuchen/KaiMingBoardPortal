# Kai Ming Board Portal Demo

A working mini board portal for the Kai Ming Head Start take-home exercise.

This version is **modular**. The application is not placed in one large `app.py`; it is split into routers and services.

## Features

- Magic-link style login. The login link is shown on the page for this demo.
- Board meeting records: date, attendees, agenda, minutes.
- Admin can create meetings.
- Documents can be attached to meetings and downloaded. PDF, DOCX, and TXT are accepted.
- Admin can create motions attached to a meeting.
- Directors can vote online.
- Recorded motions store voter identity and show named results.
- Anonymous motions store only aggregate vote totals.
- Officer elections are always anonymous on the server side, even if the form submits `recorded`.
- AI Agent page answers questions about meetings, motions, votes, and uploaded documents using a safe context.
- Privacy probe protection: the AI layer cannot receive individual votes for anonymous/officer-election motions.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`.

## Demo users

```text
admin@kaiming.org    Admin
grace@kaiming.org    Director
david@kaiming.org    Director
mei@kaiming.org      Director
```

## Privacy design

Recorded votes are stored with voter identity. Anonymous votes are stored only in `anonymous_vote_tallies`. A separate `anonymous_vote_receipts` table stores a voter hash to prevent duplicate voting, but it does not store the selected choice. The AI Agent receives only the safe context, so it cannot receive individual anonymous vote choices.

## Project structure

```text
app/
  main.py
  config.py
  database.py
  security.py
  seed.py
  ui.py
  routers/
    auth.py
    meetings.py
    documents.py
    motions.py
    agent.py
  services/
    ai_agent.py
    documents.py
    voting.py
```


## Code comments

The Python modules include short module docstrings and targeted comments around the most important interview requirements: magic-link login, document attachments, motion/vote modeling, and the anonymous-vote data-layer privacy boundary.
