# База с уже предустановленными библиотеками и браузерами Playwright  
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

# Быстрые и предсказуемые сборки
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Рабочая папка
WORKDIR /app

# Сначала зависимости (кэш слоёв эффективнее)
COPY app/requirements.txt /app/app/requirements.txt

# Устанавливаем зависимости без прокси
RUN HTTP_PROXY= HTTPS_PROXY= http_proxy= https_proxy= PIP_DISABLE_PIP_VERSION_CHECK=1 \
    pip install --no-cache-dir -r /app/app/requirements.txt

# Копируем код проекта
COPY . /app

# Устанавливаем браузеры Playwright без прокси
RUN HTTP_PROXY= HTTPS_PROXY= http_proxy= https_proxy= \
    playwright install --with-deps chromium

# Точка входа
CMD ["python", "-m", "app.main"]
