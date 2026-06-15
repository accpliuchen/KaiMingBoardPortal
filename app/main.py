"""Application entry point for Kai Ming Board Portal."""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .database import init_db
from .seed import seed_demo_data
from .routers import agent, auth, documents, meetings, motions
from .routers import agent_chatbot

app = FastAPI(title="Kai Ming Board Portal")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(meetings.router)
app.include_router(documents.router)
app.include_router(motions.router)
app.include_router(agent.router)
app.include_router(agent_chatbot.router)


@app.on_event("startup")
def startup():
    init_db()
    seed_demo_data()