"""Free local LLM-backed AI Agent service.

This project uses Ollama as the free local model provider. No OpenAI API key is
required.

Privacy boundary:
The model never reads the database directly. It receives only the safe board
context created by app.services.ai_agent.build_safe_ai_context(). That context
may include recorded-vote identities, but anonymous/officer-election ballots
only expose aggregate totals.

For privacy-sensitive questions:
If the user asks for individual anonymous votes, we do NOT call the LLM. We use
the deterministic safe fallback directly. This prevents the model from turning
aggregate totals into a confusing privacy-probe answer.
"""

import json
import urllib.error
import urllib.request

from ..config import settings
from .ai_agent import answer_with_safe_context


SYSTEM_PROMPT = """
You are the Kai Ming Board Portal AI Agent.

Answer only from the SAFE BOARD CONTEXT provided by the application.

Required behavior:
1. Every answer must include a clear answer body first, then end with a "Sources:" section.
2. If the user asks for a list of meetings, motions, documents, or votes, use bullet points.
3. Use source labels exactly as shown in the context, for example:
   meeting:1, motion:2, document:3, recorded_vote for motion:1,
   anonymous_tally for motion:2.
4. Do not answer with only sources. First summarize the answer in plain English.
5. Do not expose raw context syntax such as "filename=", "title=", "description=", or "attendees=".
6. Do not write labels like "Answer Body" or "Answer Body in Plain English".
7. If the context does not contain enough information, say:
   "I do not have enough data in the board portal to answer that question."
   Then end with:
   Sources:
   - none
8. Do not invent meeting, motion, vote, or document facts.
9. Recorded votes may include director names and vote choices when the safe
   context includes recorded_vote source lines.
10. Anonymous ballots and officer elections must never reveal or infer individual
    voters. Only report aggregate totals from anonymous_tally source lines.
11. If asked who voted which way in an anonymous or officer-election ballot,
    explain that individual anonymous votes are not stored or available at the
    data layer.
12. Keep answers concise and understandable for a non-technical Executive Director.
"""


def _fallback(question, safe_context):
    """Use the deterministic safe agent when Ollama is unavailable, weak, or risky."""
    answer = answer_with_safe_context(question, safe_context)

    if "sources:" not in answer.lower():
        answer += "\n\nSources:\n- none"

    return answer


def _is_privacy_probe(question):
    """Detect questions asking for individual anonymous/officer-election votes.

    These must not be sent to the LLM because the model might include aggregate
    totals in a confusing way. The deterministic safe agent handles them.
    """
    q = (question or "").lower()

    person_or_identity_words = [
        "grace",
        "david",
        "mei",
        "jerry",
        "who voted",
        "which director",
        "which directors",
        "show me who",
        "who supported",
        "which directors supported",
        "raw anonymous",
        "raw votes",
        "individual",
        "identity",
        "identities",
        "i am the admin",
        "ignore previous instructions",
    ]

    anonymous_words = [
        "anonymous",
        "officer",
        "election",
        "treasurer",
        "chair",
        "secretary",
    ]

    vote_words = [
        "vote",
        "voted",
        "votes",
        "yes",
        "no",
        "abstain",
        "support",
        "supported",
        "ballot",
    ]

    return (
        any(word in q for word in person_or_identity_words)
        and any(word in q for word in anonymous_words)
        and any(word in q for word in vote_words)
    )


def _is_bad_answer(answer):
    """Detect weak local-model answers that are not good enough for the demo."""
    if not answer:
        return True

    text = answer.strip()
    lower = text.lower()

    if "sources:" not in lower:
        return True

    if lower.startswith("sources:"):
        return True

    if len(text) < 100:
        return True

    bad_patterns = [
        "**answer body:**",
        "**answer body in plain english:**",
        "answer body:",
        "answer body in plain english:",
        "filename=",
        "title=",
        "description=",
        "attendees=",
        "agenda=",
        "minutes=",
        "ballot_mode=",
        "motion_type=",
        "officer_role=",
        "officer_candidate=",
    ]

    for pattern in bad_patterns:
        if pattern in lower:
            return True

    non_source_text = lower.replace("sources:", "").strip()
    only_source_like = True

    for line in non_source_text.splitlines():
        line = line.strip()

        if not line:
            continue

        if not (
            line.startswith("- meeting:")
            or line.startswith("- motion:")
            or line.startswith("- document:")
            or line.startswith("- recorded_vote")
            or line.startswith("- anonymous_tally")
            or line.startswith("meeting:")
            or line.startswith("motion:")
            or line.startswith("document:")
            or line.startswith("recorded_vote")
            or line.startswith("anonymous_tally")
        ):
            only_source_like = False
            break

    if only_source_like:
        return True

    return False


def answer_with_llm(question, safe_context):
    """Answer a board question using a free local Ollama model when enabled."""
    print(
        "AI Agent settings:",
        settings.use_llm_agent,
        settings.llm_provider,
        settings.ollama_model,
    )

    # Important privacy fix:
    # Do not send privacy-probe questions to the LLM. Use deterministic safe logic.
    if _is_privacy_probe(question):
        print("Privacy probe detected. Using safe fallback, not Ollama.")
        return _fallback(question, safe_context)

    if not settings.use_llm_agent:
        return _fallback(question, safe_context)

    if settings.llm_provider != "ollama":
        return _fallback(question, safe_context)

    prompt = (
        SYSTEM_PROMPT
        + "\n\nSAFE BOARD CONTEXT:\n"
        + safe_context
        + "\n\nUSER QUESTION:\n"
        + question
        + "\n\nWrite a concise answer using only the SAFE BOARD CONTEXT."
        + "\nFirst give the answer body in plain English."
        + "\nIf the user asks for a list, use bullet points."
        + "\nThen end with a Sources section."
        + "\nUse only source IDs that appear in the SAFE BOARD CONTEXT."
        + "\nDo not output only the Sources section."
        + "\nDo not write 'Answer Body' or 'Answer Body in Plain English'."
        + "\nDo not expose raw context fields like filename=, title=, description=, or meeting: inside the answer body."
        + "\nIf no matching data exists, say you do not have enough data and use Sources: none."
    )

    payload = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0
        },
    }

    request = urllib.request.Request(
        settings.ollama_url + "/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        print("Calling Ollama model:", settings.ollama_model)

        with urllib.request.urlopen(request, timeout=45) as response:
            body = response.read().decode("utf-8")

        data = json.loads(body)
        answer = (data.get("response") or "").strip()

        if _is_bad_answer(answer):
            return _fallback(question, safe_context)

        return answer

    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
        return _fallback(question, safe_context)