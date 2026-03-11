FROM python:3.11-slim

# Установка рабочей директории
WORKDIR /app

# Копирование файлов requirements
COPY requirements.txt .

# Установка зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода бота
COPY bot.py .

# Запуск бота
CMD ["python", "bot.py"]