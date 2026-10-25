"""Neon Auth (Managed Better Auth) helpers for this FastAPI backend.

Gameplay still uses local JWT sessions. Neon Auth provides identity JWTs verified
via JWKS; a verified Neon token can be exchanged for a local game session.
"""

from __future__ import annotations

from typing import Any

import httpx
import jwt
from fastapi import HTTPException
from jwt import PyJWKClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.game_time import utcnow
from app.core.security import create_access_token, hash_password
from app.models.user import User

_jwk_client: PyJWKClient | None = None


def _get_jwk_client() -> PyJWKClient:
    global _jwk_client
    settings = get_settings()
    if not settings.neon_auth_jwks_url:
        raise HTTPException(status_code=503, detail="NEON_AUTH_JWKS_URL not configured")
    if _jwk_client is None:
        _jwk_client = PyJWKClient(settings.neon_auth_jwks_url, cache_keys=True)
    return _jwk_client


async def verify_neon_jwt(token: str) -> dict[str, Any]:
    try:
        client = _get_jwk_client()
        # PyJWKClient is sync HTTP under the hood; fine for infrequent auth exchange
        signing_key = client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["EdDSA", "RS256", "ES256", "ES384", "ES512"],
            audience=None,
            options={"verify_aud": False},
            # Allow clock skew between the host and Neon Auth issuers
            leeway=3600,
        )
        # Prefer explicit email claim
        if not claims.get("email") and claims.get("id"):
            claims.setdefault("email", None)
        return claims
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Neon Auth token verify failed") from exc


async def status() -> dict[str, Any]:
    settings = get_settings()
    out: dict[str, Any] = {
        "configured": bool(settings.neon_auth_base_url and settings.neon_auth_jwks_url),
        "base_url": settings.neon_auth_base_url,
        "jwks_url": settings.neon_auth_jwks_url,
        "jwks_ok": False,
        "base_ok": False,
        "keys": 0,
    }
    if not out["configured"]:
        return out
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            base = await client.get(settings.neon_auth_base_url.rstrip("/") + "/ok")
            out["base_status"] = base.status_code
            out["base_ok"] = base.status_code < 500
            jwks_resp = await client.get(settings.neon_auth_jwks_url)
            jwks_resp.raise_for_status()
            data = jwks_resp.json()
            out["jwks_ok"] = True
            out["keys"] = len(data.get("keys") or [])
            # OpenAPI / reference often exists on Managed Better Auth
            ref = await client.get(
                settings.neon_auth_base_url.rstrip("/") + "/reference"
            )
            out["reference_status"] = ref.status_code
    except Exception as exc:
        out["error"] = str(exc)
    return out


async def exchange_neon_token(db: AsyncSession, neon_token: str) -> dict[str, Any]:
    """Verify Neon Auth JWT and issue a local game access_token."""
    claims = await verify_neon_jwt(neon_token)
    email = (claims.get("email") or "").lower()
    if not email:
        raise HTTPException(
            status_code=400,
            detail="Neon Auth token missing email claim; cannot link game account",
        )

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        username_base = email.split("@")[0].replace(".", "_")[:24] or "neon_user"
        username = username_base
        n = 0
        while True:
            taken = await db.execute(select(User).where(User.username == username))
            if taken.scalar_one_or_none() is None:
                break
            n += 1
            username = f"{username_base}{n}"
        user = User(
            email=email,
            username=username,
            hashed_password=hash_password(f"neon:{claims.get('sub', email)}"),
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)

    user.last_login_at = utcnow()
    token = create_access_token(
        user.id, extra={"username": user.username, "via": "neon_auth"}
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": user.id,
        "username": user.username,
        "email": user.email,
        "neon_sub": claims.get("sub"),
    }
