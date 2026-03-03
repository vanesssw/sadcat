from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import RefLeaderboardEntry

router = APIRouter(prefix="/api/refleaderboard", tags=["refleaderboard"])


class RefLeaderboardEntryOut(BaseModel):
    id: int
    rank: int
    username: str
    display_name: Optional[str]
    refs: int
    avatar_b64: Optional[str]
    updated_at: datetime

    class Config:
        from_attributes = True


class RefLeaderboardResponse(BaseModel):
    entries: List[RefLeaderboardEntryOut]
    last_updated: Optional[datetime]
    total: int


@router.get("", response_model=RefLeaderboardResponse)
async def get_ref_leaderboard(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(RefLeaderboardEntry).order_by(RefLeaderboardEntry.rank)
    )
    entries = result.scalars().all()

    last_updated = None
    if entries:
        last_updated = max(e.updated_at for e in entries)

    return RefLeaderboardResponse(
        entries=entries,
        last_updated=last_updated,
        total=len(entries),
    )
