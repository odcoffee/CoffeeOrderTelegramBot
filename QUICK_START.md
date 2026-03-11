# 🚀 Быстрый старт - Деплой на Koyeb

## 📦 Что изменилось в коде

Бот теперь использует **FastAPI + Webhook** для стабильной работы 24/7:
- **FastAPI сервер** - надежный веб-сервер для обработки webhook
- **Health check endpoint** - для мониторинга Koyeb
- **Автоматическая установка webhook** при запуске
- **Поддержка polling** для локальной разработки

---

## ⚡ Быстрый деплой за 5 минут

### 1️⃣ Загрузите файлы на GitHub
```bash
git add .
git commit -m "Add FastAPI webhook support"
git push
```

### 2️⃣ Создайте приложение на Koyeb
- Зайдите на [koyeb.com](https://www.koyeb.com)
- Create App → GitHub → выберите репозиторий
- Builder: **Docker**
- Port: **8080**
- Health check path: `/health`

### 3️⃣ Добавьте переменные окружения

```bash
TELEGRAM_BOT_TOKEN=ваш_токен
GOOGLE_SHEET_ID=id_таблицы
GOOGLE_CREDENTIALS={"type":"service_account",...}  # весь JSON
BOT_USERS={"ваш_telegram_id":"owner"}
WEBHOOK_URL=https://your-app-name.koyeb.app
PORT=8080
```

**ВАЖНО**: `WEBHOOK_URL` нужно добавить сразу, иначе бот не сможет установить webhook.

### 4️⃣ Деплой
Нажмите **Deploy** и дождитесь завершения (2-3 минуты).

### 5️⃣ Проверка
1. Откройте `https://your-app-name.koyeb.app/` - должно показать `{"status":"ok"}`
2. Напишите боту `/start` - он должен ответить

### ✅ Готово!
Бот работает 24/7 на webhook!

---

## 🔍 Проверка webhook

Откройте в браузере:
```
https://api.telegram.org/bot<TOKEN>/getWebhookInfo
```

Должно показать:
```json
{
  "ok": true,
  "result": {
    "url": "https://your-app.koyeb.app/telegram",
    "pending_update_count": 0
  }
}
```

---

## 💻 Локальная разработка

### С polling (рекомендуется для локалки):

Создайте `.env` файл:
```bash
TELEGRAM_BOT_TOKEN=токен
GOOGLE_SHEET_ID=id
GOOGLE_CREDENTIALS={"type":"service_account",...}
BOT_USERS={"id":"owner"}
USE_WEBHOOK=false
```

Запустите:
```bash
pip install -r requirements.txt
python bot.py
```

### С webhook (для тестирования):

Используйте ngrok для туннеля:
```bash
ngrok http 8080
```

В .env:
```bash
WEBHOOK_URL=https://your-ngrok-url.ngrok.io
PORT=8080
```

Запустите:
```bash
python main.py
```

---

## 🐛 Если что-то не работает

### Бот не отвечает:
1. Проверьте логи в Koyeb Dashboard
2. Откройте `https://your-app.koyeb.app/` - должно быть `{"status":"ok"}`
3. Проверьте getWebhookInfo (ссылка выше)
4. Убедитесь что WEBHOOK_URL указан БЕЗ слеша в конце

### Ошибка подключения к Google Sheets:
- Проверьте что GOOGLE_CREDENTIALS это валидный JSON (вся строка)
- Service account должен иметь доступ к таблице
- Проверьте GOOGLE_SHEET_ID

### Webhook не устанавливается:
Вручную установите через curl:
```bash
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://your-app.koyeb.app/telegram"
```

### Сбросить webhook:
```bash
curl -X POST "https://api.telegram.org/bot<TOKEN>/deleteWebhook"
```

---

## 🔄 Обновление бота

Просто сделайте git push - Koyeb автоматически обновит:
```bash
git add .
git commit -m "Update bot"
git push
```

Koyeb автоматически:
1. Соберет новый Docker образ
2. Задеплоит его
3. Переустановит webhook

---

## 📊 Структура файлов

```
your-project/
├── bot.py              # Основная логика бота
├── main.py             # FastAPI сервер для webhook
├── requirements.txt    # Зависимости Python
├── Dockerfile          # Для контейнеризации
├── .dockerignore       # Исключения для Docker
├── .gitignore          # Исключения для Git
└── .env.example        # Пример переменных окружения
```

---

## 🎯 Полная инструкция

Смотрите `DEPLOY_GUIDE.md` для подробностей.

---

## 🌐 Endpoints

- `GET /` - Health check (status page)
- `GET /health` - Health check для Koyeb
- `POST /telegram` - Webhook endpoint для Telegram

