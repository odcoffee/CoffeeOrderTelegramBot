FROM python:3.11-slim

# Установка рабочей директории
WORKDIR /app

# Копирование файлов requirements
COPY requirements.txt .

# Установка зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода бота
COPY bot.py .
COPY main.py .

# Порт для webhook
EXPOSE 8080

# Запуск через FastAPI с uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]