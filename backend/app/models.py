from datetime import datetime
from typing import Optional
from sqlalchemy import Integer, String, BigInteger, Boolean, Text, DateTime, JSON, Float
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class WheelSpin(Base):
    __tablename__ = "wheel_spins"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # ok / failed
    error_msg: Mapped[Optional[str]] = mapped_column(Text)

    # Wheel config snapshot
    wheel_version_hash: Mapped[Optional[str]] = mapped_column(String(64))   # sha256 of participants JSON
    total_tickets: Mapped[Optional[int]] = mapped_column(Integer)
    participants_json: Mapped[Optional[dict]] = mapped_column(JSON)          # [{name, tickets, ...}]

    # Draw result
    winning_ticket: Mapped[Optional[int]] = mapped_column(Integer)
    winner_username: Mapped[Optional[str]] = mapped_column(String(255))
    winner_name: Mapped[Optional[str]] = mapped_column(String(255))
    winner_avatar: Mapped[Optional[str]] = mapped_column(Text)               # base64
    winner_color: Mapped[Optional[str]] = mapped_column(String(16))
    winner_tickets: Mapped[Optional[int]] = mapped_column(Integer)
    winner_chance: Mapped[Optional[float]] = mapped_column(Float)
    winner_range_start: Mapped[Optional[int]] = mapped_column(Integer)
    winner_range_end: Mapped[Optional[int]] = mapped_column(Integer)

    # random.org proof
    rand_serial: Mapped[Optional[int]] = mapped_column(Integer)
    rand_signature: Mapped[Optional[str]] = mapped_column(Text)
    rand_random: Mapped[Optional[dict]] = mapped_column(JSON)                # object from random.org
    verify_url: Mapped[Optional[str]] = mapped_column(Text)


class LeaderboardEntry(Base):
    __tablename__ = "leaderboard"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(255))
    score: Mapped[int] = mapped_column(BigInteger, default=0)
    avatar_b64: Mapped[Optional[str]] = mapped_column(Text)
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )


class ContestInfo(Base):
    __tablename__ = "contest_info"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    prize_pool: Mapped[Optional[str]] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )


class RefLeaderboardEntry(Base):
    __tablename__ = "ref_leaderboard"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(255))
    refs: Mapped[int] = mapped_column(Integer, default=0)
    avatar_b64: Mapped[Optional[str]] = mapped_column(Text)
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )


class ParseLog(Base):
    __tablename__ = "parse_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parsed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    entries_count: Mapped[int] = mapped_column(Integer, default=0)
    error_msg: Mapped[Optional[str]] = mapped_column(Text)


class GambleCall(Base):
    __tablename__ = "gamble_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    msg_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    msg_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    msg_text: Mapped[Optional[str]] = mapped_column(Text)
    ca_address: Mapped[str] = mapped_column(String(64), nullable=False)
    pair_address: Mapped[Optional[str]] = mapped_column(String(128))
    token_name: Mapped[Optional[str]] = mapped_column(String(255))
    token_symbol: Mapped[Optional[str]] = mapped_column(String(64))
    price_at_call: Mapped[Optional[float]] = mapped_column(Float)
    mcap_at_call: Mapped[Optional[float]] = mapped_column(Float)
    current_price: Mapped[Optional[float]] = mapped_column(Float)
    current_mcap: Mapped[Optional[float]] = mapped_column(Float)
    ath_x: Mapped[float] = mapped_column(Float, default=0.0)
    min_x: Mapped[float] = mapped_column(Float, default=1.0)
    ath_atl_final: Mapped[bool] = mapped_column(Boolean, default=False)
    volume_24h: Mapped[Optional[float]] = mapped_column(Float)
    liquidity_usd: Mapped[Optional[float]] = mapped_column(Float)
    price_change_24h: Mapped[Optional[float]] = mapped_column(Float)
    dex_url: Mapped[Optional[str]] = mapped_column(Text)
    is_live: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
