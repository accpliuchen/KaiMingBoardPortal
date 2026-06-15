# 1-Page Summary — Kai Ming Board Portal

## Architecture

```text
Browser -> FastAPI routers -> Services -> SQLite

routers/auth.py       magic-link demo login
routers/meetings.py   meeting list/detail/create
routers/documents.py  document upload/download
routers/motions.py    motion create/vote/results
routers/agent.py      AI Agent chat interface

services/voting.py    recorded vs anonymous vote enforcement
services/ai_agent.py  safe context + sourced answer
services/documents.py file storage + text extraction
```

## Stack choice

I chose FastAPI, SQLite, and simple server-rendered HTML because the assignment is capped at about eight hours and asks for a working end-to-end website rather than a polished UI. FastAPI keeps the backend readable, SQLite makes the project easy to run in under five minutes, and the modular structure separates auth, meetings, documents, voting, and AI-agent concerns.

## Privacy and AI design

Anonymous votes are anonymous in the schema, not only in the prompt. Recorded votes are stored with voter identity. Anonymous votes are stored only as aggregate tallies. A separate anonymous receipt table stores a voter hash to prevent duplicate voting, but it does not store the selected choice. The AI Agent receives a safe context built from meetings, documents, motions, recorded votes, and anonymous aggregate totals only.

## With two more weeks

I would add a proper authentication provider, email delivery for magic links, role-based permissions, database migrations, audit logs, document virus scanning, production object storage, automated tests, and a real LLM gateway with prompt-injection tests and answer-quality evaluation.

## Question for Jerry

For the real Kai Ming use case, which board documents are most important for the Executive Director to ask questions about first: meeting minutes, financial packets, policy documents, or officer-election records?

## AI coding assistant used

I used ChatGPT as a coding assistant to draft the implementation, refactor the code into modules, generate the README and summary, and review the privacy boundary for anonymous voting.
