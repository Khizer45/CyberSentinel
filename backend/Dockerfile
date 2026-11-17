# CyberSentinel API image (FastAPI + shared ML runtime). Used by docker-compose.yml at the repository root.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# libgomp1: OpenMP runtime required by XGBoost and scikit-learn.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements-ml.txt requirements.txt constraints.txt ./
RUN pip install -r requirements.txt -c constraints.txt

COPY . .
RUN chmod +x docker-entrypoint.sh \
    && useradd --system --uid 10001 --home-dir /app cybersentinel \
    && mkdir -p /data/uploads /models \
    && chown -R cybersentinel /data /models

USER cybersentinel
EXPOSE 8000
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
