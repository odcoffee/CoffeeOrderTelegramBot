# 🚀 Полная инструкция по деплою бота на Koyeb

## 📋 Почему FastAPI + Webhook?

### Преимущества архитектуры

- ✅ **Стабильность**: FastAPI - production-ready веб-фреймворк
- ✅ **Health checks**: Koyeb может проверять статус приложения
- ✅ **Логирование**: Удобный мониторинг через Koyeb Dashboard
- ✅ **Нет автосна**: Бот работает 24/7 без ограничений
- ✅ **Быстрая обработка**: Telegram сам отправляет обновления
- ✅ **Масштабируемость**: Готово к росту нагрузки

### Сравнение с polling

| Параметр | Polling | Webhook + FastAPI |
|----------|---------|-------------------|
| Работа на Koyeb | ❌ Усыпает | ✅ 24/7 |
| Скорость отклика | 🐌 1-2 сек | ⚡ <100ms |
| Мониторинг | ⚠️ Сложно | ✅ Health checks |
| Ресурсы | 📈 Высокие | 📉 Минимальные |
| Логи | ⚠️ Только бот | ✅ HTTP + бот |

---

## 🔧 Архитектура проекта

```
CoffeeOrderTelegramBot/
├── bot.py              # Логика бота (обработчики, Google Sheets)
├── main.py             # FastAPI сервер (webhook endpoints)
├── requirements.txt    # Python зависимости
├── Dockerfile          # Контейнеризация
├── .env.example        # Шаблон переменных окружения
├── .gitignore          # Исключения для Git
└── .dockerignore       # Исключения для Docker
```

### Как это работает

1. **Telegram** отправляет обновление → `https://your-app.koyeb.app/telegram`
2. **FastAPI** (main.py) получает POST запрос
3. **Application** (bot.py) обрабатывает обновление
4. **Обработчики** выполняют логику
5. **Google Sheets** сохраняет данные

---

## 📦 Подготовка

### 1. Telegram Bot Token

