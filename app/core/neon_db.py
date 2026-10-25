"""Normalize Neon / Postgres URLs for SQLAlchemy + asyncpg."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


def strip_quotes(value: str) -> str:
    v = value.strip()
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return v[1:-1]
    return v


def to_async_sqlalchemy_url(database_url: str) -> tuple[str, dict]:
    """Return (sqlalchemy_url, connect_args) for Neon pooled/direct Postgres.

    Prefer the pooled ``DATABASE_URL`` for the FastAPI app.
    Use ``DATABASE_URL_UNPOOLED`` for migrations / admin.
    """
    raw = strip_quotes(database_url)
    connect_args: dict = {}

    if raw.startswith("sqlite"):
        return raw, connect_args

    if raw.startswith("postgres://"):
        raw = "postgresql://" + raw[len("postgres://") :]

    if raw.startswith("postgresql+asyncpg://"):
        scheme = "postgresql+asyncpg"
        rest = raw[len("postgresql+asyncpg://") :]
    elif raw.startswith("postgresql://"):
        scheme = "postgresql+asyncpg"
        rest = raw[len("postgresql://") :]
    else:
        return raw, connect_args

    parsed = urlparse(f"{scheme}://{rest}")
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))

    sslmode = query.pop("sslmode", None)
    query.pop("channel_binding", None)  # asyncpg does not accept this param

    if sslmode in ("require", "verify-ca", "verify-full") or "neon.tech" in (parsed.hostname or ""):
        # Neon requires TLS; True lets asyncpg negotiate.
        connect_args["ssl"] = True

    new_query = urlencode(query)
    url = urlunparse(
        (
            scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment,
        )
    )
    return url, connect_args
