FROM python:3.12.10-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp/convertvault
RUN apt-get update && apt-get install -y --no-install-recommends libreoffice-core libreoffice-writer libreoffice-calc libreoffice-impress pandoc weasyprint tesseract-ocr ocrmypdf qpdf ghostscript libheif1 libmagic1 fonts-dejavu-core && rm -rf /var/lib/apt/lists/* && groupadd -r convertvault && useradd -r -g convertvault -d /tmp/convertvault convertvault
WORKDIR /app
COPY apps/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY apps/api /app
RUN mkdir -p /data/files /tmp/convertvault && chown -R convertvault:convertvault /app /data /tmp/convertvault
USER convertvault
CMD ["celery", "-A", "convertvault.celery_app:celery", "worker", "--loglevel=INFO"]
