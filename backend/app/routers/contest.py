from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import ContestInfo

router = APIRouter(prefix="/api/contest", tags=["contest"])


class ContestInfoOut(BaseModel):
    id: int
    title: str
    description: Optional[str]
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    prize_pool: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("", response_model=List[ContestInfoOut])
async def get_contest_info(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ContestInfo).where(ContestInfo.is_active == True).order_by(ContestInfo.id)
    )
    return result.scalars().all()
