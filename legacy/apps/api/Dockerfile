FROM python:3.12.10-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends fontconfig fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
RUN groupadd -r convertvault && useradd -r -g convertvault -d /app convertvault
WORKDIR /app
COPY apps/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY apps/api /app
COPY migrations /app/migrations
COPY alembic.ini /app/alembic.ini
RUN mkdir -p /data/files && chown -R convertvault:convertvault /app /data
USER convertvault
EXPOSE 8000
CMD ["uvicorn", "convertvault.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
