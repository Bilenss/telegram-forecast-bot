# Образ с уже установленными браузерами и зависимостями
FROM mcr.microsoft.com/playwright/python:v1.46.0-jammy

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ARG DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Если графики не нужны, лучше убрать их из requirements.txt,
# чтобы не тянуть libfreetype/libpng и т.п.
COPY app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Код как пакет "app"
COPY app /app/app

ENV TZ=Etc/UTC
ENV PORT=8080

CMD ["python", "-m", "app.main"]
