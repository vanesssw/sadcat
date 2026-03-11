#!/usr/bin/env python3
import asyncio
import logging
import httpx
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import os

# Настройки
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")

# Включаем логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Команда /start"""
    await message.answer(
        "🎯 **Добро пожаловать в SADCAT Verification Bot!**\n\n"
        "📋 **Доступные команды:**\n"
        "/verify - Получить ссылку для верификации\n"
        "/help - Помощь\n\n"
        "💡 **Как работает:**\n"
        "1. Введите команду /verify\n"
        "2. Бот пришлет вам уникальную ссылку\n"
        "3. Перейдите по ссылке и решите капчу\n"
        "4. Получите +10 поинтов!\n\n"
        "🚀 **Начните с команды /verify**"
    )

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    """Команда /help"""
    await message.answer(
        "📖 **Справка по боту:**\n\n"
        "**Команды:**\n"
        "/verify - Получить ссылку для верификации\n"
        "/start - Начать работу\n"
        "/help - Эта справка\n\n"
        "**Процесс верификации:**\n"
        "1️⃣ Вводите команду /verify\n"
        "2️⃣ Получаете уникальную ссылку\n"
        "3️⃣ Переходите по ссылке\n"
        "4️⃣ Решаете Yandex SmartCaptcha\n"
        "5️⃣ Получаете +10 поинтов\n"
        "6️⃣ Уведомление приходит в Telegram\n\n"
        "❓ **Вопросы?** @iter_tea"
    )


@dp.message(Command("verify"))
async def cmd_verify(message: types.Message):
    """Команда /verify - генерирует ссылку для верификации"""
    try:
        user_id = message.from_user.id
        username = message.from_user.username or f"user_{user_id}"
        
        logger.info(f"Received /verify command from user {username} (ID: {user_id})")

        processing_msg = await message.answer("генерация")
        
        api_url = f"{BACKEND_URL}/verify/generate-state"
        logger.info(f"Calling API: {api_url}")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(
                    api_url,
                    json={
                        "user_id": user_id,
                        "username": username
                    }
                )
                logger.info(f"API Response status: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    verify_url = data["verify_url"]
                    logger.info(f"Generated verify_url: {verify_url}")

                    await processing_msg.edit_text(
                        f"ссылка**\n\n"
                        f"{verify_url}\n\n"
                    )

                    logger.info(f"Successfully generated link for user {username} (ID: {user_id})")

                else:
                    logger.error(f"API Error - Status: {response.status_code}, Response: {response.text}")
                    await processing_msg.edit_text(
                        "ошибка API"
                    )
                    
            except httpx.RequestError as e:
                logger.error(f"HTTP Request Error: {e}")
                await processing_msg.edit_text(
                    "ошибка подключения"
                )
                
    except Exception as e:
        logger.error(f"General error in cmd_verify: {e}")
        await message.answer(
            "ошибка"
        )

@dp.message()
async def echo_message(message: types.Message):
    """Ответ на другие сообщения"""
    if message.text:
        await message.answer(
            "🤔 **Неизвестная команда**\n\n"
            "Доступные команды:\n"
            "/verify - Получить ссылку для верификации\n"
            "/help - Помощь\n"
            "/start - Начать работу"
        )

async def main():
    """Запуск бота"""
    logger.info("🚀 Starting SADCAT Verification Bot...")
    
    # Проверяем токен
    if BOT_TOKEN == "YOUR_BOT_TOKEN":
        logger.error("❌ BOT_TOKEN не установлен! Установите переменную окружения.")
        return
    
    try:
        # Запускаем бота
        await dp.start_polling(bot)
        logger.info("✅ Bot started successfully!")
        
    except Exception as e:
        logger.error(f"❌ Failed to start bot: {e}")

if __name__ == "__main__":
    asyncio.run(main())
