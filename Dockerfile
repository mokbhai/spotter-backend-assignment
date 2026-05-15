FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SPOTTER_DEBUG=false \
    SPOTTER_DB_PATH=/app/data/db.sqlite3 \
    SPOTTER_RUN_MIGRATIONS=true \
    SPOTTER_IMPORT_FUEL_PRICES=true \
    SPOTTER_IMPORT_FUEL_PRICES_GEOCODE=false \
    PORT=8000

WORKDIR /app

COPY requirements.txt .

RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY . .

RUN mkdir -p /app/data /app/staticfiles \
    && python manage.py collectstatic --noinput \
    && chmod +x /app/docker-entrypoint.sh \
    && useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["sh", "-c", "gunicorn spotter_backend.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-3} --timeout ${GUNICORN_TIMEOUT:-120}"]
