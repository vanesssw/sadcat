from datetime import datetime, timedelta
from typing import Optional
import secrets
import hashlib
import logging

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

from app.database import AsyncSessionLocal
from app.models import VerificationState, LeaderboardEntry
import httpx

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/verify", tags=["verification"])


class VerifyRequest(BaseModel):
    smart_token: str
    state: str


class VerifyResponse(BaseModel):
    success: bool
    message: str


class GenerateStateRequest(BaseModel):
    user_id: int
    username: Optional[str] = None


class GenerateStateResponse(BaseModel):
    state: str
    verify_url: str


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


@router.post("/generate-state", response_model=GenerateStateResponse)
async def generate_verification_state(request: GenerateStateRequest):
    """Генерирует state для верификации через капчу"""
    # Генерируем уникальный state
    state = secrets.token_urlsafe(32)
    
    # URL для верификации
    protocol = "https" if settings.domain != "localhost" else "http"
    verify_url = f"{protocol}://{settings.domain}/captcha?state={state}"
    
    # Сохраняем в БД
    async with AsyncSessionLocal() as session:
        # Удаляем старые не верифицированные состояния для этого пользователя
        await session.execute(
            delete(VerificationState)
            .where(
                VerificationState.user_id == request.user_id,
                VerificationState.is_verified == False
            )
        )
        
        # Создаем новое состояние
        verification_state = VerificationState(
            state=state,
            user_id=request.user_id,
            username=request.username,
            expires_at=datetime.utcnow() + timedelta(hours=1)  # Истекает через час
        )
        
        session.add(verification_state)
        await session.commit()
    
    return GenerateStateResponse(
        state=state,
        verify_url=verify_url
    )


@router.post("/check", response_model=VerifyResponse)
async def verify_captcha(request: VerifyRequest, http_request: Request):
    """Проверяет SmartCaptcha токен и отмечает state как верифицированный"""

    # Prefer client IP from proxy headers (nginx) for SmartCaptcha validation
    xff = http_request.headers.get("x-forwarded-for")
    if xff:
        client_ip = xff.split(",")[0].strip()
    else:
        client_ip = http_request.headers.get("x-real-ip") or (
            http_request.client.host if http_request.client else ""
        )
    
    async with AsyncSessionLocal() as session:
        # Ищем state в БД
        result = await session.execute(
            select(VerificationState)
            .where(VerificationState.state == request.state)
        )
        verification_state = result.scalar_one_or_none()
        
        if not verification_state:
            return VerifyResponse(
                success=False,
                message="Invalid verification state"
            )
        
        # Проверяем, не истек ли срок действия
        if verification_state.expires_at < datetime.utcnow():
            return VerifyResponse(
                success=False,
                message="Verification state expired"
            )
        
        # Проверяем, не верифицирован ли уже
        if verification_state.is_verified:
            return VerifyResponse(
                success=False,
                message="Already verified"
            )
        
        # Проверяем SmartCaptcha токен
        if not await verify_smart_captcha_token(request.smart_token, client_ip=client_ip):
            return VerifyResponse(
                success=False,
                message="Captcha verification failed"
            )
        
        # Отмечаем как верифицированный
        verification_state.is_verified = True
        verification_state.verified_at = datetime.utcnow()
        await session.commit()
        
        # Начисляем поинты пользователю
        if not verification_state.points_awarded:
            await award_points_to_user(verification_state.user_id, verification_state.username, session)
            
            # Обновляем статус начисления поинтов
            verification_state.points_awarded = True
            await session.commit()
            
            # Отправляем сообщение в Telegram пользователю
            await send_telegram_notification(verification_state.user_id, verification_state.username)
        
        return VerifyResponse(
            success=True,
            message="Verification successful"
        )


async def verify_smart_captcha_token(token: str, client_ip: str = "") -> bool:
    """Проверяет токен Yandex SmartCaptcha"""
    if not settings.yandex_smartcaptcha_server_key:
        logger.error("Yandex SmartCaptcha server key not configured")
        return False
    
    try:
        logger.info("SmartCaptcha validate: client_ip=%s", client_ip)
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://smartcaptcha.yandexcloud.net/validate",
                params={
                    "secret": settings.yandex_smartcaptcha_server_key,
                    "token": token,
                    "ip": client_ip,
                },
                timeout=1.0,
            )
            
            if response.status_code == 200:
                result = response.json()
                status_value = result.get("status")
                if status_value != "ok":
                    logger.warning("SmartCaptcha validation failed: status=%s response=%s", status_value, result)
                return status_value == "ok"
            else:
                body_preview = response.text[:500] if response.text else ""
                logger.error(
                    "SmartCaptcha API error: status=%s body=%s",
                    response.status_code,
                    body_preview,
                )
                return False
                
    except Exception as e:
        logger.error(f"Error verifying SmartCaptcha: {e}")
        return False


@router.get("/status/{state}")
async def get_verification_status(state: str):
    """Проверяет статус верификации для state"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(VerificationState)
            .where(VerificationState.state == state)
        )
        verification_state = result.scalar_one_or_none()
        
        if not verification_state:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Verification state not found"
            )
        
        return {
            "state": state,
            "is_verified": verification_state.is_verified,
            "expires_at": verification_state.expires_at,
            "created_at": verification_state.created_at,
            "verified_at": verification_state.verified_at
        }


async def award_points_to_user(user_id: int, username: str, session: AsyncSession):
    """Начисляет 10 поинтов пользователю за прохождение верификации"""
    try:
        # Ищем пользователя в leaderboard
        result = await session.execute(
            select(LeaderboardEntry)
            .where(LeaderboardEntry.username == username)
        )
        user_entry = result.scalar_one_or_none()
        
        if user_entry:
            # Обновляем существующего пользователя
            user_entry.score += 10
            user_entry.updated_at = datetime.utcnow()
            logger.info(f"Added 10 points to existing user {username}")
        else:
            # Создаем новую запись для пользователя
            new_entry = LeaderboardEntry(
                rank=0,  # Будет обновлено при следующем парсинге
                username=username,
                display_name=username,
                score=10,
                updated_at=datetime.utcnow()
            )
            session.add(new_entry)
            logger.info(f"Created new leaderboard entry for user {username} with 10 points")
        
        await session.commit()
        
        # Здесь можно добавить отправку уведомления в Telegram
        # await send_verification_success_notification(user_id, username)
        
    except Exception as e:
        logger.error(f"Error awarding points to user {username}: {e}")
        raise


async def send_telegram_notification(user_id: int, username: str):
    """Отправляет уведомление в Telegram о успешной верификации"""
    try:
        from app.telegram_parser import telegram_parser
        
        if not telegram_parser.client or not telegram_parser.client.is_connected:
            logger.error("Telegram client not connected for notification")
            return
        
        message = (
            f"🎉 **Верификация пройдена успешно!**\n\n"
            f"✅ +10 поинтов начислено\n"
            f"👤 Пользователь: @{username}\n"
            f"📊 Проверьте свой рейтинг в /leaderboard"
        )
        
        await telegram_parser.client.send_message(user_id, message)
        logger.info(f"Sent verification success notification to user {username} (ID: {user_id})")
        
    except Exception as e:
        logger.error(f"Error sending Telegram notification to user {user_id}: {e}")
        # Не прерываем процесс, если сообщение не отправилось
