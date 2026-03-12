import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Optional
import secrets
import hashlib
import logging

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
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
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1)  # Истекает через час
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
            # State not in local DB — try Stream Bot captcha system
            return await _verify_via_stream_bot(request.state, request.smart_token, client_ip)
        
        # Проверяем, не истек ли срок действия
        if verification_state.expires_at < datetime.now(timezone.utc):
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
        verification_state.verified_at = datetime.now(timezone.utc)
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


async def _verify_via_stream_bot(state: str, smart_token: str, client_ip: str) -> VerifyResponse:
    """Verify captcha for states created by the Stream Bot (not in local DB)."""
    if not settings.stream_bot_token:
        return VerifyResponse(success=False, message="Invalid verification state")

    headers = {"Authorization": f"Bearer {settings.stream_bot_token}"}
    base_url = settings.stream_bot_url

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # 1. Check that state exists in stream bot
            status_resp = await client.get(
                f"{base_url}/api/captcha/status/{state}",
                headers=headers,
            )
            if status_resp.status_code != 200:
                return VerifyResponse(success=False, message="Invalid verification state")
            status_data = status_resp.json()
            if status_data.get("captcha_passed"):
                return VerifyResponse(success=False, message="Already verified")

            # 2. Verify Yandex SmartCaptcha token
            captcha_ok = await verify_smart_captcha_token(smart_token, client_ip=client_ip)

            # 3. Send callback to stream bot
            callback_resp = await client.post(
                f"{base_url}/api/captcha/callback",
                headers=headers,
                json={
                    "state": state,
                    "payload": {
                        "captcha_passed": captcha_ok,
                        "captcha_type": "smartcaptcha",
                        "fingerprint": {"metadata": {"source": "sadcat-backend"}},
                        "metadata": {"source": "sadcat-backend"},
                    },
                },
            )
            if callback_resp.status_code not in (200, 201):
                logger.error("Stream bot callback failed: %s %s", callback_resp.status_code, callback_resp.text[:200])

    except Exception as exc:
        logger.error("Stream bot verify error: %s", exc)
        return VerifyResponse(success=False, message="Connection error to server")

    if not captcha_ok:
        return VerifyResponse(success=False, message="Captcha verification failed")

    return VerifyResponse(success=True, message="Verification successful")


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


@router.get("/code-stream")
async def code_stream(state: str, request: Request):
    """SSE stream: polls Stream Bot code info every 0.5s for users on captcha page."""
    if not settings.stream_bot_token:
        return StreamingResponse(iter(["data: {}\n\n"]), media_type="text/event-stream")

    headers = {"Authorization": f"Bearer {settings.stream_bot_token}"}
    base_url = settings.stream_bot_url

    async def event_generator():
        code_id = None
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    f"{base_url}/api/captcha/status/{state}",
                    headers=headers,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    code_id = data.get("code_id") or data.get("codeId")
        except Exception as exc:
            logger.debug("code-stream: cannot get captcha status: %s", exc)

        if not code_id:
            yield "data: {}\n\n"
            return

        deadline = asyncio.get_event_loop().time() + 600  # 10 min max
        async with httpx.AsyncClient(timeout=5) as client:
            while asyncio.get_event_loop().time() < deadline:
                if await request.is_disconnected():
                    break
                try:
                    r = await client.get(
                        f"{base_url}/api/codes/info",
                        params={"code": code_id},
                        headers=headers,
                    )
                    if r.status_code == 200:
                        yield f"data: {r.text}\n\n"
                except Exception as exc:
                    logger.debug("code-stream poll error: %s", exc)
                await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
            user_entry.updated_at = datetime.now(timezone.utc)
            logger.info(f"Added 10 points to existing user {username}")
        else:
            # Создаем новую запись для пользователя
            new_entry = LeaderboardEntry(
                rank=0,  # Будет обновлено при следующем парсинге
                username=username,
                display_name=username,
                score=10,
                updated_at=datetime.now(timezone.utc)
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
