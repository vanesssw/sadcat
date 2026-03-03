from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import GambleCall

router = APIRouter(prefix="/api/gamble", tags=["gamble"])


class GambleCallOut(BaseModel):
    id: int
    msg_id: int
    msg_date: datetime
    msg_text: Optional[str]
    ca_address: str
    pair_address: Optional[str]
    token_name: Optional[str]
    token_symbol: Optional[str]
    price_at_call: Optional[float]
    mcap_at_call: Optional[float]
    current_price: Optional[float]
    current_mcap: Optional[float]
    ath_x: float
    min_x: float
    volume_24h: Optional[float]
    liquidity_usd: Optional[float]
    price_change_24h: Optional[float]
    dex_url: Optional[str]
    is_live: bool
    updated_at: datetime

    class Config:
        from_attributes = True


class GambleResponse(BaseModel):
    live: List[GambleCallOut]
    old: List[GambleCallOut]
    total: int
    last_updated: Optional[datetime]


@router.get("", response_model=GambleResponse)
async def get_gamble_calls(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(GambleCall).order_by(GambleCall.msg_date.desc())
    )
    calls = result.scalars().all()

    live = [c for c in calls if c.is_live]
    old = [c for c in calls if not c.is_live]

    last_updated = None
    if calls:
        last_updated = max(c.updated_at for c in calls)

    return GambleResponse(
        live=live,
        old=old,
        total=len(calls),
        last_updated=last_updated,
    )
