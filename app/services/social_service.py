import random
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.game_time import utcnow
from app.models.character import Character
from app.models.social import (
    AttackLog,
    DirectMessage,
    Faction,
    FactionMember,
    RelationStatus,
    RelationType,
    SocialRelation,
    WorldEvent,
)
from app.services.character_service import ensure_can_act, ensure_energy
from app.services.health_service import apply_damage
from app.services import notify_service


async def _get_by_name(db: AsyncSession, display_name: str) -> Character:
    result = await db.execute(
        select(Character).where(Character.display_name == display_name)
    )
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="Character not found")
    return target


async def request_friend(
    db: AsyncSession, character: Character, display_name: str
) -> dict:
    ensure_can_act(character)
    target = await _get_by_name(db, display_name)
    if target.id == character.id:
        raise HTTPException(status_code=400, detail="Cannot friend yourself")
    existing = await db.execute(
        select(SocialRelation).where(
            SocialRelation.from_character_id == character.id,
            SocialRelation.to_character_id == target.id,
            SocialRelation.relation_type == RelationType.FRIEND,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Already requested/friends")
    rel = SocialRelation(
        from_character_id=character.id,
        to_character_id=target.id,
        relation_type=RelationType.FRIEND,
        status=RelationStatus.PENDING,
    )
    db.add(rel)
    await notify_service.push(
        db,
        target.id,
        "Friend request",
        body=f"{character.display_name} wants to be friends",
        category="social",
    )
    await db.flush()
    return {"id": rel.id, "status": "pending", "to": target.display_name}


async def accept_friend(
    db: AsyncSession, character: Character, relation_id: int
) -> dict:
    rel = await db.get(SocialRelation, relation_id)
    if (
        rel is None
        or rel.to_character_id != character.id
        or rel.relation_type != RelationType.FRIEND
    ):
        raise HTTPException(status_code=404, detail="Request not found")
    rel.status = RelationStatus.ACTIVE
    # Mirror
    db.add(
        SocialRelation(
            from_character_id=character.id,
            to_character_id=rel.from_character_id,
            relation_type=RelationType.FRIEND,
            status=RelationStatus.ACTIVE,
        )
    )
    await notify_service.push(
        db,
        rel.from_character_id,
        "Friend accepted",
        body=f"{character.display_name} accepted your request",
        category="social",
    )
    await db.flush()
    return {"id": rel.id, "status": "active"}


async def add_enemy(
    db: AsyncSession, character: Character, display_name: str
) -> dict:
    ensure_can_act(character)
    target = await _get_by_name(db, display_name)
    if target.id == character.id:
        raise HTTPException(status_code=400, detail="Cannot enemy yourself")
    rel = SocialRelation(
        from_character_id=character.id,
        to_character_id=target.id,
        relation_type=RelationType.ENEMY,
        status=RelationStatus.ACTIVE,
    )
    db.add(rel)
    await db.flush()
    return {"id": rel.id, "enemy": target.display_name}


async def list_relations(db: AsyncSession, character_id: int) -> dict:
    result = await db.execute(
        select(SocialRelation).where(
            or_(
                SocialRelation.from_character_id == character_id,
                SocialRelation.to_character_id == character_id,
            )
        )
    )
    friends, enemies, pending = [], [], []
    for rel in result.scalars().all():
        other_id = (
            rel.to_character_id
            if rel.from_character_id == character_id
            else rel.from_character_id
        )
        other = await db.get(Character, other_id)
        name = other.display_name if other else str(other_id)
        row = {
            "id": rel.id,
            "display_name": name,
            "status": rel.status.value,
            "direction": (
                "outgoing" if rel.from_character_id == character_id else "incoming"
            ),
        }
        if rel.relation_type == RelationType.FRIEND:
            if rel.status == RelationStatus.PENDING and rel.to_character_id == character_id:
                pending.append(row)
            elif rel.status == RelationStatus.ACTIVE and rel.from_character_id == character_id:
                friends.append(row)
        elif rel.relation_type == RelationType.ENEMY and rel.from_character_id == character_id:
            enemies.append(row)
    return {"friends": friends, "enemies": enemies, "pending": pending}


async def attack(
    db: AsyncSession, attacker: Character, display_name: str
) -> dict:
    ensure_can_act(attacker)
    settings = get_settings()
    ensure_energy(attacker, settings.attack_energy_cost)
    defender = await _get_by_name(db, display_name)
    if defender.id == attacker.id:
        raise HTTPException(status_code=400, detail="Cannot attack yourself")
    if defender.is_jailed or defender.is_hospitalized or defender.is_traveling:
        raise HTTPException(status_code=400, detail="Target is unavailable")

    attacker.energy -= settings.attack_energy_cost
    attacker.last_energy_at = utcnow()

    atk_power = attacker.strength * 0.5 + attacker.speed * 0.3 + attacker.dexterity * 0.2
    def_power = defender.defense * 0.55 + defender.speed * 0.25 + defender.dexterity * 0.2
    # Luck swing
    atk_roll = atk_power * random.uniform(0.85, 1.15)
    def_roll = def_power * random.uniform(0.85, 1.15)
    won = atk_roll >= def_roll
    damage = 0
    stolen = 0.0

    if won:
        damage = apply_damage(
            defender, random.randint(12, 35), condition="beaten"
        )
        stolen = min(defender.cash, round(random.uniform(5, 80), 2))
        defender.cash = round(defender.cash - stolen, 2)
        attacker.cash = round(attacker.cash + stolen, 2)
        attacker.reputation = min(100, attacker.reputation + 1)
        summary = (
            f"{attacker.display_name} beat {defender.display_name} "
            f"(-{damage} HP, stole ${stolen:.2f})"
        )
    else:
        damage = apply_damage(
            attacker, random.randint(8, 22), condition="beaten"
        )
        summary = (
            f"{defender.display_name} defended against {attacker.display_name} "
            f"(attacker -{damage} HP)"
        )
        defender.reputation = min(100, defender.reputation + 1)

    # Auto-enemy both ways
    for a, b in ((attacker.id, defender.id), (defender.id, attacker.id)):
        exists = await db.execute(
            select(SocialRelation).where(
                SocialRelation.from_character_id == a,
                SocialRelation.to_character_id == b,
                SocialRelation.relation_type == RelationType.ENEMY,
            )
        )
        if exists.scalar_one_or_none() is None:
            db.add(
                SocialRelation(
                    from_character_id=a,
                    to_character_id=b,
                    relation_type=RelationType.ENEMY,
                    status=RelationStatus.ACTIVE,
                )
            )

    log = AttackLog(
        attacker_id=attacker.id,
        defender_id=defender.id,
        attacker_won=won,
        damage=damage,
        cash_stolen=stolen if won else 0.0,
        summary=summary,
        fought_at=utcnow(),
    )
    db.add(log)
    await notify_service.push(
        db, defender.id, "You were attacked", body=summary, category="combat"
    )
    await notify_service.push(
        db, attacker.id, "Attack result", body=summary, category="combat"
    )
    await db.flush()
    return {
        "won": won,
        "damage": damage,
        "cash_stolen": stolen if won else 0.0,
        "summary": summary,
        "attacker_health": attacker.health,
        "defender_health": defender.health,
        "energy": attacker.energy,
    }


async def send_dm(
    db: AsyncSession, character: Character, to_display_name: str, body: str
) -> DirectMessage:
    ensure_can_act(character)
    target = await _get_by_name(db, to_display_name)
    if target.id == character.id:
        raise HTTPException(status_code=400, detail="Cannot message yourself")
    msg = DirectMessage(
        from_character_id=character.id,
        to_character_id=target.id,
        body=body.strip()[:500],
        is_read=False,
        posted_at=utcnow(),
    )
    db.add(msg)
    await notify_service.push(
        db,
        target.id,
        f"DM from {character.display_name}",
        body=body[:80],
        category="dm",
    )
    await db.flush()
    await db.refresh(msg)
    return msg


async def list_dms(
    db: AsyncSession, character_id: int, *, with_name: str | None = None, limit: int = 50
) -> list[dict]:
    stmt = (
        select(DirectMessage)
        .where(
            or_(
                DirectMessage.from_character_id == character_id,
                DirectMessage.to_character_id == character_id,
            )
        )
        .order_by(DirectMessage.id.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = []
    for m in result.scalars().all():
        if with_name:
            other_id = (
                m.to_character_id
                if m.from_character_id == character_id
                else m.from_character_id
            )
            other = await db.get(Character, other_id)
            if not other or other.display_name != with_name:
                continue
        fr = await db.get(Character, m.from_character_id)
        to = await db.get(Character, m.to_character_id)
        rows.append(
            {
                "id": m.id,
                "from": fr.display_name if fr else m.from_character_id,
                "to": to.display_name if to else m.to_character_id,
                "body": m.body,
                "is_read": m.is_read,
                "posted_at": m.posted_at,
            }
        )
        if m.to_character_id == character_id and not m.is_read:
            m.is_read = True
    await db.flush()
    return rows


async def create_faction(
    db: AsyncSession, character: Character, name: str, tag: str, description: str | None
) -> Faction:
    ensure_can_act(character)
    if character.faction_id:
        raise HTTPException(status_code=400, detail="Already in a faction")
    if len(tag) < 2 or len(tag) > 8:
        raise HTTPException(status_code=400, detail="Tag must be 2–8 chars")
    faction = Faction(
        name=name.strip()[:64],
        tag=tag.strip().upper()[:8],
        description=description,
        leader_id=character.id,
        treasury=0.0,
    )
    db.add(faction)
    await db.flush()
    db.add(
        FactionMember(
            faction_id=faction.id,
            character_id=character.id,
            rank="leader",
            joined_at=utcnow(),
        )
    )
    character.faction_id = faction.id
    await db.flush()
    await db.refresh(faction)
    return faction


async def join_faction(
    db: AsyncSession, character: Character, faction_id: int
) -> dict:
    ensure_can_act(character)
    if character.faction_id:
        raise HTTPException(status_code=400, detail="Already in a faction")
    faction = await db.get(Faction, faction_id)
    if faction is None:
        raise HTTPException(status_code=404, detail="Faction not found")
    db.add(
        FactionMember(
            faction_id=faction.id,
            character_id=character.id,
            rank="member",
            joined_at=utcnow(),
        )
    )
    character.faction_id = faction.id
    await db.flush()
    return {"faction_id": faction.id, "name": faction.name, "tag": faction.tag}


async def list_factions(db: AsyncSession) -> list[dict]:
    result = await db.execute(select(Faction).order_by(Faction.id))
    out = []
    for f in result.scalars().all():
        count = await db.execute(
            select(FactionMember).where(FactionMember.faction_id == f.id)
        )
        members = list(count.scalars().all())
        out.append(
            {
                "id": f.id,
                "name": f.name,
                "tag": f.tag,
                "description": f.description,
                "leader_id": f.leader_id,
                "treasury": f.treasury,
                "members": len(members),
            }
        )
    return out


async def list_active_events(db: AsyncSession) -> list[dict]:
    now = utcnow()
    result = await db.execute(
        select(WorldEvent).where(
            WorldEvent.is_active.is_(True),
            WorldEvent.starts_at <= now,
            WorldEvent.ends_at >= now,
        )
    )
    return [
        {
            "id": e.id,
            "title": e.title,
            "summary": e.summary,
            "effect_key": e.effect_key,
            "effect_value": e.effect_value,
            "state_id": e.state_id,
            "starts_at": e.starts_at,
            "ends_at": e.ends_at,
        }
        for e in result.scalars().all()
    ]


async def seed_world_events(db: AsyncSession) -> int:
    result = await db.execute(select(WorldEvent.id).limit(1))
    if result.scalar_one_or_none() is not None:
        return 0
    now = utcnow()
    events = [
        WorldEvent(
            title="National job fair",
            summary="Employers across United Amir pay 15% more this week.",
            effect_key="job_pay_boost",
            effect_value=1.15,
            state_id=None,
            starts_at=now,
            ends_at=now + timedelta(days=7),
            is_active=True,
        ),
        WorldEvent(
            title="Gym sponsorship week",
            summary="Training gains boosted nationwide.",
            effect_key="gym_boost",
            effect_value=1.25,
            state_id=None,
            starts_at=now,
            ends_at=now + timedelta(days=5),
            is_active=True,
        ),
    ]
    for e in events:
        db.add(e)
    await db.flush()
    return len(events)
