from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.game_time import utcnow
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import RegisterRequest, TokenResponse, UserOut
from app.services import neon_auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


class NeonExchangeRequest(BaseModel):
    neon_access_token: str = Field(min_length=20)


@router.post("/register", response_model=UserOut, status_code=201)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(
        select(User).where(
            (User.email == payload.email) | (User.username == payload.username)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email or username already registered")

    user = User(
        email=payload.email.lower(),
        username=payload.username.lower(),
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).where(User.username == form_data.username.lower())
    )
    user = result.scalar_one_or_none()
    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    user.last_login_at = utcnow()
    token = create_access_token(user.id, extra={"username": user.username})
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user


@router.get("/neon/status")
async def neon_auth_status():
    """Connectivity check for Neon Auth (JWKS + base URL)."""
    return await neon_auth_service.status()


@router.post("/neon/exchange")
async def neon_auth_exchange(
    payload: NeonExchangeRequest,
    db: AsyncSession = Depends(get_db),
):
    """Verify a Neon Auth JWT and issue a State House game JWT."""
    return await neon_auth_service.exchange_neon_token(db, payload.neon_access_token)
