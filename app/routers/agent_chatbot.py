from fastapi import APIRouter, Form, Request

from ..services.ai_agent import answer_with_safe_context, build_safe_ai_context
from ..ui import e, html, require_user

router = APIRouter(prefix="/agent-chatbot")


@router.get("")
def chatbot_page(request: Request):
    user = require_user(request)
    if not hasattr(user, "keys"):
        return user

    body = """
    <section class="card chatbot-card">
        <h1>AI Agent Chatbot</h1>
        <p class="muted">
            This is a separate chatbot-style AI Agent demo page.
        </p>

        <div class="chat-window">
            <div class="chat-message bot">
                <div class="avatar">AI</div>
                <div class="bubble">
                    Hi, I am the Kai Ming Board AI Agent.
                    Ask me about meetings, motions, votes, and documents.
                    <br><br>
                    Example questions:<br>
                    • What meetings are available?<br>
                    • What motions were approved?<br>
                    • How did Grace vote on the officer election?
                </div>
            </div>
        </div>

        <form method="post" action="/agent-chatbot" class="chat-form">
            <textarea name="question" placeholder="Ask the AI Agent..." required></textarea>
            <button type="submit">Send</button>
        </form>
    </section>
    """
    return html("AI Agent Chatbot", body, user)


@router.post("")
def chatbot_answer(request: Request, question: str = Form(...)):
    user = require_user(request)
    if not hasattr(user, "keys"):
        return user

    context = build_safe_ai_context()
    answer = answer_with_safe_context(question, context)

    body = f"""
    <section class="card chatbot-card">
        <h1>AI Agent Chatbot</h1>

        <div class="chat-window">
            <div class="chat-message user">
                <div class="avatar">You</div>
                <div class="bubble">{e(question)}</div>
            </div>

            <div class="chat-message bot">
                <div class="avatar">AI</div>
                <div class="bubble">
                    <pre>{e(answer)}</pre>
                </div>
            </div>
        </div>

        <form method="post" action="/agent-chatbot" class="chat-form">
            <textarea name="question" placeholder="Ask another question..." required></textarea>
            <button type="submit">Send</button>
        </form>

        <p class="muted">
            Privacy note: anonymous and officer-election votes are filtered before the AI receives context.
        </p>
    </section>
    """
    return html("AI Agent Chatbot", body, user)