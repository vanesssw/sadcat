from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import LeaderboardEntry, ParseLog

router = APIRouter(prefix="/api/leaderboard", tags=["leaderboard"])


class LeaderboardEntryOut(BaseModel):
    id: int
    rank: int
    username: str
    display_name: Optional[str]
    score: int
    avatar_b64: Optional[str]
    updated_at: datetime

    class Config:
        from_attributes = True


class LeaderboardResponse(BaseModel):
    entries: List[LeaderboardEntryOut]
    last_updated: Optional[datetime]
    total: int


class ParseLogOut(BaseModel):
    id: int
    parsed_at: datetime
    status: str
    entries_count: int
    error_msg: Optional[str]

    class Config:
        from_attributes = True


@router.get("", response_model=LeaderboardResponse)
async def get_leaderboard(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(LeaderboardEntry).order_by(LeaderboardEntry.rank)
    )
    entries = result.scalars().all()

    last_updated = None
    if entries:
        last_updated = max(e.updated_at for e in entries)

    return LeaderboardResponse(
        entries=entries,
        last_updated=last_updated,
        total=len(entries),
    )


@router.get("/logs", response_model=List[ParseLogOut])
async def get_parse_logs(limit: int = 20, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ParseLog).order_by(ParseLog.parsed_at.desc()).limit(limit)
    )
    return result.scalars().all()
