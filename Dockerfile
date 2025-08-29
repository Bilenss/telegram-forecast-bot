# База с уже предустановленными библиотеками и браузерами Playwright
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

# Быстрые и предсказуемые сборки
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Рабочая папка
WORKDIR /app

# Сначала зависимости (кэш слоёв эффективнее)
COPY app/requirements.txt /app/app/requirements.txt
RUN pip install --no-cache-dir -r /app/app/requirements.txt

# Код проекта
COPY . /app

# На этой базе браузеры уже есть; команда ниже безвредна, но подстрахует в будущем
RUN playwright install --with-deps chromium

# Точка входа
CMD ["python", "-m", "app.main"]
