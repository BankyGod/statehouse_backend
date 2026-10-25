from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.game_time import utcnow
from app.models.legislation import NewsItem


async def publish(
    db: AsyncSession,
    headline: str,
    body: str,
    *,
    category: str = "general",
    state_id: int | None = None,
) -> NewsItem:
    item = NewsItem(
        headline=headline[:200],
        body=body,
        category=category,
        state_id=state_id,
        published_at=utcnow(),
    )
    db.add(item)
    await db.flush()
    return item


async def list_news(
    db: AsyncSession,
    *,
    limit: int = 30,
    category: str | None = None,
    state_id: int | None = None,
) -> list[NewsItem]:
    stmt = select(NewsItem).order_by(NewsItem.published_at.desc()).limit(min(limit, 100))
    if category:
        stmt = stmt.where(NewsItem.category == category)
    if state_id is not None:
        stmt = stmt.where(
            (NewsItem.state_id == state_id) | (NewsItem.state_id.is_(None))
        )
    result = await db.execute(stmt)
    return list(result.scalars().all())
