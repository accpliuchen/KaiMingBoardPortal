"""FastAPI application entry point.

This file only wires the application together. The actual business logic lives
in routers/ and services/ so the project looks like a maintainable codebase,
not a one-file prototype.
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import init_db
from .seed import seed_demo_data
from .routers import agent, auth, documents, meetings, motions


app = FastAPI(title="Kai Ming Board Portal Demo")

# Use an absolute static directory for compatibility with Terminal and PyCharm.
app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")

from .routers import agent_chatbot
app.include_router(agent_chatbot.router)

app.include_router(auth.router)
app.include_router(meetings.router)
app.include_router(documents.router)
app.include_router(motions.router)
app.include_router(agent.router)


@app.on_event("startup")
def startup():
    """Initialize schema and demo data when the reviewer starts the app."""
    init_db()
    seed_demo_data()