1. Найдите [@BotFather](https://t.me/BotFather) в Telegram
2. Отправьте `/newbot` или используйте существующего
3. Скопируйте токен: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`

### 2. Google Sheets API

#### Шаг 1: Создание проекта
1. Откройте [Google Cloud Console](https://console.cloud.google.com/)
2. Создайте новый проект или выберите существующий
3. В меню перейдите: APIs & Services → Library

#### Шаг 2: Включение API
1. Найдите и включите **Google Sheets API**
2. Найдите и включите **Google Drive API**

#### Шаг 3: Service Account
1. APIs & Services → Credentials
2. Create Credentials → Service Account
3. Заполните имя, нажмите Create
4. Пропустите Grant Access (optional)
5. Нажмите Done

#### Шаг 4: JSON ключ
1. Нажмите на созданный service account
2. Keys → Add Key → Create new key
3. Выберите JSON
4. Скачайте файл (он нужен для GOOGLE_CREDENTIALS)

#### Шаг 5: Google Таблица
1. Создайте новую [Google Таблицу](https://sheets.google.com)
2. Скопируйте ID из URL: `https://docs.google.com/spreadsheets/d/{ЭТОТ_ID}/edit`
3. Нажмите Share → добавьте email service account (из JSON файла)
4. Дайте права Editor

### 3. Узнайте свой Telegram User ID

1. Найдите [@userinfobot](https://t.me/userinfobot)
2. Отправьте любое сообщение
3. Скопируйте ваш ID (например: `123456789`)

---

## 🌐 Деплой на Koyeb

### Шаг 1: Подготовка GitHub репозитория

```bash
# Клонируйте или создайте репозиторий
git clone https://github.com/yourusername/CoffeeOrderTelegramBot.git
cd CoffeeOrderTelegramBot

# Добавьте все файлы
git add .
git commit -m "Initial commit with FastAPI webhook"
git push
```

### Шаг 2: Создание аккаунта Koyeb

1. Зайдите на [koyeb.com](https://www.koyeb.com/)
2. Sign Up (можно через GitHub)
3. Бесплатный план - достаточно для бота

### Шаг 3: Создание приложения

1. В Dashboard нажмите **"Create App"**
2. Выберите **"GitHub"** как источник
3. **Authorize** Koyeb в GitHub
4. Выберите репозиторий `CoffeeOrderTelegramBot`
5. Выберите ветку (обычно `main` или `master`)

### Шаг 4: Настройка билдера

#### Builder Settings:
- **Builder**: Docker
- **Dockerfile path**: `Dockerfile`
- **Build command**: оставьте пустым
- **Run command**: оставьте пустым (используется CMD из Dockerfile)

#### Instance Settings:
- **Region**: Frankfurt (Europe) - ближе к России/СНГ
- **Instance type**: Nano (бесплатный)

#### Ports:
- **Port**: `8080`
- **Protocol**: HTTP
- **Path**: `/health` (для health checks)

### Шаг 5: Переменные окружения

Нажмите **"Add Environment Variable"** и добавьте:

#### 1. TELEGRAM_BOT_TOKEN
```
Значение: ваш_токен_от_BotFather
```

#### 2. GOOGLE_SHEET_ID
```
Значение: id_вашей_таблицы_из_URL
```

#### 3. GOOGLE_CREDENTIALS
**ВАЖНО**: Это должен быть JSON в ОДНУ строку!

Откройте скачанный JSON файл и скопируйте всё содержимое:
```json
{"type":"service_account","project_id":"...","private_key_id":"...","private_key":"-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n","client_email":"...@...iam.gserviceaccount.com","client_id":"...","auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token","auth_provider_x509_cert_url":"...","client_x509_cert_url":"..."}
```

#### 4. BOT_USERS
```json
{"123456789":"owner","987654321":"manager"}
```
Замените `123456789` на ваш Telegram ID

#### 5. WEBHOOK_URL
**ВАЖНО**: URL вашего приложения на Koyeb

После создания приложения, Koyeb даст вам URL типа:
```
https://your-app-name-yourorganization.koyeb.app
```

Скопируйте его и добавьте переменную:
```
WEBHOOK_URL=https://your-app-name-yourorganization.koyeb.app
```

⚠️ **БЕЗ слеша в конце!**
⚠️ **БЕЗ `/telegram` на конце!**

#### 6. PORT (опционально)
```
PORT=8080
```
(можно не указывать, по умолчанию 8080)

### Шаг 6: Деплой

1. Проверьте все настройки
2. Нажмите **"Deploy"**
3. Дождитесь завершения (2-5 минут)

### Шаг 7: Проверка работы

#### 1. Проверьте статус в логах
В Koyeb Dashboard → Logs должно быть:
```
✅ Webhook установлен: https://your-app.koyeb.app/telegram
✅ Бот запущен и готов к работе
✅ CoffeeBot инициализирован
```

#### 2. Проверьте health check
Откройте в браузере:
```
https://your-app-name.koyeb.app/
```

Должно показать:
```json
{
  "status": "ok",
  "bot": "Coffee Order Bot",
  "version": "2.0"
}
```

#### 3. Проверьте webhook в Telegram
Откройте:
```
https://api.telegram.org/bot<ВАШ_ТОКЕН>/getWebhookInfo
```

Должно показать:
```json
{
  "ok": true,
  "result": {
    "url": "https://your-app.koyeb.app/telegram",
    "has_custom_certificate": false,
    "pending_update_count": 0,
    "max_connections": 40
  }
}
```

#### 4. Тестирование бота
1. Найдите вашего бота в Telegram
2. Отправьте `/start`
3. Бот должен ответить с меню

🎉 **Если всё работает - поздравляю!**

---

## 💻 Локальная разработка

### С polling (рекомендуется)

1. Создайте `.env`:
```bash
TELEGRAM_BOT_TOKEN=ваш_токен
GOOGLE_SHEET_ID=id_таблицы
GOOGLE_CREDENTIALS={"type":"service_account",...}
BOT_USERS={"ваш_id":"owner"}
USE_WEBHOOK=false
```

2. Установите зависимости:
```bash
pip install -r requirements.txt
```

3. Запустите:
```bash
python bot.py
```

### С webhook (для тестирования webhook локально)

1. Установите [ngrok](https://ngrok.com/):
```bash
# macOS
brew install ngrok

# Windows
# Скачайте с ngrok.com
```

2. Запустите ngrok:
```bash
ngrok http 8080
```

3. В `.env` укажите URL от ngrok:
```bash
WEBHOOK_URL=https://abc123.ngrok.io
PORT=8080
```

4. Запустите бота:
```bash
python main.py
```

---

## 🐛 Решение проблем

### Бот не отвечает

**Симптом**: Бот не реагирует на сообщения

**Решение**:
1. Проверьте логи в Koyeb Dashboard
2. Убедитесь что WEBHOOK_URL правильный
3. Проверьте getWebhookInfo
4. Убедитесь что все переменные окружения добавлены

### Ошибка "TELEGRAM_BOT_TOKEN не установлен"

**Симптом**: В логах ошибка про токен

**Решение**:
1. Проверьте переменную TELEGRAM_BOT_TOKEN в Koyeb
2. Убедитесь что нет пробелов в начале/конце
3. Пересоздайте токен у @BotFather если нужно

### Ошибка Google Sheets

**Симптом**: "Ошибка инициализации Google Sheets"

**Решение**:
1. Проверьте формат GOOGLE_CREDENTIALS (должен быть валидный JSON)
2. Убедитесь что service account email добавлен в Google таблицу
3. Проверьте что включены Google Sheets API и Drive API
4. Проверьте GOOGLE_SHEET_ID

### Webhook не устанавливается

**Симптом**: В getWebhookInfo пустой url

**Решение**:
1. Проверьте что WEBHOOK_URL добавлен в переменные
2. Убедитесь что URL без слеша в конце
3. Проверьте логи - должно быть "Webhook установлен"
4. Вручную установите:
```bash
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://your-app.koyeb.app/telegram"
```

### Health check падает

**Симптом**: Koyeb показывает "Unhealthy"

**Решение**:
1. Убедитесь что Port в настройках = 8080
2. Проверьте что Health check path = `/health`
3. Откройте `https://your-app.koyeb.app/health` в браузере
4. Проверьте логи

### "Update object has no attribute..."

**Симптом**: Ошибки про отсутствующие атрибуты

**Решение**:
1. Обновите python-telegram-bot: `pip install -U python-telegram-bot`
2. Проверьте версию в requirements.txt
3. Пересоберите Docker образ

---

## 🔄 Обновление бота

### Через Git Push

Самый простой способ:
```bash
# Внесите изменения в код
git add .
git commit -m "Update: описание изменений"
git push
```

Koyeb автоматически:
1. Обнаружит изменения
2. Соберет новый Docker образ
3. Задеплоит обновленную версию
4. Переустановит webhook

### Ручное обновление

В Koyeb Dashboard:
1. Перейдите в ваше приложение
2. Settings → Deployments
3. Нажмите "Redeploy"

---

## 📊 Мониторинг

### Логи

В реальном времени в Koyeb Dashboard → Logs

Полезные логи:
```
✅ Webhook установлен: ...
✅ Бот запущен и готов к работе
INFO - Обработка заказа от пользователя ...
ERROR - Ошибка: ...
```

### Метрики

Koyeb Dashboard → Metrics:
- CPU использование
- Memory использование
- Network трафик
- HTTP запросы

### Endpoints для мониторинга

- `GET /` - Основной health check
- `GET /health` - Health check для Koyeb
- Оба должны возвращать status: ok

---

## 💰 Стоимость

### Koyeb Free Tier

- ✅ **1 приложение бесплатно** навсегда
- ✅ **2GB RAM**
- ✅ **0.1 CPU**
- ✅ **Unlimited bandwidth** (в разумных пределах)
- ✅ **Custom domains** доступны

### Альтернативы

Если нужно больше приложений:

1. **Railway.app**
   - 500 часов/месяц бесплатно
   - $5 за месяц после

2. **Render.com**
   - 750 часов/месяц бесплатно
   - Засыпает при неактивности

3. **Fly.io**
   - Ограниченный бесплатный план
   - Сложнее в настройке

---

## 🔐 Безопасность

### Best Practices

1. **Никогда не коммитьте секреты**
   ```bash
   # Проверьте .gitignore
   echo ".env" >> .gitignore
   ```

2. **Используйте переменные окружения**
   - Все секреты только через Koyeb Environment Variables
   - Не храните в коде

3. **Ограничьте доступ**
   - Используйте BOT_USERS для контроля доступа
   - Регулярно проверяйте список пользователей

4. **Обновляйте зависимости**
   ```bash
   pip list --outdated
   pip install -U package_name
   ```

5. **Логирование**
   - Не логируйте токены и пароли
   - Проверяйте логи на чувствительную информацию

### Ротация токенов

Если токен скомпрометирован:
1. Создайте новый токен у @BotFather: `/token`
2. Обновите TELEGRAM_BOT_TOKEN в Koyeb
3. Приложение автоматически перезапустится

---

## 📚 Дополнительные ресурсы

- [Telegram Bot API](https://core.telegram.org/bots/api)
- [python-telegram-bot Docs](https://docs.python-telegram-bot.org/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Koyeb Docs](https://www.koyeb.com/docs)
- [Google Sheets API](https://developers.google.com/sheets/api)

---

## ❓ FAQ

**Q: Можно ли использовать бесплатно навсегда?**
A: Да! Koyeb Free Tier бесплатен для 1 приложения без ограничений по времени.

**Q: Бот засыпает на Koyeb?**
A: Нет! При использовании webhook бот активен 24/7.

**Q: Сколько запросов в секунду выдержит?**
A: Free tier Koyeb легко обработает сотни запросов в секунду. Для обычного бота это более чем достаточно.

**Q: Можно ли использовать свой домен?**
A: Да, Koyeb поддерживает custom domains.

**Q: Как посмотреть реальное использование ресурсов?**
A: Koyeb Dashboard → Metrics покажет CPU, RAM, трафик.

**Q: Что если превышу лимиты Free Tier?**
A: Вас предупредят и предложат перейти на платный план (~$5/месяц).

---

## 🎯 Итоговый чеклист

Перед деплоем убедитесь:

- ✅ Bot token получен от @BotFather
- ✅ Google Sheets API включен
- ✅ Service Account создан и JSON скачан
- ✅ Google таблица создана и доступ дан service account
- ✅ Telegram User ID узнан
- ✅ Код загружен на GitHub
- ✅ Koyeb аккаунт создан
- ✅ Все переменные окружения добавлены
- ✅ WEBHOOK_URL правильный (без слеша)
- ✅ Health check настроен на /health
- ✅ Port = 8080

После деплоя:
- ✅ Логи показывают успешный запуск
- ✅ Health check возвращает {"status":"ok"}
- ✅ getWebhookInfo показывает правильный URL
- ✅ Бот отвечает на /start

---

**Готово! Ваш бот работает 24/7 на production! 🎉**

Если возникли вопросы - проверьте раздел "Решение проблем" или создайте Issue на GitHub.
