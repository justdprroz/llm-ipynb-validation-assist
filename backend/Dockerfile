FROM python:3.12-slim

# Static Docker **client** only (``docker.io`` Debian package ships ``dockerd`` without ``docker`` CLI).
ARG DOCKER_CLI_VERSION=26.1.4
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && ARCH=$(dpkg --print-architecture) \
    && case "$ARCH" in amd64) DARCH=x86_64 ;; arm64) DARCH=aarch64 ;; *) echo "unsupported arch: $ARCH"; exit 1 ;; esac \
    && curl -fsSL "https://download.docker.com/linux/static/stable/${DARCH}/docker-${DOCKER_CLI_VERSION}.tgz" \
        | tar xz -C /tmp \
    && install -m0755 /tmp/docker/docker /usr/local/bin/docker \
    && rm -rf /tmp/docker \
    && apt-get purge -y curl \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Build context is repo root (``gradelab/``); shared defaults for run pipeline_config.
COPY packages/gradelab_contracts /packages/gradelab_contracts
RUN uv pip install --system /packages/gradelab_contracts

COPY backend/pyproject.toml .

RUN uv pip install --system \
        "fastapi>=0.111.0" \
        "uvicorn[standard]>=0.29.0" \
        "python-multipart>=0.0.9" \
        "pydantic>=2.7.0" \
        "pydantic-settings>=2.2.0" \
        "redis>=5.0.0" \
        "httpx>=0.27.0" \
        "pymongo>=4.8.0" \
        "motor>=3.5.0" \
        "arq>=0.26.0" \
        "boto3>=1.35.0" \
        "opentelemetry-sdk>=1.26.0" \
        "opentelemetry-exporter-otlp-proto-grpc>=1.26.0" \
        "opentelemetry-instrumentation-fastapi>=0.47b0" \
        "opentelemetry-instrumentation-httpx>=0.47b0"

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN uv pip install --system \
    "anytask-scraper @ git+https://github.com/Coldish-elf/anytask-scraper.git"

COPY backend/ .

RUN chmod +x entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
