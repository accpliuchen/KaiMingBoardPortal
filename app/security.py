"""Security helpers for demo magic-link login and anonymous-vote receipts.

This is not production authentication, but it demonstrates the requested
passwordless login flow and the privacy-preserving anonymous voting design.
"""

import hashlib
from typing import Optional
from itsdangerous import BadSignature, URLSafeSerializer
from .config import settings

serializer = URLSafeSerializer(settings.app_secret, salt="kai-ming-demo-login")

def make_login_token(email: str) -> str:
    """Create a signed token for the demo magic-link login."""
    return serializer.dumps({"email": email})

def verify_login_token(token: str) -> Optional[str]:
    """Return the email in a valid token, or None for invalid/expired input."""
    try:
        payload = serializer.loads(token)
    except BadSignature:
        return None
    return payload.get("email")

def voter_hash(email: str, motion_id: int) -> str:
    """Create a per-motion receipt hash for anonymous vote de-duplication.

    The hash is intentionally stored separately from the anonymous tally choice.
    That lets the system enforce one vote per person without storing who voted yes/no.
    """
    raw = f"{settings.app_secret}:{motion_id}:{email}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
