FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libfreetype6-dev \
    libpng-dev \
    libjpeg-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Установка Chromium + зависимостей для playwright
RUN python -m playwright install --with-deps chromium

# Кладём пакет 'app' в /app/app
COPY app /app/app

ENV TZ=Etc/UTC
ENV PORT=8080

CMD ["python", "-m", "app.main"]
