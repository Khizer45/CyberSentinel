# Optional JupyterLab for training (docker compose --profile notebooks up). The repository is mounted at /workspace,
# so data/, reports/ and model_artifacts/ written by the notebooks appear on your computer.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY backend/requirements-ml.txt backend/constraints.txt backend/
COPY notebooks/requirements.txt notebooks/
RUN pip install -r notebooks/requirements.txt -c backend/constraints.txt

WORKDIR /workspace/notebooks
EXPOSE 8888
# Without JUPYTER_TOKEN a random token is generated. The login link is printed in: docker compose logs notebooks
CMD ["sh", "-c", "export JUPYTER_TOKEN=${JUPYTER_TOKEN:-$(python -c 'import secrets; print(secrets.token_urlsafe(24))')}; echo \"JupyterLab: http://localhost:8888/lab?token=$JUPYTER_TOKEN\"; exec jupyter lab --ip=0.0.0.0 --port=8888 --no-browser --allow-root --ServerApp.root_dir=/workspace"]
