from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services import news_service

router = APIRouter(prefix="/news", tags=["news"])


@router.get("")
async def list_news(
    limit: int = Query(default=30, ge=1, le=100),
    category: str | None = Query(default=None),
    state_id: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    items = await news_service.list_news(
        db, limit=limit, category=category, state_id=state_id
    )
    return [
        {
            "id": n.id,
            "headline": n.headline,
            "body": n.body,
            "category": n.category,
            "state_id": n.state_id,
            "published_at": n.published_at,
        }
        for n in items
    ]
