FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv/app

# Build deps for psycopg/wheels, purged after install.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt \
    && apt-get purge -y build-essential \
    && apt-get autoremove -y

COPY app ./app

# Run as an unprivileged user.
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /srv/app
USER appuser

EXPOSE 8000

# Single replica on purpose: APScheduler runs in-process, so extra
# replicas would double-fire the expiry and auto-checkout jobs.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
