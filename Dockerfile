FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ARG DEBIAN_FRONTEND=noninteractive

# ← СБОРКА БЕЗ ПРОКСИ
ENV http_proxy=""
ENV https_proxy=""
ENV HTTP_PROXY=""
ENV HTTPS_PROXY=""

# apt без прокси
RUN apt-get update -o Acquire::http::Proxy=false -o Acquire::https::Proxy=false \
    && apt-get install -y --no-install-recommends \
       build-essential libfreetype6-dev libpng-dev libjpeg-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Playwright + Chromium (тоже без прокси на build-этапе)
RUN python -m playwright install --with-deps chromium

# Пакет приложения
COPY app /app/app

ENV TZ=Etc/UTC
ENV PORT=8080

CMD ["python", "-m", "app.main"]
