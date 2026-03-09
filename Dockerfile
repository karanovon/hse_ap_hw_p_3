FROM python:3.11-slim

WORKDIR /app

# Копируем зависимости
COPY requirements.txt .

# Устанавливаем зависимости (просто и понятно)
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY . .

# Создаем папку для данных с правильными правами
RUN mkdir -p /app/data && chmod 777 /app/data

# Проверяем установку
RUN python -c "import fastapi, sqlalchemy, aiosqlite, pydantic, apscheduler" && echo "Все зависимости установлены"

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]