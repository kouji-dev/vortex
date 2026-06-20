FROM python:3.12-slim

WORKDIR /app

# System deps for psycopg binary
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src/ ./src/

RUN pip install --no-cache-dir -e .

COPY alembic.ini .
COPY alembic/ ./alembic/

# Render sets $PORT; default to 8000 for local
ENV PORT=8000
ENV PYTHONUNBUFFERED=1

CMD ["sh", "-c", "python -m alembic upgrade head && uvicorn ai_portal.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips='*'"]
