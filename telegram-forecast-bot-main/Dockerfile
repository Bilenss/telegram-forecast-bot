# Playwright image includes Chromium/Firefox/WebKit preinstalled, good for headless scraping later 
FROM mcr.microsoft.com/playwright/python:v1.46.0-jammy

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ARG DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# 🟩 Устанавливаем tesseract и необходимые библиотеки
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

COPY app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app

ENV TZ=Etc/UTC
ENV PORT=8080

CMD ["python", "-m", "app.main"]
