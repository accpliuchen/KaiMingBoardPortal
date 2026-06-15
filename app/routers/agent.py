"""AI Agent routes.

Logged-in users can ask questions about meetings, motions, votes, and uploaded
documents. The route builds a safe context first, then optionally sends that
safe context to a free local LLM through Ollama.
"""

from fastapi import APIRouter, Form, Request

from ..config import settings
from ..services.ai_agent import build_safe_ai_context
from ..services.llm_client import answer_with_llm
from ..ui import e, html, require_user

router = APIRouter(prefix="/agent")


@router.get("")
def agent_page(request: Request):
    user = require_user(request)
    if not hasattr(user, "keys"):
        return user

    if settings.use_llm_agent:
        mode = "Free local Ollama model: {0}".format(settings.ollama_model)
    else:
        mode = "Local safe agent fallback"

    body = f"""
    <section class="card">
        <h1>AI Agent</h1>
        <p>
            Ask about meetings, motions, votes, and uploaded documents.
            The agent answers from the board portal's safe data context and
            cites meeting, motion, vote, or document sources.
        </p>
        <p class="hint"><b>Mode:</b> {e(mode)}</p>

        <form method="post" action="/agent">
            <label>Question</label>
            <textarea
                name="question"
                placeholder="Example: What was the result of the treasurer election?"
                required
            ></textarea>
            <button type="submit">Ask</button>
        </form>

        <div class="hint">
            <p><b>Try these:</b></p>
            <p>What meetings are available?</p>
            <p>What motions are attached to the May Board Meeting?</p>
            <p>What documents are attached to the May Board Meeting?</p>
            <p>How did Grace vote on the recorded budget motion?</p>
            <p>Who voted yes in the anonymous treasurer election?</p>
        </div>
    </section>
    """

    return html("AI Agent", body, user)


@router.post("")
def agent_answer(request: Request, question: str = Form(...)):
    user = require_user(request)
    if not hasattr(user, "keys"):
        return user

    safe_context = build_safe_ai_context()
    answer = answer_with_llm(question, safe_context)

    body = f"""
    <section class="card">
        <h1>AI Agent</h1>
        <p><b>Question:</b> {e(question)}</p>

        <h2>Answer</h2>
        <div class="answer">
            <pre>{e(answer)}</pre>
        </div>

        <div class="privacy-note">
            <b>Privacy enforcement:</b>
            recorded votes may include director names and choices.
            Anonymous and officer-election ballots expose aggregate totals only.
            The model context does not contain individual anonymous vote choices.
        </div>

        <details class="debug-context">
            <summary>Show safe context sent to AI</summary>
            <pre>{e(safe_context[:10000])}</pre>
        </details>

        <p><a href="/agent">Ask another question</a></p>
    </section>
    """

    return html("AI Agent Answer", body, user)