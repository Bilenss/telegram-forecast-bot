FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1

WORKDIR /app
COPY app/requirements.txt /app/app/requirements.txt
RUN pip install --no-cache-dir -r app/requirements.txt  && python -m playwright install --with-deps chromium

COPY app /app/app

CMD ["python", "-m", "app.main"]
