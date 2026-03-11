import os
import logging
from fastapi import FastAPI, Request
from telegram import Update
from bot import application, bot_instance

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Создание FastAPI приложения
app = FastAPI(title="Coffee Order Bot")


@app.get("/")
async def health_check():
    """Health check endpoint для мониторинга"""
    return {
        "status": "ok",
        "bot": "Coffee Order Bot",
        "version": "2.0"
    }


@app.get("/health")
async def health():
    """Дополнительный health check"""
    return {"status": "healthy"}


@app.post("/telegram")
async def telegram_webhook(request: Request):
    """Endpoint для получения обновлений от Telegram"""
    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
        return {"ok": True}
    except Exception as e:
        logger.error(f"Ошибка обработки webhook: {e}")
        return {"ok": False, "error": str(e)}


@app.on_event("startup")
async def on_startup():
    """Инициализация при запуске"""
    # Используем встроенную переменную Koyeb или fallback на WEBHOOK_URL
    koyeb_url = os.getenv('KOYEB_APP_URL')
    webhook_base = os.getenv('WEBHOOK_URL')

    if koyeb_url:
        # Koyeb автоматически предоставляет домен без https://
        webhook_url = f"https://{koyeb_url}"
        logger.info(f"📡 Используется Koyeb URL: {koyeb_url}")
    elif webhook_base:
        webhook_url = webhook_base
        logger.info(f"📡 Используется WEBHOOK_URL: {webhook_url}")
    else:
        logger.error("❌ Ни KOYEB_APP_URL, ни WEBHOOK_URL не установлены")
        return

    # Инициализация application (ВАЖНО: сначала initialize, потом start)
    await application.initialize()
    await application.start()

    # Установка webhook
    full_webhook_url = f"{webhook_url}/telegram"
    await application.bot.set_webhook(
        url=full_webhook_url,
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )

    logger.info(f"✅ Webhook установлен: {full_webhook_url}")
    logger.info(f"✅ Бот запущен и готов к работе")

    # Инициализация класса бота
    if bot_instance:
        logger.info("✅ CoffeeBot инициализирован")


@app.on_event("shutdown")
async def on_shutdown():
    """Очистка при остановке"""
    logger.info("Остановка бота...")
    await application.stop()
    await application.shutdown()
    logger.info("Бот остановлен")


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)