"""AI Agent routes.

The agent UI accepts questions from logged-in users and answers only from a
safe context that excludes individual anonymous-vote identities.
"""

from fastapi import APIRouter, Form, Request
from ..services.ai_agent import answer_with_safe_context, build_safe_ai_context
from ..ui import e, html, require_user

router = APIRouter(prefix="/agent")

@router.get("")
def agent_page(request: Request):
    user = require_user(request)
    if not hasattr(user, "keys"):
        return user
    body = '''<section class="card"><h1>AI Agent</h1><p>Ask about meetings, motions, votes, and uploaded documents. The agent uses only a safe context.</p><form method="post" action="/agent"><label>Question</label><textarea name="question">How did Grace vote on the officer election?</textarea><button type="submit">Ask</button></form><p class="hint">Try: What did the board decide about the classroom renovation budget?</p></section>'''
    return html("AI Agent", body, user)

@router.post("")
def agent_answer(request: Request, question: str = Form(...)):
    user = require_user(request)
    if not hasattr(user, "keys"):
        return user
    context = build_safe_ai_context()
    answer = answer_with_safe_context(question, context)
    body = f'''<section class="card"><h1>AI Agent</h1><p><b>Question:</b> {e(question)}</p><h2>Answer</h2><div class="answer"><pre>{e(answer)}</pre></div><div class="privacy-note"><b>Privacy enforcement:</b> recorded votes include voter names; anonymous and officer-election votes expose aggregate totals only. The AI context does not contain individual anonymous vote choices.</div><details class="debug-context"><summary>Show safe context used by agent</summary><pre>{e(context[:5000])}</pre></details><p><a href="/agent">Ask another question</a></p></section>'''
    return html("AI Agent Answer", body, user)
