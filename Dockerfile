# syntax=docker/dockerfile:1
FROM python:3.12-slim AS runtime
WORKDIR /app
COPY requirements.txt requirements.lock .
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then PIP_CERT=/run/secrets/proxy_ca pip install --no-compile --no-cache-dir -r requirements.lock; else pip install --no-compile --no-cache-dir -r requirements.lock; fi
COPY . .
RUN useradd --uid 10001 --create-home appuser && mkdir -p /data && chown appuser /data && chmod -R a+rX /app
USER appuser
ENV PYTHONUNBUFFERED=1
CMD ["python","-m","uvicorn","app.api:app","--host","0.0.0.0","--port","8000"]

FROM python:3.12-slim AS tests
WORKDIR /app
COPY requirements.txt requirements.lock .
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then PIP_CERT=/run/secrets/proxy_ca pip install --no-compile --no-cache-dir -r requirements.lock pytest==9.2.0; else pip install --no-compile --no-cache-dir -r requirements.lock pytest==9.2.0; fi
COPY . .
ENV OTEL_EXPORTER_OTLP_ENDPOINT=""
CMD ["python","-m","pytest","-q"]

FROM runtime AS final
