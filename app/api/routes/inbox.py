"""Unified mailbox: personal/company mail + job invites."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services import character_service, employee_service, social_service

router = APIRouter(prefix="/inbox", tags=["inbox"])


class MailSendRequest(BaseModel):
    body: str = Field(min_length=1, max_length=500)
    subject: str | None = Field(default=None, max_length=128)
    to_character_id: int | None = Field(default=None, gt=0)
    to_display_name: str | None = Field(default=None, min_length=3, max_length=64)
    business_id: int | None = Field(default=None, gt=0)


@router.get("")
async def inbox_overview(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    messages = await social_service.list_dms(db, character.id, limit=40, mark_read=False)
    invites = await employee_service.list_incoming_invites(db, character)
    job = await employee_service.my_company_job(db, character)
    unread = sum(1 for m in messages if m["direction"] == "in" and not m["is_read"])
    return {
        "unread_mail": unread,
        "pending_invites": len(invites),
        "messages": messages,
        "invites": invites,
        "company_job": job,
    }


@router.get("/messages")
async def list_messages(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    mark_read: bool = Query(default=True),
):
    character = await character_service.get_character_for_user(db, user)
    return {
        "messages": await social_service.list_dms(
            db, character.id, limit=60, mark_read=mark_read
        )
    }


@router.post("/messages", status_code=201)
async def send_message(
    payload: MailSendRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    msg = await social_service.send_mail(
        db,
        character,
        to_character_id=payload.to_character_id,
        to_display_name=payload.to_display_name,
        body=payload.body,
        subject=payload.subject,
        business_id=payload.business_id,
    )
    return {
        "id": msg.id,
        "subject": msg.subject,
        "body": msg.body,
        "business_id": msg.business_id,
        "posted_at": msg.posted_at,
    }


@router.get("/invites")
async def list_invites(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return {"invites": await employee_service.list_incoming_invites(db, character)}


@router.post("/invites/{invite_id}/accept")
async def accept_invite(
    invite_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await employee_service.accept_invite(db, character, invite_id)


@router.post("/invites/{invite_id}/decline")
async def decline_invite(
    invite_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return await employee_service.decline_invite(db, character, invite_id)


@router.get("/job")
async def my_company_job(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    character = await character_service.get_character_for_user(db, user)
    return {"job": await employee_service.my_company_job(db, character)}
