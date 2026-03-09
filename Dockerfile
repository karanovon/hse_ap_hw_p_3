FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем минимальные системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Копируем только зависимости сначала (для кэширования)
COPY requirements.txt .

# Устанавливаем зависимости с явным указанием платформы
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --platform manylinux2014_x86_64 -r requirements.txt

# Копируем остальной код
COPY . .

# Создаем папку для данных с правильными правами
RUN mkdir -p /app/data && chmod 777 /app/data

# Проверяем, что все необходимые файлы на месте
RUN ls -la && ls -la /app/data || true

# Указываем порт
EXPOSE 8000

# Запускаем приложение
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]