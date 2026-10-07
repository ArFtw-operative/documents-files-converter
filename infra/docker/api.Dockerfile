# Verso Folio API / CPU worker image.
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/apps/api:/app/services
RUN apt-get update \
 && apt-get install -y --no-install-recommends qpdf fontconfig libmagic1 \
      fonts-noto-core fonts-liberation2 fonts-dejavu-core fonts-urw-base35 \
 && rm -rf /var/lib/apt/lists/* \
 && fc-cache -f \
 && useradd --uid 10001 --create-home --shell /usr/sbin/nologin folio
WORKDIR /app
COPY apps/api/requirements.txt apps/api/requirements.txt
RUN pip install -r apps/api/requirements.txt
COPY apps/api apps/api
COPY services services
USER folio
EXPOSE 8000
CMD ["uvicorn", "folio.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]

FROM runtime AS dev
USER root
COPY apps/api/requirements-dev.txt apps/api/requirements-dev.txt
RUN pip install -r apps/api/requirements-dev.txt
USER folio
