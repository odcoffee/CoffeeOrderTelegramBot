# ☕ Coffee Order Telegram Bot

Telegram бот для управления заказами кофе с интеграцией Google Sheets.

## 🌟 Возможности

- 📝 Управление заказами (создание, редактирование, просмотр)
- 📍 Управление адресами доставки
- 📦 Учет товаров и остатков на складе
- 💰 Учет расходов и кассы менеджеров
- 👥 Разграничение прав доступа (owner, manager, developer)
- 📊 Интеграция с Google Sheets для хранения данных
- 🚀 **FastAPI webhook** для стабильной работы 24/7
- 🔄 Поддержка polling для локальной разработки

## 🏗️ Архитектура

- **bot.py** - основная логика бота и обработчики
- **main.py** - FastAPI сервер для webhook режима
- **Webhook режим** (продакшн) - используется на Koyeb/Render/Railway
- **Polling режим** (разработка) - для локального тестирования

## 🚀 Быстрый старт

### Локальная разработка

1. Клонируйте репозиторий:
```bash
git clone https://github.com/yourusername/CoffeeOrderTelegramBot.git
cd CoffeeOrderTelegramBot
```

2. Установите зависимости:
```bash
pip install -r requirements.txt
```

3. Создайте `.env` файл (скопируйте из `.env.example`):
```bash
cp .env.example .env
```

4. Заполните `.env` вашими данными:
```env
TELEGRAM_BOT_TOKEN=ваш_токен
GOOGLE_SHEET_ID=id_таблицы
GOOGLE_CREDENTIALS={"type":"service_account",...}
BOT_USERS={"ваш_telegram_id":"owner"}
USE_WEBHOOK=false
```

5. Запустите бота:
```bash
python bot.py
```

### Деплой на Koyeb (бесплатно, 24/7)

📖 Подробная инструкция: [DEPLOY_GUIDE.md](DEPLOY_GUIDE.md)

⚡ Быстрый старт: [QUICK_START.md](QUICK_START.md)

**Кратко:**
1. Загрузите код на GitHub
2. Создайте приложение на [Koyeb](https://koyeb.com)
3. Подключите GitHub репозиторий
4. Добавьте переменные окружения
5. Деплой!

## 📋 Требования

- Python 3.11+
- Telegram Bot Token
- Google Sheets API credentials
- Google Таблица с правами для service account

## 🔧 Конфигурация

### Переменные окружения

| Переменная | Описание | Обязательна |
|------------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Токен от @BotFather | ✅ |
| `GOOGLE_SHEET_ID` | ID Google таблицы | ✅ |
| `GOOGLE_CREDENTIALS` | JSON credentials service account | ✅ |
| `BOT_USERS` | JSON со списком пользователей и их ролями | ✅ |
| `WEBHOOK_URL` | URL для webhook (обязателен для продакшн) | ✅ (для webhook) |
| `PORT` | Порт для webhook | ❌ (default: 8080) |
| `USE_WEBHOOK` | `false` для polling в локальной разработке | ❌ (webhook по умолчанию) |

### Роли пользователей

- **developer**: Полный доступ ко всем функциям
- **owner**: Доступ ко всем функциям кроме технических
- **manager**: Базовый доступ для работы с заказами

## 📊 Структура Google Sheets

Бот автоматически создаст следующие листы:

- **Адреса**: Точки доставки
- **Товары**: Каталог продукции
- **Заказы**: История заказов
- **Расходы**: Учет расходов
- **Остатки**: Складской учет
- **Касса менеджеров**: Учет наличных
- **Сдача кассы**: История сдачи денег

## 🛠️ Технологии

- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) - Telegram Bot API
- [FastAPI](https://fastapi.tiangolo.com/) - Современный веб-фреймворк для webhook
- [uvicorn](https://www.uvicorn.org/) - ASGI сервер
- [gspread](https://github.com/burnash/gspread) - Google Sheets API
- [google-auth](https://github.com/googleapis/google-auth-library-python) - Google Authentication

## 📝 Лицензия

MIT

## 🤝 Контрибьюция

Pull requests приветствуются!

## 📞 Поддержка

Если возникли вопросы:
1. Проверьте [DEPLOY_GUIDE.md](DEPLOY_GUIDE.md)
2. Посмотрите Issues
3. Создайте новый Issue

## ⚠️ Важно

- Никогда не коммитьте `.env` файл
- Храните токены и credentials в безопасности
- Используйте переменные окружения платформы для продакшн деплоя
