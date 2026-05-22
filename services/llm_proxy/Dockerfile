FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir \
    "uvicorn[standard]>=0.29" "fastapi>=0.111" "httpx>=0.27" \
    "pydantic>=2.7" "pydantic-settings>=2.2" "pymongo>=4.8" \
    "opentelemetry-sdk>=1.26.0" "opentelemetry-exporter-otlp-proto-grpc>=1.26.0" \
    "opentelemetry-instrumentation-fastapi>=0.47b0" \
    "opentelemetry-instrumentation-httpx>=0.47b0"
COPY src/llm_proxy /app/llm_proxy
ENV PYTHONPATH=/app
EXPOSE 8082
CMD ["sh", "-c", "uvicorn llm_proxy.main:app --host 0.0.0.0 --port 8082 --log-level ${LOG_LEVEL:-debug} --access-log"]
